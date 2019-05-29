import asyncio
import aiohttp
import logging
import multidict
import nanoid
import yaml
import signal
import sys
import os
import platform
from portcullis.context import Context, TcpSentinel, HttpSentinel
from portcullis.logger import Logger
from portcullis.handler import RequestHandler, ChunkRejection, WsConnectionAbort, ProcessingMode, Request, Response
from portcullis.rpc import RpcServer, RpcClient
from portcullis.state import State
from aiohttp import web


try:
    import systemd.journal
    import systemd.daemon
    systemd_enabled = True
except ImportError:
    systemd_enabled = False


class DummyRule(RequestHandler):
    def __init__(self):
        self.mode = ProcessingMode.STREAMING

    def process_request(self, request):
        return request

    def process_request_body_chunk(self, chunk):
        return chunk

    def process_response(self, response):
        return response

    def process_response_body_chunk(self, chunk):
        return chunk

    def process_outcoming_ws(self, msg):
        return msg

    def process_incoming_ws(self, msg):
        return msg

    def make_handler(self, _):
        return DummyRule.INSTANCE

    def __repr__(self):
        return "'<dummy>'"


DummyRule.INSTANCE = DummyRule()


class TooBigBody(Exception):
    pass


class ConnectionContext:
    def __init__(self, logger, state):
        self._marks = {}
        self.state = state
        self.logger = logger

    def add_mark(self, mark):
        self._marks[mark] = self._marks.get(mark, 0) + 1


class PortcullisHttpHandler:
    def __init__(self, context, state, loop, logger, conn_id):
        self._ctx = context
        self._state = state
        self._loop = loop
        self._logger = logger
        self._conn_id = conn_id
        self._conn_ctx = ConnectionContext(logger, state)

    def _pre_process_request(self, request):
        request.headers.pop("content-length", None)
        request.headers.pop("transfer-encoding", None)
        request.headers["accept-encoding"] = "identity"
        request.headers["X-Conn-Id"] = self._conn_id

    def _post_process_response(self, response):
        response.headers["Server"] = "portcullis"
        response.headers["X-Conn-Id"] = self._conn_id
        self._logger.info("response status %d", response.status)
        return response

    def _reject(self, status, text=None):
        return self._post_process_response(web.Response(status=status, text=text))

    def _transform_url(self, url):
        return url.with_scheme("http").with_host(self._ctx.backend_host).with_port(self._ctx.backend_port)

    def _select_rule(self, request):
        for rule in self._ctx.sentinel.rules:
            if rule.matches(request):
                return rule

        return DummyRule.INSTANCE

    async def __call__(self, request):
        self._logger.info(
            "%s - %s - %s %s",
            request.remote,
            request.host,
            request.method,
            request.path_qs,
        )

        try:
            rule = self._select_rule(request)
            handler = rule.make_handler(self._conn_ctx)

            if rule.mode == ProcessingMode.RAW:
                self._logger.debug("raw rule %s selected", rule)
                return await handler.handle(request)
            else:
                self._logger.debug("rule %s selected", rule)
                return await self._handler(request, rule, handler)
        except:
            self._logger.exception("unhandled error occured in handler")
            return self._reject(status=500, text="Internal server error")
        finally:
            self._logger.debug("request finished")

    async def _proxy_ws(self, request, rule, handler):
        url = self._transform_url(request.url)
        async with aiohttp.ClientSession() as sess:
            try:
                from_backend = await sess.ws_connect(url, headers=request.headers)
                from_client = web.WebSocketResponse()
                await from_client.prepare(request)

                async def runner(fut, source, sink, handler, mark):
                    try:
                        async for msg in source:
                            msg = handler(msg.data)
                            if msg is None:
                                continue
                            elif isinstance(msg, str):
                                self._logger.debug("[ws] %s message of size %d", mark, len(msg))
                                await sink.send_str(msg)
                            elif isinstance(msg, bytes):
                                self._logger.debug("[ws] %s message of size %d", mark, len(msg))
                                await sink.send_bytes(msg)
                            else:
                                raise ValueError("invalid return value")
                    except Exception as e:
                        if not fut.done():
                            fut.set_exception(e)

                    if not fut.done():
                        fut.set_result(None)

                fut = asyncio.Future()

                from_backend_task = self._loop.create_task(runner(
                    fut,
                    from_backend,
                    from_client,
                    handler.process_outcoming_ws,
                    "<-"
                ))

                from_client_task = self._loop.create_task(runner(
                    fut,
                    from_client,
                    from_backend,
                    handler.process_incoming_ws,
                    "->"
                ))

                try:
                    await fut
                except asyncio.CancelledError:
                    from_backend_task.cancel()
                    from_client_task.cancel()
                except:
                    self._logger.exception("unhandled exception occured while proxying websockets")
                    from_backend_task.cancel()
                    from_client_task.cancel()

                return from_client
            finally:
                try:
                    await from_backend.close()
                except asyncio.CancelledError:
                    pass

    async def _accumulate_body(self, content, max_body_size):
        data = b""
        while True:
            chunk = await content.read(8192)
            if len(chunk) == 0:
                break
            if len(chunk) + len(data) > max_body_size:
                raise TooBigBody()
            data += chunk

        if len(data) > 0:
            self._logger.debug("read request body of size %d", len(data))

        return data

    async def _stream_response_body(self, content, handler, response):
        while True:
            chunk = await content.read(8192)
            if len(chunk) == 0:
                break

            self._logger.debug("read response body chunk of length %d", len(chunk))

            chunk = handler.process_response_body_chunk(chunk)
            if len(chunk) == 0:
                break

            await response.write(chunk)

    async def _handler(self, request, rule, handler):
        url = self._transform_url(request.url)

        try:
            proxied_request = Request.from_aiohttp(request)
            self._pre_process_request(proxied_request)
            proxied_request = handler.process_request(proxied_request)
            if proxied_request is None:
                self._logger.debug("rule rejected request")
                return self._reject(status=400, text="Bad request")

            if proxied_request.headers.get("connection", "").lower() == "upgrade" \
                    and proxied_request.headers.get("upgrade", "").lower() == "websocket":
                return await self._proxy_ws(request, rule, handler)


            if rule.mode == ProcessingMode.STREAMING:
                async def data_sender():
                    while True:
                        chunk = await request.content.read(8192)

                        if len(chunk) == 0:
                            return

                        self._logger.debug("read request body chunk of length %d", len(chunk))

                        yield handler.process_request_body_chunk(chunk)

                data = data_sender()
            elif rule.mode == ProcessingMode.ACCUMULATING:
                try:
                    data = await self._accumulate_body(request.content, rule.max_body_size)
                except TooBigBody:
                    self._logger.debug("rejecting request due to exceeding max body size")
                    return self._reject(status=413)

            proxied_request = proxied_request.build()
            proxied_request["allow_redirects"] = False
            proxied_request["url"] = self._transform_url(proxied_request["url"])
            proxied_request["data"] = data
            proxied_request["chunked"] = 1024

            async with aiohttp.client.request(**proxied_request) as r:
                response = Response.from_aiohttp(r)
                response.headers.pop("content-length", None)
                response.headers.pop("transfer-encoding", None)
                response = handler.process_response(response)

                if response is None:
                    self._logger.debug("rule rejected response")
                    return self._reject(status=502, text="Bad response")

                if rule.mode == ProcessingMode.STREAMING:
                    response = response.build(stream=True)
                    response = self._post_process_response(response)
                    await response.prepare(request)

                    try:
                        await self._stream_response_body(r.content, handler, response)
                    except:
                        self._logger.exception("unhandled exception occurde while streaming response body")

                    await response.write_eof()
                    return response
                else:
                    try:
                        data = await self._accumulate_body(r.content, rule.max_body_size)
                    except TooBigBody:
                        return self._reject(status=502, text="Too big response")

                    print("here")
                    data = handler.process_response_body_chunk(data)
                    response = response.build(stream=False)
                    response.body = data
                    return self._post_process_response(response)
        except aiohttp.client_exceptions.ClientConnectorError as e:
            self._logger.err("cannot connect to backend: %s", e)
            return self._reject(status=503, text="Service is unavailable")
        except ChunkRejection:
            self._logger.debug("rule rejected request chunk")
            return self._reject(text="Bad body", status=400)


async def _error_handler(request):
    response = web.Response(
        status=500,
        text="Internal server error",
        headers={
            "Server": "portcullis",
        })
    return response


class InstanceRpc:
    def __init__(self, server):
        self._logger = logging.getLogger("portcullis.instance_rpc")
        self._server = server

    async def merge_state(self, state):
        self._server._state.merge(state)


class PeerWatcher:
    def __init__(self, server):
        self._server = server
        self._ctx = server._ctx
        self._loop = server._loop
        self._logger = logging.getLogger("portcullis.peer_watcher")
        self._meet_peers()

    async def _do_watch_peer(self, peer_host, peer_port):
        while True:
            try:
                client = await RpcClient.connect(peer_host, peer_port, loop=self._loop)
                break
            except ConnectionRefusedError:
                self._logger.info("connection refused to peer %s:%s", peer_host, peer_port)

            await asyncio.sleep(2)

        while True:
            await client.merge_state(self._server._state.serialize())
            await asyncio.sleep(1)


    async def _peer_watcher(self, peer_host, peer_port):
        while True:
            try:
                await self._do_watch_peer(peer_host, peer_port)
            except:
                self._logger.exception("unhandled exception occured while contacting with peer %s:%s", peer_host, peer_port)

            await asyncio.sleep(1)

    def _meet_peers(self):
        for peer in self._ctx.neighbours:
            peer_host, peer_port = peer.split(":")
            peer_port = int(peer_port)
            self._loop.create_task(self._peer_watcher(peer_host, peer_port))


class PortcullisServer(web.Server):
    # ==== http hack ====
    def get_rh(self):
        conn_id = nanoid.generate()

        try:
            logger = self._logger.child(CONN_ID=conn_id)
            return PortcullisHttpHandler(self._ctx, self._state, self._loop, logger, conn_id)
        except:
            self._logger.exception("unhandled exception occured")
            return _error_handler

    def set_rh(self, _):
        pass

    request_handler = property(fget=get_rh, fset=set_rh)
    # ==== http hack ====

    def __init__(self, config_file, *args, **kwargs):
        super().__init__(self._dummy_handler)
        self._config_file = config_file

        self._logger = logging.getLogger("portcullis")
        self._logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)
        self._logger.addHandler(handler)

        if systemd_enabled:
            systemd_logger = logging.getLogger("systemd.daemon")
            systemd_logger.setLevel(logging.CRITICAL)
            handler = systemd.journal.JournaldLogHandler()
            handler.setLevel(logging.DEBUG)
            self._logger.addHandler(handler)

        self._logger = Logger(self._logger)

        self._ctx = self._load_context()

        node_id = "{}-{}".format(platform.node(), self._ctx.listen_port)
        self._logger.info("running at node '%s'", node_id)
        self._state = State(node_id)

        if self._ctx.rpc_addr:
            rpc_host, rpc_port = self._ctx.rpc_addr.split(":")
            self._rpc_server = RpcServer(InstanceRpc(self), rpc_host, rpc_port)

        self._loop.add_signal_handler(signal.SIGUSR1, self._reload_context)

        if systemd_enabled:
            self._watchdog_responder = self._loop.create_task(self._pinger())
            systemd.daemon.notify(systemd.daemon.Notification.READY)

    async def _pinger(self):
        while True:
            try:
                systemd.daemon.notify(systemd.daemon.Notification.STATUS, "OK")
            except:
                pass
            await asyncio.sleep(1)

    def _reload_context(self):
        self._ctx = self._load_context()

        if self._ctx.logging_level == "INFO":
            self._logger.setLevel(logging.INFO)
        elif self._ctx.logging_level == "WARNING":
            self._logger.setLevel(logging.WARNING)
        elif self._ctx.logging_level == "DEBUG":
            self._logger.setLevel(logging.DEBUG)

    def _load_context(self):
        with open(self._config_file) as f:
            conf = yaml.load(f, Loader=yaml.FullLoader)

        try:
            ctx = Context.from_yaml(conf)
            self._logger.info("loaded context with name '%s'", ctx.name)
            return ctx
        except:
            self._logger.exception("cannot load new context")

    async def prepare_and_start(self):
        if self._ctx.rpc_addr:
            self._logger.info("RPC server is listening at %s", self._ctx.rpc_addr)
            self._peer_watcher = PeerWatcher(self)
            await self._rpc_server.start()

        if isinstance(self._ctx.sentinel, HttpSentinel):
            runner = aiohttp.web.ServerRunner(self)
            await runner.setup()

            site = aiohttp.web.TCPSite(
                runner,
                host=self._ctx.listen_host,
                port=self._ctx.listen_port,
                reuse_address=True,
            )
            await site.start()

            self._logger.info("http sentinel is listening at %s:%d", self._ctx.listen_host, self._ctx.listen_port)

    async def _dummy_handler(self, request):
        raise Exception("should never be called")

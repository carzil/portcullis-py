import logging
import asyncio
import struct
import msgpack
from .utils import msgpack_translate, msgpack_ext_hook


class RpcCallStatus:
    SUCCESS = 0
    EXCEPTION = 1
    NO_SUCH_METHOD = 2

def _packb(*args, **kwargs):
    return msgpack.packb(
        *args,
        default=msgpack_translate,
        use_bin_type=True,
        **kwargs,
    )


class RpcAttrProxy:
    def __init__(self, client, method):
        self._client = client
        self._method = method

    async def __call__(self, *args, **kwargs):
        return await self._client.call(self._method, args, kwargs)


class RpcClient:
    @staticmethod
    async def connect(host, port, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        client = RpcClient(host, port, loop=loop)
        await client.init()
        return client

    def __init__(self, host, port, loop):
        self._host = host
        self._port = port
        self._loop = loop
        self._curr_reqid = 0
        self._requests = {}
        self._unpacker = msgpack.Unpacker(
            raw=False,
            ext_hook=msgpack_ext_hook,
        )

    async def call(self, method, args=[], kwargs={}):
        data = msgpack
        self._writer.write(_packb((method, args, kwargs),))

        while True:
            data = await self._reader.read(8192)
            if len(data) == 0:
                raise ValueError("EOF!")

            self._unpacker.feed(data)

            try:
                typ, data = next(self._unpacker)
            except StopIteration:
                continue

            if typ == RpcCallStatus.NO_SUCH_METHOD:
                raise Exception("no such method")
            elif typ == RpcCallStatus.SUCCESS:
                return data
            elif typ == RpcCallStatus.EXCEPTION:
                raise Exception("exception on server-side: {}".format(data))

    def __getattr__(self, name):
        return RpcAttrProxy(self, name)

    async def init(self):
        self._reader, self._writer = await asyncio.open_connection(host=self._host, port=self._port, loop=self._loop)


class RpcServer:
    def __init__(self, handler, host, port, loop=None):
        self._host = host
        self._port = port
        self._loop = loop or asyncio.get_event_loop()
        self._handler = handler
        self._logger = logging.getLogger("portcullis.rpc_server")

    async def _serve_conn(self, reader, writer, *args, **kwargs):
        unpacker = msgpack.Unpacker(
            ext_hook=msgpack_ext_hook,
            raw=False
        )

        self._logger.info("new connection")
        while True:
            data = await reader.read(8192)
            if len(data) == 0:
                break
            unpacker.feed(data)

            try:
                method, args, kwargs = next(unpacker)
            except StopIteration:
                continue

            handler_method = getattr(self._handler, method, None)

            if handler_method is None:
                writer.write(_packb((RpcCallStatus.NO_SUCH_METHOD, None)))
                continue

            try:
                res = await handler_method(*args, **kwargs)
                writer.write(_packb((RpcCallStatus.SUCCESS, res)))
            except Exception as e:
                writer.write(_packb((RpcCallStatus.EXCEPTION, str(e))))

            await writer.drain()

    async def start(self):
        await asyncio.start_server(self._serve_conn, host=self._host, port=self._port)

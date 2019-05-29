from aiohttp import web
from dataclasses import dataclass
from enum import Enum
from http.cookies import SimpleCookie
from multidict import CIMultiDict
from typing import Any, Union
from yarl import URL


class ProcessingMode(Enum):
    ACCUMULATING = 1
    STREAMING = 2
    RAW = 3


class WsConnectionAbort(Exception):
    pass


class ChunkRejection(Exception):
    pass


@dataclass
class Request:
    method: str
    url: URL
    major_version: int
    minor_version: int
    headers: CIMultiDict
    cookies: SimpleCookie

    @staticmethod
    def from_aiohttp(request):
        cookies = SimpleCookie()
        if "Cookie" in request.headers:
            for value in request.headers.getall("Cookie"):
                cookies.load(value)

        req = Request(
            method=request.method,
            major_version=request.version.major,
            minor_version=request.version.minor,
            url=request.url,
            headers=request.headers.copy(),
            cookies=cookies
        )

        return req

    def build(self):
        for cookie in self.cookies:
            self.headers.add("Cookie", self.cookies[cookie].OutputString())

        return {
            "method": self.method,
            "url": self.url,
            "headers": self.headers,
        }


@dataclass
class Response:
    status: int
    reason: str
    major_version: int
    minor_version: int
    headers: CIMultiDict
    cookies: SimpleCookie

    @staticmethod
    def from_aiohttp(response):
        cookies = SimpleCookie()
        if "Set-Cookie" in response.headers:
            for value in response.headers.getall("Set-Cookie"):
                cookies.load(value)

        resp = Response(
            status=response.status,
            reason=response.reason,
            major_version=response.version.major,
            minor_version=response.version.minor,
            headers=response.headers.copy(),
            cookies=cookies,
        )

        return resp

    def build(self, stream=False):
        for cookie in self.cookies:
            self.headers.add("Set-Cookie", self.cookies[cookie].OutputString())

        if stream:
            return web.StreamResponse(
                status=self.status,
                reason=self.reason,
                headers=self.headers,
            )
        else:
            return web.Response(
                status=self.status,
                reason=self.reason,
                headers=self.headers,
            )


class Handler:
    def __init__(self, ctx):
        self.ctx = ctx
        self.logger = ctx.logger


class RequestHandler(Handler):
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


class RawRequestHandler(Handler):
    async def handle(self, request):
        pass


class TcpHandler:
    pass


class RawTcpHandler:
    async def handle(self, reader, writer):
        pass

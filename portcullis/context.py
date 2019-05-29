from dataclasses import dataclass, field
from typing import List, Any, Union
from enum import Enum
from portcullis.sentinel import *
from portcullis.handler import TcpHandler, RawTcpHandler


class SentinelType(Enum):
    HTTP = 1
    TCP = 2


@dataclass
class HttpSentinel:
    rules: List[Rule]

    @staticmethod
    def from_yaml(conf):
        return HttpSentinel(
            rules=list(map(Rule.from_yaml, conf["rules"]))
        )


@dataclass
class TcpSentinel:
    def __init__(self, handler):
        self._handler = handler

    @staticmethod
    def from_yaml(conf):
        filename = conf.get("handler")
        if filename is not None:
            with open(filename) as f:
                globls = {}
                exec(compile(f.read(), filename, "exec"), globls)
                handler = globls.get("Handler")
                if handler is None:
                    raise ValueError("Handler class must be defined in python rule.")
                # TODO: check base class here
            return TcpSentinel(handler)

        raise ValueError("should specify handler", conf)

    def make_handler(*args, **kwargs):
        return self._handler(*args, **kwargs)



@dataclass
class Context:
    name: str
    listen_host: str
    listen_port: int
    backend_host: str
    backend_port: int
    sentinel: Union[HttpSentinel, TcpSentinel]
    logging_level: str
    rpc_addr: Union[str, None]
    neighbours: Union[List[str], None]

    @staticmethod
    def from_yaml(conf):
        http = conf.get("http")
        tcp = conf.get("tcp")
        if http is not None:
            sentinel = HttpSentinel.from_yaml(http)
        elif tcp is not None:
            sentinel = TcpSentinel.from_yaml(tcp)
        else:
            raise ValueError("no sentinel configured")

        rpc_addr = conf.get("rpc_addr", None)
        neighbours = conf.get("neighbours", None)

        backend_host, backend_port = conf["backend_addr"].split(":")
        listen_host, listen_port = conf["listen_addr"].split(":")

        return Context(
            name=conf["name"],
            listen_host=listen_host,
            listen_port=int(listen_port),
            rpc_addr=conf.get("rpc_addr"),
            backend_host=backend_host,
            backend_port=int(backend_port),
            logging_level=conf.get("logging_level", "WARNING"),
            sentinel=sentinel,
            neighbours=conf.get("neighbours"),
        )

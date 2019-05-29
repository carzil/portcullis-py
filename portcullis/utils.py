import struct
import msgpack


def msgpack_translate(obj):
    if isinstance(obj, PNCounter):
        return msgpack.ExtType(42, obj.to_bytes())
    return obj


def msgpack_ext_hook(code, data):
    if code == 42:
        return PNCounter.from_bytes(data)
    return msgpack.ExtType(code, data)


class PNCounter:
    __slots__ = ("_p", "_n")

    @staticmethod
    def from_value(value):
        if value >= 0:
            return PNCounter(p=value, n=0)
        else:
            return PNCounter(p=0, n=-value)

    @staticmethod
    def from_bytes(data):
        p, n = struct.unpack("<QQ", data)
        return PNCounter(p, n)

    def to_bytes(self):
        return struct.pack("<QQ", self._p, self._n)

    def __init__(self, p, n):
        self._p = p
        self._n = n

    def add(self, diff):
        if not isinstance(diff, int):
            raise ValueError("add with non-integer argument")

        if diff < 0:
            self._n += -diff
        elif diff > 0:
            self._p += diff

    def value(self):
        return self._p - self._n

    def merge(self, pn):
        self._p = max(self._p, pn._p)
        self._n = max(self._n, pn._n)

    def __repr__(self):
        return "PNCounter(p={}, n={})".format(self._p, self._n)

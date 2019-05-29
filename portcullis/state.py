import copy
import struct
import msgpack
from .utils import PNCounter, msgpack_translate, msgpack_ext_hook


class NamespacedState:
    __slots__ = ("_state", "_name")

    def __init__(self, state, name):
        self._state = state
        self._name = name

    def get(self, key):
        return self._state.aggregate_key(self._name, key)

    def add(self, key, diff):
        return self._state.change_key(self._name, key, diff)


def _merge_pns(ours, theirs):
    if ours is None:
        return copy.copy(theirs)

    for replica, pn in theirs.items():
        our = ours.get(replica, None)
        if our is None:
            ours[replica] = pn
        else:
            ours[replica].merge(pn)


class State:
    def __init__(self, our_replica):
        self._namespaces = {}
        self._our_replica = our_replica

    def _merge_ns(self, ns, state):
        our_ns = self._namespaces.get(ns, None)

        if our_ns is None:
            self._namespaces[ns] = state
            return

        for key, theirs in state.items():
            ours = our_ns.get(key)
            if ours is None:
                our_ns[key] = copy.copy(theirs)
            else:
                _merge_pns(ours, theirs)

    def merge(self, other_state):
        for ns, ns_state in other_state.items():
            self._merge_ns(ns, ns_state)

    def serialize(self):
        return self._namespaces

    def __getitem__(self, name):
        return NamespacedState(self, name)

    def aggregate_key(self, ns, key):
        ns = self._namespaces.get(ns)
        if ns is None:
            return 0

        pns = ns.get(key)
        if pns is None:
            return 0

        return sum(map(lambda pn: pn.value(), pns.values()))

    def change_key(self, ns_name, key, diff):
        ns = self._namespaces.get(ns_name)

        if ns is None:
            self._namespaces[ns_name] = {
                key: {
                    self._our_replica: PNCounter.from_value(diff)
                }
            }
            return

        key = ns.get(key)
        if key is None:
            ns[key] = PNCounter.from_value(diff)
        else:
            our = key.get(self._our_replica)
            if our is None:
                key[self._our_replica] = PNCounter.from_value(diff)
            else:
                our.add(diff)

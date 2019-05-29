import re
from base64 import b64decode, b64encode


class CompositeMatcher:
    def __init__(self, then):
        assert then is not None
        self._then = then

    def is_match(self, s):
        return self._then.is_match(self._transform(s))


class MatchRegex:
    def __init__(self, regex):
        self._re = re.compile(regex)

    @staticmethod
    def from_yaml(conf):
        return MatchRegex(conf["regex"])

    def is_match(self, s):
        return self._re.match(s) is not None


class Lowercase(CompositeMatcher):
    @staticmethod
    def from_yaml(conf):
        return Lowercase(Matcher.from_yaml(conf))

    def _transform(self, s):
        return s.lower()


class Uppercase(CompositeMatcher):
    @staticmethod
    def from_yaml(conf):
        return Uppercase(Matcher.from_yaml(conf))

    def _transform(self, s):
        return s.upper()


_MATCHER_DEFS = {
    "upper": Uppercase,
    "lower": Lowercase,
    "match_regex": MatchRegex,
}


class Matcher:
    @staticmethod
    def from_yaml(conf):
        matcher = None
        for k, v in _MATCHER_DEFS.items():
            matcher_def = conf.get(k)
            if matcher_def is not None:
                if matcher is not None:
                    raise ValueError("only one matcher allowed, did you forget indentation?")
                matcher = v.from_yaml(matcher_def)

        if matcher is None:
            raise ValueError("no matchers are configured")

        return matcher

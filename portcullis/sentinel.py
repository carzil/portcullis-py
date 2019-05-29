import re
from portcullis.predef.cookie_obfuscator import CookieObfuscatorAction
from portcullis.predef.libinjection_checker import LibInjectionCheckerAction
from portcullis.handler import ProcessingMode, RawRequestHandler


class Action:
    def __init__(self, handler):
        self.handler = handler

    def make_handler(self, ctx):
        return self.handler(ctx)

    def is_raw(self):
        return issubclass(self.handler, RawRequestHandler)

    @staticmethod
    def from_yaml(conf):
        if len(conf.items()) != 1:
            raise ValueError("multiple actions in rule, don't know to do")

        filename = conf.get("python")
        if filename is not None:
            with open(filename) as f:
                globls = {}
                exec(compile(f.read(), filename, "exec"), globls)
                handler = globls.get("Handler")
                if handler is None:
                    raise ValueError("Handler class must be defined in python rule.")
            return Action(handler)

        cookie_obfuscator = conf.get("cookie_obfuscator")
        if cookie_obfuscator is not None:
            return CookieObfuscatorAction(**cookie_obfuscator)

        libinjection_checker = conf.get("libinjection")
        if libinjection_checker is not None:
            return LibInjectionCheckerAction(**libinjection_checker)

        raise ValueError("unknown action def: %s", conf)


class RuleInstance:
    def __init__(self, parent, ctx):
        self._actions = []
        for action in parent._actions:
            self._actions.append(action.make_handler(ctx))

    def process_outcoming_ws(self, msg):
        for action in self._actions:
            msg = action.process_outcoming_ws(msg)
            if msg is None:
                return None
        return msg

    def process_incoming_ws(self, msg):
        for action in self._actions:
            msg = action.process_incoming_ws(msg)
            if msg is None:
                return None
        return msg

    def process_request(self, request):
        for action in self._actions:
            request = action.process_request(request)
            if request is None:
                return None
        return request

    def process_response(self, response):
        for action in self._actions:
            response = action.process_response(response)
            if response is None:
                return None
        return response

    def process_request_body_chunk(self, chunk):
        for action in self._actions:
            chunk = action.process_request_body_chunk(chunk)
        return chunk

    def process_response_body_chunk(self, chunk):
        for action in self._actions:
            chunk = action.process_response_body_chunk(chunk)
        return chunk

    async def handle(self, request):
        return await self._actions[0].handle()


class Rule:
    @staticmethod
    def _check_raw_mode(actions):
        has_raw = False
        for action in actions:
            if action.is_raw():
                has_raw = True
                break

        if has_raw and len(actions) > 0:
            raise ValueError("raw handler should be the only one in rule")

        return has_raw

    def __repr__(self):
        return repr(self.regexp.pattern)

    @staticmethod
    def from_yaml(conf):
        actions = []
        for action_conf in conf["actions"]:
            actions.append(Action.from_yaml(action_conf))

        if len(actions) == 0:
            raise ValueError("no actions configured for rule")

        if Rule._check_raw_mode(actions):
            mode = ProcessingMode.RAW
        else:
            mode = ProcessingMode[conf["mode"].upper()]

        return Rule(
            regexp=conf["regexp"],
            actions=actions,
            mode=mode,
            max_body_size=conf.get("max_body_size", 1024 * 1024)
        )

    def __init__(self, regexp, actions, mode, max_body_size):
        self.regexp = re.compile(regexp)
        self._actions = actions
        self.mode = mode
        self.max_body_size = max_body_size

    def matches(self, request):
        return self.regexp.match(request.path_qs) is not None

    def make_handler(self, ctx):
        return RuleInstance(self, ctx)

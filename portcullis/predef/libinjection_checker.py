import libinjection
from portcullis.handler import RequestHandler


class LibInjectionChecker(RequestHandler):
    def __init__(self, xss, sqli):
        self._xss = xss
        self._sqli = sqli

    def process_request(self, request):
        if self._xss and libinjection.is_xss(request.url.path_qs).get("is_xss", False):
            return

        if self._sqli and libinjection.is_sql_injection(request.url.path_qs).get("is_sqli", False):
            return

        return request


class LibInjectionCheckerAction:
    def __init__(self, xss=False, sqli=False):
        self._xss = xss
        self._sqli = sqli

    def make_handler(self, ctx):
        return LibInjectionChecker(self._xss, self._sqli)

    def is_raw(self):
        return False

from portcullis.handler import RequestHandler


class Handler(RequestHandler):
    def process_response(self, response):
        response.headers["X-Test"] = "net"
        return

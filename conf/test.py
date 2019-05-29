from portcullis.handler import RequestHandler


class Handler(RequestHandler):
    def process_request(self, request):
        print(self.ctx.state["users"].get("carzil"))
        self.ctx.state["users"].add("carzil", -1)
        return request

    def process_response_body_chunk(self, chunk):
        return chunk

    def process_response(self, response):
        return response

    def process_incoming_ws(self, msg):
        if int(msg) % 2 != 0:
            msg = str(int(msg) + 1)
        return msg


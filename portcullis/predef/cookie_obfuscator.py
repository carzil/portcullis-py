import hashlib
import base64
from http.cookies import SimpleCookie
from Crypto import Random
from Crypto.Cipher import AES
from portcullis.handler import RequestHandler


def _pad16(s):
    return s.encode() + b"\x00" * (16 - len(s) % 16)


def aes_decrypt(key, iv, s):
    aes = AES.new(key, AES.MODE_CBC, iv)
    try:
        return aes.decrypt(base64.b64decode(s)).rstrip(b"\x00").decode("ascii")
    except:
        return s


def aes_encrypt(key, iv, s):
    aes = AES.new(key, AES.MODE_CBC, iv)
    return base64.b64encode(aes.encrypt(_pad16(s))).decode("ascii")


class CookieObfuscator(RequestHandler):
    def __init__(self, key, iv, obfuscate_name):
        self._key = key
        self._iv = iv

    def process_request(self, request):
        new_cookies = SimpleCookie()
        for name in request.cookies:
            try:
                new_cookies[name] = aes_decrypt(self._key, self._iv, request.cookies[name].value)
            except:
                new_cookies[name] = request.cookies[name]
        request.cookies = new_cookies
        return request

    def process_response(self, response):
        new_cookies = SimpleCookie()
        for name in response.cookies:
            try:
                new_cookies[name] = aes_encrypt(self._key, self._iv, response.cookies[name].value)
            except:
                new_cookies[name] = response.cookies[name]
        response.cookies = new_cookies
        return response


def _sha256(s):
    return hashlib.sha256(s.encode()).digest()


def _md5(s):
    return hashlib.md5(s.encode()).digest()


class CookieObfuscatorAction:
    def __init__(self, secret, obfuscate_name=False):
        self._key = _sha256(secret[len(secret) // 2:])
        self._iv = _md5(secret[:len(secret) // 2])
        self._obfuscate_name = obfuscate_name

    def make_handler(self, ctx):
        return CookieObfuscator(self._key, self._iv, self._obfuscate_name)

    def is_raw(self):
        return False

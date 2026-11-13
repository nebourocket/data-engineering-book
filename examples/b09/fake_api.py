"""テスト用の偽 REST API。ページング・認証・レート制限 (429 と Retry-After) を再現します。

本物の API を叩く代わりに、標準ライブラリの http.server を別スレッドで動かします。
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN = "secret-token"


class FakeApi:
    """items を order_id 順に返す API。with 文で使うと、終わりにサーバーが止まります。"""

    def __init__(self, items, reject_first=2):
        self.items = sorted(items, key=lambda r: r["order_id"])
        self.reject_first = reject_first  # 最初の何回かを 429 で断る
        self.requests = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def _handler(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                api.requests += 1
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._send(401, {"error": "unauthorized"})
                if api.requests <= api.reject_first:
                    return self._send(429, {"error": "too many requests"}, {"Retry-After": "1"})
                query = parse_qs(urlparse(self.path).query)
                limit = int(query.get("limit", ["100"])[0])
                after = int(query.get("after_id", ["0"])[0])
                rest = [r for r in api.items if r["order_id"] > after]
                page = rest[:limit]
                has_next = len(rest) > limit
                self._send(200, {"items": page, "next_after_id": page[-1]["order_id"] if has_next else None})

            def _send(self, status, body, headers=None):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):  # 標準のアクセスログを出さない
                pass

        return Handler

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

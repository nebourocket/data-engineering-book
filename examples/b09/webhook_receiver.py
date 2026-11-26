"""Webhook を受け取る小さな HTTP 受け口です。署名を確かめ、届いたままの本文を残し、再送を取り除きます。

 - 署名: 本文と共有の秘密から HMAC-SHA256 を計算し、ヘッダー X-Signature と比べる。
 - 保存: 本文は加工せず、届いたバイト列のまま raw_events に入れる。
 - 重複: event_id を主キーにし、再送は INSERT OR IGNORE で無視する (冪等)。
"""
import hashlib
import hmac
import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = b"neboske-webhook-secret"


def sign(body, secret=SECRET):
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


class Receiver:
    def __init__(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.execute("CREATE TABLE raw_events (event_id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                # compare_digest は文字列だと ASCII 以外で例外になるので、バイト列にして比べる
                if not hmac.compare_digest(self.headers.get("X-Signature", "").encode(), sign(body).encode()):
                    return self._reply(401)
                event_id = json.loads(body)["event_id"]
                receiver.db.execute("INSERT OR IGNORE INTO raw_events VALUES (?, ?)", (event_id, body.decode()))
                receiver.db.commit()
                self._reply(200)  # 再送でも 200 を返す。エラーを返すと、送り手がさらに再送する

            def _reply(self, status):
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):  # 標準のアクセスログを出さない
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def count(self):
        return self.db.execute("SELECT count(*) FROM raw_events").fetchone()[0]

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

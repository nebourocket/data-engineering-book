"""HTTP の API から JSON を取ります。一時的な失敗だけを再試行します。"""
import json
import urllib.error
import urllib.request
from typing import Any

from .retry import call_with_retry


class TransientError(Exception):
    """時間を置けば直るかもしれない失敗（混んでいる、つながらない）。"""


def fetch_json(url: str, timeout: float = 10.0, **retry_options: Any) -> Any:
    def once() -> Any:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:  # 混んでいる・サーバ側の失敗
                raise TransientError(f"HTTP {exc.code}") from exc
            raise  # 404 や 403 は待っても直らない
        except urllib.error.URLError as exc:  # つながらない（HTTPError はここに来ない）
            raise TransientError(str(exc.reason)) from exc

    return call_with_retry(once, on=(TransientError, TimeoutError), **retry_options)

"""HTTP の API から JSON を取ります。一時的な失敗だけを再試行します。"""
import http.client
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .retry import call_with_retry


class TransientError(Exception):
    """時間を置けば直るかもしれない失敗（混んでいる、つながらない）。"""


def fetch_json(url: str, timeout: float = 10.0, *, attempts: int = 3, wait: float = 1.0,
               sleep: Callable[[float], None] = time.sleep) -> Any:
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
        except (http.client.IncompleteRead, json.JSONDecodeError) as exc:  # 本文が途中で切れた
            raise TransientError(f"応答が不完全です: {type(exc).__name__}") from exc

    return call_with_retry(once, attempts=attempts, wait=wait, on=(TransientError, TimeoutError), sleep=sleep)

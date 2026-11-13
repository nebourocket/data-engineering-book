"""一時的な失敗を再試行するデコレータ。"""
import functools
import logging
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")
logger = logging.getLogger(__name__)


def retry(attempts: int = 3, wait: float = 1.0, on: tuple[type[Exception], ...] = (OSError,)):
    """on に挙げた例外のときだけ、待ち時間を倍にしながら attempts 回まで試します。"""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            delay = wait
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except on as exc:
                    if attempt == attempts:
                        raise
                    logger.warning("%s が失敗しました (%d/%d 回目): %s。%.1f 秒後に再試行します",
                                   func.__name__, attempt, attempts, exc, delay)
                    time.sleep(delay)
                    delay *= 2
            raise AssertionError("到達しません")

        return wrapper

    return decorator

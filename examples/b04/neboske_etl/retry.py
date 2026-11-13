"""一時的な失敗を再試行する関数。"""
import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


def call_with_retry(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    wait: float = 1.0,
    on: tuple[type[Exception], ...] = (ConnectionError, TimeoutError),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """func() を呼び、on に挙げた例外のときだけ、最大 attempts 回まで試します。

    待ち時間の上限は 1 回ごとに倍になり（wait, 2*wait, ...）、実際の待ちは 0 から上限までの乱数です。
    sleep を引数にしてあるのは、テストで本当に待たずに済ませるためです。
    """
    ceiling = wait
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except on as exc:
            if attempt == attempts:
                raise
            pause = random.uniform(0, ceiling)
            logger.warning("失敗しました (%d/%d 回目): %s。%.1f 秒後に再試行します", attempt, attempts, exc, pause)
            sleep(pause)
            ceiling *= 2
    raise ValueError("attempts は 1 以上にしてください")

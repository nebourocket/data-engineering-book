"""python -m neboske_etl で動かす入口。ログの設定はここだけで行います。"""
import logging
import sys

from .config import Settings
from .pipeline import TooManyRejects, run, upload

logger = logging.getLogger("neboske_etl")


def main() -> int:
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        result = run(settings)
    except TooManyRejects as exc:
        logger.error("%s", exc)
        return 1
    if settings.s3_bucket:
        upload(settings, result.parquet_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

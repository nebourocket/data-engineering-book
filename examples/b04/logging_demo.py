import logging

logger = logging.getLogger("neboske_etl.demo")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logger.debug("INFO より下のレベルなので、表示されません")
    logger.info("読み込み %d 行", 3000)
    logger.warning("除外 %d 行", 4)
    try:
        int("abc")
    except ValueError:
        logger.exception("整数に直せない値がありました")


if __name__ == "__main__":
    main()

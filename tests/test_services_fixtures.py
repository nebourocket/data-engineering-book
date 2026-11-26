"""サービス用フィクスチャの skip / fail の切り替えを確かめます。"""
pytest_plugins = ["pytester"]

CONFTEST = "examples/conftest.py"


def run(pytester, monkeypatch, require):
    from pathlib import Path

    pytester.makeconftest((Path(__file__).resolve().parent.parent / CONFTEST).read_text(encoding="utf-8"))
    pytester.makepyfile("def test_x(pg_dsn, s3_client, kafka_bootstrap):\n    pass\n")
    for name in ("PG_DSN", "S3_ENDPOINT", "KAFKA_BOOTSTRAP", "DE_BOOK_REQUIRE_SERVICES"):
        monkeypatch.delenv(name, raising=False)
    if require:
        monkeypatch.setenv("DE_BOOK_REQUIRE_SERVICES", "1")
    return pytester.runpytest_subprocess()


def test_skips_when_unset(pytester, monkeypatch):
    run(pytester, monkeypatch, require=False).assert_outcomes(skipped=1)


def test_fails_when_required(pytester, monkeypatch):
    run(pytester, monkeypatch, require=True).assert_outcomes(errors=1)

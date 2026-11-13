import psycopg

import acid
import anomalies
import constraints
import locks
import normalization
import safe_read


def test_normalization_removes_update_anomaly(pg_dsn):
    out = normalization.run_stages(pg_dsn)
    assert out["before"] == 1
    assert out["after_partial_update"] == 2  # 第 1 正規形では 1 行だけ直すと食い違う
    assert out["updated_rows"] == 1  # 第 3 正規形なら 1 行の更新で済む
    assert out["wide"] == out["normalized"] == [("寝具", 19000), ("飲み物", 2400)]


def test_constraints_reject_bad_rows(pg_dsn):
    assert constraints.try_bad_statements(pg_dsn) == {
        "主キーの重複": "UniqueViolation",
        "一意制約（メール）": "UniqueViolation",
        "NOT NULL": "NotNullViolation",
        "外部キー（存在しない顧客）": "ForeignKeyViolation",
        "CHECK（未知の状態）": "CheckViolation",
        "CHECK（数量が 0）": "CheckViolation",
    }
    assert "customers_email_key" in constraints.load_neboske_customers(pg_dsn)


def test_dirty_read_never_happens_in_postgresql(pg_dsn):
    for level in anomalies.LEVELS:
        assert anomalies.dirty_read(pg_dsn, level) == 10


def test_non_repeatable_read_and_phantom(pg_dsn):
    assert anomalies.non_repeatable_read(pg_dsn, "READ COMMITTED") == (10, 7)
    assert anomalies.non_repeatable_read(pg_dsn, "REPEATABLE READ") == (10, 10)
    assert anomalies.phantom_read(pg_dsn, "READ COMMITTED") == (2, 3)
    assert anomalies.phantom_read(pg_dsn, "REPEATABLE READ") == (2, 2)  # PostgreSQL は標準より強い


def test_lost_update_and_fixes(pg_dsn):
    assert anomalies.lost_update(pg_dsn, "READ COMMITTED") == (8, None)  # 正しくは 5。a の 3 個が消えた
    assert anomalies.lost_update(pg_dsn, "REPEATABLE READ") == (7, "SerializationFailure")
    assert anomalies.atomic_update(pg_dsn, "READ COMMITTED") == 5
    assert anomalies.select_for_update(pg_dsn) == (1, 7)  # b は a の COMMIT まで待たされ、7 を読む


def test_write_skew_needs_serializable(pg_dsn):
    assert anomalies.write_skew(pg_dsn, "REPEATABLE READ") == (0, None)  # 店番が 0 人になる
    assert anomalies.write_skew(pg_dsn, "SERIALIZABLE") == (1, "SerializationFailure")


def test_mvcc_row_versions(pg_dsn):
    before, after = locks.row_versions(pg_dsn)
    assert before[0] != after[0] and before[1] != after[1]  # 更新は行を書き換えず、新しい版を作る
    assert (before[3], after[3]) == (10, 9)


def test_readers_do_not_block_but_writers_wait(pg_dsn):
    seen, writer = locks.reader_is_not_blocked(pg_dsn)
    assert seen == 10 and "時間切れ" in writer


def test_deadlock_and_consistent_order(pg_dsn):
    assert len(locks.deadlock(pg_dsn, same_order=False)) == 1
    assert locks.deadlock(pg_dsn, same_order=True) == []


def test_safe_read(pg_dsn):
    safe_read.prepare(pg_dsn, 2500)
    assert [len(r) for r in safe_read.read_in_batches(pg_dsn)] == [1000, 1000, 500]
    assert "read-only" in safe_read.write_is_refused(pg_dsn)
    rows = safe_read.show_my_session(pg_dsn)
    assert len(rows) == 1 and rows[0][2] == "idle in transaction"


def test_atomicity_rolls_back_both_updates(pg_dsn):
    assert acid.atomicity(pg_dsn) == (0, 5, "stock_quantity_check")


def test_retry_after_serialization_failure(pg_dsn):
    assert acid.write_skew_with_retry(pg_dsn) == ([(False, 1)], 1)

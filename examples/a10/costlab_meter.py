"""クエリが読んだバイト数と秒数を測ります。"""
import time


def _rchar():
    """このプロセスが read 系の呼び出しで読んだ累計バイト数 (Linux の /proc/self/io)。"""
    with open("/proc/self/io") as f:
        return next(int(line.split()[1]) for line in f if line.startswith("rchar"))


def measure(con, sql, repeat=8):
    """同じ SQL を repeat 回流し、読み取りバイト数の最小・最短秒・行数を返します。

    読み取りバイト数は、先読みの境界で実行ごとに数 % 揺れます。最小を取り、本文では MB に丸めて書きます。
    """
    best, read, rows = None, None, None
    for _ in range(repeat):
        before = _rchar()
        t0 = time.perf_counter()
        rows = len(con.execute(sql).fetchall())
        sec = time.perf_counter() - t0
        used = _rchar() - before
        read = used if read is None else min(read, used)
        best = sec if best is None else min(best, sec)
    return {"read_bytes": read, "seconds": best, "rows": rows}


def mb(nbytes):
    """バイト数を MB (10 の 6 乗) の文字列にします。"""
    return f"{nbytes / 1e6:,.2f} MB"

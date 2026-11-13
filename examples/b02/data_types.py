"""整数・浮動小数・decimal の実験です。"""
from decimal import ROUND_HALF_UP, Decimal

import duckdb

# 浮動小数点数（float）は 2 進数で近似するので、10 進数の 0.1 を正確に持てない
print(0.1 + 0.2, 0.1 + 0.2 == 0.3)
total = 0.0
for _ in range(10):
    total += 0.1  # 0.1 円ではなく 0.1 を 10 回足す
print(total, total == 1.0)
print(Decimal(0.1))  # float の 0.1 が実際に持っている値

# decimal は 10 進数のまま計算する。文字列から作る（float から作ると誤差ごと取り込む）
print(Decimal("0.1") + Decimal("0.2"), Decimal("0.1") + Decimal("0.2") == Decimal("0.3"))

# 金額を「小数のドル」から「整数のセント」に直す: float だと 1 セントずれる金額がある
cents = range(1, 10000)
float_wrong = [c for c in cents if int(c / 100 * 100) != c]
print(float_wrong[:5], len(float_wrong), "/", len(cents))
print(int(0.29 * 100), int(Decimal("0.29") * 100))

# 丸め方も仕様: Python の round() は偶数丸め（2.5 → 2）、請求書では四捨五入が多い
print(round(2.5), round(3.5))
print(Decimal("2.5").quantize(Decimal("1"), rounding=ROUND_HALF_UP))

# DuckDB の型: 固定長の整数はあふれるとエラーになり、DOUBLE は誤差が出る
con = duckdb.connect()
print(con.execute("SELECT 0.1::DOUBLE + 0.2::DOUBLE = 0.3::DOUBLE").fetchone())
print(con.execute("SELECT 0.1::DECIMAL(18,2) + 0.2::DECIMAL(18,2) = 0.3::DECIMAL(18,2)").fetchone())
try:
    con.execute("SELECT 2147483647::INTEGER + 1")
except duckdb.OutOfRangeException as e:
    print("あふれ:", str(e).splitlines()[0])

# 2**53 を超える整数は、JSON を double で読む環境（JavaScript など）で正確に持てない
big = 2**53 + 1
print(big, int(float(big)))

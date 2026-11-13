!!! tip
    プログラムを書くのが初めての方は、先に準備編 [第5章](../start/s05-sql-1.md)・[第6章](../start/s06-sql-2.md) (SQL) を読んでください。

# 第5章 SQL 基礎

## この章でできるようになること

- `SELECT` `WHERE` `ORDER BY` `LIMIT` で、表から欲しい行と列を取り出せる。
- `NULL` が絡む比較が「真でも偽でもない」第三の値を返すことを説明し、行が消える事故を避けられる。
- `GROUP BY` と `HAVING` で集計し、`WHERE` との使い分けを説明できる。
- `INNER` `LEFT` `FULL` `CROSS` の `JOIN` を使い分け、結合で行が増える・消える原因を見つけられる。
- `CASE` 式、日付の変換、サブクエリ、`UNION` / `UNION ALL` を使える。
- SQL が「書いた順」ではなく決まった順で評価されることを使って、エラーの理由を読める。

この章は、これから先ずっと使う道具の章です。パイプラインの変換も、dbt のモデルも、データ品質のテストも、中身はほとんど SQL です。急がず、出力を自分の手元の数字と見比べながら進めてください。

## SQL とは何か、どこで動かすか

SQL は、表の形をしたデータに「何が欲しいか」を伝える言語です。Python のように「どの順番で何をするか」を書くのではなく、結果の条件だけを書きます。ファイルを 1 行ずつ読んで条件を判定するループは書かず、「東京の顧客の件数が欲しい」と書けば、データベースが読み方や順序を選びます。これを宣言型と呼びます。選び方が変わっても結果は同じなので、データが 100 倍になったときは、データベースの側が賢い読み方に切り替えてくれます。第 6 章の実行計画は、その選び方を覗く話です。

SQL には国際標準（ISO/IEC 9075）があり、PostgreSQL や DuckDB など多くの製品が標準の一部を実装し、独自の拡張を足しています。PostgreSQL の文書には、どの機能が標準のどの項目に当たるかの一覧があります（参考文献）。標準の部分は、どの製品でもほぼ同じ書き方で通ります。この章でも、DuckDB だけの書き方が出てきたときは、そう断ります。

本書では DuckDB（バージョン 2.0.0）を使います。サーバーを立てずに、ファイル 1 つのデータベースとして動く分析向けの DBMS（データベース管理システム。データを保存し、SQL を受けて処理するソフトウェア）で、Python から呼べるため、Docker の開発用イメージだけで試せます。使うデータは、本書で共通に使う架空の通販「ねぼすけ商店」です。顧客・商品・注文・注文明細・行動ログの 5 つの表が、`examples/common/neboske_shop.py` から作られます。このデータには、欠損・重複・表記ゆれが意図して入っています。本物のデータも同じ姿をしているので、それに出会う練習も兼ねます。

SQL をファイルに書いて流す小さなスクリプトを用意しました。クエリは `-- name: 名前` の行で区切り、名前を渡すとそのクエリだけを実行します。`shop.duckdb` が無ければ、ねぼすけ商店のデータで作ります。

```python
import re
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from neboske_shop import write_duckdb  # noqa: E402


def split_queries(text: str) -> dict[str, str]:
    """「-- name: 名前」で区切って {名前: SQL} を返します。"""
    parts = re.split(r"^-- name: (\S+)\n", text, flags=re.M)
    return {name: sql.strip() for name, sql in zip(parts[1::2], parts[2::2])}


if __name__ == "__main__":
    db = Path("shop.duckdb")
    if not db.exists():
        write_duckdb(db)
    queries = split_queries(Path(sys.argv[1]).read_text(encoding="utf-8"))
    con = duckdb.connect(str(db))
    for name in sys.argv[2:] or queries:
        print(f"-- {name}")
        con.sql(queries[name]).show()
```

本章のすべてのクエリは `examples/b05/queries.sql` にあります。次のように、名前を指定して実行できます。

```bash
python examples/b05/run_sql.py examples/b05/queries.sql count_tokyo
```

まず表の列と型を見ます。`DESCRIBE` は列名と型の一覧を返します。

```sql
DESCRIBE orders;
```

```text
┌─────────────┬─────────────┬─────────┬─────────┬─────────┬─────────┐
│ column_name │ column_type │  null   │   key   │ default │  extra  │
│   varchar   │   varchar   │ varchar │ varchar │ varchar │ varchar │
├─────────────┼─────────────┼─────────┼─────────┼─────────┼─────────┤
│ order_id    │ BIGINT      │ YES     │ NULL    │ NULL    │ NULL    │
│ customer_id │ BIGINT      │ YES     │ NULL    │ NULL    │ NULL    │
│ ordered_at  │ VARCHAR     │ YES     │ NULL    │ NULL    │ NULL    │
│ status      │ VARCHAR     │ YES     │ NULL    │ NULL    │ NULL    │
└─────────────┴─────────────┴─────────┴─────────┴─────────┴─────────┘
```

注目してほしいのは `ordered_at` の型が `VARCHAR`（文字列）であることです。日時が文字列のまま入っているデータは、現場で頻繁にあります。この章の後半で、これを日時型に直して扱います。

## 取り出す、絞る、並べる

SQL の基本形は `SELECT`（どの列）、`FROM`（どの表）、`WHERE`（どの行）、`ORDER BY`（どの順）、`LIMIT`（何行まで）の組み合わせです。東京の顧客を、`customer_id` の順に 5 件取り出します。

```sql
SELECT customer_id, name, prefecture
FROM customers
WHERE prefecture = '東京'
ORDER BY customer_id
LIMIT 5;
```

```text
┌─────────────┬──────────┬────────────┐
│ customer_id │   name   │ prefecture │
│    int64    │ varchar  │  varchar   │
├─────────────┼──────────┼────────────┤
│           8 │ 小林美咲 │ 東京       │
│          17 │ 鈴木健   │ 東京       │
│          28 │ 鈴木蓮   │ 東京       │
│          43 │ 高橋大輔 │ 東京       │
│          47 │ 山本太郎 │ 東京       │
└─────────────┴──────────┴────────────┘
```

`WHERE` の中で使う主な道具は、比較（`=` `<>` `<` `>=`）、`AND` / `OR` / `NOT`、範囲の `BETWEEN`、候補から選ぶ `IN`、パターンの `LIKE` です。日時の範囲は、`BETWEEN` ではなく「以上、未満」の組み合わせで書く習慣をお勧めします。`BETWEEN` は両端を含むため、`BETWEEN '2026-03-01' AND '2026-03-31'` と書くと、3 月 31 日の昼の注文が落ちます。文字列として比べると `'2026-03-31 12:00:00'` は `'2026-03-31'` より大きく、日時型でも `'2026-03-31'` は 0 時 0 分 0 秒として扱われるためです。「3 月 1 日以上、4 月 1 日未満」と書けば、月末が何日でも、時刻の細かさが変わっても、同じ形で書けます。

```sql
SELECT order_id, ordered_at, status
FROM orders
WHERE status IN ('shipped', 'delivered')
  AND ordered_at >= '2026-03-01'
  AND ordered_at < '2026-04-01'
ORDER BY ordered_at
LIMIT 3;
```

```text
┌──────────┬─────────────────────┬─────────┐
│ order_id │     ordered_at      │ status  │
│  int64   │       varchar       │ varchar │
├──────────┼─────────────────────┼─────────┤
│     2283 │ 2026-03-01 00:37:35 │ shipped │
│     2699 │ 2026-03-01 01:45:52 │ shipped │
│     2308 │ 2026-03-01 05:28:23 │ shipped │
└──────────┴─────────────────────┴─────────┘
```

`LIKE` は `%`（任意の文字列）と `_`（任意の 1 文字）が使えます。コーヒーを含む商品名は次のとおりです。

```sql
SELECT name FROM products WHERE name LIKE '%コーヒー%';
```

```text
┌──────────────────┐
│       name       │
│     varchar      │
├──────────────────┤
│ コーヒー豆(標準) │
│ コーヒー豆(大)   │
└──────────────────┘
```

`LIMIT` は便利ですが、`ORDER BY` なしで使うと「どの行が返るか」が決まりません。表を覗くための `LIMIT 3` は構いませんが、結果に意味を持たせたいときは、必ず `ORDER BY` と一緒に使ってください。同じ値の行が並ぶ場合は、`ORDER BY customer_id` のように、一意に決まる列を最後に足します。並びが実行のたびに変わると、テストが不安定になります。

## NULL と三値論理

`NULL` は「値が無い」「分からない」を表す印です。0 でも空文字でもありません。505 人の顧客のうち 20 人は、メールアドレスが `NULL` でした。

ここで SQL の最大の落とし穴が出ます。`NULL` と何かを比べた結果は、真（TRUE）でも偽（FALSE）でもなく、「分からない」（NULL）になります。真・偽・不明の 3 つの値を持つので、三値論理と呼びます。`WHERE` は、条件が TRUE の行だけを残します。FALSE の行も、NULL の行も落ちます。

```sql
SELECT NULL = NULL AS eq,
       NULL IS NULL AS is_null,
       1 + NULL AS plus,
       NULL AND FALSE AS and_false,
       NULL OR TRUE AS or_true;
```

```text
┌─────────┬─────────┬───────┬───────────┬─────────┐
│   eq    │ is_null │ plus  │ and_false │ or_true │
│ boolean │ boolean │ int32 │  boolean  │ boolean │
├─────────┼─────────┼───────┼───────────┼─────────┤
│ NULL    │ true    │  NULL │ false     │ true    │
└─────────┴─────────┴───────┴───────────┴─────────┘
```

`NULL = NULL` が TRUE にならないのは、2 つの「分からない」が等しいかどうかも分からないからです。主な式の結果を表にまとめます（値は DuckDB に計算させて書き出しています）。

{{ table("b05-null-logic") }}

メールアドレスが無い顧客を探すつもりで `= NULL` と書くと、結果は 0 件です。エラーにはなりません。これが怖いところで、書いた人は「該当者がいない」と受け取ります。

```sql
SELECT count(*) AS n FROM customers WHERE email = NULL;
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│     0 │
└───────┘
```

`NULL` かどうかを調べる専用の演算子が `IS NULL` と `IS NOT NULL` です。

```sql
SELECT count(*) AS n FROM customers WHERE email IS NULL;
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│    20 │
└───────┘
```

もう 1 つの落とし穴は、`<>`（等しくない）です。特定のメールアドレス以外の顧客を数えたいとします。全顧客は 505 件で、そのアドレスの本人 1 件を除けば 504 件のはずですが、結果は 484 件です。メールが `NULL` の 20 件が、そのアドレスと「等しくない」はずなのに、比較が NULL になって落ちたからです。

```sql
SELECT count(*) AS n FROM customers WHERE email <> 'user0001@example.com';
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│   484 │
└───────┘
```

`NULL` も「等しくない側」に含めたいときは、`IS DISTINCT FROM` を使います。`NULL` を普通の値のように比べる演算子です。DuckDB と PostgreSQL のどちらでも使えます。

```sql
SELECT count(*) AS n
FROM customers
WHERE email IS DISTINCT FROM 'user0001@example.com';
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│   504 │
└───────┘
```

集約関数にも `NULL` の扱いがあります。`count(*)` は行を数え、`count(列)` は `NULL` でない値を数え、`count(DISTINCT 列)` は `NULL` でない値の種類を数えます。3 つは別の質問です。

```sql
SELECT count(*) AS all_rows,
       count(email) AS with_email,
       count(DISTINCT email) AS distinct_email
FROM customers;
```

```text
┌──────────┬────────────┬────────────────┐
│ all_rows │ with_email │ distinct_email │
│  int64   │   int64    │     int64      │
├──────────┼────────────┼────────────────┤
│      505 │        485 │            480 │
└──────────┴────────────┴────────────────┘
```

505 行のうちメールがある行は 485 行、そのうち重複を除くと 480 種類です。差の 5 は、このデータに意図して入れた二重登録（同じメールで `customer_id` だけ違う）の数です。`sum` や `avg` は `NULL` の行を無視します。「平均値の分母に `NULL` の行は入らない」ことは、レポートを読む人にも伝わっていないことが多いので、数字を出すときは注記してください。

最後に、`NOT IN` の罠です。`x NOT IN (サブクエリ)` は、サブクエリの結果に `NULL` が 1 つでも混ざると、0 件を返します。サブクエリの値と一致しない行は、`NULL` との比較が NULL（分からない）になるため全体が NULL に、一致する行は FALSE になり、どの行も TRUE にならないためです。表の「1 NOT IN (2, NULL)」の行がそれです。

```sql
SELECT count(*) AS n
FROM customers
WHERE customer_id NOT IN (SELECT x FROM (VALUES (1), (NULL)) AS t(x));
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│     0 │
└───────┘
```

`customer_id` が 1 でない顧客は 504 人いるはずなのに、結果は 0 です。`NOT EXISTS` に書き換えると、期待どおり 504 件になります。

```sql
SELECT count(*) AS n
FROM customers AS c
WHERE NOT EXISTS (
  SELECT 1 FROM (VALUES (1), (NULL)) AS t(x) WHERE t.x = c.customer_id
);
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│   504 │
└───────┘
```

「あるものの中に無い行」を探すときは、`NOT IN` ではなく `NOT EXISTS`（または後で出てくる `LEFT JOIN ... IS NULL`）を使う、と決めておくと事故が減ります。

`NULL` を扱う道具も覚えておきます。`coalesce(a, b, ...)` は、左から順に見て最初の `NULL` でない値を返します。メールが無いときの表示用の値を入れる、といった場面で使います。

```sql
SELECT customer_id, coalesce(email, '(未登録)') AS email
FROM customers
WHERE email IS NULL
ORDER BY customer_id
LIMIT 3;
```

```text
┌─────────────┬──────────┐
│ customer_id │  email   │
│    int64    │ varchar  │
├─────────────┼──────────┤
│           2 │ (未登録) │
│          26 │ (未登録) │
│          36 │ (未登録) │
└─────────────┴──────────┘
```

`nullif(a, b)` は、a と b が等しければ `NULL`、違えば a を返します。0 で割るエラーを避けるのに使います。分母が 0 になりうるときは、`nullif(分母, 0)` と書くと、結果が `NULL` になって計算が止まりません。顧客ごとの「キャンセル数 ÷ 出荷数」です。出荷が 0 件の顧客は、エラーではなく `NULL` になります（下の 10 人は全員が出荷 1 件以上なので、すべて値が出ています）。

```sql
SELECT customer_id,
       count(*) FILTER (WHERE status = 'cancelled') AS cancelled,
       count(*) FILTER (WHERE lower(status) = 'shipped') AS shipped,
       count(*) FILTER (WHERE status = 'cancelled')
         / nullif(count(*) FILTER (WHERE lower(status) = 'shipped'), 0) AS cancel_per_shipped
FROM orders
WHERE customer_id <= 10
GROUP BY customer_id
ORDER BY customer_id;
```

```text
┌─────────────┬───────────┬─────────┬────────────────────┐
│ customer_id │ cancelled │ shipped │ cancel_per_shipped │
│    int64    │   int64   │  int64  │       double       │
├─────────────┼───────────┼─────────┼────────────────────┤
│           1 │         1 │       2 │                0.5 │
│           2 │         2 │       2 │                1.0 │
│           3 │         0 │       2 │                0.0 │
│           4 │         0 │       3 │                0.0 │
│           5 │         1 │       3 │ 0.3333333333333333 │
│           6 │         1 │       2 │                0.5 │
│           7 │         2 │       1 │                2.0 │
│           8 │         0 │       1 │                0.0 │
│           9 │         4 │       3 │ 1.3333333333333333 │
│          10 │         0 │       2 │                0.0 │
└─────────────┴───────────┴─────────┴────────────────────┘
  10 rows                                      4 columns
```

文字列を整える関数もよく使います。`trim` は前後の空白を除き、`replace` は文字列を置き換えます。型の変換には `CAST` のほかに `TRY_CAST` があります。`CAST` は 1 件でも変換できない値があると、クエリ全体がエラーで止まります。`TRY_CAST` は、変換できない値を `NULL` にして先へ進みます。

```sql
SELECT trim('  090-1234-5678 ') AS trimmed,
       replace('090-1234-5678', '-', '') AS digits,
       TRY_CAST('12' AS INTEGER) AS good,
       TRY_CAST('12a' AS INTEGER) AS bad;
```

```text
┌───────────────┬─────────────┬───────┬───────┐
│    trimmed    │   digits    │ good  │  bad  │
│    varchar    │   varchar   │ int32 │ int32 │
├───────────────┼─────────────┼───────┼───────┤
│ 090-1234-5678 │ 09012345678 │    12 │  NULL │
└───────────────┴─────────────┴───────┴───────┘
```

`CAST` の場合は、次のように止まります。

```sql
SELECT CAST('12a' AS INTEGER) AS n;
```

```text
Conversion Error: Could not convert string '12a' to INT32

LINE 3: SELECT CAST('12a' AS INTEGER) AS n
               ^^^^^^^^^^^^^^^^^^^^^^
```

大量のデータに汚れた値が混ざっている場合は `TRY_CAST` で `NULL` にし、`NULL` になった行の数を数えて品質の指標にする、という使い方が定番です（第 13 章）。黙って捨てるのではなく、何件あったかを必ず記録します。

並べ替えでも `NULL` は問題になります。DuckDB は、昇順なら `NULL` を最後に置きます（`NULLS LAST`）。PostgreSQL は昇順で最後、降順では最初です。DuckDB は降順でも最後に置くため、製品を移すと並びが変わります（どちらも `NULLS FIRST` / `NULLS LAST` で明示できます）。

```sql
SELECT customer_id, email
FROM customers
ORDER BY email NULLS FIRST, customer_id
LIMIT 3;
```

```text
┌─────────────┬─────────┐
│ customer_id │  email  │
│    int64    │ varchar │
├─────────────┼─────────┤
│           2 │ NULL    │
│          26 │ NULL    │
│          36 │ NULL    │
└─────────────┴─────────┘
```

## 集約と GROUP BY、HAVING

集約は、複数の行を 1 つの値にまとめる操作です。`count` `sum` `avg` `min` `max` が基本で、`GROUP BY` で「何ごとに」まとめるかを指定します。注文の状態ごとの件数です。

```sql
SELECT status, count(*) AS n
FROM orders
GROUP BY status
ORDER BY n DESC;
```

```text
┌───────────┬───────┐
│  status   │   n   │
│  varchar  │ int64 │
├───────────┼───────┤
│ delivered │   977 │
│ shipped   │   925 │
│ cancelled │   528 │
│ placed    │   511 │
│ SHIPPED   │    59 │
└───────────┴───────┘
```

`shipped` と `SHIPPED` が別々に数えられています。このデータに意図して入れた表記ゆれです。SQL は文字列を厳密に比べるので、人間が同じと読むものも、別のグループになります。`lower()` で小文字にそろえてから数えると、`shipped` は 984 件になります。

```sql
SELECT lower(status) AS status, count(*) AS n
FROM orders
GROUP BY lower(status)
ORDER BY n DESC;
```

```text
┌───────────┬───────┐
│  status   │   n   │
│  varchar  │ int64 │
├───────────┼───────┤
│ shipped   │   984 │
│ delivered │   977 │
│ cancelled │   528 │
│ placed    │   511 │
└───────────┴───────┘
```

`GROUP BY` では、`SELECT` に書ける列は「グループにした列」か「集約関数の中の列」だけです。グループにしていない列を裸で書けないのは、グループの中に複数の値があり、どれを返すか決められないからです。

集計結果を絞るのが `HAVING` です。`WHERE` は集計の前に行を絞り、`HAVING` は集計の後にグループを絞ります。顧客が 55 人以上の都道府県を探します。

```sql
SELECT prefecture, count(*) AS n
FROM customers
GROUP BY prefecture
HAVING count(*) >= 55
ORDER BY n DESC;
```

```text
┌────────────┬───────┐
│ prefecture │   n   │
│  varchar   │ int64 │
├────────────┼───────┤
│ 愛知       │    59 │
│ 福岡       │    57 │
└────────────┴───────┘
```

「ある都道府県だけを集計したい」なら `WHERE` です。`WHERE` で先に絞れば集計に回る行が減ります（`HAVING` に書いても、結果が同じなら最適化で先に絞られることがありますが、意図が伝わるのは `WHERE` です）。「集計した値で絞る」ときだけ `HAVING` を使います。

結合と集計を組み合わせれば、売上の分析ができます。カテゴリごとの明細の行数と売上（数量 × 単価の合計）です。

```sql
SELECT p.category,
       count(*) AS lines,
       sum(i.quantity * i.unit_price) AS revenue
FROM order_items AS i
INNER JOIN products AS p ON p.product_id = i.product_id
GROUP BY p.category
ORDER BY revenue DESC;
```

```text
┌──────────┬───────┬──────────┐
│ category │ lines │ revenue  │
│ varchar  │ int64 │  int128  │
├──────────┼───────┼──────────┤
│ 飲み物   │  1784 │ 10944850 │
│ 朝食     │  1406 │ 10746650 │
│ 寝具     │  1740 │  9218200 │
│ 雑貨     │  1419 │  6430600 │
│ 目覚まし │  1120 │  4325450 │
└──────────┴───────┴──────────┘
```

## JOIN で表をつなぐ

正規化された表は、1 つの事実を 1 か所にだけ持ちます（第 7 章）。そのため、分析では表をつないで使います。`JOIN` は、2 つの表の行を、条件（`ON`）が合うものどうしで組にします。

{{ table("b05-join-types") }}

`INNER JOIN` は、上の集計で使いました。ここで押さえるのは `LEFT JOIN` です。左の表の行を全部残し、右に相手がいなければ右の列を `NULL` にします。これを使うと、「注文が 1 件もない顧客」が探せます。注文側の主キーが `NULL` の行が、相手のいない行です。

```sql
SELECT c.customer_id, c.name
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

```text
┌─────────────┬──────────┐
│ customer_id │   name   │
│    int64    │ varchar  │
├─────────────┼──────────┤
│         261 │ 渡辺結衣 │
└─────────────┴──────────┘
```

505 人の顧客のうち、注文が無いのは 1 人でした。この書き方は、アンチ結合と呼ばれる定番です。`NOT EXISTS` と同じ意味で、どちらでも構いません。

`LEFT JOIN` で最もよく起きる事故は、右の表の条件を `WHERE` に書いてしまうことです。「キャンセルされた注文」について、顧客と合わせて見たいとします。条件を `ON` に書くと、キャンセルのない顧客も（右側が `NULL` で）残ります。

```sql
SELECT count(*) AS n
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id AND o.status = 'cancelled';
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│   699 │
└───────┘
```

同じ条件を `WHERE` に書くと、結果が変わります。

```sql
SELECT count(*) AS n
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.status = 'cancelled';
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│   528 │
└───────┘
```

左の表の行がすべて残るのが `LEFT JOIN` の約束なのに、右の列が `NULL` の行は `WHERE o.status = 'cancelled'` が NULL になって落ち、実質 `INNER JOIN` になりました。結果は 528 件で、`orders` のキャンセルの件数に等しくなっています。「`ON` は結合する相手を決める条件、`WHERE` は結合後の結果を絞る条件」と覚えてください。

`FULL JOIN` は、両側の全行を残します。2 つの表の差分を調べる突き合わせに使います。顧客台帳と注文の顧客 ID を比べると、注文に現れない顧客が 1 人いて、顧客台帳に無い ID の注文は 0 件でした。

```sql
SELECT count(*) FILTER (WHERE o.customer_id IS NULL) AS only_customers,
       count(*) FILTER (WHERE c.customer_id IS NULL) AS only_orders,
       count(*) AS total
FROM customers AS c
FULL JOIN orders AS o ON o.customer_id = c.customer_id;
```

```text
┌────────────────┬─────────────┬───────┐
│ only_customers │ only_orders │ total │
│     int64      │    int64    │ int64 │
├────────────────┼─────────────┼───────┤
│              1 │           0 │  3001 │
└────────────────┴─────────────┴───────┘
```

`CROSS JOIN` は条件なしで全組み合わせを作ります。都道府県 10 × カテゴリ 5 = 50 行の枠を作るときなどに使います。ただし、`JOIN` の条件を書き忘れたときの結果も同じ直積になるため、行数が突然かけ算になっていたら、条件の書き忘れを疑ってください。

```sql
SELECT count(*) AS n
FROM (SELECT DISTINCT prefecture FROM customers) AS a
CROSS JOIN (SELECT DISTINCT category FROM products) AS b;
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│    50 │
└───────┘
```

## 行が増える、行が消える

JOIN で数字が合わなくなる原因の大半は、「結合のキーが一意でない」ことです。1 行の注文に明細が複数あれば、注文と明細を結合した結果は明細の数だけ行ができます。これをファンアウトと呼びます。結合の前後で、行数を確かめてみます。

```sql
SELECT count(*) AS joined_rows,
       count(DISTINCT o.order_id) AS orders
FROM orders AS o
INNER JOIN order_items AS i ON i.order_id = o.order_id;
```

```text
┌─────────────┬────────┐
│ joined_rows │ orders │
│    int64    │ int64  │
├─────────────┼────────┤
│        7469 │   3000 │
└─────────────┴────────┘
```

3,000 件の注文が、結合後は 7,469 行です。ここで `count(*)` を「注文数」として報告すると、2.5 倍の数字になります。直すには、`count(DISTINCT o.order_id)` にするか、先に注文単位に集計してから結合します。

さらに厄介なのは、「1 対多」の表を 2 つ続けて結合したときです。顧客 122 は、注文が 3 件、行動ログが 11 件あります。両方を顧客 ID でつなぐと、組み合わせの 33 行になります。

```sql
SELECT
  (SELECT count(*) FROM orders WHERE customer_id = 122) AS orders_n,
  (SELECT count(*) FROM events WHERE customer_id = 122) AS events_n,
  (SELECT count(*)
     FROM orders AS o
     INNER JOIN events AS e ON e.customer_id = o.customer_id
    WHERE o.customer_id = 122) AS joined_n;
```

```text
┌──────────┬──────────┬──────────┐
│ orders_n │ events_n │ joined_n │
│  int64   │  int64   │  int64   │
├──────────┼──────────┼──────────┤
│        3 │       11 │       33 │
└──────────┴──────────┴──────────┘
```

この結果に注文側の金額の `sum` を足すと、金額は 11 倍に膨らみます。直し方は、「結合する前に、それぞれを顧客単位に集計する」です。`WITH`（第 6 章で詳しく扱う CTE）を使って書きます。

```sql
WITH o AS (
  SELECT customer_id, count(*) AS orders_n FROM orders GROUP BY customer_id
), e AS (
  SELECT customer_id, count(*) AS events_n FROM events GROUP BY customer_id
)
SELECT o.customer_id, o.orders_n, e.events_n
FROM o
LEFT JOIN e ON e.customer_id = o.customer_id
WHERE o.customer_id = 122;
```

```text
┌─────────────┬──────────┬──────────┐
│ customer_id │ orders_n │ events_n │
│    int64    │  int64   │  int64   │
├─────────────┼──────────┼──────────┤
│         122 │        3 │       11 │
└─────────────┴──────────┴──────────┘
```

消える側の事故もあります。`INNER JOIN` は、相手のいない行を黙って捨てます。結合キーが `NULL` の行も同じです。このデータの二重登録の顧客は、同じメールで `customer_id` が違う 2 行になっています。自分自身と結合して見つけられます。

```sql
SELECT a.customer_id AS id_a, b.customer_id AS id_b, a.email
FROM customers AS a
INNER JOIN customers AS b
  ON a.email = b.email AND a.customer_id < b.customer_id
ORDER BY a.customer_id;
```

```text
┌───────┬───────┬──────────────────────┐
│ id_a  │ id_b  │        email         │
│ int64 │ int64 │       varchar        │
├───────┼───────┼──────────────────────┤
│   165 │   505 │ user0165@example.com │
│   296 │   501 │ user0296@example.com │
│   307 │   502 │ user0307@example.com │
│   396 │   503 │ user0396@example.com │
│   420 │   504 │ user0420@example.com │
└───────┴───────┴──────────────────────┘
```

この 5 組は、どちらの ID にも注文がぶら下がり得るため、顧客単位の集計がずれる原因になります。実際の現場では、重複を見つけたら、どちらを正とするかの規則を決めて、1 行に寄せてから結合します（第 6 章の重複排除）。

JOIN を書いたら、次の習慣を付けてください。

- 結合のキーが、どちらの側で一意かを言える。
- 結合の前後で、行数（と `count(DISTINCT キー)`）を確かめる。
- `INNER JOIN` で行が減ったら、減った行が何かを `LEFT JOIN ... IS NULL` で見る。

これらは、第 13 章のデータ品質テスト（一意性・件数・参照整合性）に、そのままつながります。

## CASE で条件分岐する

`CASE` 式は、値によって結果を切り替えます。商品を価格帯に分けて数えます。

```sql
SELECT CASE
         WHEN price < 1000 THEN '低価格'
         WHEN price < 3000 THEN '中価格'
         ELSE '高価格'
       END AS band,
       count(*) AS n
FROM products
GROUP BY band
ORDER BY min(price);
```

```text
┌─────────┬───────┐
│  band   │   n   │
│ varchar │ int64 │
├─────────┼───────┤
│ 低価格  │    10 │
│ 中価格  │    18 │
│ 高価格  │    24 │
└─────────┴───────┘
```

`CASE` は `GROUP BY` と組み合わせて、条件に合う行だけを数える使い方もよく見ます。キャンセル率は次のように出せます。

```sql
SELECT sum(CASE WHEN lower(status) = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
       count(*) AS total,
       round(100.0 * sum(CASE WHEN lower(status) = 'cancelled' THEN 1 ELSE 0 END) / count(*), 1) AS cancel_pct
FROM orders;
```

```text
┌───────────┬───────┬────────────┐
│ cancelled │ total │ cancel_pct │
│  int128   │ int64 │   double   │
├───────────┼───────┼────────────┤
│       528 │  3000 │       17.6 │
└───────────┴───────┴────────────┘
```

`WHEN` は上から順に判定され、最初に真になった枝が使われます。どれにも合わず `ELSE` も無ければ、結果は `NULL` です。`ELSE` を書き忘れると、想定外の値が `NULL` になり、後の集計から落ちます。

## 日付と時刻

ねぼすけ商店の日時は文字列でした。確認します。

```sql
SELECT typeof(ordered_at) AS stored_as,
       typeof(CAST(ordered_at AS TIMESTAMP)) AS cast_as
FROM orders
LIMIT 1;
```

```text
┌───────────┬───────────┐
│ stored_as │  cast_as  │
│  varchar  │  varchar  │
├───────────┼───────────┤
│ VARCHAR   │ TIMESTAMP │
└───────────┴───────────┘
```

`YYYY-MM-DD HH:MM:SS` の形は、文字列として比べても時刻順になるため、前の節の範囲指定が動きました。しかし文字列のままでは、「月ごと」「7 日後」「2 つの時刻の差」の計算ができません。`CAST(列 AS TIMESTAMP)` で日時型に変換してから使います。

```sql
SELECT CAST(ordered_at AS TIMESTAMP) AS t,
       date_trunc('month', CAST(ordered_at AS TIMESTAMP)) AS month_start,
       CAST(ordered_at AS DATE) + 7 AS plus_7_days
FROM orders
ORDER BY order_id
LIMIT 2;
```

```text
┌─────────────────────┬─────────────────────┬─────────────┐
│          t          │     month_start     │ plus_7_days │
│      timestamp      │      timestamp      │    date     │
├─────────────────────┼─────────────────────┼─────────────┤
│ 2026-02-24 13:22:12 │ 2026-02-01 00:00:00 │ 2026-03-03  │
│ 2026-05-11 17:49:45 │ 2026-05-01 00:00:00 │ 2026-05-18  │
└─────────────────────┴─────────────────────┴─────────────┘
```

`date_trunc('month', 時刻)` は月の頭に切り捨てます。日付に整数を足すと、その日数だけ進みます。月ごとの集計には `strftime`（書式を指定して文字列にする関数）が便利です。

```sql
SELECT strftime(CAST(ordered_at AS TIMESTAMP), '%Y-%m') AS month,
       count(*) AS n
FROM orders
GROUP BY month
ORDER BY month;
```

```text
┌─────────┬───────┐
│  month  │   n   │
│ varchar │ int64 │
├─────────┼───────┤
│ 2026-01 │   163 │
│ 2026-02 │   497 │
│ 2026-03 │   820 │
│ 2026-04 │   847 │
│ 2026-05 │   518 │
│ 2026-06 │   155 │
└─────────┴───────┘
```

時間の差は `INTERVAL`（期間）で書きます。行動ログには、遅れて届いたものがあります。到着時刻が発生時刻の 1 日以上後のものを数えます。

```sql
SELECT count(*) AS late_events
FROM events
WHERE CAST(received_at AS TIMESTAMP) - CAST(event_time AS TIMESTAMP) > INTERVAL '1 day';
```

```text
┌─────────────┐
│ late_events │
│    int64    │
├─────────────┤
│         122 │
└─────────────┘
```

日時の計算には、よく起きる事故が 3 つあります。1 つ目はタイムゾーンです。ここのデータは、タイムゾーンの情報を持たない時刻です。複数の国のログを混ぜるときは、最初に UTC にそろえるのが安全です。2 つ目は、「その日の終わり」の扱いです。`<= '2026-03-31'` ではなく、`< '2026-04-01'` と書きます。3 つ目は、関数名が製品ごとに違うことです。`date_trunc` は PostgreSQL にもありますが、`strftime` は DuckDB の名前で、PostgreSQL では `to_char` を使います。

## サブクエリ

サブクエリは、クエリの中に入れた別のクエリです。置く場所で 3 つの使い方があります。

1 つ目は、1 つの値を返すサブクエリ（スカラーサブクエリ）です。全商品の平均より高い商品を探します。

```sql
SELECT name, price
FROM products
WHERE price > (SELECT avg(price) FROM products)
ORDER BY price DESC
LIMIT 3;
```

```text
┌────────────────┬───────┐
│      name      │ price │
│    varchar     │ int64 │
├────────────────┼───────┤
│ シリアル(標準) │  5850 │
│ ジャム(大)     │  5450 │
│ はちみつ(大)   │  5450 │
└────────────────┴───────┘
```

2 つ目は `EXISTS` / `IN` で、「ある条件を満たす行が存在するか」を調べます。キャンセルされた注文を持つ顧客の数です。

```sql
SELECT count(*) AS n
FROM customers AS c
WHERE EXISTS (
  SELECT 1 FROM orders AS o
  WHERE o.customer_id = c.customer_id AND o.status = 'cancelled'
);
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│   334 │
└───────┘
```

3 つ目は `FROM` の中に書く方法で、集計結果をさらに集計するときに使います。注文 1 件あたりの平均明細数です。

```sql
SELECT round(avg(n), 2) AS avg_lines_per_order
FROM (
  SELECT order_id, count(*) AS n FROM order_items GROUP BY order_id
) AS per_order;
```

```text
┌─────────────────────┐
│ avg_lines_per_order │
│       double        │
├─────────────────────┤
│                2.49 │
└─────────────────────┘
```

サブクエリが深くなって読みにくくなったら、第 6 章の CTE に書き直します。

## UNION と UNION ALL

`UNION` は、同じ列を持つ 2 つの結果を縦につなぎます。`UNION` は重複した行を取り除き、`UNION ALL` は取り除きません。注文した顧客の ID と、行動のあった顧客の ID を合わせます。

```sql
SELECT count(*) AS n
FROM (
  SELECT customer_id FROM orders
  UNION
  SELECT customer_id FROM events
) AS u;
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│   505 │
└───────┘
```

```sql
SELECT count(*) AS n
FROM (
  SELECT customer_id FROM orders
  UNION ALL
  SELECT customer_id FROM events
) AS u;
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│  7040 │
└───────┘
```

`UNION` は 505 行、`UNION ALL` は 7,040 行（注文 3,000 + ログ 4,040）です。重複を取り除くには全行を比べる必要があるので、`UNION` のほうが重くなります。重複が起きない（または起きてもよい）と分かっているときは、`UNION ALL` を使います。「とりあえず `UNION`」と書くと、重複が静かに消えて数字が合わなくなる、遅くなる、のどちらかが起きます。

`SELECT DISTINCT` は、結果から重複した行を取り除きます。都道府県の一覧を取るときなどに使います。

```sql
SELECT DISTINCT prefecture FROM customers ORDER BY prefecture;
```

```text
┌────────────┐
│ prefecture │
│  varchar   │
├────────────┤
│ 京都       │
│ 北海道     │
│ 大阪       │
│ 宮城       │
│ 愛知       │
│ 東京       │
│ 沖縄       │
│ 石川       │
│ 神奈川     │
│ 福岡       │
└────────────┘
   10 rows
```

2 つの結果の差や共通部分は、`EXCEPT` と `INTERSECT` で取れます（どちらも重複を除きます）。注文のない顧客は、顧客の ID から注文の ID を引いて求められます。

```sql
SELECT customer_id FROM customers
EXCEPT
SELECT customer_id FROM orders;
```

```text
┌─────────────┐
│ customer_id │
│    int64    │
├─────────────┤
│         261 │
└─────────────┘
```

注文があり、かつ行動ログにも現れる顧客の数は次のとおりです。

```sql
SELECT count(*) AS n
FROM (
  SELECT customer_id FROM orders
  INTERSECT
  SELECT customer_id FROM events
) AS both_sides;
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│   504 │
└───────┘
```

`EXCEPT` は、`LEFT JOIN ... IS NULL` や `NOT EXISTS` と同じ答えを返します。列の組全体を比べるので、`NULL` どうしは等しいものとして扱われる点が `=` と違います。

## 表を作る、書き換える

ここまでは読む SQL でした。データを作って書き換える文も、基本の形を知っておきます。深い話（制約、トランザクション）は第 7 章で扱います。`CREATE TABLE ... AS SELECT` は、クエリの結果から新しい表を作ります。飲み物の商品だけの表を作ります。

```sql
CREATE TABLE my_products AS
SELECT product_id, name, price FROM products WHERE category = '飲み物';
```

作った表に 1 行足し、更新し、確かめ、消します。`INSERT` は行を追加し、`UPDATE` は条件に合う行を書き換え、`DELETE` は条件に合う行を消します。

```sql
INSERT INTO my_products VALUES (999, 'テスト商品', 100);
```

```sql
UPDATE my_products SET price = price + 100 WHERE product_id = 999;
```

```sql
SELECT product_id, name, price FROM my_products WHERE product_id = 999;
```

```text
┌────────────┬────────────┬───────┐
│ product_id │    name    │ price │
│   int64    │  varchar   │ int64 │
├────────────┼────────────┼───────┤
│        999 │ テスト商品 │   200 │
└────────────┴────────────┴───────┘
```

```sql
DELETE FROM my_products WHERE product_id = 999;
```

`UPDATE` と `DELETE` で `WHERE` を書き忘れると、全行が書き換わる・消えるので、実行する前に同じ `WHERE` で `SELECT` して、対象の行数を確かめる習慣をつけてください。`CREATE VIEW` は、クエリに名前を付けて、表のように使えるようにします。データは複製されず、使うたびに元のクエリが走ります。

```sql
CREATE VIEW cheap_products AS
SELECT product_id, name, price FROM products WHERE price < 1000;
```

```sql
SELECT count(*) AS n FROM cheap_products;
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│    10 │
└───────┘
```

型と制約を決めて表を作るときは、`CREATE TABLE` に列と型を書きます。主キー（行を一意に決める列）を付けた表に同じキーを入れると、データベースが止めてくれます。

```sql
CREATE TABLE memo (id INTEGER PRIMARY KEY, body VARCHAR NOT NULL);
```

```sql
INSERT INTO memo VALUES (1, 'one'), (1, 'two');
```

```text
Constraint Error: PRIMARY KEY or UNIQUE constraint violation: duplicate key "1"
```

これらの文は `examples/b05/ddl.sql` にあり、上から順に流さないと動きません（前の文で作った表を使うため）。最後の文は、重複キーのエラーで止まるのが正しい動きです。流した後の `shop.duckdb` は、表が増えた状態になります。本の数字と合わなくなったときは、`shop.duckdb` を削除してから、もう一度 `run_sql.py` を流せば、元のデータで作り直されます。

## SQL は書いた順に動かない

SQL は、書く順（`SELECT` が先頭）と、評価される順が違います。論理的な評価の順序は、次のとおりです。

{{ table("b05-eval-order") }}

この順序を知っていると、エラーの理由が読めます。たとえば `WHERE` で `SELECT` の別名を使うと、`SELECT` は `WHERE` の後に評価されるので、PostgreSQL では次のエラーになります。PostgreSQL の文書にも、出力列の名前は `ORDER BY` と `GROUP BY` では使えるが、`WHERE` と `HAVING` では使えないとあります。

```text
column "double_price" does not exist
```

ところが DuckDB は、この別名を `WHERE` で許します。同じクエリが動いてしまいます。

```sql
SELECT price * 2 AS double_price FROM products WHERE double_price > 11000;
```

```text
┌──────────────┐
│ double_price │
│    int64     │
├──────────────┤
│        11700 │
└──────────────┘
```

DuckDB 2.0.0 で試すと、この別名が通ります。DuckDB で動いた SQL が PostgreSQL や他の製品で動かないことがあるのは、このような方言の差があるからです。ほかにも、次のような差があります。

- 間隔の書き方。この章では `INTERVAL '1 day'` と書いています（PostgreSQL でも通る形）。DuckDB は `INTERVAL 1 DAY` の短縮形も許します。
- `GROUP BY` で `SELECT` の別名を使う書き方。PostgreSQL の文書によると、SQL-92 では入力列の式しか書けず、出力列の名前を許すのは PostgreSQL などの拡張です。
- `QUALIFY`（第 6 章）、`arg_max`、`PIVOT` 文は DuckDB などの拡張で、PostgreSQL にはありません。
- 集約の `FILTER (WHERE ...)` は標準 SQL ですが、MySQL・SQL Server・Oracle などには無く、`CASE` で書き換えます。

本番の DWH（データウェアハウス。分析用に大量のデータを集めて持つ DB）に流す前に、その製品で動かして確かめます。もう 1 つ、整数の割り算の差があります。`7 / 2` は PostgreSQL では 3（整数の割り算）で、DuckDB では 3.5 です。DuckDB で整数の割り算をするには `//` を使います。

```sql
SELECT 7 / 2 AS slash, 7 // 2 AS int_div;
```

```text
┌────────┬─────────┐
│ slash  │ int_div │
│ double │  int32  │
├────────┼─────────┤
│    3.5 │       3 │
└────────┴─────────┘
```

なお、この評価順序は「論理的な」順序です。実行エンジンは、結果が同じになる範囲で、順番を入れ替えて速くします（`WHERE` の条件を、結合より先に適用するなど）。第 6 章の実行計画で、その様子を見ます。

## 読みやすい SQL を書く

- 予約語は大文字、表名・列名は小文字、など、チームで書き方をそろえる。
- 列の別名は `AS` で明示し、結合する表には短い別名を付ける。ただし `a` `b` ではなく `o`（orders）、`c`（customers）のように、元の名前が分かるものにする。
- `SELECT *` は、中身を覗くときだけ使う。パイプラインに入れるときは、列を明示する。上流で列が増えたとき、下流が壊れたり、重くなったりする。
- 結合のキーが何であるかを、`ON` に必ず書く。`USING` も使えるが、同じ名前の列が複数あるときは `ON` が安全。
- 1 つのクエリが 50 行を超えたら、分けることを考える。

## よくある失敗

- `= NULL` で比べて、0 件になる。`IS NULL` を使う。
- `NOT IN` のサブクエリに `NULL` が混ざり、0 件になる。`NOT EXISTS` を使う。
- `LEFT JOIN` した右の表の列を `WHERE` で絞り、`INNER JOIN` と同じ結果になる。条件は `ON` に書く。
- 1 対多の結合で `count(*)` や `sum` が膨らむ。結合前に集計するか、`count(DISTINCT キー)` にする。
- `BETWEEN` で日時の範囲を書いて、最後の日が落ちる。「以上、未満」で書く。
- `ORDER BY` なしの `LIMIT` を、結果として報告する。
- `UNION` で重複が消えたのに気づかない。意図がなければ `UNION ALL`。
- 表記ゆれ（`shipped` と `SHIPPED`）を数え分けてしまう。集計の前に正規化する。
- DuckDB で動いた SQL を、そのまま別の製品に流す。方言の差を確かめる。

## まとめ

- SQL は、欲しい結果を書く宣言型の言語です。読み方はデータベースが選びます。
- `NULL` との比較は「分からない」を返し、`WHERE` はそれを捨てます。`IS NULL`・`IS DISTINCT FROM`・`NOT EXISTS` を使います。
- `WHERE` は集計の前、`HAVING` は集計の後に絞ります。
- `JOIN` は、結合キーが一意かどうかで行数が変わります。前後で行数を数えます。
- 日時は文字列のままでなく型に直して扱い、範囲は「以上、未満」で書きます。
- SQL は論理的な順序で評価されるので、別名が使える場所と使えない場所があります。製品によっても違います。

## 練習問題

次の問題に、`examples/b05/run_sql.py` と同じ方法でクエリを流して答えてください。

問 1. 注文の状態を `lower()` でそろえたうえで、状態ごとの件数を、多い順に出してください。`cancelled` 以外の状態の合計は何件ですか。

??? note "解答例"
    ```sql
    SELECT lower(status) AS status, count(*) AS n
    FROM orders
    GROUP BY lower(status)
    ORDER BY n DESC;
    ```
    本文の `group_status_lower` と同じ結果です。`shipped` 984、`delivered` 977、`cancelled` 528、`placed` 511 件で、`cancelled` 以外の合計は 984 + 977 + 511 = 2,472 件です。全体の 3,000 件から 528 件を引いても同じになることを確かめてください。

問 2. メールアドレスが `NULL` ではない顧客のうち、同じメールアドレスで登録が 2 回以上ある人を、メールアドレスと登録回数で出してください。

??? note "解答例"
    ```sql
    SELECT email, count(*) AS n
    FROM customers
    WHERE email IS NOT NULL
    GROUP BY email
    HAVING count(*) >= 2
    ORDER BY email;
    ```
    5 件が返ります。どの行も `n` は 2 です。`WHERE` で `NULL` を先に除いてから、`HAVING` でグループを絞っています。`WHERE email IS NOT NULL` を外すと、`NULL` が 1 つのグループにまとめられて 20 件として出てきます。`GROUP BY` は `NULL` どうしを同じグループとして扱うためです。

問 3. 1 度も `cancelled` になっていない顧客の数を、`NOT EXISTS` で求めてください。次に、`LEFT JOIN` に `WHERE o.status = 'cancelled'` を足したクエリが、なぜこの答えを出せないかを説明してください。

??? note "解答例"
    ```sql
    SELECT count(*) AS n
    FROM customers AS c
    WHERE NOT EXISTS (
      SELECT 1 FROM orders AS o
      WHERE o.customer_id = c.customer_id AND o.status = 'cancelled'
    );
    ```
    顧客は 505 人で、キャンセルのある顧客は本文のとおり 334 人です。したがって 505 - 334 = 171 人になります。`LEFT JOIN ... WHERE o.status = 'cancelled'` は、右側が `NULL` の行（キャンセルのない顧客）を `WHERE` が落とすので、数えたい顧客がちょうど消えます。条件を `ON` に移して、右側が `NULL` の行を数える書き方でも求められます。

問 4. 3 月の注文の件数を、`BETWEEN '2026-03-01' AND '2026-03-31'` と「以上、未満」の 2 通りで書いて比べてください。差は何件ですか。また、6 月では同じ書き方で差が出ません。なぜですか。

??? note "解答例"
    ```sql
    SELECT count(*) FROM orders
    WHERE ordered_at >= '2026-03-01' AND ordered_at < '2026-04-01';
    ```

    ```sql
    SELECT count(*) FROM orders
    WHERE ordered_at BETWEEN '2026-03-01' AND '2026-03-31';
    ```

    「以上、未満」は 820 件、`BETWEEN` は 789 件で、差の 31 件は 3 月 31 日の 0 時 0 分 0 秒より後の注文です（文字列で比べると `'2026-03-31 12:00:00'` は `'2026-03-31'` より大きいため、範囲から外れます）。6 月は、最後の注文が 6 月 28 日（`select max(ordered_at)` で確かめられます）で末日に注文が無いので、どちらの書き方でも 155 件になり、差が出ません。差が出ないことは、書き方が正しい証拠にはなりません。末日に注文が入った月になって初めて壊れます。

## 参考文献

- DuckDB Documentation, “SQL Introduction”, <https://duckdb.org/docs/2.0/sql/introduction.html>（2026年11月時点）
- DuckDB Documentation, “SELECT Clause”, <https://duckdb.org/docs/2.0/sql/query_syntax/select.html>
- DuckDB Documentation, “GROUP BY”, <https://duckdb.org/docs/2.0/sql/query_syntax/groupby.html>
- DuckDB Documentation, “Comparison Operators”（`IS DISTINCT FROM`）, <https://duckdb.org/docs/2.0/sql/expressions/comparison_operators.html>
- DuckDB Documentation, “ORDER BY Clause”（`NULLS FIRST` / `NULLS LAST` の既定）, <https://duckdb.org/docs/2.0/sql/query_syntax/orderby.html>
- DuckDB Documentation, “Set Operations”（`UNION` / `UNION ALL`）, <https://duckdb.org/docs/2.0/sql/query_syntax/setops.html>
- DuckDB Documentation, “Date Functions”, <https://duckdb.org/docs/2.0/sql/functions/date.html>
- PostgreSQL Documentation, “SELECT”（処理の順序、出力列の別名の制約）, <https://www.postgresql.org/docs/current/sql-select.html>
- PostgreSQL Documentation, “Table Expressions”（JOIN の種類）, <https://www.postgresql.org/docs/current/queries-table-expressions.html>
- PostgreSQL Documentation, “Appendix D. SQL Conformance”, <https://www.postgresql.org/docs/current/features.html>

!!! tip "さらに深く"
    大きなデータに同じ SQL を流したときに何が起きるかは、応用編 第1章「分散処理の内側」で扱います。

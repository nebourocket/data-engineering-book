# 第6章 SQL 応用

## この章でできるようになること

- ウィンドウ関数で、行を潰さずに順位・前後の行との差・累積和・移動平均を計算できる。
- `ROWS` と `RANGE` のフレーム指定の違いを説明し、`last_value` の罠を避けられる。
- CTE（`WITH`）で長いクエリを段に分け、再帰 CTE で日付の連番や階層をたどれる。
- 重複排除と「各グループの最新 1 行」を、複数の書き方から選んで書ける。
- 行動ログをセッションに分け、縦持ちの集計を横持ち（ピボット）に直せる。
- `EXPLAIN` と `EXPLAIN ANALYZE` を読み、見積もりと実測のずれ、読んでいる列と行を確かめられる。
- インデックスが行指向の DB と列指向の DB で、どう違う効き方をするかを説明できる。

第 5 章のクエリが書ければ、この章に進めます。使うデータは同じ「ねぼすけ商店」で、クエリは `examples/b06/queries.sql` にあります。実行は第 5 章の `run_sql.py` と同じ要領です。

## ウィンドウ関数の考え方

`GROUP BY` は、同じグループの行を 1 行に潰して集計します。ウィンドウ関数は、行を潰さずに、各行に「その行の周りの行を使った計算結果」を足します。「周り」の指定が `OVER (...)` です。

- `PARTITION BY` は、行をグループに分けます（`GROUP BY` に似ていますが、行は減りません）。
- `ORDER BY` は、グループの中の並びを決めます。
- フレーム（次の節）は、各行の計算に使う範囲を決めます。

顧客 122 の注文に、その顧客の何回目の注文かを付けます。

```sql
SELECT order_id, customer_id, ordered_at,
       row_number() OVER (PARTITION BY customer_id ORDER BY ordered_at) AS nth
FROM orders
WHERE customer_id = 122
ORDER BY nth;
```

```text
┌──────────┬─────────────┬─────────────────────┬───────┐
│ order_id │ customer_id │     ordered_at      │  nth  │
│  int64   │    int64    │       varchar       │ int64 │
├──────────┼─────────────┼─────────────────────┼───────┤
│     1983 │         122 │ 2026-02-01 00:33:14 │     1 │
│        1 │         122 │ 2026-02-24 13:22:12 │     2 │
│     2085 │         122 │ 2026-03-15 01:31:34 │     3 │
└──────────┴─────────────┴─────────────────────┴───────┘
```

もう 1 つ覚えておくのは、評価の順序です。ウィンドウ関数は `WHERE` `GROUP BY` `HAVING` の後に計算されるので、`WHERE` の中では使えません。PostgreSQL の文書にも同じ説明があります。ウィンドウ関数の結果で行を絞りたいときは、サブクエリで包むか、DuckDB の `QUALIFY`（後述）を使います。

この節以降のいくつかのクエリは、日別の売上を使います。キャンセル以外の注文の売上を日ごとに集計したビューを作っておきます。ビューは `shop.duckdb` に残るので、一度作れば、後のクエリは名前を指定して 1 つずつ流せます。

```sql
CREATE OR REPLACE VIEW daily_sales AS
SELECT CAST(o.ordered_at AS DATE) AS d,
       sum(i.quantity * i.unit_price) AS revenue
FROM orders AS o
INNER JOIN order_items AS i USING (order_id)
WHERE lower(o.status) <> 'cancelled'
GROUP BY d;
```

```sql
SELECT count(*) AS days, min(d) AS first_day, max(d) AS last_day FROM daily_sales;
```

```text
┌───────┬────────────┬────────────┐
│ days  │ first_day  │  last_day  │
│ int64 │    date    │    date    │
├───────┼────────────┼────────────┤
│   171 │ 2026-01-04 │ 2026-06-28 │
└───────┴────────────┴────────────┘
```

手元で試すときは、第 5 章の `run_sql.py` に、ビューを作るクエリと、それを使うクエリの名前を並べて渡します。`daily_sales_view` を先に流す必要があります。ビューを作る前に `moving_avg_frames` だけを流すと、`daily_sales` が無いというエラーになります。

```bash
python examples/b05/run_sql.py examples/b06/queries.sql daily_sales_view moving_avg_frames
```

注文のあった日は 171 日分です。1 月 4 日から 6 月 28 日まで 176 日あるので、注文のない日が 5 日あります。この「日が欠けている」ことが、後の移動平均で効いてきます。

## 順位と連番、前後の行

順位を付ける関数は 3 つあります。違いは、同じ値の行（タイ）の扱いにあります。

{{ table("b06-window-functions") }}

目覚まし時計のカテゴリで、3 つを並べてみます。`置き時計(大)` と `ベル式時計(標準)` は、価格が 850 円で同じです。

```sql
SELECT name, price,
       row_number() OVER (ORDER BY price DESC, name) AS rn,
       rank() OVER (ORDER BY price DESC) AS rk,
       dense_rank() OVER (ORDER BY price DESC) AS drk
FROM products
WHERE category = '目覚まし'
ORDER BY price DESC, name;
```

```text
┌────────────────────┬───────┬───────┬───────┬───────┐
│        name        │ price │  rn   │  rk   │  drk  │
│      varchar       │ int64 │ int64 │ int64 │ int64 │
├────────────────────┼───────┼───────┼───────┼───────┤
│ 光る目覚まし(標準) │  4050 │     1 │     1 │     1 │
│ 置き時計(標準)     │  3750 │     2 │     2 │     2 │
│ 光る目覚まし(大)   │  3000 │     3 │     3 │     3 │
│ ベル式時計(大)     │  1650 │     4 │     4 │     4 │
│ ベル式時計(標準)   │   850 │     5 │     5 │     5 │
│ 置き時計(大)       │   850 │     6 │     5 │     5 │
│ 振動リスト(標準)   │   500 │     7 │     7 │     6 │
│ 振動リスト(大)     │   450 │     8 │     8 │     7 │
└────────────────────┴───────┴───────┴───────┴───────┘
```

`rank` は 5 位が 2 つで次が 7 位、`dense_rank` は次が 6 位です。`row_number` はタイを区別して 5 と 6 を付けます。ここでは `ORDER BY price DESC, name` と名前まで並べ条件に足したので、どちらが 5 かが決まります。名前を足さないと、どちらが 5 になるかは実行のたびに変わり得ます。**`row_number` を使うときは、並び順が一意に決まるようにキーを足す**、というのがこの章で最も大事な習慣の 1 つです。

前後の行の値は、`lag`（前の行）と `lead`（後の行）で取ります。前回の注文からの日数です。

```sql
SELECT order_id, ordered_at,
       lag(ordered_at) OVER (ORDER BY ordered_at) AS prev_at,
       date_diff('day',
                 CAST(lag(ordered_at) OVER (ORDER BY ordered_at) AS TIMESTAMP),
                 CAST(ordered_at AS TIMESTAMP)) AS days_since_prev
FROM orders
WHERE customer_id = 122
ORDER BY ordered_at;
```

```text
┌──────────┬─────────────────────┬─────────────────────┬─────────────────┐
│ order_id │     ordered_at      │       prev_at       │ days_since_prev │
│  int64   │       varchar       │       varchar       │      int64      │
├──────────┼─────────────────────┼─────────────────────┼─────────────────┤
│     1983 │ 2026-02-01 00:33:14 │ NULL                │            NULL │
│        1 │ 2026-02-24 13:22:12 │ 2026-02-01 00:33:14 │              23 │
│     2085 │ 2026-03-15 01:31:34 │ 2026-02-24 13:22:12 │              19 │
└──────────┴─────────────────────┴─────────────────────┴─────────────────┘
```

最初の行には前の行が無いので `NULL` です。なお、DuckDB の `date_diff('day', ...)` は、2 つの時刻の間にある日付の境目の数を数えます。経過時間ではなく暦の日の差です。0 時 5 分と、その前日の 23 時 55 分は、10 分しか離れていなくても 1 日の差になります。経過時間を測りたいときは、`date_diff('second', ...)` などで秒を求めて割ります。以下の「日数」は、すべて暦の日の差です。`lag(列, 2, 0)` のように、行数と、無いときの既定値を指定できます。`PARTITION BY customer_id` を足せば、全注文から顧客ごとの間隔を出せます（練習問題 2）。

## 累積和と全体に占める割合

`sum` に `OVER (ORDER BY ...)` を付けると、先頭から現在の行までの累積和になります。

```sql
SELECT d, revenue,
       sum(revenue) OVER (ORDER BY d) AS running_total
FROM daily_sales
ORDER BY d
LIMIT 4;
```

```text
┌────────────┬─────────┬───────────────┐
│     d      │ revenue │ running_total │
│    date    │ int128  │    int128     │
├────────────┼─────────┼───────────────┤
│ 2026-01-04 │    4900 │          4900 │
│ 2026-01-07 │   19400 │         24300 │
│ 2026-01-08 │   10350 │         34650 │
│ 2026-01-09 │   33050 │         67700 │
└────────────┴─────────┴───────────────┘
```

`OVER ()` のように中身を空にすると、全体が 1 つのウィンドウになります。集約の結果を、さらに全体で割る使い方ができます。カテゴリごとの価格合計が、全体のどれだけを占めるかです。

```sql
SELECT category,
       sum(price) AS category_price,
       round(100.0 * sum(price) / sum(sum(price)) OVER (), 1) AS pct
FROM products
GROUP BY category
ORDER BY category_price DESC;
```

```text
┌──────────┬────────────────┬────────┐
│ category │ category_price │  pct   │
│ varchar  │     int128     │ double │
├──────────┼────────────────┼────────┤
│ 飲み物   │          37700 │   25.8 │
│ 朝食     │          37500 │   25.7 │
│ 寝具     │          33100 │   22.7 │
│ 雑貨     │          22500 │   15.4 │
│ 目覚まし │          15100 │   10.3 │
└──────────┴────────────────┴────────┘
```

`sum(sum(price)) OVER ()` は、`GROUP BY` で集計した後の合計を、さらに全体で足しています。PostgreSQL の文書にも、集約関数をウィンドウ関数の引数に入れてよい（逆は不可）とあります。

## フレーム指定：ROWS と RANGE

ウィンドウ関数が各行で使う行の範囲を、フレームと呼びます。省略したときの既定は、DuckDB でも PostgreSQL でも同じです。`ORDER BY` が無ければパーティション全体、`ORDER BY` があれば「先頭から現在の行まで、および現在の行と同じ値の行（ピア）まで」です。累積和が先頭から現在の行までになるのは、この既定のためです。

明示するときは、単位（`ROWS` `RANGE` `GROUPS`）と、始点と終点を書きます。

{{ table("b06-frame-units") }}

7 日間の移動平均を、`ROWS` と `RANGE` の両方で計算します。`days_in_range` は、フレームに実際に入った日数です。

```sql
SELECT d, revenue,
       round(avg(revenue) OVER (ORDER BY d
             ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)) AS avg_rows,
       round(avg(revenue) OVER (ORDER BY d
             RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW)) AS avg_range,
       count(*) OVER (ORDER BY d
             RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW) AS days_in_range
FROM daily_sales
ORDER BY d
LIMIT 10;
```

```text
┌────────────┬─────────┬──────────┬───────────┬───────────────┐
│     d      │ revenue │ avg_rows │ avg_range │ days_in_range │
│    date    │ int128  │  double  │  double   │     int64     │
├────────────┼─────────┼──────────┼───────────┼───────────────┤
│ 2026-01-04 │    4900 │   4900.0 │    4900.0 │             1 │
│ 2026-01-07 │   19400 │  12150.0 │   12150.0 │             2 │
│ 2026-01-08 │   10350 │  11550.0 │   11550.0 │             3 │
│ 2026-01-09 │   33050 │  16925.0 │   16925.0 │             4 │
│ 2026-01-10 │   26150 │  18770.0 │   18770.0 │             5 │
│ 2026-01-11 │   83050 │  29483.0 │   34400.0 │             5 │
│ 2026-01-12 │   39600 │  30929.0 │   35267.0 │             6 │
│ 2026-01-13 │   18050 │  32807.0 │   32807.0 │             7 │
│ 2026-01-14 │   68250 │  39786.0 │   39786.0 │             7 │
│ 2026-01-16 │   94150 │  51757.0 │   54875.0 │             6 │
└────────────┴─────────┴──────────┴───────────┴───────────────┘
  10 rows                                           5 columns
```

1 月 11 日の行を見てください。`ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` は「現在の行と、その前の最大 6 行」です。1 月 11 日の前には 5 行（1 月 4 日、7 日、8 日、9 日、10 日）しかないので、現在の行と合わせて 6 行（8 日間にまたがります）の平均になります。`RANGE BETWEEN INTERVAL 6 DAYS PRECEDING` は「6 日前の日付以降」なので、1 月 5 日から 11 日の 7 日間のうち、売上のある 5 日分の平均です。

ここで平均の分母は、どちらも「売上のある日の数」です。売上のない日を 0 円の日として平均したいなら、日付の表を作って左外部結合し、`coalesce` で 0 を入れてからウィンドウ関数を計算します。この日付の表を作るのに、後述の再帰 CTE を使います。**どちらが正しいかは、レポートの定義で決まります。** 「直近 7 日の平均」と「直近 7 営業日の平均」は別の数字です。定義を先に決めて、それに合う単位を選んでください。

`last_value` の罠も、フレームが原因です。既定のフレームは現在の行で終わるので、`last_value` は現在の行の値を返します。パーティションの最後の値が欲しいなら、フレームを明示します。

```sql
SELECT d, revenue,
       last_value(revenue) OVER (ORDER BY d) AS default_frame,
       last_value(revenue) OVER (
         ORDER BY d
         ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS whole_partition
FROM daily_sales
ORDER BY d
LIMIT 3;
```

```text
┌────────────┬─────────┬───────────────┬─────────────────┐
│     d      │ revenue │ default_frame │ whole_partition │
│    date    │ int128  │    int128     │     int128      │
├────────────┼─────────┼───────────────┼─────────────────┤
│ 2026-01-04 │    4900 │          4900 │           30000 │
│ 2026-01-07 │   19400 │         19400 │           30000 │
│ 2026-01-08 │   10350 │         10350 │           30000 │
└────────────┴─────────┴───────────────┴─────────────────┘
```

`default_frame` の列は、どの行でも自分自身の売上と同じです。パーティションの最後の日の売上（30,000）が欲しければ、`ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` と書きます。

## CTE で段に分ける

CTE（共通テーブル式）は、クエリに名前を付けて `WITH` で先に定義する書き方です。第 5 章のサブクエリを入れ子にすると読みにくくなる場面で、上から下に読める形にできます。キャンセル以外の注文から、顧客ごとの売上の上位 3 人を出します。

```sql
WITH paid AS (
  SELECT * FROM orders WHERE lower(status) <> 'cancelled'
), totals AS (
  SELECT p.customer_id, sum(i.quantity * i.unit_price) AS total
  FROM paid AS p
  INNER JOIN order_items AS i USING (order_id)
  GROUP BY p.customer_id
)
SELECT customer_id, total FROM totals ORDER BY total DESC LIMIT 3;
```

```text
┌─────────────┬────────┐
│ customer_id │ total  │
│    int64    │ int128 │
├─────────────┼────────┤
│         442 │ 257400 │
│         434 │ 187950 │
│         226 │ 183000 │
└─────────────┴────────┘
```

名前を付けた段ごとに、「何をしたか」が読めます。`paid` で絞り、`totals` で集計し、最後に並べます。デバッグするときも、途中の段だけを `SELECT` して中身を確かめられます。

CTE は、読みやすさのための道具です。性能のための道具ではありません。同じ CTE を複数箇所で参照した場合、DuckDB は既定で一度計算して使い回します（結果を保存すること、マテリアライズ）。条件によっては、定義を各参照箇所に展開する場合もあります。`AS MATERIALIZED` / `AS NOT MATERIALIZED` で指定もできますが、DuckDB の文書は、原則として最適化に任せ、明示は必要なときだけにするよう勧めています。PostgreSQL は、複数回参照された CTE は 1 回だけ計算し、`NOT MATERIALIZED` を付けるとこれを避けると文書に書いています。

## 再帰 CTE

`WITH RECURSIVE` は、自分自身を参照できる CTE です。形は決まっています。最初の行を作る部分、`UNION ALL`、自分を参照して次の行を作る部分の 3 つです。次の行が 0 件になった時点で終わります。

1 月 1 日から 1 月 7 日までの日付を、再帰で作ります。

```sql
WITH RECURSIVE days(d) AS (
  SELECT DATE '2026-01-01'
  UNION ALL
  SELECT d + 1 FROM days WHERE d < DATE '2026-01-07'
)
SELECT d FROM days;
```

```text
┌────────────┐
│     d      │
│    date    │
├────────────┤
│ 2026-01-01 │
│ 2026-01-02 │
│ 2026-01-03 │
│ 2026-01-04 │
│ 2026-01-05 │
│ 2026-01-06 │
│ 2026-01-07 │
└────────────┘
```

終了条件（ここでは `WHERE d < DATE '2026-01-07'`）を書き忘れると、無限に続きます。DuckDB の文書も、終わるように書く必要があると注意しています。実務で日付を並べるだけなら、`generate_series` のような専用の関数のほうが短く書けますが、再帰 CTE はもう 1 つの用途、階層をたどるために必要です。

さきほどの「日が欠けている」問題を、日付の表を作って直します。注文のない日が 0 円で入ります。

```sql
WITH RECURSIVE calendar(d) AS (
  SELECT DATE '2026-01-04'
  UNION ALL
  SELECT d + 1 FROM calendar WHERE d < DATE '2026-01-12'
)
SELECT c.d, coalesce(s.revenue, 0) AS revenue
FROM calendar AS c
LEFT JOIN daily_sales AS s ON s.d = c.d
ORDER BY c.d;
```

```text
┌────────────┬─────────┐
│     d      │ revenue │
│    date    │ int128  │
├────────────┼─────────┤
│ 2026-01-04 │    4900 │
│ 2026-01-05 │       0 │
│ 2026-01-06 │       0 │
│ 2026-01-07 │   19400 │
│ 2026-01-08 │   10350 │
│ 2026-01-09 │   33050 │
│ 2026-01-10 │   26150 │
│ 2026-01-11 │   83050 │
│ 2026-01-12 │   39600 │
└────────────┴─────────┘
```

1 月 5 日と 6 日が 0 円で出ています。このようにカレンダーから `LEFT JOIN` する形は、日次の集計を作るときの定番です。

もう 1 つの用途が階層です。上司と部下の関係のように、「誰の下にいるか」が行ごとに持たれている表を、根からたどって深さを付けます。

```sql
WITH RECURSIVE staff(id, name, boss_id) AS (
  VALUES (1, '店長', NULL), (2, '発送係長', 1), (3, '発送担当', 2), (4, '問い合わせ担当', 1)
), chain(id, name, depth) AS (
  SELECT id, name, 0 FROM staff WHERE boss_id IS NULL
  UNION ALL
  SELECT s.id, s.name, c.depth + 1
  FROM staff AS s
  INNER JOIN chain AS c ON s.boss_id = c.id
)
SELECT * FROM chain ORDER BY depth, id;
```

```text
┌───────┬────────────────┬───────┐
│  id   │      name      │ depth │
│ int32 │    varchar     │ int32 │
├───────┼────────────────┼───────┤
│     1 │ 店長           │     0 │
│     2 │ 発送係長       │     1 │
│     4 │ 問い合わせ担当 │     1 │
│     3 │ 発送担当       │     2 │
└───────┴────────────────┴───────┘
```

店長が深さ 0、その部下が 1、さらにその部下が 2 です。サイクル（A の上司が B で B の上司が A）がある表は、`UNION ALL` だと終わらなくなります。PostgreSQL の文書は、`UNION` で重複行を捨てるか、すでにたどった値を配列に持って確かめる方法を挙げています。

## 重複排除と「各グループの最新 1 行」

データエンジニアリングで、最もよく書く SQL のうちの 1 つです。ねぼすけ商店の行動ログには、同じ `event_id` が 2 回届いているものがありました。

```sql
SELECT count(*) AS raw_rows, count(DISTINCT event_id) AS distinct_ids FROM events;
```

```text
┌──────────┬──────────────┐
│ raw_rows │ distinct_ids │
│  int64   │    int64     │
├──────────┼──────────────┤
│     4040 │         4000 │
└──────────┴──────────────┘
```

4,040 行のうち、一意の ID は 4,000 です。重複を除くには、`event_id` ごとに番号を付けて、1 番だけ残します。どの行を残すかは `ORDER BY` で決めます。ここでは最初に届いたものを残します。

```sql
SELECT count(*) AS n
FROM (
  SELECT *,
         row_number() OVER (PARTITION BY event_id ORDER BY received_at, event_id) AS rn
  FROM events
) AS t
WHERE rn = 1;
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│  4000 │
└───────┘
```

「顧客ごとの最新の注文」も、同じ形です。番号を降順で付けて、1 番を残します。DuckDB の `QUALIFY` を使うと、サブクエリで包まずに、ウィンドウ関数の結果で行を絞れます。`QUALIFY` は、ウィンドウ関数が計算された後、`ORDER BY` の前に評価される句です。

```sql
SELECT customer_id, order_id, ordered_at
FROM orders
QUALIFY row_number() OVER (
  PARTITION BY customer_id ORDER BY ordered_at DESC, order_id DESC) = 1
ORDER BY customer_id
LIMIT 3;
```

```text
┌─────────────┬──────────┬─────────────────────┐
│ customer_id │ order_id │     ordered_at      │
│    int64    │  int64   │       varchar       │
├─────────────┼──────────┼─────────────────────┤
│           1 │     1926 │ 2026-06-08 02:48:54 │
│           2 │     1989 │ 2026-06-02 20:01:53 │
│           3 │     1213 │ 2026-06-24 11:32:03 │
└─────────────┴──────────┴─────────────────────┘
```

`ORDER BY ordered_at DESC, order_id DESC` と、`order_id` まで並びに足しているのは、同じ時刻の注文があっても結果が一意になるようにするためです。

{{ table("b06-dedup-methods") }}

PostgreSQL の `DISTINCT ON` は、DuckDB でも使えます。グループごとに、`ORDER BY` の先頭の行を 1 つ残します。

```sql
SELECT DISTINCT ON (customer_id) customer_id, order_id, ordered_at
FROM orders
ORDER BY customer_id, ordered_at DESC, order_id DESC
LIMIT 3;
```

```text
┌─────────────┬──────────┬─────────────────────┐
│ customer_id │ order_id │     ordered_at      │
│    int64    │  int64   │       varchar       │
├─────────────┼──────────┼─────────────────────┤
│           1 │     1926 │ 2026-06-08 02:48:54 │
│           2 │     1989 │ 2026-06-02 20:01:53 │
│           3 │     1213 │ 2026-06-24 11:32:03 │
└─────────────┴──────────┴─────────────────────┘
```

DuckDB の `arg_max(値, 並べる列)` は、並べる列が最大の行の値を取り出します。1 列だけが欲しいなら、短く書けます。

```sql
SELECT customer_id, arg_max(order_id, ordered_at) AS order_id
FROM orders
GROUP BY customer_id
ORDER BY customer_id
LIMIT 3;
```

```text
┌─────────────┬──────────┐
│ customer_id │ order_id │
│    int64    │  int64   │
├─────────────┼──────────┤
│           1 │     1926 │
│           2 │     1989 │
│           3 │     1213 │
└─────────────┴──────────┘
```

三者は同じ結果を返します（テストでも確かめています）。どれを選ぶかは、動かす製品と、取り出したい列の数で決めます。行全体が欲しければ `row_number` か `DISTINCT ON`、移植性が必要なら `row_number` のサブクエリ形です。

顧客の二重登録も、同じ方法で 1 行に寄せられます。同じメールアドレスで登録が複数あるときは、`customer_id` の小さい（古い）行を正とします。

```sql
SELECT count(*) AS n
FROM (
  SELECT *
  FROM customers
  WHERE email IS NOT NULL
  QUALIFY row_number() OVER (PARTITION BY email ORDER BY customer_id) = 1
) AS t;
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│   480 │
└───────┘
```

505 行から、メールのある 485 行を対象にして 480 行が残ります。メールが `NULL` の行は別の問題（同一人物かの判断材料がない）なので、この例では除いています。どのキーで同一と見なし、どの行を正とするかは、SQL ではなく業務の決めごとです。必ず決めた人（と日付）を残してください。

## セッション化

行動ログの分析では、「ひとまとまりの訪問」（セッション）を作る場面が頻繁にあります。定義の定番は「前のイベントから一定時間が空いたら、新しいセッション」です。3 つの手順で書けます。

1. `lag` で前のイベントの時刻を取り、間隔が閾値を超えたら 1、そうでなければ 0 の印を付ける。
2. 印を累積和して、セッション番号にする。
3. （顧客, セッション番号）で集計する。

30 分を閾値にして、小さなデータで動きを確かめます。顧客 1 は 9 時台に 3 回、14 時台に 2 回です。

```sql
WITH e(customer_id, t) AS (
  VALUES (1, TIMESTAMP '2026-05-01 09:00:00'),
         (1, TIMESTAMP '2026-05-01 09:10:00'),
         (1, TIMESTAMP '2026-05-01 09:25:00'),
         (1, TIMESTAMP '2026-05-01 14:00:00'),
         (1, TIMESTAMP '2026-05-01 14:20:00'),
         (2, TIMESTAMP '2026-05-01 09:05:00')
), flagged AS (
  SELECT customer_id, t,
         CASE WHEN t - lag(t) OVER (PARTITION BY customer_id ORDER BY t)
                   > INTERVAL '30 minutes' THEN 1 ELSE 0 END AS is_new
  FROM e
)
SELECT customer_id, t,
       sum(is_new) OVER (PARTITION BY customer_id ORDER BY t) + 1 AS session_no
FROM flagged
ORDER BY customer_id, t;
```

```text
┌─────────────┬─────────────────────┬────────────┐
│ customer_id │          t          │ session_no │
│    int32    │      timestamp      │   int128   │
├─────────────┼─────────────────────┼────────────┤
│           1 │ 2026-05-01 09:00:00 │          1 │
│           1 │ 2026-05-01 09:10:00 │          1 │
│           1 │ 2026-05-01 09:25:00 │          1 │
│           1 │ 2026-05-01 14:00:00 │          2 │
│           1 │ 2026-05-01 14:20:00 │          2 │
│           2 │ 2026-05-01 09:05:00 │          1 │
└─────────────┴─────────────────────┴────────────┘
```

顧客 1 は 9:25 から 14:00 まで 4 時間以上空いているので、そこで新しいセッションになります。顧客ごとに番号が 1 から振り直されています。

実際の行動ログは 180 日分で、顧客 1 人あたり 8 件ほどしかなく、30 分以内に連続することはほとんどありません。そこで閾値を 7 日にして、全体で数えます。

```sql
WITH e AS (
  SELECT DISTINCT customer_id, CAST(event_time AS TIMESTAMP) AS t, event_id FROM events
), flagged AS (
  SELECT customer_id, t,
         CASE WHEN t - lag(t) OVER (PARTITION BY customer_id ORDER BY t)
                   > INTERVAL '7 days' THEN 1 ELSE 0 END AS is_new
  FROM e
), numbered AS (
  SELECT customer_id,
         sum(is_new) OVER (PARTITION BY customer_id ORDER BY t) + 1 AS session_no
  FROM flagged
)
SELECT count(*) AS sessions
FROM (SELECT DISTINCT customer_id, session_no FROM numbered) AS s;
```

```text
┌──────────┐
│ sessions │
│  int64   │
├──────────┤
│     2930 │
└──────────┘
```

閾値は分析の定義です。30 分なのか、サイトの種類によって変えるのかは、決めた理由と一緒に残します。ここでは発生時刻の `event_time` で並べています。遅れて届いた行（`received_at` が遅い行）を含めるかどうかでも、結果は変わります。

## ピボット

縦持ち（1 行が 1 件の事実）を横持ち（列が値の種類）に直すのがピボットです。月ごと・状態ごとの注文数を、状態を列にして並べます。どの製品でも使える形は `sum(CASE WHEN 条件 THEN 1 ELSE 0 END)` です。次のクエリは `count(*) FILTER (WHERE 条件)` で書いています。`FILTER` は標準 SQL ですが、対応していない製品があるので、その場合は `CASE` に書き換えます。

```sql
SELECT strftime(CAST(ordered_at AS TIMESTAMP), '%Y-%m') AS month,
       count(*) FILTER (WHERE lower(status) = 'placed') AS placed,
       count(*) FILTER (WHERE lower(status) = 'shipped') AS shipped,
       count(*) FILTER (WHERE lower(status) = 'delivered') AS delivered,
       count(*) FILTER (WHERE lower(status) = 'cancelled') AS cancelled
FROM orders
GROUP BY month
ORDER BY month;
```

```text
┌─────────┬────────┬─────────┬───────────┬───────────┐
│  month  │ placed │ shipped │ delivered │ cancelled │
│ varchar │ int64  │  int64  │   int64   │   int64   │
├─────────┼────────┼─────────┼───────────┼───────────┤
│ 2026-01 │     28 │      64 │        38 │        33 │
│ 2026-02 │     77 │     175 │       153 │        92 │
│ 2026-03 │    140 │     266 │       274 │       140 │
│ 2026-04 │    157 │     262 │       294 │       134 │
│ 2026-05 │     79 │     172 │       166 │       101 │
│ 2026-06 │     30 │      45 │        52 │        28 │
└─────────┴────────┴─────────┴───────────┴───────────┘
```

DuckDB には、専用の `PIVOT` 文があり、列を自動で作ります。

```sql
PIVOT (
  SELECT strftime(CAST(ordered_at AS TIMESTAMP), '%Y-%m') AS month,
         lower(status) AS status
  FROM orders
)
ON status
USING count(*)
GROUP BY month
ORDER BY month;
```

```text
┌─────────┬───────────┬───────────┬────────┬─────────┐
│  month  │ cancelled │ delivered │ placed │ shipped │
│ varchar │   int64   │   int64   │ int64  │  int64  │
├─────────┼───────────┼───────────┼────────┼─────────┤
│ 2026-01 │        33 │        38 │     28 │      64 │
│ 2026-02 │        92 │       153 │     77 │     175 │
│ 2026-03 │       140 │       274 │    140 │     266 │
│ 2026-04 │       134 │       294 │    157 │     262 │
│ 2026-05 │       101 │       166 │     79 │     172 │
│ 2026-06 │        28 │        52 │     30 │      45 │
└─────────┴───────────┴───────────┴────────┴─────────┘
```

結果は同じです（列の順番だけ、アルファベット順になります）。ただし、どちらの方法でも列は固定です。ステータスが増えたとき、`CASE` 版は新しい状態の注文が集計から静かに落ち、`PIVOT` 版は下流の表のスキーマが予告なく変わります。パイプラインに入れるなら、`CASE` 版で列を明示し、想定外の値が来たら検知する（第 13 章）ほうが安全です。見せるための表なら、BI ツールのピボットに任せるのが普通です。

## 実行計画を読む

同じ結果を返す SQL でも、データベースは中でいくつもの計算方法から 1 つを選びます。その選択が実行計画で、`EXPLAIN` を付けて見ます。`EXPLAIN` は実行せずに計画だけを返し、`EXPLAIN ANALYZE` は実行して、実際の行数と時間を足して返します。PostgreSQL の文書にあるとおり、`ANALYZE` は文を本当に実行します。`INSERT` や `DELETE` に付けるとデータが変わるので、トランザクションに入れて取り消すか、`SELECT` だけに使います。

月間の都道府県別売上を、3 つの表を結合して出すクエリで見ます。

```sql
EXPLAIN
SELECT c.prefecture, sum(i.quantity * i.unit_price) AS revenue
FROM orders AS o
INNER JOIN customers AS c USING (customer_id)
INNER JOIN order_items AS i USING (order_id)
WHERE o.ordered_at >= '2026-03-01'
GROUP BY c.prefecture;
```

```text
╭─ Projection ─────────────────────────────╮
│ Projections:                             │
│ __internal_decompress_string(#0), #1     │
│ ~11 rows                                 │
╰─────────────────────┬────────────────────╯
╭─ Hash Group By ─────┴────────────────────╮
│ Groups: #0                               │
│ Aggregates: sum(#1)                      │
│ ~11 rows                                 │
╰─────────────────────┬────────────────────╯
╭─ Projection ────────┴────────────────────╮
│ Projections: prefecture,                 │
│              quantity * unit_price       │
│ ~840 rows                                │
╰─────────────────────┬────────────────────╯
╭─ Projection ────────┴────────────────────╮
│ Projections:                             │
│ #0, #1,                                  │
│ __internal_compress_string_uhugeint(#2)  │
│ ~840 rows                                │
╰─────────────────────┬────────────────────╯
╭─ Hash Join ─────────┴────────────────────╮
│ Join Type: INNER                         │
│ Conditions: order_id = order_id          │
│ ~840 rows                                │
╰─────────────────────┬────────────────────╯
                      ├───────────────────────────────────────────╮
╭─ Seq Scan ──────────┴────────────────────╮  ╭─ Hash Join ───────┴───────────────────╮
│ Table: shop.main.order_items             │  │ Join Type: INNER                      │
│ Type: Sequential Scan                    │  │ Conditions: customer_id = customer_id │
│ Projections: order_id, quantity,         │  │ ~542 rows                             │
│              unit_price                  │  ╰───────────────────┬───────────────────╯
│ ~7,469 rows                              │                      ├─────────────────────────────────────────╮
╰──────────────────────────────────────────╯  ╭─ Seq Scan ────────┴───────────────────╮  ╭─ Seq Scan ───────┴──────────────────╮
                                              │ Table: shop.main.customers            │  │ Table: shop.main.orders             │
                                              │ Type: Sequential Scan                 │  │ Type: Sequential Scan               │
                                              │ Projections: customer_id, prefecture  │  │ Projections: customer_id, order_id  │
                                              │ ~505 rows                             │  │ Filters: ordered_at >= '2026-03-01' │
                                              ╰───────────────────────────────────────╯  │ ~600 rows                           │
                                                                                         ╰─────────────────────────────────────╯
```

読み方の基本は、**下から上に読む**ことです。木の葉に当たる一番下が表の読み込み（Seq Scan）で、そこから結合、集計へと上に向かって進みます。この計画で、見てほしい場所は次の 4 つです。

1. 読み込みの `Filters: ordered_at >= '2026-03-01'`。`WHERE` の条件が、結合の前の読み込みの段階で適用されています。第 5 章の最後で触れた、実行エンジンが評価の順序を入れ替えて速くする例です。
2. `Projections`。`orders` から `customer_id` と `order_id` の 2 列だけを読んでいます。列指向のデータベースは、必要な列だけを読めます。
3. `Hash Join`。片方の表からハッシュ表を作り、もう片方を引いて結合します。結合の条件が書かれています。
4. `~600 rows` のような `~` の付いた数字は、**見積もり**です。

次に `EXPLAIN ANALYZE` で、見積もりと実際を比べます（時間は実行のたびに変わります）。

```sql
EXPLAIN ANALYZE
SELECT c.prefecture, sum(i.quantity * i.unit_price) AS revenue
FROM orders AS o
INNER JOIN customers AS c USING (customer_id)
INNER JOIN order_items AS i USING (order_id)
WHERE o.ordered_at >= '2026-03-01'
GROUP BY c.prefecture;
```

```text
╭─ Summary ───────────╮
│ Total Time: 0.0017s │
╰─────────────────────╯
╭─ Projection ─────────────────────────────╮
│ Projections:                             │
│ __internal_decompress_string(#0), #1     │
│ 10 rows                              0µs │
╰─────────────────────┬────────────────────╯
╭─ Hash Group By ─────┴────────────────────╮
│ Groups: #0                               │
│ Aggregates: sum(#1)                      │
│ 10 rows                              0µs │
╰─────────────────────┒┎───────────────────╯
╭─ Projection ────────┚┖───────────────────╮
│ Projections: prefecture,                 │
│              quantity * unit_price       │
│ 5,812 rows                           0µs │
╰─────────────────────┒┎───────────────────╯
╭─ Projection ────────┚┖───────────────────╮
│ Projections:                             │
│ #0, #1,                                  │
│ __internal_compress_string_uhugeint(#2)  │
│ 5,812 rows                           0µs │
╰─────────────────────┒┎───────────────────╯
╭─ Hash Join ─────────┚┖───────────────────╮
│ Join Type: INNER                         │
│ Conditions: order_id = order_id          │
│ 5,812 rows                           0µs │
╰─────────────────────┰┰───────────────────╯
                      ┃┠───────────────────────────────────────────────────────┒
╭─ Table Scan ────────┚┖───────────────────╮  ╭─ Hash Join ────────────────────┸────────────────────────────────╮
│ Table: shop.main.order_items             │  │ Join Type: INNER                                                │
│ Type: Sequential Scan                    │  │ Conditions: customer_id = customer_id                           │
│ Projections: order_id, quantity,         │  │ 2,340 rows                                                  0µs │
│              unit_price                  │  ╰────────────────────────────────┬────────────────────────────────╯
│ Dynamic Filters:                         │                                   ├──────────────────────────────────────────────────────┒
│ optional: order_id IN PRF(order_id)      │  ╭─ Table Scan ───────────────────┴────────────────────────────────╮  ╭─ Table Scan ─────┸──────────────────╮
│ Row Groups Scanned: 1 / 1                │  │ Table: shop.main.customers                                      │  │ Table: shop.main.orders             │
│ 5,812 rows                           0µs │  │ Type: Sequential Scan                                           │  │ Type: Sequential Scan               │
╰──────────────────────────────────────────╯  │ Projections: customer_id, prefecture                            │  │ Projections: customer_id, order_id  │
                                              │ Dynamic Filters:                                                │  │ Filters: ordered_at >= '2026-03-01' │
                                              │ optional: (customer_id >= 1) AND optional: (customer_id <= 505) │  │ Row Groups Scanned: 1 / 1           │
                                              │ Row Groups Scanned: 1 / 1                                       │  │ 2,340 rows                      0µs │
                                              │ 505 rows                                                    0µs │  ╰─────────────────────────────────────╯
                                              ╰─────────────────────────────────────────────────────────────────╯
```

`orders` の読み込みは、見積もり `~600` 行に対して実際は 2,340 行で、結合後も見積もり `~840` 行に対し実際は 5,812 行でした。ここでは約 4 倍と約 7 倍のずれです。ずれが大きいノードが、遅いクエリを調べる手がかりです。見積もりの元になる統計がずれていると、データベースは間違った結合の順や方法を選びます。このデータは小さいので、ずれても実害はありません。大きなデータでは、実際の行数が見積もりの 10 倍や 100 倍になると、結合の方法や順序が不適切になって、時間が大きく変わります。

読むときの手順を決めておくと、迷いません。

1. 一番行数が多い（あるいは時間のかかる）ノードを探す。
2. そのノードの見積もりと実際の差を見る。
3. 読み込みなら、条件が読み込みの段階で適用されているか、必要な列だけを読んでいるかを見る。
4. 結合なら、行数が爆発していないか（第 5 章のファンアウト）を見る。

PostgreSQL の `EXPLAIN` は、`cost=0.00..43752.00 rows=1 width=41` のような形です。`cost` は計算量の目安（時間ではありません）、`rows` は見積もり行数です。`ANALYZE` を付けると実測が加わるのは DuckDB と同じです。

## インデックスは、行指向と列指向で効き方が違う

インデックス（英語の index）は、ある列の値から行を素早く探すための補助的なデータ構造です。本の巻末にある用語の一覧と同じ考え方で、探す手間を減らす代わりに、作る手間と置く場所が要ります。

手元で試すには、`examples/b06/run_index.py` を使います。DuckDB の実験はメモリ上で動きます。PostgreSQL の実験は、README の手順で `docker compose up -d --wait` を済ませたうえで、接続先を環境変数 `PG_DSN` で渡します（接続先は README のとおり `postgresql://deb:deb@localhost:5432/deb`）。

```bash
python examples/b06/run_index.py duckdb
PG_DSN=postgresql://deb:deb@localhost:5432/deb python examples/b06/run_index.py postgres
```

まず PostgreSQL（バージョン 16）で、200 万行の一時テーブルを作り、`id` で 1 行を探します。一時テーブルは並列実行の対象外で、計画が読みやすいためです。

```sql
CREATE TEMP TABLE big AS
SELECT g AS id, g % 1000 AS grp, md5(g::text) AS h
FROM generate_series(1, 2000000) AS g;
```

```sql
ANALYZE big;
```

インデックスなしの計画です。

```sql
EXPLAIN SELECT * FROM big WHERE id = 123456;
```

```text
Seq Scan on big  (cost=0.00..43752.00 rows=1 width=41)
  Filter: (id = 123456)
```

全件を順に読む `Seq Scan` です。`id` のインデックスを作ってから、同じクエリの計画を見ます。

```sql
CREATE INDEX big_id ON big (id);
```

```sql
EXPLAIN SELECT * FROM big WHERE id = 123456;
```

```text
Index Scan using big_id on big  (cost=0.43..8.45 rows=1 width=41)
  Index Cond: (id = 123456)
```

`Index Scan` に変わり、見積もりコストが 43752 から 8.45 に下がりました（値は実行のたびに多少変わります）。ただし、インデックスは万能ではありません。`grp` の値は 0 から 999 まで均等に散らばっています。`grp < 900` は全体の約 9 割の行に当たります。インデックスを作っても、計画は `Seq Scan` のままです。

```sql
CREATE INDEX big_grp ON big (grp);
```

```sql
EXPLAIN SELECT * FROM big WHERE grp < 900;
```

```text
Seq Scan on big  (cost=0.00..43752.00 rows=1792439 width=41)
  Filter: (grp < 900)
```

条件に合う行が全体の約 0.1%（`grp = 7`）なら、インデックスが使われます。

```sql
EXPLAIN SELECT * FROM big WHERE grp = 7;
```

```text
Bitmap Heap Scan on big  (cost=23.87..5813.83 rows=1992 width=41)
  Recheck Cond: (grp = 7)
  ->  Bitmap Index Scan on big_grp  (cost=0.00..23.37 rows=1992 width=0)
        Index Cond: (grp = 7)
```

行の多くを読むなら、インデックスで 1 行ずつ探すよりも、全部を順に読むほうが速いからです。ここでは、`Bitmap Index Scan` で該当する場所を先に調べてから、まとめて読む方式が選ばれています。PostgreSQL の文書も、インデックスは表の更新のたびに同期が必要で、書き込みの負担が増えるので、ほとんど（またはまったく）使われないインデックスは削除するよう勧めています。

PostgreSQL のインデックスを使うときの注意を、実務で迷う順にまとめます。

- 結合の条件に使う列（外部キーの列を含む）にインデックスが要るかを確かめます。外部キーの参照先の列には必ずインデックスがありますが、参照する側の列には自動では作られません（PostgreSQL の文書は、参照する側の行を探す `DELETE` や `UPDATE` が遅くなるため、インデックスを付けることをよく勧めています）。
- 複数の列をまとめたインデックスは、左の列から順に効きます。`(customer_id, ordered_at)` は `customer_id` だけの条件にも使えますが、`ordered_at` だけの条件には効きにくくなります。条件に必ず入る列、等しいかを比べる列を左に置きます。
- 列を関数で包むと、その列のインデックスは使われません。`WHERE lower(email) = '...'` には、`lower(email)` に対する式のインデックスが要ります。
- 今回は一時テーブルなので、`ANALYZE` を手で流しました。autovacuum（自動の掃除・統計更新）は一時テーブルに届かないため、手で統計を更新しないと、計画が悪くなります。普通のテーブルでは自動で更新されます。

どれも PostgreSQL の文書にある内容です（参考文献）。

次に、DuckDB で同じ実験をします。DuckDB は列指向で、列ごとに値を並べて保存し、行のまとまり（行グループ）ごとに最小値と最大値（ゾーンマップ）を自動で持ちます。ここでも 200 万行を、`id` がばらばらの順に並ぶように作ります。

```sql
CREATE TABLE big AS
SELECT range AS id, range % 1000 AS grp, md5(CAST(range AS VARCHAR)) AS h
FROM range(2000000)
ORDER BY h;
```

```text
┌─────────┐
│  Count  │
│  int64  │
├─────────┤
│ 2000000 │
└─────────┘
```

インデックスなしで `id` を探します。

```sql
EXPLAIN ANALYZE SELECT * FROM big WHERE id = 123456;
```

```text
╭─ Summary ───────────╮
│ Total Time: 0.0009s │
╰─────────────────────╯
╭─ Table Scan ────────────────╮
│ Table: memory.main.big      │
│ Type: Sequential Scan       │
│ Projections: id, grp, h     │
│ Filters: id = 123456        │
│ Row Groups Scanned: 17 / 17 │
│ 1 row                   0µs │
╰─────────────────────────────╯
```

`Row Groups Scanned: 17 / 17` は、17 個ある行グループをすべて読んだことを示します。`id` がばらばらに並んでいると、どの行グループにも最小値と最大値の範囲に目的の値が入るため、読み飛ばせません。ART（Adaptive Radix Tree）インデックスを作ります。

```sql
CREATE INDEX big_id ON big (id);
```

```sql
EXPLAIN ANALYZE SELECT * FROM big WHERE id = 123456;
```

```text
╭─ Summary ───────────╮
│ Total Time: 0.0005s │
╰─────────────────────╯
╭─ Table Scan ───────────────╮
│ Table: memory.main.big     │
│ Type: Index Scan           │
│ Projections: id, grp, h    │
│ Filters: id = 123456       │
│ Row Groups Scanned: 0 / 17 │
│ 1 row                  0µs │
╰────────────────────────────╯
```

今度は `Type: Index Scan` で、`Row Groups Scanned: 0 / 17` です。ところが `EXPLAIN` だけでは、この環境では次のように `Sequential Scan` と出ます。

```sql
EXPLAIN SELECT * FROM big WHERE id = 123456;
```

```text
╭─ Seq Scan ─────────────╮
│ Table: memory.main.big │
│ Type: Sequential Scan  │
│ Projections: id, grp,  │
│              h         │
│ Filters: id = 123456   │
│ ~1 row                 │
╰────────────────────────╯
```

DuckDB 2.0.0 で試すと、`EXPLAIN` だけでは、インデックスを作った後でも `Sequential Scan` と表示されます。一方 `EXPLAIN ANALYZE` では `Index Scan` になっていました。計画の表示と実行時の挙動が食い違うことがあるので、**インデックスが使われたかを確かめるときは、`EXPLAIN ANALYZE` で見ます。** 次に、`id` の順に並べて保存した表を試します。

```sql
CREATE TABLE big_sorted AS SELECT * FROM big ORDER BY id;
```

```text
┌─────────┐
│  Count  │
│  int64  │
├─────────┤
│ 2000000 │
└─────────┘
```

```sql
EXPLAIN ANALYZE SELECT * FROM big_sorted WHERE id = 123456;
```

```text
╭─ Summary ───────────╮
│ Total Time: 0.0005s │
╰─────────────────────╯
╭─ Table Scan ──────────────────╮
│ Table: memory.main.big_sorted │
│ Type: Sequential Scan         │
│ Projections: id, grp, h       │
│ Filters: id = 123456          │
│ Row Groups Scanned: 1 / 17    │
│ 1 row                     0µs │
╰───────────────────────────────╯
```

`Row Groups Scanned: 1 / 17` です。DuckDB の文書も、データが並んでいるほどゾーンマップが効くと説明しています。時刻の順に入れる時系列のデータのように、並んだ列では、この仕組みで足りることが多くなります。DuckDB の文書は、ART インデックスについて、主キーなどの制約の確認と、ごく少数の行を探す場合に使うもので、結合・集計・並べ替えの性能には影響しないと書いています。インデックスが使われる目安の行数は、既定では「2,048 行と、表の行数の 0.1% の大きいほう」で、`index_scan_percentage` と `index_scan_max_count` の設定で変えられます。

もう 1 つの列指向の特徴は、読む列の数です。

```sql
EXPLAIN SELECT avg(id) FROM big WHERE grp = 7;
```

```text
╭─ Projection ────────────────────────────────╮
│ Projections:                                │
│ "/"(CAST(#0 AS DOUBLE), CAST(#1 AS DOUBLE)) │
│ ~1 row                                      │
╰──────────────────────┬──────────────────────╯
╭─ Ungrouped Aggregate ┴──────────────────────╮
│ Aggregates: sum_no_overflow(#0),            │
│             count_star()                    │
│ ~1 row                                      │
╰──────────────────────┬──────────────────────╯
╭─ Projection ─────────┴──────────────────────╮
│ Projections: id                             │
│ ~1,602 rows                                 │
╰──────────────────────┬──────────────────────╯
╭─ Seq Scan ───────────┴──────────────────────╮
│ Table: memory.main.big                      │
│ Type: Sequential Scan                       │
│ Projections: id                             │
│ Filters: grp = 7                            │
│ ~1,602 rows                                 │
╰─────────────────────────────────────────────╯
```

`h`（長い文字列の列）は、計画のどこにもありません。`avg(id)` と `grp = 7` の条件に要る 2 列だけを読み、残りの列は読みません。行指向の DB は、行全体を 1 つの塊として置くのが基本なので、1 列しか要らない集計でも、行を丸ごと読む場面が多くなります。

{{ table("b06-index-compare") }}

指針をまとめます。業務システムのように、主キーで 1 件を取る・更新する処理が中心なら、インデックスが要ります（第 7 章）。分析のように、多数の行を読んで集計するなら、インデックスより「必要な列だけを読む」「並べて置いて読み飛ばす」「パーティションに分ける」（第 11 章）が効きます。

## 読みやすい SQL を書く

- CTE の名前は、中身を表す名前にする（`paid` `totals`）。`t1` `t2` は避ける。
- 1 つの CTE は 1 つの目的に絞る。絞る、結合する、集計する、を別の段にする。
- ウィンドウ関数の `ORDER BY` は、同じ値が残らないようにキーを足す。
- 閾値や定義（30 分、キャンセルを除く）は、クエリの先頭の CTE かコメントに書く。数字が埋もれる。

## よくある失敗

- `row_number` の `ORDER BY` が一意でなく、実行のたびに残る行が変わる。
- `last_value` が現在の行を返す。フレームを明示する。
- 日付の欠けを考えずに `ROWS` で移動平均を取り、7 日より長いフレームになる。`RANGE` か、カレンダーを結合する。
- 再帰 CTE に終了条件を書かず、終わらない。
- 重複排除で、どの行を残すかを決めずに `DISTINCT` を使う。
- `EXPLAIN` の `~` の数字を実測と取り違える。`EXPLAIN ANALYZE` で確かめる。
- インデックスを、とりあえず全部の列に作る。書き込みが遅くなる。
- 列指向の DB に、行指向の癖で「インデックスを足せば速くなる」と考える。まず読む列と順序を見る。

## まとめ

- ウィンドウ関数は、行を潰さずに計算結果を足します。`PARTITION BY` で分け、`ORDER BY` で並べ、フレームで範囲を決めます。
- `row_number` のキーは一意にします。`rank` / `dense_rank` はタイの扱いが違います。
- 移動平均では、`ROWS`（行数）と `RANGE`（値の距離）を区別し、欠けた日の扱いを定義から決めます。
- CTE は読みやすさの道具で、再帰 CTE は連番と階層に使います。
- 「各グループの最新 1 行」と重複排除は、`row_number`・`QUALIFY`・`DISTINCT ON`・`arg_max` から選びます。
- `EXPLAIN ANALYZE` は下から読み、見積もりと実際の行数の差と、読み込みの条件と列を見ます。
- インデックスは、行指向の DB では点検索の道具、列指向の DB では例外的な道具です。分析 DB では並べ方と読む列を先に考えます。

## 練習問題

問 1. 商品のカテゴリごとに、価格の高い上位 2 商品を出してください。価格が同じ場合は商品名の順にします。

??? note "解答例"
    ```sql
    SELECT category, name, price
    FROM (
      SELECT category, name, price,
             row_number() OVER (PARTITION BY category ORDER BY price DESC, name) AS rn
      FROM products
    ) AS t
    WHERE rn <= 2
    ORDER BY category, price DESC, name;
    ```

    カテゴリ 5 つ × 2 商品で 10 行が返ります。`rank` を使うと、同じ価格の商品が 3 つ以上あるカテゴリでは 3 行以上が返ります。「ちょうど 2 件」が欲しいのか、「上位 2 位まで」が欲しいのかで、`row_number` と `rank` を選び分けます。

問 2. 同じ顧客の連続する 2 回の注文の間隔（日数）が、全体で平均何日かを出してください。間隔の件数も合わせて出します。

??? note "解答例"
    ```sql
    WITH gaps AS (
      SELECT date_diff('day',
               CAST(lag(ordered_at) OVER (PARTITION BY customer_id ORDER BY ordered_at) AS TIMESTAMP),
               CAST(ordered_at AS TIMESTAMP)) AS days
      FROM orders
    )
    SELECT count(days) AS gaps, round(avg(days), 1) AS avg_days FROM gaps;
    ```

    間隔は 2,496 件で、平均は 12.0 日です（暦の日の差の平均です）。件数は、注文 3,000 件から、顧客ごとの最初の注文（前の注文がなく `lag` が `NULL`）の 504 件を引いた数と一致します。`avg` は `NULL` を無視するので、最初の注文は平均に入りません。

問 3. 注文が 2 回以上ある顧客の数を、ウィンドウ関数で求めてください。

??? note "解答例"
    ```sql
    SELECT count(*) AS customers_with_2plus_orders
    FROM (
      SELECT customer_id
      FROM orders
      QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY ordered_at, order_id) = 2
    ) AS t;
    ```

    498 人です。顧客ごとに注文を時刻順に並べて 2 番目の行が存在する顧客を数えています。注文のある 504 人のうち、注文が 1 回だけの顧客が 6 人いる計算です。`GROUP BY customer_id HAVING count(*) >= 2` でも求められ、そちらのほうが短く書けます。ウィンドウ関数でなくてもよい場面が多いことを覚えておいてください。

問 4. 行動ログを `event_id` で重複排除したうえで、`event_type` ごとの件数を出してください。重複排除前の件数との差は何件ですか。

??? note "解答例"
    ```sql
    WITH dedup AS (
      SELECT *
      FROM events
      QUALIFY row_number() OVER (PARTITION BY event_id ORDER BY received_at, event_id) = 1
    )
    SELECT event_type, count(*) AS n FROM dedup GROUP BY event_type ORDER BY n DESC;
    ```

    `view` 1,991、`purchase` 677、`add_to_cart` 674、`search` 658 で、合計 4,000 件です。元の 4,040 件との差の 40 件が、二重に届いた行です。重複排除の前後で件数を比べて、差が想定どおりか確かめる習慣をつけてください。

## 参考文献

- DuckDB Documentation, “Window Functions”（フレーム、`ROWS` / `RANGE` / `GROUPS`、既定のフレーム）, <https://duckdb.org/docs/2.0/sql/functions/window_functions.html>（2026年11月時点）
- DuckDB Documentation, “QUALIFY Clause”, <https://duckdb.org/docs/2.0/sql/query_syntax/qualify.html>
- DuckDB Documentation, “WITH Clause”（CTE、マテリアライズ、再帰 CTE）, <https://duckdb.org/docs/2.0/sql/query_syntax/with.html>
- DuckDB Documentation, “PIVOT Statement”, <https://duckdb.org/docs/2.0/sql/statements/pivot.html>
- DuckDB Documentation, “EXPLAIN: Inspect Query Plans”, <https://duckdb.org/docs/2.0/guides/meta/explain.html>
- DuckDB Documentation, “EXPLAIN ANALYZE: Profile Queries”, <https://duckdb.org/docs/2.0/guides/meta/explain_analyze.html>
- DuckDB Documentation, “Indexes”, <https://duckdb.org/docs/2.0/sql/indexes.html>
- DuckDB Documentation, “Indexing”（ゾーンマップと ART インデックス）, <https://duckdb.org/docs/2.0/guides/performance/indexing.html>
- PostgreSQL Documentation, “Window Function Tutorial”, <https://www.postgresql.org/docs/current/tutorial-window.html>
- PostgreSQL Documentation, “WITH Queries (Common Table Expressions)”, <https://www.postgresql.org/docs/current/queries-with.html>
- PostgreSQL Documentation, “SELECT”（`DISTINCT ON`）, <https://www.postgresql.org/docs/current/sql-select.html>
- PostgreSQL Documentation, “Using EXPLAIN”, <https://www.postgresql.org/docs/current/using-explain.html>
- PostgreSQL Documentation, “EXPLAIN”, <https://www.postgresql.org/docs/current/sql-explain.html>
- PostgreSQL Documentation, “Indexes: Introduction”, <https://www.postgresql.org/docs/current/indexes-intro.html>
- PostgreSQL Documentation, “Multicolumn Indexes”, <https://www.postgresql.org/docs/current/indexes-multicolumn.html>
- PostgreSQL Documentation, “Indexes on Expressions”, <https://www.postgresql.org/docs/current/indexes-expressional.html>
- PostgreSQL Documentation, “Constraints”（外部キーとインデックス）, <https://www.postgresql.org/docs/current/ddl-constraints.html>
- PostgreSQL Documentation, “Routine Vacuuming”（一時テーブルと autovacuum）, <https://www.postgresql.org/docs/current/routine-vacuuming.html>

!!! tip "さらに深く"
    実行計画の読み方を分散処理に広げた内容は、応用編 第2章「Spark の性能調整」で扱います。重複排除と「各グループの最新 1 行」を CDC（変更データの取り込み）で扱う設計は、応用編 第5章「CDC とイベント駆動」で、列指向のデータとインデックスの関係をテーブルフォーマットで見る話は、応用編 第3章「レイクハウスとテーブルフォーマット」で扱います。

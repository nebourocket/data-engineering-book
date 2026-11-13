# 第6章 SQL 入門 2 (集計と JOIN)

## この章でできるようになること

- `count` `sum` `avg` `min` `max` で、表全体の件数・合計・平均・最小・最大を出し、手計算と見比べられる。
- `GROUP BY` で、グループごとの集計ができる。`WHERE` と `HAVING` の違いを説明できる。
- `JOIN` で 2 つの表をつなぎ、`INNER JOIN` と `LEFT JOIN` で、行が増える理由と消える理由を説明できる。
- `NULL` が「空の文字列」とも「0」とも違うことを説明し、`IS NULL` で探せる。`count(*)` と `count(列)` の違いが分かる。
- 別の `SELECT` の結果を条件に使う、サブクエリの入口に立てる。

前の章では、表から行を取り出し、絞り、並べました。この章では、行を **まとめて** 数字にする方法と、**複数の表をつなぐ** 方法を扱います。どちらも、データエンジニアの仕事で毎日使います。使う表は小さくしてあります。結果を、自分の目と手計算で確かめられる大きさです。

## この章で使う表

この章では、顧客の表 `customers` と、注文の表 `orders` を使います。どちらも数行しかありません。前の章と同じ `shop.duckdb` に、2 つの表を足します。この本のフォルダで、次の 2 行を打ってください。1 行目は、ターミナルを開き直したときに必要な `DEV` の別名です (第5章を参照)。2 行目が、表を作る SQL を流します。

```bash
alias DEV='docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev'
```

```bash
DEV python examples/s05/run_sql.py shop.duckdb examples/s06/setup.sql
```

何も表示されなければ成功です。表を作り直したいときは、`shop.duckdb` を消して (`rm shop.duckdb`)、もう一度流します。第5章の `products` も消えるので、必要ならそちらも作り直します。以降の SQL は、第5章と同じく `try.sql` に書いて、次の 1 行で流します。

```bash
DEV python examples/s05/run_sql.py shop.duckdb try.sql
```

2 つの表の中身は、次のとおりです。顧客の表です。

{{ table("s06-customers") }}

注文の表です。`customer_id` は、「どの顧客の注文か」を指す番号で、顧客の表の `customer_id` と対応しています。

{{ table("s06-orders") }}

なお、顧客の表には、ほかに `email` (メールアドレス) と `points` (ポイント) の列もあります。この 2 つは、あとの NULL の節で使います。全部の列を見ておきます。

```sql
SELECT * FROM customers;
```

```text
┌─────────────┬───────────┬────────────┬────────────────────┬────────┐
│ customer_id │   name    │ prefecture │       email        │ points │
│    int32    │  varchar  │  varchar   │      varchar       │ int32  │
├─────────────┼───────────┼────────────┼────────────────────┼────────┤
│           1 │ 佐藤 太郎 │ 東京       │ taro@example.com   │    100 │
│           2 │ 鈴木 花子 │ 大阪       │                    │    300 │
│           3 │ 高橋 健   │ 東京       │ NULL               │   NULL │
│           4 │ 田中 美咲 │ 石川       │ misaki@example.com │    200 │
└─────────────┴───────────┴────────────┴────────────────────┴────────┘
```

`email` の 3 行目が `NULL`、`points` の 3 行目も `NULL` です。2 行目の `email` は、何も表示されていませんが、これは `NULL` ではなく、「空の文字列」です。違いは、NULL の節で確かめます。

## 集計関数: 行をまとめて 1 つの数字にする

**集計関数** は、複数の行を 1 つの値にまとめる関数です。使うのは 5 つです。

{{ table("s06-aggregates") }}

まず、注文の件数を数えます。`count(*)` は、行の数を返します。

```sql
SELECT count(*) AS n FROM orders;
```

```text
┌───────┐
│   n   │
│ int64 │
├───────┤
│     6 │
└───────┘
```

6 行あるので、6 です。次に、5 つのうち 4 つをまとめて出します。

```sql
SELECT count(*) AS n,
       sum(amount) AS total,
       min(amount) AS smallest,
       max(amount) AS largest
FROM orders;
```

```text
┌───────┬────────┬──────────┬─────────┐
│   n   │ total  │ smallest │ largest │
│ int64 │ int128 │  int32   │  int32  │
├───────┼────────┼──────────┼─────────┤
│     6 │  15400 │      900 │    5800 │
└───────┴────────┴──────────┴─────────┘
```

手計算で確かめます。注文の金額は 3200、900、5800、1200、2800、1500 です。合計は 3200 + 900 + 5800 + 1200 + 2800 + 1500 で 15400 です。画面の `total` と合っています。最小は 900、最大は 5800 で、これも表を見て確かめられます。

!!! note "int128 という型について"
    `sum` の結果の型が `int128` と出ています。合計は大きな数になりうるので、整数を大きな範囲で持てる型に直されるためです。この章では、ふつうの整数と同じように読んで構いません。

平均は、合計を件数で割った値です。15400 ÷ 6 を手で計算すると、2566.666… と割り切れません。

```sql
SELECT avg(amount) AS average, round(avg(amount), 1) AS rounded FROM orders;
```

```text
┌────────────────────┬─────────┐
│      average       │ rounded │
│       double       │ double  │
├────────────────────┼─────────┤
│ 2566.6666666666665 │  2566.7 │
└────────────────────┴─────────┘
```

`avg(amount)` は、小数点以下がとても長い数で返ります。`round(値, 桁数)` は、四捨五入する関数で、`round(avg(amount), 1)` は、小数第 1 位までに丸めます。結果は 2566.7 です。

集計関数は、`WHERE` で絞った後の行に対して働きます。顧客 3 の注文だけの合計を出します。

```sql
SELECT sum(amount) AS total FROM orders WHERE customer_id = 3;
```

```text
┌────────┐
│ total  │
│ int128 │
├────────┤
│   5500 │
└────────┘
```

顧客 3 の注文は 1200、2800、1500 の 3 つで、合計は 5500 です。手計算と一致しました。

## GROUP BY: カードを山に分ける

ここまでの集計は、表全体で 1 つの数字でした。「顧客ごとの合計」が欲しいときは、`GROUP BY` を使います。

注文の 1 行を、1 枚のカードだと考えてください。`GROUP BY customer_id` は、「`customer_id` が同じカードを集めて、山に分ける」という指示です。そのあとで、山ごとに集計関数が働きます。

![注文のカードを customer_id の山に分ける図](../assets/figures/s06_group_by.svg)

SQL で書くと、次のとおりです。

```sql
SELECT customer_id, count(*) AS n, sum(amount) AS total
FROM orders
GROUP BY customer_id
ORDER BY customer_id;
```

```text
┌─────────────┬───────┬────────┐
│ customer_id │   n   │ total  │
│    int32    │ int64 │ int128 │
├─────────────┼───────┼────────┤
│           1 │     2 │   4100 │
│           2 │     1 │   5800 │
│           3 │     3 │   5500 │
└─────────────┴───────┴────────┘
```

結果は 3 行です。山が 3 つできたので、3 行になります。顧客 1 の山は 2 枚で合計 4100 (3200 + 900)、顧客 2 は 1 枚で 5800、顧客 3 は 3 枚で 5500 です。図の数字と同じです。

`SELECT` の後ろに書けるのは、2 種類です。1 つは、`GROUP BY` に書いた列 (`customer_id`)。もう 1 つは、集計関数です。山の中の `amount` は 1 つの値に決まらないので、そのまま書くとエラーになります。

```sql
SELECT customer_id, amount FROM orders GROUP BY customer_id;
```

```text
Binder Error: column "amount" must appear in the GROUP BY clause or must be part of an aggregate function.
Either add it to the GROUP BY list, or use ANY_VALUE("amount") if the exact value of "amount" is not important.
```

メッセージのとおり、`amount` を `GROUP BY` に足すか、集計関数の中に入れる必要があります。`customer_id` の山には複数の `amount` が入っていて、どれを出せばよいか決まらない、という意味です。

### WHERE と HAVING の違い

絞り込みには、2 つの書き方があります。

{{ table("s06-where-having") }}

違いを、実際の例で確かめます。まず、**山に分ける前** に絞る `WHERE` です。1,000 円以上の注文だけを、顧客ごとに数えます。

```sql
SELECT customer_id, count(*) AS n, sum(amount) AS total
FROM orders
WHERE amount >= 1000
GROUP BY customer_id
ORDER BY customer_id;
```

```text
┌─────────────┬───────┬────────┐
│ customer_id │   n   │ total  │
│    int32    │ int64 │ int128 │
├─────────────┼───────┼────────┤
│           1 │     1 │   3200 │
│           2 │     1 │   5800 │
│           3 │     3 │   5500 │
└─────────────┴───────┴────────┘
```

顧客 1 の山は、2 枚から 1 枚に減りました。900 円のカードが、山に分ける前に取り除かれたためです。合計も 4100 から 3200 になりました。

次は、**山に分けたあと** に絞る `HAVING` です。注文が 2 件以上の顧客だけを残します。

```sql
SELECT customer_id, count(*) AS n, sum(amount) AS total
FROM orders
GROUP BY customer_id
HAVING count(*) >= 2
ORDER BY customer_id;
```

```text
┌─────────────┬───────┬────────┐
│ customer_id │   n   │ total  │
│    int32    │ int64 │ int128 │
├─────────────┼───────┼────────┤
│           1 │     2 │   4100 │
│           3 │     3 │   5500 │
└─────────────┴───────┴────────┘
```

顧客 2 の山 (1 枚) が消えました。山の枚数は、山に分けたあとでないと分かりません。そのため、`count(*) >= 2` は `WHERE` には書けず、`HAVING` に書きます。`WHERE` に書くと、次のエラーになります。

```sql
SELECT customer_id FROM orders WHERE count(*) >= 2 GROUP BY customer_id;
```

```text
Binder Error: WHERE clause cannot contain aggregates!
```

「`WHERE` には集計を書けない」というメッセージのとおりです。

2 つを同時に使えます。1,000 円以上の注文だけを、顧客ごとに数え、3 件以上の顧客だけを残す、という順で処理されます。

```sql
SELECT customer_id, count(*) AS n, sum(amount) AS total
FROM orders
WHERE amount >= 1000
GROUP BY customer_id
HAVING count(*) >= 2
ORDER BY customer_id;
```

```text
┌─────────────┬───────┬────────┐
│ customer_id │   n   │ total  │
│    int32    │ int64 │ int128 │
├─────────────┼───────┼────────┤
│           3 │     3 │   5500 │
└─────────────┴───────┴────────┘
```

処理の順は、`WHERE` が先、`GROUP BY` が次、`HAVING` が最後です。顧客 3 だけが残りました。

## JOIN: 2 つの表をつなぐ

注文の表には、顧客の番号だけがあり、名前はありません。「誰の注文か」を名前で見るには、顧客の表と注文の表を、`customer_id` でつなぐ必要があります。この操作を **JOIN** (結合) と呼びます。

つなぐ前の 2 つの表を、線で結んだ図にします。左が顧客、右が注文です。同じ `customer_id` を持つ行どうしを、線で結んでいます。

![顧客と注文を customer_id でつなぐ図](../assets/figures/s06_join.svg)

図のとおり、顧客 1 には 2 本、顧客 3 には 3 本の線があります。顧客 4 には 1 本もありません。つなぐと、この線の数だけ行ができる、と考えてください。

### INNER JOIN

線で結ばれた組み合わせだけを残すのが、`INNER JOIN` です。

```sql
SELECT c.customer_id, c.name, o.order_id, o.amount
FROM customers AS c
INNER JOIN orders AS o ON o.customer_id = c.customer_id
ORDER BY o.order_id;
```

```text
┌─────────────┬───────────┬──────────┬────────┐
│ customer_id │   name    │ order_id │ amount │
│    int32    │  varchar  │  int32   │ int32  │
├─────────────┼───────────┼──────────┼────────┤
│           1 │ 佐藤 太郎 │      101 │   3200 │
│           1 │ 佐藤 太郎 │      102 │    900 │
│           2 │ 鈴木 花子 │      103 │   5800 │
│           3 │ 高橋 健   │      104 │   1200 │
│           3 │ 高橋 健   │      105 │   2800 │
│           3 │ 高橋 健   │      106 │   1500 │
└─────────────┴───────────┴──────────┴────────┘
```

SQL の読み方です。`FROM customers AS c` で、顧客の表に `c` という短い名前を付けます。`INNER JOIN orders AS o` で、注文の表を `o` という名前でつなぎます。`ON o.customer_id = c.customer_id` が、「どの行どうしをつなぐか」の条件です。`c.name` のように、表の名前 (別名) と列の名前を `.` でつなぐと、「`c` の `name`」という意味になります。

つなぐ前の 2 つの表は、顧客が 4 行、注文が 6 行でした。つないだ後を見てください。

{{ table("s06-join-inner") }}

行は 6 行です。顧客 1 (佐藤 太郎) は 2 回、顧客 3 (高橋 健) は 3 回出ています。顧客 1 の注文が 2 件あるので、顧客の側の行が注文の数だけ増えたためです。1 対 1 でなく、1 対多でつながると、行が増える、と覚えてください。

一方で、顧客 4 (田中 美咲) は、結果から消えました。注文が 1 件もなく、つなぐ相手が見つからなかったためです。`INNER JOIN` は、相手がある行だけを残します。

両方の表に同じ名前の列 (`customer_id`) があるので、表の別名を付けずに書くと、どちらの列か分からず、エラーになります。

```sql
SELECT customer_id FROM customers AS c INNER JOIN orders AS o ON o.customer_id = c.customer_id;
```

```text
Binder Error: Ambiguous reference to column name "customer_id" (use: 'c.customer_id' or 'o.customer_id')
```

### LEFT JOIN

注文がない顧客も、結果に残したいときは、`LEFT JOIN` を使います。左の表 (`FROM` の後ろに書いた表) の行を、全部残します。

```sql
SELECT c.customer_id, c.name, o.order_id, o.amount
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

```text
┌─────────────┬───────────┬──────────┬────────┐
│ customer_id │   name    │ order_id │ amount │
│    int32    │  varchar  │  int32   │ int32  │
├─────────────┼───────────┼──────────┼────────┤
│           1 │ 佐藤 太郎 │      101 │   3200 │
│           1 │ 佐藤 太郎 │      102 │    900 │
│           2 │ 鈴木 花子 │      103 │   5800 │
│           3 │ 高橋 健   │      104 │   1200 │
│           3 │ 高橋 健   │      105 │   2800 │
│           3 │ 高橋 健   │      106 │   1500 │
│           4 │ 田中 美咲 │     NULL │   NULL │
└─────────────┴───────────┴──────────┴────────┘
```

つないだ後は、次のとおりです。

{{ table("s06-join-left") }}

7 行になりました。顧客 4 (田中 美咲) が残り、注文の列 (`order_id` と `amount`) が `NULL` になっています。「つなぐ相手がなかった」という意味の印です。

2 つの JOIN の違いを、行数で確かめます。

{{ table("s06-join-kinds") }}

```sql
SELECT (SELECT count(*) FROM customers) AS customers_rows,
       (SELECT count(*) FROM orders) AS orders_rows,
       (SELECT count(*)
        FROM customers AS c
        INNER JOIN orders AS o ON o.customer_id = c.customer_id) AS inner_rows,
       (SELECT count(*)
        FROM customers AS c
        LEFT JOIN orders AS o ON o.customer_id = c.customer_id) AS left_rows;
```

```text
┌────────────────┬─────────────┬────────────┬───────────┐
│ customers_rows │ orders_rows │ inner_rows │ left_rows │
│     int64      │    int64    │   int64    │   int64   │
├────────────────┼─────────────┼────────────┼───────────┤
│              4 │           6 │          6 │         7 │
└────────────────┴─────────────┴────────────┴───────────┘
```

顧客 4 行・注文 6 行で、`INNER JOIN` の結果は 6 行、`LEFT JOIN` の結果は 7 行でした。6 行は、注文の数と同じです。7 行は、そこに、注文がない顧客 1 人が足されたものです。つなぐ前後で行数を数える習慣を付けると、結合の間違いに気づけます。

`LEFT JOIN` には、使いどころがあります。「注文のない顧客」を探すには、つないだあとに、注文側が `NULL` の行を取り出します。

```sql
SELECT c.name
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

```text
┌───────────┐
│   name    │
│  varchar  │
├───────────┤
│ 田中 美咲 │
└───────────┘
```

`IS NULL` の意味は、次の節で説明します。JOIN と集計も組み合わせられます。顧客ごとの注文数と合計です。

```sql
SELECT c.name, count(o.order_id) AS n, sum(o.amount) AS total
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
GROUP BY c.name
ORDER BY c.name;
```

```text
┌───────────┬───────┬────────┐
│   name    │   n   │ total  │
│  varchar  │ int64 │ int128 │
├───────────┼───────┼────────┤
│ 佐藤 太郎 │     2 │   4100 │
│ 田中 美咲 │     0 │   NULL │
│ 鈴木 花子 │     1 │   5800 │
│ 高橋 健   │     3 │   5500 │
└───────────┴───────┴────────┘
```

田中 美咲の注文数は 0、合計は `NULL` (注文がないので足すものがない) です。注文数を `count(o.order_id)` と書いたことに注目してください。`count(*)` と書くと、田中 美咲の行 (注文側が NULL の 1 行) を数えて 1 になってしまいます。この違いは、次の節の `count(列)` で説明します。

## NULL: 空であることの意味

これまで何度か出てきた `NULL` を、ここで整理します。**NULL** は、「値が分からない・入っていない」ことを表す特別な印です。0 でも、空の文字列でもありません。

顧客の表で確かめます。`email` と `points` の列を見ます。

```sql
SELECT customer_id, email, points FROM customers;
```

```text
┌─────────────┬────────────────────┬────────┐
│ customer_id │       email        │ points │
│    int32    │      varchar       │ int32  │
├─────────────┼────────────────────┼────────┤
│           1 │ taro@example.com   │    100 │
│           2 │                    │    300 │
│           3 │ NULL               │   NULL │
│           4 │ misaki@example.com │    200 │
└─────────────┴────────────────────┴────────┘
```

顧客 2 の `email` は、空の文字列 (`''`、文字が 0 個の文字列) で、`NULL` ではありません。顧客 3 の `email` と `points` が `NULL` です。同じ「何もない」ように見えても、別の値です。

### NULL との計算と比較

`NULL` が混ざった計算の結果は、`NULL` です。`NULL` どうしの比較 (`=`) も、`true` でも `false` でもなく、`NULL` (分からない) になります。

```sql
SELECT 1 + NULL AS plus, NULL = NULL AS equal, NULL IS NULL AS is_null;
```

```text
┌───────┬─────────┬─────────┐
│ plus  │  equal  │ is_null │
│ int32 │ boolean │ boolean │
├───────┼─────────┼─────────┤
│  NULL │ NULL    │ true    │
└───────┴─────────┴─────────┘
```

`1 + NULL` は、「1 に何かを足す」でも、その何かが分からないので、答えも分からず、`NULL` です。`NULL = NULL` も、「分からないものどうしが等しいか」は分からない、で `NULL` です。`NULL IS NULL` は、`true` を返します。「空であるか」を聞く専用の書き方が `IS NULL` です。

そのため、`email = NULL` で空の行を探すと、1 件も見つかりません。

```sql
SELECT name FROM customers WHERE email = NULL;
```

```text
┌─────────┐
│  name   │
│ varchar │
└─────────┘
  0 rows 
```

0 行でした。エラーにならないので、見落としやすい間違いです。空を探すには、`IS NULL` を使います。

```sql
SELECT name FROM customers WHERE email IS NULL;
```

```text
┌─────────┐
│  name   │
│ varchar │
├─────────┤
│ 高橋 健 │
└─────────┘
```

逆に、空ではない行は `IS NOT NULL` で探します。

```sql
SELECT name FROM customers WHERE email IS NOT NULL;
```

```text
┌───────────┐
│   name    │
│  varchar  │
├───────────┤
│ 佐藤 太郎 │
│ 鈴木 花子 │
│ 田中 美咲 │
└───────────┘
```

3 人が返りました。`email` が空の文字列の鈴木 花子も、`NULL` ではないので、ここに入っています。空の文字列を探すときは、`= ''` と書きます。

```sql
SELECT name FROM customers WHERE email = '';
```

```text
┌───────────┐
│   name    │
│  varchar  │
├───────────┤
│ 鈴木 花子 │
└───────────┘
```

{{ table("s06-null-compare") }}

### NULL の行は、条件で消える

もう 1 つ、大事な性質があります。`WHERE` は、条件が `true` の行だけを残します。`NULL` の行は、`true` ではないので、**どちらの条件でも消えます**。`points` が 200 以上の人です。

```sql
SELECT name, points FROM customers WHERE points >= 200;
```

```text
┌───────────┬────────┐
│   name    │ points │
│  varchar  │ int32  │
├───────────┼────────┤
│ 鈴木 花子 │    300 │
│ 田中 美咲 │    200 │
└───────────┴────────┘
```

では、200 未満の人です。

```sql
SELECT name, points FROM customers WHERE points < 200;
```

```text
┌───────────┬────────┐
│   name    │ points │
│  varchar  │ int32  │
├───────────┼────────┤
│ 佐藤 太郎 │    100 │
└───────────┴────────┘
```

200 以上が 2 人、200 未満が 1 人で、合わせて 3 人です。顧客は 4 人いるので、1 人が足りません。`points` が `NULL` の高橋 健が、どちらの結果にも出ていないためです。「どちらかに必ず入る」という思い込みが、数字のずれのもとになります。

### 集計と NULL

集計関数は、`count(*)` 以外、`NULL` を無視します。

```sql
SELECT count(*) AS all_rows, count(email) AS with_email, count(points) AS with_points
FROM customers;
```

```text
┌──────────┬────────────┬─────────────┐
│ all_rows │ with_email │ with_points │
│  int64   │   int64    │    int64    │
├──────────┼────────────┼─────────────┤
│        4 │          3 │           3 │
└──────────┴────────────┴─────────────┘
```

{{ table("s06-count-kinds") }}

`count(*)` は 4 ですが、`count(points)` は 3 です。NULL の行を数えないためです。`email` は、空の文字列を数えるので 3 です。平均も同じです。

```sql
SELECT avg(points) AS average, sum(points) AS total, count(points) AS n FROM customers;
```

```text
┌─────────┬────────┬───────┐
│ average │ total  │   n   │
│ double  │ int128 │ int64 │
├─────────┼────────┼───────┤
│   200.0 │    600 │     3 │
└─────────┴────────┴───────┘
```

`points` の平均は 200 です。100・300・200 の 3 つの合計 600 を、NULL を除いた 3 件で割っています。4 人で割った値ではありません。もし NULL を 0 として扱いたいなら、`coalesce(列, 0)` を使います。`coalesce` は、最初の NULL でない値を返す関数です。

```sql
SELECT avg(coalesce(points, 0)) AS average_with_zero FROM customers;
```

```text
┌───────────────────┐
│ average_with_zero │
│      double       │
├───────────────────┤
│             150.0 │
└───────────────────┘
```

0 として数えると、平均は 150 (600 ÷ 4) になります。どちらが正しいかは、データの意味で決まります。「ポイントを持っていない人」を 0 として数えるのか、「分からない人」として除くのか、を考えて選びます。NULL の扱いは、基礎編 第5章で、さらに詳しく扱います。

## サブクエリの入口

最後に、**サブクエリ** を紹介します。SQL の中に、丸括弧で囲んだ別の `SELECT` を入れる書き方です。

たとえば、「平均より高い金額の注文」を知りたいとします。平均を先に求めて、その数字を自分で書き写すのは大変です。サブクエリを使うと、平均を求める `SELECT` を、条件の中に直接書けます。

```sql
SELECT order_id, amount
FROM orders
WHERE amount > (SELECT avg(amount) FROM orders)
ORDER BY order_id;
```

```text
┌──────────┬────────┐
│ order_id │ amount │
│  int32   │ int32  │
├──────────┼────────┤
│      101 │   3200 │
│      103 │   5800 │
│      105 │   2800 │
└──────────┴────────┘
```

丸括弧の中の `SELECT avg(amount) FROM orders` が、先に実行され、2566.67 という 1 つの数字になります。それが、`amount > 2566.67` という条件として使われます。結果は 3 行で、3200・5800・2800 の注文です。手元の表で、平均 (2566.7) を超える金額を探して、確かめてください。

サブクエリが、複数の値を返すこともあります。その場合は、`IN` と組み合わせます。注文が 1 件でもある顧客の名前です。

```sql
SELECT name
FROM customers
WHERE customer_id IN (SELECT customer_id FROM orders)
ORDER BY customer_id;
```

```text
┌───────────┐
│   name    │
│  varchar  │
├───────────┤
│ 佐藤 太郎 │
│ 鈴木 花子 │
│ 高橋 健   │
└───────────┘
```

`SELECT customer_id FROM orders` は、注文のある顧客の番号の一覧を返します。その一覧に含まれる顧客だけが残りました。注文のない田中 美咲は入っていません。

`FROM` の後ろにも、サブクエリを書けます。顧客ごとの合計を先に作り、その中で一番大きい値を取り出します。

```sql
SELECT max(total) AS best_total
FROM (SELECT customer_id, sum(amount) AS total FROM orders GROUP BY customer_id) AS per_customer;
```

```text
┌────────────┐
│ best_total │
│   int128   │
├────────────┤
│       5800 │
└────────────┘
```

内側の `SELECT` が、顧客ごとの合計の表 (3 行) を作り、外側が、その表の最大値を返します。5800 は、顧客 2 の合計です。

サブクエリは、入れ子が深くなると読みにくくなります。基礎編 第5章では、読みやすく書き分ける方法を扱います。この章では、「丸括弧の中の `SELECT` が、先に実行される」と分かれば十分です。

## 基礎編 第5章へ

準備編の SQL は、ここまでです。次のことができるようになりました。

- 表を作り、行を入れる (`CREATE TABLE`、`INSERT`)。
- 行を選び、絞り、並べる (`SELECT`、`WHERE`、`ORDER BY`、`LIMIT`)。
- 集計し、グループに分ける (`count` など、`GROUP BY`、`HAVING`)。
- 表をつなぐ (`INNER JOIN`、`LEFT JOIN`)。
- 空 (`NULL`) を、空の文字列と区別して扱う。
- サブクエリを読む。

基礎編 [第5章 SQL 基礎](../basics/05-sql-basics.md) は、これらを 3,000 件の注文があるねぼすけ商店のデータで、もう一度、より深く扱います。NULL と三値論理、`FULL JOIN`、`CASE`、日付、`UNION`、SQL の評価順などが加わります。そのあとの [第6章 SQL 応用](../basics/06-sql-advanced.md) は、ウィンドウ関数や実行計画に進みます。

## よくある失敗

- `GROUP BY` に書いていない列を、そのまま `SELECT` に書いて、エラーになる。集計関数に入れるか、`GROUP BY` に足す。
- `WHERE` に `count(*)` などの集計関数を書いて、エラーになる。グループへの条件は `HAVING` に書く。
- `INNER JOIN` で、相手のない行が消えたことに気づかない。つなぐ前後で行数を数える。
- 両方の表にある列を、別名なしで書いて、エラーになる。`c.customer_id` のように書く。
- 1 対多でつないだあとに、行が増えたことを忘れ、件数や合計を数え間違える。
- `= NULL` で空を探して、0 行になる。`IS NULL` を使う。
- `LEFT JOIN` のあとに `count(*)` を使い、相手のない行まで 1 として数える。数えたい相手の側の列を、`count(列)` で数える。
- 空の文字列と `NULL` を同じだと思い込む。別の値として、両方を調べる。
- `NULL` の行が、`>=` の条件にも `<` の条件にも入らないことを忘れる。

## まとめ

- 集計関数は、複数の行を 1 つの値にまとめます。小さな表なら、手計算で確かめられます。
- `GROUP BY` は、同じ値の行を 1 つの山にまとめ、山ごとに 1 行を返します。
- `WHERE` は山に分ける前、`HAVING` は山に分けたあとに絞ります。
- `INNER JOIN` は、つながった行だけを残します。`LEFT JOIN` は、左の表の行をすべて残し、相手のない行は右の列が `NULL` になります。1 対多なら、行は増えます。
- `NULL` は、空の文字列とも 0 とも違います。探すときは `IS NULL`、数えるときは `count(*)` と `count(列)` を使い分けます。
- サブクエリは、丸括弧の中の `SELECT` が先に実行されます。

## 練習問題

次の問題は、`try.sql` に書いて流してください。表は、この章の `customers` と `orders` を使います。

問 1. 金額が 2,000 円以上の注文の、件数と合計金額を出してください。手計算でも確かめてください。

??? note "解答例"
    ```sql
    SELECT count(*) AS n, sum(amount) AS total FROM orders WHERE amount >= 2000;
    ```
    2,000 円以上の注文は 3200・5800・2800 の 3 件で、合計は 11800 です。

問 2. 顧客ごとに、一番高い注文の金額を出してください。

??? note "解答例"
    ```sql
    SELECT customer_id, max(amount) AS largest
    FROM orders
    GROUP BY customer_id
    ORDER BY customer_id;
    ```
    顧客 1 は 3200、顧客 2 は 5800、顧客 3 は 2800 です。山に分けてから、山ごとに `max` が働きます。

問 3. 注文の合計金額が 5,000 円以上の顧客を、顧客の番号と合計金額で出してください。`WHERE` ではなく `HAVING` を使う理由も説明してください。

??? note "解答例"
    ```sql
    SELECT customer_id, sum(amount) AS total
    FROM orders
    GROUP BY customer_id
    HAVING sum(amount) >= 5000
    ORDER BY customer_id;
    ```
    顧客 2 (5800) と顧客 3 (5500) が残ります。合計は、山に分けたあとでないと決まらないので、`WHERE` には書けず、`HAVING` に書きます。

問 4. 都道府県が東京の顧客の、名前・注文番号・金額を、`INNER JOIN` で出してください。何行になるか、先に予想してから流してください。

??? note "解答例"
    ```sql
    SELECT c.name, o.order_id, o.amount
    FROM customers AS c
    INNER JOIN orders AS o ON o.customer_id = c.customer_id
    WHERE c.prefecture = '東京'
    ORDER BY o.order_id;
    ```
    東京の顧客は 佐藤 太郎 (注文 2 件) と 高橋 健 (注文 3 件) の 2 人で、5 行になります。1 対多なので、顧客の人数 (2) ではなく、注文の数だけ行が出ます。

問 5. 都道府県ごとに、顧客の人数と `points` の平均を出してください。東京の平均が 50 ではなく 100 になる理由を説明してください。

??? note "解答例"
    ```sql
    SELECT prefecture, count(*) AS n, avg(points) AS average_points
    FROM customers
    GROUP BY prefecture
    ORDER BY prefecture;
    ```
    東京の顧客は 2 人で、`points` は 100 と `NULL` です。`avg` は `NULL` を除いて、100 の 1 件だけで割るので、100 になります。0 として 2 人で割りたいなら、`avg(coalesce(points, 0))` と書き、50 になります。

問 6. 一番金額の大きい注文の、注文番号と金額を、サブクエリで求めてください。

??? note "解答例"
    ```sql
    SELECT order_id, amount
    FROM orders
    WHERE amount = (SELECT max(amount) FROM orders);
    ```
    丸括弧の中が先に実行され、5800 になります。結果は注文 103 の 1 行です。

## 参考文献

- DuckDB Documentation, “Aggregate Functions”, <https://duckdb.org/docs/2.0/sql/functions/aggregates.html>（2026年11月時点）
- DuckDB Documentation, “GROUP BY Clause”, <https://duckdb.org/docs/2.0/sql/query_syntax/groupby.html>
- DuckDB Documentation, “HAVING Clause”, <https://duckdb.org/docs/2.0/sql/query_syntax/having.html>
- DuckDB Documentation, “FROM and JOIN Clauses”, <https://duckdb.org/docs/2.0/sql/query_syntax/from.html>
- DuckDB Documentation, “NULL Values”, <https://duckdb.org/docs/2.0/sql/data_types/nulls.html>
- DuckDB Documentation, “Subqueries”, <https://duckdb.org/docs/2.0/sql/expressions/subqueries.html>
- PostgreSQL Documentation, “Table Expressions”（JOIN の種類）, <https://www.postgresql.org/docs/current/queries-table-expressions.html>

次に読む章: [第7章 データの形 (表・CSV・JSON)](s07-data-shapes.md)

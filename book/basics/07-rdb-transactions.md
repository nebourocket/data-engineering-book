# 第7章 RDB・正規化・トランザクション

## この章でできるようになること

- 主キー・外部キー・一意・CHECK・NOT NULL の各制約が何を守るかを説明し、PostgreSQL で実際に違反させて確かめられる。
- 崩れた表を、第1〜第3正規形へ段階的に直せる。正規化しすぎない判断（意図的な非正規化）も説明できる。
- トランザクションと ACID の 4 つの性質を、注文と在庫の例で説明できる。
- 分離レベルごとに起きる異常（ダーティリード・反復不能読み取り・ファントム・更新の消失・書き込みスキュー）を、2 つの接続で再現して見分けられる。
- 行ロックとデッドロックの起き方と、避け方を言える。MVCC の考え方を、行のバージョンで説明できる。
- OLTP と OLAP の違いを言い、本番のデータベースから読むときの作法を守れる。

## なぜデータエンジニアが RDB を知る必要があるのか

データエンジニアが扱うデータの出発点は、たいていアプリの裏側にあるリレーショナルデータベース（RDB）です。データを「表」の形で持ち、SQL で操作するデータベースで、第1章のライフサイクルでは生成の段階にいる相手です。ねぼすけ商店でも、注文・顧客・商品は通販アプリの RDB にあります。

この相手のことを知らずにデータを取りに行くと、2 種類の事故が起きます。読み取りの負荷でアプリを遅くしてしまう事故と、RDB が何を守り何を守らないかを知らないために、「同じ注文が 2 行ある」「在庫がマイナスになっている」といった現象の原因を絞れない事故です。

この章では、表の設計（制約と正規化）、同時に使われても壊れない仕組み（トランザクション）、分析用データベースとの違いを順に見ます。動かすのは PostgreSQL です。第5章と第6章の SQL は知っているものとして進めます。

### 動かす準備

この章のコードは `examples/b07/` にあります。PostgreSQL が必要なので、リポジトリのルートで `docker compose up -d --wait` を実行して起動してから、環境変数で接続先を教えます。WSL や Linux のシェルで動かす例です。コードはスキーマ `b07` を作り直して使い、他のスキーマには触りません。

```console
$ export PG_DSN=postgresql://deb:deb@localhost:5432/deb
$ cd examples/b07
$ python normalization.py
```

Python からは psycopg（バージョン 3）でつなぎます。`b07_db.py` の `connect()` は `search_path` を `b07` にそろえ、`autocommit=True` で `BEGIN` と `COMMIT` を自分で書く形にします。対話の道具 psql を 2 つ開いて同じ順に打つのと同じことを、プログラムの中でやる形です。

## リレーショナルモデルと表

リレーショナルモデルは、1970 年に E. F. Codd が示した考え方です（参考文献 12）。データを「関係」（relation）の集まりとして持ちます。実装の言葉では、関係は表、組は行、属性は列です。大事なのは、行の並び順に意味がなく、どの行も「主キー」という値で 1 つに決まることです。そして、表と表を、値の一致（外部キー）でつなぎます。

この設計の利点は、同じ事実を 1 か所にだけ書けることです。メールアドレスは顧客の表に 1 回だけ置き、注文からは顧客番号で指します。変わったら 1 行を直すだけで、すべての注文から新しい値が見えます。これを段階を追って実現する手順が、後で見る正規化です。

もうひとつの利点は、守るべきルールをデータベースに任せられることです。アプリもバッチも、人が手で打つ SQL もあり、それぞれがルールを守る前提では、いつか誰かが破ります。次の節の制約が、その最後の砦です。

## 制約でデータを入口で守る

制約（constraint）は、表に書き込める値の条件をデータベースに教える宣言です。条件に合わない書き込みは、エラーとして拒否されます。PostgreSQL の制約は公式ドキュメントにまとまっています（参考文献 1）。

{{ table("b07-constraints") }}

ねぼすけ商店の表に、制約を付けた DDL が次です。`examples/b07/constraints.py` にあります。

```sql
CREATE TABLE customers (
    customer_id int PRIMARY KEY,
    name        text NOT NULL,
    email       text UNIQUE,
    prefecture  text NOT NULL);
CREATE TABLE products (
    product_id int PRIMARY KEY,
    name       text NOT NULL,
    category   text NOT NULL,
    price      int NOT NULL CHECK (price > 0));
CREATE TABLE orders (
    order_id    int PRIMARY KEY,
    customer_id int NOT NULL REFERENCES customers,
    ordered_at  timestamp NOT NULL,
    status      text NOT NULL CHECK (status IN ('placed', 'shipped', 'delivered', 'cancelled')));
CREATE TABLE order_items (
    order_id   int REFERENCES orders,
    line_no    int,
    product_id int NOT NULL REFERENCES products,
    quantity   int NOT NULL CHECK (quantity > 0),
    unit_price int NOT NULL CHECK (unit_price > 0),
    PRIMARY KEY (order_id, line_no))
```

この DDL で表を作り、顧客・商品・注文・明細を 1 行ずつ入れてから、壊れた行を 6 つ試します。

```python
BAD_STATEMENTS = {
    "主キーの重複": "INSERT INTO customers VALUES (1, '別人', 'other@example.com', '大阪')",
    "一意制約（メール）": "INSERT INTO customers VALUES (2, '別人', 'hanako@example.com', '大阪')",
    "NOT NULL": "INSERT INTO customers VALUES (3, NULL, 'x@example.com', '大阪')",
    "外部キー（存在しない顧客）": "INSERT INTO orders VALUES (2, 999, '2026-03-02 10:00:00', 'placed')",
    "CHECK（未知の状態）": "INSERT INTO orders VALUES (3, 1, '2026-03-02 10:00:00', 'SHIPPED')",
    "CHECK（数量が 0）": "INSERT INTO order_items VALUES (1, 2, 1, 0, 3000)",
}
```

`python constraints.py` の出力は次のとおりです。各行の右側が、止めた制約の種類（psycopg の例外クラス名）です。

```text
主キーの重複: UniqueViolation
一意制約（メール）: UniqueViolation
NOT NULL: NotNullViolation
外部キー（存在しない顧客）: ForeignKeyViolation
CHECK（未知の状態）: CheckViolation
CHECK（数量が 0）: CheckViolation
customer_id=501: duplicate key value violates unique constraint "customers_email_key" / Key (email)=(user0296@example.com) already exists.
```

最後の行は、第1章から使ってきたねぼすけ商店の顧客を、先頭から順に入れたときの結果です。501 番目の行で一意制約が止めました。同じメールアドレスで customer_id だけが違う二重登録が入っているからです。制約は、データの欠陥を「集計が合わなくなってから」ではなく「入る瞬間」に見つけます。`status` の `SHIPPED` も同様で、CHECK に引っかかります。

### 制約をどこまで付けるか

アプリ側の RDB には、できるだけ付けます。データウェアハウスのような分析用の製品では事情が違います。BigQuery の主キー・外部キーは `NOT ENFORCED`（強制しない）と書く必要があり、実際には検査しません（参考文献 2）。Snowflake の標準テーブルも、主キー・外部キー・一意制約は強制せず、NOT NULL と CHECK を強制します（参考文献 3、2026年11月時点）。巨大なテーブルで毎回検査すると書き込みが遅くなるためです。

そのため分析基盤では、主キーが一意かどうかを取り込みの後で自分でテストします（第13章）。宣言だけの制約も、説明書き（メタデータ）としては役に立ちます。

## 正規化: 同じ事実を 1 か所にだけ書く

正規化は、表を「同じ事実が 2 か所に書かれない」形に分ける作業です。分ける基準が正規形で、第1正規形から順に厳しくなります。ねぼすけ商店の崩れた表で追います。コードは `examples/b07/normalization.py` にあります。

{{ table("b07-normal-forms") }}

### 段階 0: 表計算ソフトのまま

Excel で管理していた注文を、そのまま貼り付けた表です。

```sql
CREATE TABLE sheet (
    order_id int, ordered_at date,
    customer_name text, customer_email text, customer_prefecture text,
    items text)
```

`items` の 1 つのセルに、複数の商品が入っています。「枕を買った注文」を探すにも文字列の検索が要り、商品ごとの集計もできません。

### 第1正規形: 1 つのセルに 1 つの値

1 つのセルには 1 つの値だけを入れ、複数の明細は行を分けます。明細が行になるので、主キーは `(order_id, line_no)` の組になります。

```sql
CREATE TABLE orders_1nf (
    order_id int, line_no int, ordered_at date,
    customer_name text, customer_email text, customer_prefecture text,
    product_id int, product_name text, category text, unit_price int, quantity int,
    PRIMARY KEY (order_id, line_no))
```

これで集計はできます。しかし、同じ注文の顧客名・メールアドレスが明細の行ごとに繰り返されています。佐藤花子さんのメールアドレスを直そうとして、1 行だけ更新してしまった場合を考えます。

```sql
UPDATE orders_1nf SET customer_email = 'hanako@neboske.example'
WHERE order_id = 1 AND line_no = 1
```

```sql
SELECT count(DISTINCT customer_email) FROM orders_1nf WHERE customer_name = '佐藤花子'
```

2 つ目の SQL（佐藤花子さんのメールアドレスの種類の数）は、更新の前は 1、後は 2 になります（`python normalization.py` の出力の `before` と `after_partial_update`）。同じ人のメールアドレスが 2 つあるデータができました。これを更新の異常と呼びます。繰り返しがある限り、全部直し忘れた行が必ず出てきます。

### 第2正規形: 主キーの一部だけで決まる列を出す

第2正規形は、主キーが複数の列でできている表を問題にします。注文日・顧客名・メールアドレス・都道府県は、`order_id` だけで決まり、`line_no` は関係ありません。主キーの一部にだけ従う列があると、第2正規形を満たしません。注文の列を `orders_2nf` に出します。

```sql
CREATE TABLE orders_2nf (
    order_id int PRIMARY KEY, ordered_at date,
    customer_name text, customer_email text, customer_prefecture text);
CREATE TABLE order_items_2nf (
    order_id int REFERENCES orders_2nf, line_no int,
    product_id int, product_name text, category text, unit_price int, quantity int,
    PRIMARY KEY (order_id, line_no))
```

主キーが 1 列の表は、自動的に第2正規形です。

### 第3正規形: 主キー以外の列から決まる列を出す

まだ `orders_2nf` に、顧客名・メールアドレス・都道府県が残っています。これらは注文ではなく顧客で決まる情報です。同じ顧客が 10 回注文したら 10 回繰り返されます。`order_items_2nf` の商品名とカテゴリも同じで、`product_id` が決まれば決まります。主キー以外の列（顧客、商品）が、別の列を決めている形を、推移的な従属といいます。これらを `customers` と `products` に出したのが第3正規形です。

```sql
CREATE TABLE customers (
    customer_id int PRIMARY KEY, name text, email text, prefecture text);
CREATE TABLE products (
    product_id int PRIMARY KEY, name text, category text);
CREATE TABLE orders (
    order_id int PRIMARY KEY, ordered_at date,
    customer_id int REFERENCES customers);
CREATE TABLE order_items (
    order_id int REFERENCES orders, line_no int,
    product_id int REFERENCES products, unit_price int, quantity int,
    PRIMARY KEY (order_id, line_no))
```

`order_items` に `unit_price` が残っているのは、見落としではありません。注文した時点の価格は、後で商品の価格が変わっても動かない履歴の値で、商品の現在の価格とは別の事実です。ここで更新の異常を確かめ直します。

```sql
UPDATE customers SET email = 'hanako@neboske.example'
WHERE customer_id = 1
```

メールアドレスの置き場所は `customers` の 1 行だけなので、更新は 1 行で終わります（出力の `updated_rows` は 1）。

正規形にはボイス・コッド正規形（BCNF）や第4・第5正規形もありますが、第3正規形まで直せば足りる場面が多いです。迷ったら、各列が「キーに、キー全体に、キーだけに従っているか」を確かめます（参考文献 4 の言い方です）。

### 意図的な非正規化

正規化した表は、書き込みに強く、分析には向きません。カテゴリ別・都道府県別の集計をするたびに 4 つの表を結合するのは、読む側にとって手間で、大量のデータでは遅くなります。そこで分析用に、結合済みの幅広い表を別に作ります。

```sql
CREATE TABLE order_lines_wide AS
SELECT o.order_id, i.line_no, o.ordered_at, c.prefecture, p.category,
       i.quantity * i.unit_price AS sales
FROM orders AS o
JOIN customers AS c USING (customer_id)
JOIN order_items AS i USING (order_id)
JOIN products AS p USING (product_id)
```

この表は正規化された表のコピーなので、元の表を直しても勝手には追いつきません。作り直す手順（第10章）が要ります。元の表は残し、読むための表を別に持つのが基本です。出力では、幅広い表と正規化した表のカテゴリ別売上は一致します。第8章では、この発展形としてスタースキーマを作ります。

## トランザクションと ACID

トランザクションは、いくつかの操作をひとまとめにして、「全部成功するか、全部なかったことになる」ように扱う仕組みです。注文を受けると、`orders` に注文を足し、`stock` の在庫を減らします。片方だけ起きてはいけません。

SQL では `BEGIN` で始めて、`COMMIT`（確定）か `ROLLBACK`（取り消し）で終わります。`BEGIN` なしで 1 文だけ実行した場合も、PostgreSQL はその 1 文を 1 つのトランザクションとして扱います。psycopg では `with conn.transaction():` で囲むと、ブロックを抜けたら確定、例外が出たら取り消しになります（参考文献 5）。

```python
def place_order(conn, product_id: int, quantity: int) -> None:
    """注文を登録し、在庫を減らす。2 つの更新は全部成功するか、全部なかったことになる。"""
    with conn.transaction():
        conn.execute("INSERT INTO orders (product_id, quantity) VALUES (%s, %s)", (product_id, quantity))
        conn.execute("UPDATE stock SET quantity = quantity - %s WHERE product_id = %s", (quantity, product_id))
```

在庫が 5 しかないのに 9 個の注文を入れてみます。在庫の列には `CHECK (quantity >= 0)` が付けてあります。

```python
def atomicity(dsn: str) -> tuple[int, int, str]:
    """在庫 5 に対して 9 個の注文を入れる。在庫の CHECK が失敗し、先に入れた注文の行も消える。"""
    prepare(dsn)
    with connect(dsn) as conn:
        try:
            place_order(conn, 1, 9)
            error = "成功"
        except psycopg.errors.CheckViolation as e:
            error = e.diag.constraint_name
        orders = conn.execute("SELECT count(*) FROM orders").fetchone()[0]
        stock = conn.execute("SELECT quantity FROM stock WHERE product_id = 1").fetchone()[0]
    return orders, stock, error
```

```text
(0, 5, 'stock_quantity_check')
```

在庫の更新が CHECK に違反して失敗した結果、先に入れた注文の行も消えて、注文は 0 件、在庫は 5 のままです。これが ACID の最初の A です。

ACID は、トランザクションが満たすべき 4 つの性質の頭文字です。

- **A（Atomicity、原子性）**: 全部成功するか、全部なかったことになる。上の例です。
- **C（Consistency、一貫性）**: トランザクションの前後で、制約が満たされている。在庫がマイナスの状態は確定しません。
- **I（Isolation、分離性）**: 同時に走るトランザクションが、お互いの途中経過に邪魔されない。次の節の主題です。
- **D（Durability、永続性）**: COMMIT が成功したら、その直後にサーバーが落ちても結果は残る。PostgreSQL は、変更を先にログ（WAL、先行書き込みログ）へ書いてから確定して実現しています（参考文献 6）。

一番難しいのは分離性です。完全に守ろうとすると同時に動けず、性能が落ちます。そこで SQL には、どこまで守るかを選ぶ分離レベルがあります。

## 分離レベルと異常

複数のトランザクションが同時に動くと、途中経過が見えて、おかしな結果が出ることがあります。これを異常と呼びます。SQL 標準は、読み取りの異常として次の 3 つを定めています。

- **ダーティリード**: 他のトランザクションがまだ確定していない変更を読んでしまう。
- **反復不能読み取り**: 同じトランザクションの中で同じ行を 2 回読んだら、値が変わっていた（間に他のトランザクションが確定した）。
- **ファントム**: 同じ条件で 2 回検索したら、行の数が変わっていた（間に他のトランザクションが条件に合う行を足した）。

ここに、標準の定義にはないものの現場でよく起きる 2 つを加えます。

- **更新の消失**: 2 つのトランザクションが同じ値を読み、それぞれ計算して書き戻したため、片方の更新が上書きされて消える。
- **書き込みスキュー**: 2 つのトランザクションが、同じ条件を読んで確かめたうえで、別々の行を書いた結果、2 つ合わせると条件が壊れる。

分離レベルは、トランザクションが見える範囲を決める設定で、`BEGIN ISOLATION LEVEL ...` で指定します。PostgreSQL が実際に防ぐ異常を、公式ドキュメントの表（参考文献 7）と、この章の実行結果にもとづいてまとめます。

{{ table("b07-isolation") }}

PostgreSQL では、READ UNCOMMITTED を指定しても READ COMMITTED と同じ動きになり、REPEATABLE READ は標準が求める以上にファントムも防ぎます（参考文献 7）。既定は READ COMMITTED です。製品によって異なるので、MySQL や SQL Server で同じ表を期待してはいけません。

### 2 つの接続で再現する

`examples/b07/anomalies.py` は、接続 a と b を同じプログラムの中で交互に動かします。まず、ダーティリードを試します。a が在庫を 0 に更新して、まだ確定しないうちに、b が読みます。

```python
def dirty_read(dsn: str, level: str) -> int:
    """a がまだ COMMIT していない更新を、b が読めるか。読めたら 0、読めなければ 10 が返る。"""
    a, b = fresh(dsn)
    a.execute(f"BEGIN ISOLATION LEVEL {level}")
    a.execute("UPDATE stock SET quantity = 0 WHERE product_id = 1")
    b.execute(f"BEGIN ISOLATION LEVEL {level}")
    seen = read_stock(b)
    a.execute("ROLLBACK")
    b.execute("COMMIT")
    return seen
```

どの分離レベルでも、b が読むのは更新前の 10 です。PostgreSQL ではダーティリードは起きません。

反復不能読み取りは、b が同じ行を 2 回読む間に、a が確定させます。

```python
def non_repeatable_read(dsn: str, level: str) -> tuple[int, int]:
    """b が同じ行を 2 回読む間に、a が更新して COMMIT する。2 回の値が変わるか。"""
    a, b = fresh(dsn)
    b.execute(f"BEGIN ISOLATION LEVEL {level}")
    first = read_stock(b)
    a.execute("UPDATE stock SET quantity = 7 WHERE product_id = 1")
    second = read_stock(b)
    b.execute("COMMIT")
    return first, second
```

ファントムは、同じ形で読む対象を件数にしたものです。

```python
def phantom_read(dsn: str, level: str) -> tuple[int, int]:
    """b が同じ条件で 2 回数える間に、a が条件に合う行を足して COMMIT する。件数が変わるか。"""
    a, b = fresh(dsn)
    count = "SELECT count(*) FROM pending_orders WHERE status = 'placed'"
    b.execute(f"BEGIN ISOLATION LEVEL {level}")
    first = b.execute(count).fetchone()[0]
    a.execute("INSERT INTO pending_orders VALUES (3, 'placed')")
    second = b.execute(count).fetchone()[0]
    b.execute("COMMIT")
    return first, second
```

全分離レベルを順に動かした出力（`python anomalies.py`）は次のとおりです。

```text
READ UNCOMMITTED  ダーティリード=10 反復不能=(10, 7) ファントム=(2, 3) 更新の消失=(8, None) 書き込みスキュー=(0, None)
READ COMMITTED    ダーティリード=10 反復不能=(10, 7) ファントム=(2, 3) 更新の消失=(8, None) 書き込みスキュー=(0, None)
REPEATABLE READ   ダーティリード=10 反復不能=(10, 10) ファントム=(2, 2) 更新の消失=(7, 'SerializationFailure') 書き込みスキュー=(0, None)
SERIALIZABLE      ダーティリード=10 反復不能=(10, 10) ファントム=(2, 2) 更新の消失=(7, 'SerializationFailure') 書き込みスキュー=(1, 'SerializationFailure')
```

READ COMMITTED は、SELECT のたびにその時点で確定している最新のデータを見るので、2 回目に 7 が見えます。REPEATABLE READ は、最初の SELECT の時点の断面（スナップショット）を終わりまで見続けるので、2 回とも 10 です（参考文献 7）。

### 更新の消失

在庫 10 の商品を、a が 3 個、b が 2 個売ります。正しい最終在庫は 5 です。どちらも「読んで、計算して、書き戻す」形で書くと次のようになります。

```python
def lost_update(dsn: str, level: str) -> tuple[int, str | None]:
    """a も b も在庫を読み、読んだ値から計算した結果を書き戻す。a は 3 個、b は 2 個売る。

    正しい最終在庫は 10 - 3 - 2 = 5。戻り値は (最終在庫, b の更新が失敗したときのエラー名)。
    """
    a, b = fresh(dsn)
    a.execute(f"BEGIN ISOLATION LEVEL {level}")
    b.execute(f"BEGIN ISOLATION LEVEL {level}")
    seen_a, seen_b = read_stock(a), read_stock(b)
    a.execute("UPDATE stock SET quantity = %s WHERE product_id = 1", (seen_a - 3,))
    a.execute("COMMIT")
    error = None
    try:
        b.execute("UPDATE stock SET quantity = %s WHERE product_id = 1", (seen_b - 2,))
        b.execute("COMMIT")
    except psycopg.errors.SerializationFailure as e:
        error = type(e).__name__
        b.execute("ROLLBACK")
    return read_stock(a), error
```

```mermaid
sequenceDiagram
    participant A as 接続 a
    participant B as 接続 b
    participant DB as stock
    A->>DB: 読む (10)
    B->>DB: 読む (10)
    A->>DB: 7 に更新して COMMIT
    B->>DB: 8 に更新して COMMIT
    Note over DB: 最終 8。a の 3 個が消えた
```

READ COMMITTED の出力 `(8, None)` は、エラーが出ないまま最終在庫が 8 になったことを示します。b は a の更新を知らずに「10 - 2」を書いたからです。エラーが出ないので、気づきにくい異常です。REPEATABLE READ 以上では、b の更新が「自分のスナップショットの後で変わった行」にあたるため、`SerializationFailure` になり、b のトランザクションは取り消されます。出力の 7 は a の結果だけが残った状態で、b はトランザクションをやり直すことになります（SQLSTATE 40001。参考文献 7）。

直し方のひとつは、読んだ値を持ち回らず、データベースの中で計算させることです。

```python
def atomic_update(dsn: str, level: str) -> int:
    """直し方 1: 読んだ値を持ち回らず、データベースの中で引き算する。"""
    a, b = fresh(dsn)
    a.execute(f"BEGIN ISOLATION LEVEL {level}")
    b.execute(f"BEGIN ISOLATION LEVEL {level}")
    a.execute("UPDATE stock SET quantity = quantity - 3 WHERE product_id = 1")
    a.execute("COMMIT")
    b.execute("UPDATE stock SET quantity = quantity - 2 WHERE product_id = 1")
    b.execute("COMMIT")
    return read_stock(a)
```

READ COMMITTED のままでも、最終在庫は 5 になります。`SET quantity = quantity - 2` は、更新の時点で最新の行を読み直して引くためです。もうひとつは、読むときに `SELECT ... FOR UPDATE` で行ロックを取ることです。後から来たトランザクションは、先のトランザクションが終わるまで待たされ、確定後の値を読みます（`anomalies.py` の `select_for_update`）。

### 書き込みスキュー

「店番は必ず 1 人は残す」という規則を考えます。出勤が 2 人（hanako と ken）の状態で、2 人が同時に休みを申請します。どちらも「2 人いるから自分は休める」と確かめてから、自分の行だけを更新します。

```python
def write_skew(dsn: str, level: str) -> tuple[int, str | None]:
    """「店番は必ず 1 人は残す」規則で、a と b が同時に自分だけ休みを取る。

    どちらも「2 人いるから自分は休める」と確かめてから、自分の行だけ更新する。
    戻り値は (最後に出勤している人数, 後から来た側のエラー名)。
    """
    a, b = fresh(dsn)
    on_duty = "SELECT count(*) FROM shifts WHERE on_duty"
    a.execute(f"BEGIN ISOLATION LEVEL {level}")
    b.execute(f"BEGIN ISOLATION LEVEL {level}")
    assert a.execute(on_duty).fetchone()[0] == 2 and b.execute(on_duty).fetchone()[0] == 2
    a.execute("UPDATE shifts SET on_duty = false WHERE staff = 'hanako'")
    b.execute("UPDATE shifts SET on_duty = false WHERE staff = 'ken'")
    a.execute("COMMIT")
    error = None
    try:
        b.execute("COMMIT")
    except psycopg.errors.SerializationFailure as e:
        error = type(e).__name__
    return a.execute(on_duty).fetchone()[0], error
```

2 人の更新は別々の行なので、行ロックはぶつかりません。REPEATABLE READ までは、どちらも成功して、出勤が 0 人になります（出力は `(0, None)`）。SERIALIZABLE では、PostgreSQL がトランザクションどうしの読み書きの依存を監視して、片方の COMMIT を `SerializationFailure` で失敗させます。結果は出勤 1 人（`(1, 'SerializationFailure')`）です。

SERIALIZABLE は、「1 つずつ順に実行した結果と同じになる」ことを保証します（参考文献 7）。代わりに、アプリは失敗を受けて最初からやり直す前提で書きます。やり直しのコードは次のとおりです。

```python
def take_day_off(conn, staff: str) -> bool:
    """店番が 2 人以上いるときだけ、自分の休みを登録する。SERIALIZABLE で動かす。"""
    with conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        if conn.execute("SELECT count(*) FROM shifts WHERE on_duty").fetchone()[0] < 2:
            return False
        conn.execute("UPDATE shifts SET on_duty = false WHERE staff = %s", (staff,))
        return True


def retry(conn, func, *args, tries: int = 3):
    """直列化失敗（SQLSTATE 40001）なら、取引を最初からやり直す。"""
    for attempt in range(1, tries + 1):
        try:
            return func(conn, *args), attempt
        except psycopg.errors.SerializationFailure:
            if attempt == tries:
                raise
```

```python
def write_skew_with_retry(dsn: str) -> tuple[list, int]:
    """2 人が同時に休みを申請する。片方は直列化失敗になり、やり直しで「1 人しかいない」と断られる。"""
    prepare(dsn)
    a, b = connect(dsn), connect(dsn)
    a.execute("BEGIN ISOLATION LEVEL SERIALIZABLE")
    b.execute("BEGIN ISOLATION LEVEL SERIALIZABLE")
    for conn in (a, b):
        conn.execute("SELECT count(*) FROM shifts WHERE on_duty")
    a.execute("UPDATE shifts SET on_duty = false WHERE staff = 'hanako'")
    b.execute("UPDATE shifts SET on_duty = false WHERE staff = 'ken'")
    a.execute("COMMIT")
    results = []
    try:
        b.execute("COMMIT")
    except psycopg.errors.SerializationFailure:
        b.execute("ROLLBACK")
        results.append(retry(b, take_day_off, "ken"))  # やり直し: 今度は hanako が休みなので断られる
    return results, a.execute("SELECT count(*) FROM shifts WHERE on_duty").fetchone()[0]
```

```text
([(False, 1)], 1)
```

失敗した ken のトランザクションが最初からやり直されると、そのときは hanako が休みを確定しているため、出勤は 1 人しかおらず、休みは断られます（`False`）。出勤は 1 人のままです。

## ロックとデッドロック

`UPDATE` や `SELECT ... FOR UPDATE` は、対象の行にロックをかけます。他のトランザクションが同じ行を更新しようとすると、ロックが外れる（COMMIT か ROLLBACK される）まで待たされます。PostgreSQL の通常の SELECT は行のロックを取らないので、更新中の行も待たずに読めます。

`locks.py` の `reader_is_not_blocked` で確かめます。a が更新中（未確定）でも、b の SELECT は待たずに更新前の 10 を返し、b の UPDATE は待たされます（`lock_timeout` を 300 ミリ秒にしてあるので、時間切れで終わります）。

```text
(10, '更新は a の COMMIT を待って時間切れ')
```

### デッドロック

2 つのトランザクションがお互いのロックを待つと、永久に進めません。これがデッドロックです。a は商品 1 → 2 の順に、b は商品 2 → 1 の順に更新すると起きます。

```python
def deadlock(dsn: str, same_order: bool) -> list[str]:
    """a は商品 1 → 2、b は商品 2 → 1 の順に更新する。same_order=True なら b も 1 → 2 の順にする。

    戻り値は、エラーになった側の名前の一覧。デッドロックなら、PostgreSQL がどちらか 1 つを中止する。
    """
    a, b = fresh(dsn)
    failed = []

    def run(name, conn, first, second, pause):
        try:
            conn.execute("BEGIN")
            conn.execute("UPDATE stock SET quantity = quantity - 1 WHERE product_id = %s", (first,))
            time.sleep(pause)
            conn.execute("UPDATE stock SET quantity = quantity - 1 WHERE product_id = %s", (second,))
            conn.execute("COMMIT")
        except psycopg.errors.DeadlockDetected:
            failed.append(name)
            conn.execute("ROLLBACK")

    order_b = (1, 2) if same_order else (2, 1)
    threads = [threading.Thread(target=run, args=("a", a, 1, 2, 0.5)),
               threading.Thread(target=run, args=("b", b, *order_b, 0.5))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return failed
```

```text
順番がばらばら ['b']
順番をそろえた []
```

PostgreSQL は、待ちが `deadlock_timeout`（既定は 1 秒）を超えると、待ちの輪を検査して、トランザクションの 1 つを `DeadlockDetected` で中止します（参考文献 8）。どちらが中止されるかは決まっていません。避け方は、複数の行を更新する順番をそろえることです。両方が 1 → 2 の順なら、後から来た側は待つだけで輪はできません。短く終えることも確率を下げます。

## MVCC: 更新は書き換えではなく、新しい版を作る

読むトランザクションが待たされず、REPEATABLE READ が「トランザクションの最初の断面」を見続けられるのは、PostgreSQL が MVCC（Multi-Version Concurrency Control、多版同時実行制御）で動いているからです。行を更新すると、元の行を書き換えず、新しい版（バージョン）を別の場所に作ります。トランザクションは、自分が見てよい版だけを見ます。公式ドキュメントには、MVCC では読むためのロックと書くためのロックがぶつからず、読むことは書くことを待たせず、書くことは読むことを待たせない、とあります（参考文献 9）。

行の版は、システム列で覗けます。`row_versions` は、更新の前後で `ctid`（行の物理的な位置）と `xmin`（その版を作ったトランザクションの番号）を表示します。

```python
def row_versions(dsn: str) -> tuple[tuple, tuple]:
    """UPDATE の前後で、行の物理的な位置 ctid と作った取引の番号 xmin がどう変わるか。"""
    a, _ = fresh(dsn)
    query = "SELECT ctid::text, xmin::text, xmax::text, quantity FROM stock WHERE product_id = 1"
    before = a.execute(query).fetchone()
    a.execute("UPDATE stock SET quantity = 9 WHERE product_id = 1")
    after = a.execute(query).fetchone()
    return before, after
```

```text
(('(0,1)', '1533', '0', 10), ('(0,3)', '1534', '0', 9))
```

（番号は環境で変わります。見るのは「変わった」ことです。）数量が 10 から 9 になっただけでなく、位置が `(0,1)` から `(0,3)` に移り、`xmin` も変わりました。古い版は、見る必要のあるトランザクションがいなくなってから、VACUUM という掃除で回収されます（参考文献 9）。

教訓は、開きっぱなしの長いトランザクションがあると、それが見る可能性のある古い版を消せず、表が膨らむことです。トランザクションを短く終えるのは、性能の話でもあります。

## OLTP と OLAP

RDB が得意な仕事は、注文の登録、在庫の更新といった、小さな更新を大量に、正しく処理することです。これを OLTP（Online Transaction Processing、オンライントランザクション処理）と呼びます。一方、半年分の注文をカテゴリ別に集計するような、大量の行を読む仕事を OLAP（Online Analytical Processing、オンライン分析処理）と呼びます。

{{ table("b07-oltp-olap") }}

OLTP のデータベースで OLAP の集計を走らせると、重い問い合わせが業務の処理と資源を奪い合います。そこで、データを分析向けのデータベースへ運んで集計します。第2章で見た行指向と列指向の違いが効く場面で、第11章（データウェアハウス）で続きを扱います。

## 本番の DB から読むときの作法

分析のためにデータを取りに行く側も、本番の RDB の利用者です。守ることを表にまとめます。

{{ table("b07-read-rules") }}

PostgreSQL のレプリカ（ホットスタンバイ）は、主サーバーの変更を受け取りながら読み取り専用の問い合わせに答える複製です（参考文献 10）。主から少し遅れることがあるので、「たった今確定した注文」が見えない可能性を取り込みの設計で考えます。

接続の設定を守る形で、大きな表を少しずつ読むコードが次です。

```python
def read_in_batches(dsn: str, batch_size: int = 1000):
    """表を batch_size 件ずつ読む。接続の設定で、書き込みと長居を止めておく。"""
    with psycopg.connect(
        dsn,
        options="-c search_path=b07 -c default_transaction_read_only=on"
                " -c statement_timeout=30s -c idle_in_transaction_session_timeout=60s",
        application_name="de-book-extract",
    ) as conn:
        with conn.cursor(name="extract") as cur:  # 名前付きカーソル: サーバー側に結果を置き、少しずつ取る
            cur.execute("SELECT order_id, status FROM orders ORDER BY order_id")
            while rows := cur.fetchmany(batch_size):
                yield rows
```

`default_transaction_read_only=on` で書き込みを止め、`statement_timeout` と `idle_in_transaction_session_timeout` で長居を止めます。`application_name` は、監視画面で接続の持ち主がわかるための名札です。名前を付けたカーソル（`conn.cursor(name="extract")`）は、結果をサーバー側に置いたまま少しずつ取り出すので、全件をメモリへ載せる事故を避けられます（参考文献 11）。

```text
[1000, 1000, 500]
cannot execute DELETE in a read-only transaction
```

2 行目は、同じ設定の接続から `DELETE` を試したエラーです。

トランザクションを開きっぱなしの接続は、`pg_stat_activity` で見つけます。

```sql
SELECT pid, application_name, state, now() - xact_start AS open_for
FROM pg_stat_activity
WHERE xact_start IS NOT NULL AND pid <> pg_backend_pid()
ORDER BY xact_start
```

```text
[(5037, 'de-book-forgotten', 'idle in transaction', datetime.timedelta(microseconds=10179))]
```

`idle in transaction`（トランザクションを開いたまま何もしていない）という状態の接続が、名前つきで見えます（pid と時間は例です）。自分のツールが開きっぱなしにならないよう、`with` で接続を囲むのも作法のひとつです。

## よくある失敗

**読んで、計算して、書き戻す。** 在庫や残高を、アプリで読んだ値から計算して書き戻す形は、READ COMMITTED で更新が消えます。`SET quantity = quantity - n` の形でデータベースに計算させるか、行ロックを取ります。

**正規化しすぎる、または全くしない。** 分析用の表を毎回 6 つ結合するのも、アプリ用の表を 1 枚にして更新の異常を抱えるのも、目的に合っていません。書き込み側は正規化し、読む側は用途に合わせて崩します。

**制約を外して、後で直す。** 「取り込みを止めないために」と制約を外すと、欠陥のあるデータが入ります。後から直す手間は、入口で止める手間より大きくなります。強制されない製品でも、テストで同じ条件を確かめます。

**トランザクションを開いたまま待つ。** 外部 API の応答などを途中で待つと、ロックが保持され、MVCC の掃除も止まります。

## まとめ

- RDB は、同じ事実を 1 か所にだけ書く設計と制約で、書き込みの正しさを守る。
- 正規化は 1NF（セルに 1 値）、2NF（主キーの一部に従う列を出す）、3NF（主キー以外から決まる列を出す）と進み、更新の異常を消す。読む側には崩した表を別に作る。
- トランザクションの ACID のうち、分離性は程度を選べる。PostgreSQL の既定は READ COMMITTED で、更新の消失は原子的な更新・行ロック・REPEATABLE READ 以上で防ぎ、書き込みスキューは SERIALIZABLE とやり直しで防ぐ。
- ロックは待ちを、デッドロックは中止を生む。更新の順番をそろえ、トランザクションを短くする。
- MVCC は、更新を新しい版の追加として扱い、読むトランザクションが待たない。長いトランザクションは掃除を止める。
- 本番のデータベースは、レプリカから、読み取り専用・時間制限・小分け・名前付きで読む。

## 練習問題

**問1.** 次の表は第何正規形まで満たしていますか。違反している列を指摘して、直し方を書いてください。主キーは `(order_id, line_no)` です。列: `order_id, line_no, product_id, product_name, quantity, ordered_at`。

??? note "解答例"
    第1正規形までです。`ordered_at` は `order_id` だけで決まり、主キーの一部に従うので第2正規形を満たしません。`product_name` は主キー以外の `product_id` で決まるので、第3正規形も満たしません。`ordered_at` を `orders` 表へ、`product_name` を `products` 表へ出し、外部キーでつなぎます。

**問2.** `constraints.py` の `SHOP_DDL` で、`orders.status` の CHECK を外して第1章のデータの `orders` を全件入れると、`SHIPPED` が入ってしまいます。このとき、どんな集計が静かに間違えますか。CHECK を付けたまま取り込むには、どこで何をしますか。

??? note "解答例"
    第1章で見たとおり、`status = 'shipped'` で数える集計は、大文字の `SHIPPED` の 59 件を落とします。エラーが出ないので気づきません。CHECK を付けたまま取り込むには、変換の段階で `lower(status)` のようにそろえてから書き込みます。変換の抜けが、取り込みの失敗として見つかります。

**問3.** （手を動かす）`anomalies.py` の `lost_update` を READ COMMITTED で動かし、最終在庫が 8 になることを確かめてください。そのうえで、a の更新だけを `SET quantity = quantity - 3` の形に直すと最終在庫がどうなるかを予想し、確かめてください。b の更新は変えません。

??? note "解答例"
    a の更新を `quantity = quantity - 3` にすると、a は 10 - 3 = 7 を書きます。b は読んだ 10 から計算した 8 を、そのまま書き込むので、最終在庫は 8 のままです。片方を直しても、もう片方が「読んだ値を書き戻す」形であれば、更新は消えます。両方の更新を、データベースの中で引き算する形にそろえて初めて、`atomic_update` の結果の 5 になります。

**問4.** 毎晩、本番の PostgreSQL から注文を取り込むバッチが、あるとき業務の処理を遅くしました。この章の作法から、見直す点を 3 つ挙げてください。

??? note "解答例"
    (1) 主サーバーでなくレプリカから読む。(2) `statement_timeout` を設定し、名前付きカーソルなどで少しずつ読む。(3) `application_name` を付け、`pg_stat_activity` で自分の接続が長く開いていないかを見る。業務のピーク時間を避けることも効きます。

## 参考文献

1. PostgreSQL 16 Documentation. "5.4. Constraints". <https://www.postgresql.org/docs/16/ddl-constraints.html>
2. Google Cloud. "Use primary and foreign keys" (BigQuery). <https://cloud.google.com/bigquery/docs/primary-foreign-keys>
3. Snowflake Documentation. "Constraints". <https://docs.snowflake.com/en/sql-reference/constraints-overview>
4. William Kent. "A Simple Guide to Five Normal Forms in Relational Database Theory". Communications of the ACM, 26(2), 1983.
5. psycopg 3 Documentation. "Transactions management". <https://www.psycopg.org/psycopg3/docs/basic/transactions.html>
6. PostgreSQL 16 Documentation. "30.3. Write-Ahead Logging (WAL)". <https://www.postgresql.org/docs/16/wal-intro.html>
7. PostgreSQL 16 Documentation. "13.2. Transaction Isolation". <https://www.postgresql.org/docs/16/transaction-iso.html>
8. PostgreSQL 16 Documentation. "20.12. Lock Management" (`deadlock_timeout`). <https://www.postgresql.org/docs/16/runtime-config-locks.html>
9. PostgreSQL 16 Documentation. "13.1. Introduction" (MVCC). <https://www.postgresql.org/docs/16/mvcc-intro.html>
10. PostgreSQL 16 Documentation. "27.4. Hot Standby". <https://www.postgresql.org/docs/16/hot-standby.html>
11. psycopg 3 Documentation. "Cursors" (server-side cursors). <https://www.psycopg.org/psycopg3/docs/advanced/cursors.html>
12. E. F. Codd. "A Relational Model of Data for Large Shared Data Banks". Communications of the ACM, 13(6), 1970.

!!! tip "さらに深く"
    本番のデータベースの変更を負荷をかけずに追う方法は、応用編 第5章「CDC とイベント駆動」で扱います。

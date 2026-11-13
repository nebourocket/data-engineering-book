# 第11章 データウェアハウス

## この章でできるようになること

- データウェアハウス（DWH）が、アプリの DB（第7章）と何が違い、なぜ別に置くのかを説明できる。
- Inmon と Kimball の違い、データレイクとの関係を説明できる。
- 列指向エンジンが速い理由（必要な列だけ読む・ベクトル化・並列）を、自分の言葉で言える。
- パーティションとクラスタリングの違いを説明し、読み飛ばしが効いているかを `EXPLAIN ANALYZE` で確かめられる。
- ストレージと計算の分離を、課金の単位と結びつけて説明できる。
- BigQuery・Snowflake・Amazon Redshift・Databricks SQL の用語を対応づけて読める。
- コストを増やす書き方を見つけて直せる。マテリアライズドビューとアクセス制御の入口を使える。

第7章でアプリの DB、第8章でスタースキーマ、第10章で ELT と dbt を学びました。この章は、それらのデータを置いて、分析のクエリを受け止める場所の話です。クラウドサービスの契約は要りません。手元の DuckDB で、仕組みを実測して確かめます。コードは `examples/b11/` にあり、リポジトリの直下で動かします（出力は `work/` に作られます）。

## DWH の役割と歴史

DWH は、分析のために作るデータベースです。アプリの DB は **OLTP**（オンライン取引処理）に向けて作られています。1 件の注文を素早く、間違いなく登録・更新するのが仕事です。分析は **OLAP**（オンライン分析処理）と呼ばれ、数百万行を読んで集計します。この 2 つを同じ DB でやると、長い集計がアプリの注文処理を遅くします。そこで、データを分析用の別の場所へ写して集計します。これが DWH の出発点です。

違いを並べると、次のようになります。

- **書き方**: アプリは 1 件ずつ更新する。分析は大量の行を読んで集計する。
- **保存の形**: アプリの DB は行ごとにまとめる（行指向）。DWH は列ごとにまとめる（列指向。第2章）。
- **履歴**: アプリは最新の状態を持つ。DWH は変更の履歴を残す（第8章の SCD2）。
- **使う人**: アプリは利用者の操作。DWH はアナリストと BI（ダッシュボードなどを作る道具）。

DWH の作り方には、有名な 2 つの流派があります。Reis と Housley の *Fundamentals of Data Engineering* によると、Bill Inmon が 1989 年にデータウェアハウスの考え方を作り、Ralph Kimball が 1990 年代の初めにディメンショナルモデリングを作りました。

{{ table("b11-inmon-kimball") }}

Inmon は DWH を「主題ごとに整理され、統合され、書いたあとは変わらず、時間とともに履歴を持つ、意思決定のためのデータの集まり」と定義しました。要は、全社のデータを 1 か所に統合して正規化し、そこから部門向けのデータマート（特定の部門や用途に絞った小さな集まり）を切り出す考え方です。Kimball は反対側から、分析に使いやすい形（第8章のスタースキーマ）を部門ごとに作り、それを積み上げて全体にします。現場では、どちらか一方を厳密に守るより、混ぜて使うことが普通です。dbt（第10章）の `staging` から `marts` へ進む層は、「生のデータを整える層」と「分析向けに形を決めた層」を分けるという、両者に共通する考え方の表れです。

もう 1 つ、**データレイク**という言葉があります。形を問わず、生のファイルを安いストレージ（S3 のようなオブジェクトストレージ。第14章）にそのまま置く場所です。DWH は書くときに表の形を決める（スキーマオンライト）のに対し、レイクは読むときに形を決めます（スキーマオンリード）。レイクは安く、何でも置けます。その代わり、管理しないと「どこに何があるのか分からない」状態になりがちです。そこで、レイクの安さと DWH の扱いやすさを合わせた「レイクハウス」という作り方が出てきました。この章では名前だけ挙げます。仕組みは応用編で扱います。

## 列指向エンジンの中身

第2章で、列指向の利点を 2 つ学びました。必要な列だけ読めること、同じ種類の値が並ぶので圧縮が効くことです。第6章では、Parquet の行グループごとに最小値と最大値（ゾーンマップ）を持ち、条件に合わない行グループを読み飛ばせると学びました。ここでは、その上に載る 2 つの考え方を足します。

**ベクトル化実行。** クエリエンジンが 1 行ずつ「この値を取り出し、足し、次の行へ」と進むと、1 つの値を処理するたびに、関数の呼び出しや型の判断といった管理の手間がかかります。ベクトル化は、同じ列の値を数千個ぶんまとめて配列にし、1 回の呼び出しでまとめて処理します。管理の手間を、値ごとではなく塊ごとに 1 回にまとめられます。配列は CPU のキャッシュに収まりやすく、CPU が 1 命令で複数の値を処理する仕組み（SIMD）も使いやすくなります。DuckDB の文書によると、1 回に処理する塊（ベクトル）は既定で 2,048 個の値です。同じ列の値が連続して並んでいる列指向だから、成り立つ工夫です。

**MPP（大規模並列処理）。** 1 台の機械の CPU には限りがあります。そこで、データを多数のノード（計算機）やスロットに分けて持ち、各ノードが自分の分だけを集計して、最後に結果を合算します。ねぼすけ商店の売上明細を月ごとに分けた手元のデータで、この考え方を確かめます。月ごとの部分集計と、それを合算した値が、全体を一度に集計した値と一致するかを見ます。まず、データを作ります。

```bash
python examples/b11/partition_demo.py
```

次に、月ごとの売上と件数（部分集計）を出します。`run_query.py` は、`queries.sql` の名前付きクエリを 1 つ流します。

```bash
python examples/b11/run_query.py monthly_partial
```

```sql
SELECT month, sum(quantity * unit_price) AS revenue, count(*) AS n
FROM sales
GROUP BY month
ORDER BY month;
```

```text
┌─────────┬───────────┬───────┐
│  month  │  revenue  │   n   │
│ varchar │  int128   │ int64 │
├─────────┼───────────┼───────┤
│ 2026-01 │  54996750 │  8788 │
│ 2026-02 │ 144453800 │ 23378 │
│ 2026-03 │ 268815700 │ 43339 │
│ 2026-04 │ 258292600 │ 41852 │
│ 2026-05 │ 155564450 │ 25172 │
│ 2026-06 │  46827300 │  7639 │
└─────────┴───────────┴───────┘
```

売上の合計は、月ごとの合計を足せば全体になります。件数も同じです。では平均はどうでしょうか。次のクエリは、部分集計から全体の平均を 2 通りに求めます（`python examples/b11/run_query.py combine_partials`）。

```sql
SELECT sum(revenue) AS revenue,
       sum(revenue) / sum(n) AS avg_line,
       avg(revenue / n) AS avg_of_avgs
FROM (
  SELECT month, sum(quantity * unit_price) AS revenue, count(*) AS n
  FROM sales
  GROUP BY month
) AS partial;
```

```text
┌───────────┬───────────────────┬──────────────────┐
│  revenue  │     avg_line      │   avg_of_avgs    │
│  int128   │      double       │      double      │
├───────────┼───────────────────┼──────────────────┤
│ 928950600 │ 6186.075595333226 │ 6186.91698185768 │
└───────────┴───────────────────┴──────────────────┘
```

`avg_line` は、各ノードが「合計」と「件数」を持ち寄って、最後に割った平均です。全体を直接 `avg` した値（`direct_total` クエリ。テストで確かめています）と一致します。`avg_of_avgs` は、各ノードが平均を出して、その平均をさらに平均した値で、一致しません。件数の違う月を同じ重みで扱ってしまうからです。MPP のエンジンは、`avg` を内部で「合計と件数の組」に分けて処理します。書く側が意識する必要はあまりありませんが、自分で段階的に集計を組むとき（たとえば日次の集計表から月次を出すとき）は、平均を持ち越さず、合計と件数を持ち越します。

もう 1 つ覚えておきたいのは、ノード間でデータを動かす処理が高くつくことです。結合キーや集計キーが違うノードに散らばっていると、データを組み直して送り合う必要があります。この仕組みの詳しい説明は、応用編 第1章にあります。

## ストレージと計算の分離

昔の DWH は、データを計算機のディスクに置いていました。処理が足りなければノードを増やし、データも新しいノードへ分け直します。保存と計算が、いつも一緒に増えます。

いまの主要なクラウド DWH（BigQuery・Snowflake・Databricks SQL）は、データをクラウドのストレージに置き、計算はその上で必要なときだけ立ち上げます。Amazon Redshift も、RA3 ノードは管理ストレージ（S3 が土台）にデータを置く形で、世代によって一体型と分離型があります。分離すると、3 つのことができます。

1. 保存と計算を、別々に増減できる。
2. 同じデータを、複数の計算が同時に読める。夜間バッチ用と BI 用を分けると、お互いを遅くしない。
3. 使わない時間は、計算を止められる。

代わりに、2 つのことに気をつけます。1 つは、データがネットワークの向こうにあるので、読む量そのものを減らす工夫（この章のパーティションと並べ方）の価値が上がることです。もう 1 つは、課金が「動いた分」になるので、止め忘れや、大量に読むクエリが、そのままお金になることです。課金の話は、後の節に書きます。

## DWH へのデータの入れ方

DWH にデータを入れる方法は、大きく 2 つです。1 つは**ロード**で、ファイルの中身を DWH の表に読み込みます。製品ごとに専用のコマンドがあります（BigQuery の `bq load`、Snowflake と Databricks の `COPY INTO`、Redshift の `COPY`）。読み込んだあとは、製品の内部形式になり、並べ方やパーティションを DWH 側で最適化できます。もう 1 つは**外部テーブル**で、ストレージ上のファイルを、読み込まずに表として見せます。このあとの実験の `sales` ビューは、後者にあたります。ファイルを置くだけで見え、二重に保存しなくて済みますが、並べ方や統計の最適化は、ファイルの作り方に左右されます。

手元の DuckDB では、外部テーブルのように見える `sales` から、条件に合う行だけを表へ読み込めます。

```sql
CREATE TABLE sales_loaded AS
SELECT * FROM sales WHERE month = '2026-03';
```

`python examples/b11/run_query.py load_into_table` で流すと、3 月の 43,339 行が表 `sales_loaded` に入ります（テストで確かめています）。定期的なロードの組み方は、第9章と第12章の話です。

## 手を動かす: パーティションと読み飛ばし

**パーティション**は、表を、ある列の値ごとに別のフォルダやファイルに分けて置くことです。分ける列は、日付がもっとも多く使われます。**プルーニング**（剪定）は、クエリの条件が分ける列に対するものだと、関係のないパーティションを最初から開かないことです。

ねぼすけ商店の注文と明細をつなぎ、seed を 20 通り重ねて約 15 万行の売上明細を作ります（1 回分では小さすぎて差が見えません）。これを、注文月（`2026-03` の形）ごとに Parquet に分けて書きます。

```python
def write_partitioned(root: Path, rows: list[dict]) -> None:
    """month 列（'2026-03' の形）の値ごとに、root/month=2026-03/ というフォルダへ書き分けます。"""
    root.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("t", pa.Table.from_pylist(rows))
    con.execute("""
        CREATE TABLE s AS
        SELECT *, strftime(CAST(ordered_at AS TIMESTAMP), '%Y-%m') AS month FROM t""")
    con.execute(f"COPY s TO '{root}' (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (month), OVERWRITE_OR_IGNORE)")
    con.close()
```

`PARTITION_BY (month)` が、分け方の指定です。`work/sales/month=2026-03/data_0.parquet` のようなフォルダ名になります。この `列名=値` の形を、Hive 形式と呼びます。Hadoop 時代の Hive というソフトが決めた並べ方で、いまも Spark・DuckDB・BigQuery の外部テーブルなど、多くの道具が読めます。読むときは、全体を 1 つのビューとして開きます。

```python
def open_sales(root: Path) -> duckdb.DuckDBPyConnection:
    """Hive 形式のフォルダ全体を、sales という 1 つのビューとして開きます。"""
    con = duckdb.connect()
    con.execute(f"CREATE VIEW sales AS SELECT * FROM read_parquet('{root}/*/*.parquet', hive_partitioning = true)")
    return con
```

`hive_partitioning = true` は、フォルダ名の `month=2026-03` を `month` 列として読む指定です。ファイルの中には `month` 列は入っていません。次の 4 つのクエリで、読む量を比べます。

```sql
SELECT sum(quantity * unit_price) AS revenue
FROM sales;
```

```sql
SELECT sum(quantity * unit_price) AS revenue
FROM sales
WHERE month = '2026-03';
```

```sql
SELECT sum(quantity * unit_price) AS revenue
FROM sales
WHERE ordered_at >= '2026-03-01' AND ordered_at < '2026-04-01';
```

```sql
SELECT *
FROM sales
WHERE month = '2026-03';
```

1 つ目は条件なしです。2 つ目は、パーティション列 `month` で絞ります。3 つ目は、同じ 3 月を、パーティション列ではなく `ordered_at` の範囲で絞ります。4 つ目は、2 つ目と同じ条件で、`SELECT *` で全列を取ります。読んだ量は、`EXPLAIN ANALYZE` の出力から取り出します。1 つのクエリだけを見るなら、`python examples/b11/run_query.py month_filter`（開いたファイル数と読んだバイト数も出ます）です。

```python
def scan_stats(con: duckdb.DuckDBPyConnection, sql: str) -> dict:
    """EXPLAIN ANALYZE の出力から、開いたファイル数と読んだバイト数を取り出します（DuckDB 2.0 の出力形式）。"""
    plan = con.execute("EXPLAIN ANALYZE " + sql).fetchall()[0][1]
    read = int(re.search(r"Total Files Read: (\d+)", plan).group(1))
    value, unit = re.search(r"Data Read:\s+([\d.]+) (B|kB|MB|GB)", plan).groups()
    return {"files_read": read, "bytes_read": round(float(value) * UNITS[unit])}
```

実行すると、次のように出ます（DuckDB 2.0.0 の出力です）。

```text
files: 6
full_scan          files_read=6  bytes_read=264,500
month_filter       files_read=1  bytes_read=80,200
date_filter_only   files_read=6  bytes_read=275,900
select_star        files_read=1  bytes_read=347,700
```

![パーティションの条件の有無で、開いたファイル数と読んだバイト数がどう変わるか](../assets/figures/b11_partition_pruning.svg)

この図は、`examples/figures/b11_partition_pruning.py` が同じ測定をして描いたものです。バイト数は、実行のたびに数百バイト揺れます。表示された値の読み方は、次のとおりです。

- **条件なし**: 6 ファイルを開き、約 265 kB を読みます。
- **`month = '2026-03'`**: 1 ファイルだけを開き、約 80 kB です。3 月は全体の約 29 %（43,339 / 150,168 行）で、読む量は条件なしの約 30 % です。
- **`ordered_at` だけ**: 6 ファイルを開き、読んだ量は条件なしよりも多い約 276 kB です。
- **`SELECT *`**: 同じ 1 ファイルでも、約 348 kB と、2 列だけのときの 4 倍以上です。

3 つ目が、いちばん読み解くのが難しいところです。EXPLAIN ANALYZE の出力（一部）を見ます。

```text
│ Projections: quantity, unit_price                            │
│ Filters:                                                     │
│ (ordered_at >= '2026-03-01') AND (ordered_at < '2026-04-01') │
│ Total Files Read: 6                                          │
│ Row Groups Scanned: 1 / 6                                    │
```

`Row Groups Scanned: 1 / 6` とあるので、行グループ（Parquet の読み飛ばし単位）は 1 つしか読んでいません。第6章のゾーンマップが働き、`ordered_at` の最小値と最大値が条件に合わない 5 つを読み飛ばしたのです。それでも読む量が減らなかったのは、2 つの理由が考えられます。1 つは、`ordered_at` 自体を読む必要が出たことです。3 月のファイルの `ordered_at` 列は、圧縮後で約 130 kB（`parquet_metadata` で確かめた値）あり、集計に使う 2 列の合計より大きい列です。残りの差は、6 つのファイルを開いて、フッター（ファイルの末尾にある、列の位置や統計を書いたメタデータ）を読む分だと思われますが、確かめてはいません。

2 つ目のクエリなら、そもそも 1 ファイルしか開かず、`ordered_at` も読みません。パーティション列を条件に使うことには、読み飛ばしのためだけではなく、条件の列を読まずに済む、という意味もあります。なお、この例で `ordered_at` の条件がある程度効いたのは、`ordered_at` の値が月ごとのファイルにきれいに分かれていたからです。パーティションを作ったときの副産物です。

「パーティション列を使わなければ必ず全部を読む」わけではありません。DuckDB 2.0.0 は、パーティション列を関数で包んだ条件（`substr(month, 1, 7) = '2026-03'`）でも、1 ファイルに絞れました（`month_wrapped` クエリ。テストで確かめています）。ほかの製品では、パーティション列そのものを定数と比べる形でないと効かない場合があります。使う製品の文書で、プルーニングが効く条件の書き方を確かめます。

分け方の選び方にも決まりがあります。

- **ほとんどのクエリが条件に使う列にする。** 日付がもっとも多いのは、分析が「期間」で絞ることが多いからです。
- **分けすぎない。** `customer_id` で分けると、500 の小さなフォルダができます。小さなファイルが大量にあると、開く手間が増えて逆に遅くなります。ファイルの大きさと、パーティションの数の上限は、製品ごとに文書があります。
- **分けた単位で作り直せるようにする。** 1 日の分を 1 パーティションにすると、その日だけ置き換えられます。第12章の日次ジョブは、この形で動きます。

## クラスタリングとソートキー

パーティションは、フォルダを分ける粗い分け方です。もう 1 つ、**クラスタリング**（並べ方の指定）があります。ファイルの中の行を、よく絞る列の順に並べておきます。そうすると、各行グループの最小値と最大値の幅が狭くなり、条件に合わない行グループを読み飛ばせます。

同じ行を、ばらばらの順と `customer_id` の順で 2 つの Parquet に書き、`customer_id = 42` を数えます（`clustering_demo.py` は、絞る列と値を `--column` と `--value` で変えられます）。

```python
def write_both(workdir: Path) -> dict[str, Path]:
    """同じ行を、並べ方だけ変えて 2 つのファイルに書きます（random() は並べ替えの乱数です）。"""
    workdir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("t", pa.Table.from_pylist(sales_lines()))
    paths = {"ばらばら": workdir / "shuffled.parquet", "customer_id 順": workdir / "sorted.parquet"}
    orders = {"ばらばら": "random()", "customer_id 順": "customer_id"}
    for label, path in paths.items():
        con.execute(f"COPY (SELECT * FROM t ORDER BY {orders[label]}) TO '{path}' "
                    f"(FORMAT parquet, ROW_GROUP_SIZE {ROW_GROUP})")
    con.close()
    return paths
```

行グループは 10,000 行にしています。実行は次のとおりです。

```bash
python examples/b11/clustering_demo.py
```

```text
ばらばら           行グループ 15 / 15  読んだバイト数 232,900
customer_id 順  行グループ 1 / 15  読んだバイト数 16,700
```

答えは同じ件数のままで、読む量が約 14 分の 1 になりました。ただし、効くのは並べた列だけです。`customer_id` 順のファイルに `--column product_id --value 7` で絞っても、15 / 15 を全部読みます（練習問題 3）。

製品ごとの名前は、後の対応表にまとめます。注意点は 3 つです。

- 並べる列は、最初の 1 つが強く効きます。複数の列を指定するときは、よく絞る列を先に書きます。
- データが後から増えると並びが崩れ、効きが落ちます。並べ直しを製品が自動で行うものと、手で行うものがあります。
- 並べ替えは、書き込みのときの手間です。読む回数が少ない表には、割に合いません。

日付で絞るならパーティション、それ以外でよく絞る列（顧客や商品、カテゴリ）があるならクラスタリング、と使い分けるのが基本です。

## マテリアライズドビュー

ビュー（第6章の `daily_sales` のような、名前を付けたクエリ）は、読むたびに計算し直します。**マテリアライズドビュー**は、クエリの結果を保存しておくビューです。毎日同じ集計を何度も見るダッシュボードのように、元の表が大きく、結果が小さいときに効きます。

代わりに、元の表が変わると、保存した結果は古くなります。古さをどう直すかは、製品によって違います。PostgreSQL は、`REFRESH` を自分で実行します。第7章と同じ PostgreSQL 16 で試します。事前に `docker compose up -d --wait` でサービスを起動します（README の「サービスを使う章」。接続先は環境変数 `PG_DSN`）。次の `pg_demo.sh` は、`compose.yaml` の `postgres` サービスの `psql` に、4 つの SQL ファイルを順に流します。

```bash
PSQL="docker compose exec -T postgres psql -U deb -d deb"

$PSQL -f - < examples/b11/setup_pg.sql
$PSQL -f - < examples/b11/matview_flow.sql
```

`setup_pg.sql` は、スキーマ `b11`、3,000 明細の表 `sales_lines`、そこから作るマテリアライズドビュー `daily_revenue` を用意します。ビューの定義は次のとおりです（一意のインデックスは、後の `CONCURRENTLY` に必要です）。

```sql
CREATE MATERIALIZED VIEW b11.daily_revenue AS
SELECT CAST(ordered_at AS date) AS d, sum(quantity * unit_price) AS revenue
FROM b11.sales_lines
GROUP BY 1;

CREATE UNIQUE INDEX daily_revenue_d ON b11.daily_revenue (d);
```

`matview_flow.sql` は、「合計を見る → 元の表に 1 行足す → もう一度見る → `REFRESH` → もう一度見る」の流れです。

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY b11.daily_revenue;
```

```text
 revenue 
---------
 4799000
(1 row)

INSERT 0 1
 revenue 
---------
 4799000
(1 row)

REFRESH MATERIALIZED VIEW
 revenue 
---------
 4800000
(1 row)
```

元の表に 1,000 円の明細を足しても、`REFRESH` までは合計が 4,799,000 のまま古く、`REFRESH` のあとに 4,800,000 になりました。`CONCURRENTLY` を付けると、更新中も読み取りを止めません。同じ流れは `examples/b11/test_b11_warehouse.py` でも確かめています。

BigQuery・Snowflake・Redshift・Databricks にもマテリアライズドビューがありますが、自動で更新される範囲、使える SQL の書き方、料金のかかり方は製品ごとに違います。導入の前に、使う製品の文書で制限を確かめます。第10章の dbt で、モデルを `table` にして結果を保存しておくのも、同じ考え方です。「毎回計算するか、保存して古さを引き受けるか」の選択になります。

## 主要サービスの用語の対応

名前は違っても、同じ役割のものがあります。次の表で、用語を対応づけます。

{{ table("b11-service-terms") }}

使い始めの頃は、「パーティション」「クラスタリング」「ソートキー」の名前の違いに戸惑います。仕組みは、この章で実測したものと同じです。分ける、並べる、保存する、のどれを指す用語かを考えれば、読み解けます。

課金は、サービスで考え方が違います。(2026年11月時点) の課金の単位を、次の表にまとめます。出典は参考文献に挙げた各社の公式ページです。

{{ table("b11-billing") }}

大きく 2 つの考え方があります。**読んだ量に払う**（BigQuery のオンデマンド）と、**計算を動かした時間に払う**（Snowflake・Redshift・Databricks SQL、BigQuery のキャパシティ）です。前者では、`SELECT *` と期間の指定漏れが、そのまま請求に出ます。後者では、同じクエリでも、ウェアハウスを大きくして短く終えるか、小さく長く動かすかで総量が変わり、止め忘れが請求に出ます。

具体的な金額は、リージョン・エディション・契約で変わり、改定もあるので、この本には書きません。出典の公式ページで確かめてください。BigQuery には、クエリを実行せずに処理するバイト数を見積もる dry run があります。ほかの製品でも、実行前に `EXPLAIN` を見る、実行後にクエリ履歴で読んだ量を見る、という手順を習慣にします。

## コストを増やす書き方と直し方

読む量を増やす書き方は、パターンが決まっています。

{{ table("b11-costly-queries") }}

この中で、いちばん多いのは `SELECT *` です。先の実測で、同じ 1 ファイルでも、2 列のときの約 80 kB が約 348 kB になりました。列指向では、読む量が列の数に比例して増えます。確認のために中身を見たいときに `LIMIT 10` を付けても、読む量が減るとは限りません。BigQuery の料金に関する文書には、`SELECT *` に `LIMIT` を付けても読むデータ量は変わらない、という趣旨の説明があります。製品とクエリの形で変わるので、実行後に読んだ量を確かめます。

直し方の基本は、「必要な列だけを書く」「パーティション列を、そのままの形で条件に書く」「大きな表から同じ集計を繰り返さない」の 3 つです。クエリを直したら、読んだ量が下がったかを、`EXPLAIN ANALYZE` や製品のクエリ履歴で必ず確かめます。確かめない最適化は、効いたかどうかが分かりません。

## アクセス制御の入口

DWH には、会社のデータが集まります。誰が何を読めるかの決め方は、最初から考えておきます。基本は 2 つです。

- **最小権限。** 必要な人に、必要なものだけ許す（第3章の権限の考え方と同じです）。
- **個人ではなく、ロール（役割）に許す。** 「アナリスト」というロールを作り、人をそのロールに入れます。人が入れ替わっても、権限の設定は変わりません。

PostgreSQL では、次のように書きます（`$PSQL -f - < examples/b11/grant_pg.sql`。`SET ROLE` で、そのロールになって読んでみます）。他の製品も `GRANT` の考え方は近いですが、権限を付ける対象の階層や名前は製品ごとに違います（BigQuery は IAM を使います）。

```sql
CREATE ROLE b11_analyst NOLOGIN;
GRANT USAGE ON SCHEMA b11 TO b11_analyst;
GRANT SELECT ON b11.daily_revenue TO b11_analyst;
```

```text
 days 
------
   31
(1 row)

psql:<stdin>:7: ERROR:  permission denied for table sales_lines
```

このロールは、集計済みのマテリアライズドビューだけを読めます。同じスキーマにある元の表を読もうとすると、権限エラーになります（出力は、ロールを使って 2 つの `SELECT` を試した結果です）。後片付けは `cleanup_pg.sql` で行います。「生のデータは取り込みジョブだけ、アナリストには整えたマートだけ」という分け方は、アクセス制御の基本の型です。列や行の単位で見せ方を変える機能（個人情報の列を隠すなど）は、製品ごとに用意されています。個人情報の扱いは、応用編 第9章で扱います。

## よくある失敗

- アプリの DB に、そのまま分析のクエリを流して、注文処理を遅くする。
- パーティション列を条件に書かず、毎回全期間を読む。
- `customer_id` のような値の種類が多い列でパーティションを分け、小さなファイルが大量にできる。
- 平均や中央値を、日次や月次の集計表から「平均の平均」で出して、数字がずれる。
- マテリアライズドビューを作ったまま、更新が止まっていることに気づかない。
- 計算資源を止め忘れる。課金が時間単位の製品では、使っていない時間も請求に出る。
- 課金の見積もりを、手元の DuckDB の読んだ量と取り違える。数え方は製品ごとに違い、比の目安にしかならない。
- 「全員が全部を読める」状態で DWH を公開する。

## まとめ

- DWH は、アプリの DB から分析を切り離すための場所です。Inmon は統合してからマートを切り出し、Kimball は部門ごとのスタースキーマを積み上げます。現場ではそれを混ぜます。
- データレイクは、生のファイルを安く置く場所です。DWH は書くときに形を決めます。両方を合わせた形（レイクハウス）は、応用編 第3章で扱います。
- 列指向エンジンは、必要な列だけを、ベクトル化と並列処理で速く読みます。分散で集計するときは、平均を「合計と件数」に分けて合算します。
- パーティションは、フォルダで分ける粗い読み飛ばしです。パーティション列を、そのままの形で条件に書きます。クラスタリングは、ファイルの中の並べ方で、並べた列にだけ効きます。
- ストレージと計算の分離では、課金が「読んだ量」か「動かした時間」になります。止め忘れと `SELECT *` が、そのまま請求になります。
- マテリアライズドビューは、結果を保存する代わりに、古さを引き受けます。更新の仕組みは製品ごとに違います。
- アクセス制御は、最小権限と、ロール単位の許可が基本です。

## 練習問題

問 1. 4 月と 5 月の売上の合計を出してください。開いたファイルの数は何個になりますか。

??? note "解答例"
    ```sql
    SELECT sum(quantity * unit_price) AS revenue
    FROM sales
    WHERE month IN ('2026-04', '2026-05');
    ```

    答えは 413,857,050 で、開いたファイルは 6 個のうち 2 個です（`python examples/b11/run_query.py ex_two_months` の出力にある `files_read` が 2）。月の売上の表（258,292,600 と 155,564,450）を足した値と一致します。パーティション列 `month` が `IN` で並んでいても、必要なフォルダだけを開きます。

問 2. 3 月 5 日の 1 日分の売上を、`month = '2026-03'` の条件を付けた場合と付けない場合で出してください。開いたファイルの数と、読んだバイト数がどう違いますか。

??? note "解答例"
    ```sql
    SELECT sum(quantity * unit_price) AS revenue
    FROM sales
    WHERE month = '2026-03'
      AND ordered_at >= '2026-03-05' AND ordered_at < '2026-03-06';
    ```

    ```sql
    SELECT sum(quantity * unit_price) AS revenue
    FROM sales
    WHERE ordered_at >= '2026-03-05' AND ordered_at < '2026-03-06';
    ```

    答えは同じ 7,121,050 です。開いたファイルは、`month` を付けたほうが 1 個、付けないほうが 6 個です。読んだバイト数は約 210 kB と約 276 kB（実行のたびに少し揺れます）で、差はファイル数の差ほど大きくありません。1 日を絞るには `ordered_at` 列そのものを読む必要があり、その列が大きいためです。1 日が小さな行グループに収まるように、日付順に並べておくと、さらに読む量を減らせます（先のクラスタリングの考え方です）。

問 3. クラスタリングの例で、`customer_id` 順に並べたファイルに `product_id = 7` で絞って数えたとき、読む行グループはいくつですか。理由も説明してください。

??? note "解答例"
    `examples/b11/clustering_demo.py` の `row_groups_scanned` に `column="product_id", value=7` を渡すと、`customer_id` 順のファイルでも 15 / 15 の行グループをすべて読みます（ばらばらのファイルも同じ 15 / 15 です）。並べたのは `customer_id` だけで、`product_id` は各行グループにばらばらに入っています。どの行グループにも、最小値と最大値の幅に 7 が入ってしまうので、読み飛ばせません。クラスタリングは、並べた列を条件にするクエリにだけ効きます。

問 4. 月ごとの部分集計（月、売上の合計、件数）が表に残っているとします。この表だけから、全期間の 1 明細あたりの平均売上を出す式を書いてください。

??? note "解答例"
    `sum(revenue) / sum(n)` です。各月の `revenue` は月の売上の合計、`n` は月の明細数なので、全部足した合計を、全部足した件数で割れば、全体の平均になります。実測では 6186.0756 で、全体を直接 `avg` した値と一致します。`avg(revenue / n)` は月ごとの平均の平均で、6186.9170 と一致しません。月ごとの件数が違うのに、同じ重みで足しているからです。

## 参考文献

- Joe Reis, Matt Housley, *Fundamentals of Data Engineering*, O'Reilly, 2022. 第8章 “Data Modeling”（Inmon と Kimball の説明）。
- W. H. Inmon, *Building the Data Warehouse*, Wiley（DWH の定義）。 Ralph Kimball, Margy Ross, *The Data Warehouse Toolkit*, 3rd ed., Wiley, 2013（ディメンショナルモデリング）。
- DuckDB Documentation, “Hive Partitioning”, <https://duckdb.org/docs/2.0/data/partitioning/hive_partitioning>
- DuckDB Documentation, “Analyzing Query Performance (EXPLAIN ANALYZE)”, <https://duckdb.org/docs/2.0/guides/meta/explain_analyze>
- DuckDB Documentation, “Execution Format（ベクトルの大きさ）”, <https://duckdb.org/docs/2.0/internals/vector>
- DuckDB, “Why DuckDB”（列指向とベクトル化実行）, <https://duckdb.org/why_duckdb>
- P. Boncz, M. Zukowski, N. Nes, “MonetDB/X100: Hyper-Pipelining Query Execution”, CIDR 2005, <https://www.cidrdb.org/cidr2005/papers/P19.pdf>
- Google Cloud, BigQuery “Pricing”（2026年11月時点）, <https://cloud.google.com/bigquery/pricing>
- Google Cloud, BigQuery “Introduction to partitioned tables”, <https://cloud.google.com/bigquery/docs/partitioned-tables> ／ “Introduction to clustered tables”, <https://cloud.google.com/bigquery/docs/clustered-tables> ／ “Introduction to materialized views”, <https://cloud.google.com/bigquery/docs/materialized-views-intro> ／ “Estimate and control costs”, <https://cloud.google.com/bigquery/docs/best-practices-costs>
- Snowflake Documentation, “Understanding compute cost”（2026年11月時点）, <https://docs.snowflake.com/en/user-guide/cost-understanding-compute> ／ “Micro-partitions & Data Clustering”, <https://docs.snowflake.com/en/user-guide/tables-clustering-micropartitions> ／ “Materialized views”, <https://docs.snowflake.com/en/user-guide/views-materialized>
- Amazon Redshift, “Pricing”（2026年11月時点）, <https://aws.amazon.com/redshift/pricing/> ／ “Sort keys”, <https://docs.aws.amazon.com/redshift/latest/dg/c_best-practices-sort-key.html> ／ “Data warehouse system architecture”, <https://docs.aws.amazon.com/redshift/latest/dg/c_high_level_system_architecture.html> ／ “Materialized views”, <https://docs.aws.amazon.com/redshift/latest/dg/materialized-view-overview.html>
- Databricks, “Databricks SQL pricing”（2026年11月時点）, <https://www.databricks.com/product/pricing/databricks-sql> ／ “SQL warehouses”, <https://docs.databricks.com/aws/en/compute/sql-warehouse/> ／ “Use liquid clustering for tables”, <https://docs.databricks.com/aws/en/delta/clustering>
- PostgreSQL Documentation, “CREATE MATERIALIZED VIEW”, <https://www.postgresql.org/docs/current/sql-creatematerializedview.html> ／ “GRANT”, <https://www.postgresql.org/docs/current/sql-grant.html>

!!! tip "さらに深く"
    レイクハウスとテーブルフォーマットは応用編 第3章「レイクハウスとテーブルフォーマット」、読む量とお金の最適化は応用編 第10章「コスト最適化」で扱います。

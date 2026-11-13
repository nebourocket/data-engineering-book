# 第13章 データ品質とテスト

## この章でできるようになること

- データ品質を 8 つの観点(正確さ・完全性・一意性・鮮度・量・スキーマ・分布・参照整合性)に分け、それぞれを SQL の数字で測れる。
- 確認を入れる場所(取り込み時・変換時・提供前)を選び、「止める」か「知らせる」かを理由つきで決められる。
- 確認の結果を表に残し、不合格が続いている確認や観点ごとの合格率を SQL で見られる。
- 日別の件数の前日比と Z スコアで、分布の変化を簡単に見つけられる。
- 悪い行を捨てずに隔離(quarantine)テーブルへ分け、件数が合うことを確かめられる。
- dbt のテストに閾値と重大度を付け、独自の確認を単発テストとして書ける。
- 確認が落ちたとき、データの持ち主へどの順番で何を伝えるかを決められる。

第5・6章の SQL が書けて、第10章で dbt のテストを一度見ていれば進めます。使うデータは、これまでと同じ架空の通販「ねぼすけ商店」です。このデータには、意図的に 5 種類の欠陥が入れてあります(`examples/common/neboske_shop.py` の説明を参照)。この章は、その欠陥を実際に見つけて、止めて、知らせる仕組みを作る章です。

## データ品質とは何か

データ品質は、「そのデータは、使う目的に対して足りているか」で決まります。同じ表でも、用途によって合否が変わります。ねぼすけ商店の行動ログには、発生から 1 日以上遅れて届く行があります。月次の売上報告なら誤差の範囲ですが、「今この瞬間のカート放棄」を見る画面では致命的です。品質に絶対の基準はなく、「誰が、何のために使うか」を先に決めてから、観点を選びます。

観点は、次の 8 つに分けると整理しやすくなります(分け方は文献によって少しずつ違います。ここでは、現場で確認を書くときに使いやすい形にしました)。

{{ table("b13-dimensions") }}

表の「測り方」を、1 つずつ補います。

**正確さ**は、一番測りにくい観点です。「正解」を知らないと比べられないからです。そこで、(a) 決まった規則に照らす(`status` は 4 種類のどれか)、(b) 別の正本と突き合わせる(明細の単価は商品表の価格と同じはず)の 2 つで近づきます。突き合わせる相手が無いデータの正確さは、データだけからは保証できません。

**完全性**は、「ある値が欠けていないか」と「あるはずの行が来ているか」の 2 つがあります。前者は NULL の割合で、後者は取り込み元の件数との比較で測ります。

**一意性**は、キーが重複していないかです。重複は、集計の合計を静かに膨らませます。しかも、エラーにならずに結果が出てしまうので、気づきにくい欠陥です。

**鮮度**は、データがどれだけ新しいかです。「最新の行の時刻と、今との差」で測ります。似た言葉に「遅延」がありますが、これは別の話です。鮮度は表全体の新しさ、遅延は個々の行が発生から届くまでにかかった時間です。ねぼすけ商店の遅れて届く行は、表の鮮度が保たれていても起こります。

**量**は、行数が普段の範囲に入っているかです。ゼロ件のファイルが取り込まれたのに、エラーにならずに空の表ができる事故を捕まえます。

**スキーマ**は、列の名前と型が約束どおりかです。上流の都合で列が消えたり型が変わったりしたことを、下流のエラーになる前に見つけます(契約として扱う方法は応用編で触れます)。

**分布**は、値の偏りが普段と同じかです。件数・平均・割合を、過去と比べます。

**参照整合性**は、参照先が存在するかです。注文の `customer_id` が顧客表にあるか、を見ます。PostgreSQL のような DBMS(データベース管理システム)では、外部キー制約を宣言すればデータベースが守ってくれます(第7章)。一方、クラウドのデータウェアハウス(分析用の大きな DB)では事情が違います。たとえば BigQuery は主キーや外部キーを宣言できますが `NOT ENFORCED`(強制しない)で、Snowflake も標準のテーブルでは NOT NULL 以外の制約を強制しません(参考文献)。宣言があっても守られていると思い込まず、自分で確認を書きます。

## どこで確かめるか

確認を入れる場所は、データの流れに沿って 3 か所あります。

{{ table("b13-where") }}

原則は、悪いデータを早く見つけるほど安く直せる、です。ただし、入口で厳しくしすぎると、取り込み自体が止まります。第9章で見たように、取り込んだ生データはそのまま残す(landing や raw)のが基本です。生データは「受け取ったとおり」を保ち、確認は次の層から効かせます。入口で止めるのは、ファイルが空、必須の列が無い、のように「中身を読む前に分かる壊れ方」に絞ると、運用が楽になります。

変換時は、確認を一番たくさん置く場所です。結合のあとに行数が変わっていないか(1 対多の結合で行が増える事故は、第5章の JOIN で見ました)、結合キーに NULL が混ざっていないかを見ます。提供前は、ダッシュボードや他の部署に渡す直前の、最後の関所です。前日比のような「分布」の確認はここに置くと効きます。

## 止めるか、知らせるか

確認が不合格のとき、できることは 2 つです。処理を止めるか、止めずに知らせるかです。この選び方を「重大度」(severity)と呼びます。本書では次の 2 段階を使い、記録だけの段を足すこともあります。

{{ table("b13-severity") }}

決め方は、「このデータが下流に流れたとき、後から直せるか」です。重複した行動ログをそのまま集計に流せば、昨日のダッシュボードの数字が膨らみます。誰かがその数字を見て判断したあとでは、取り返せません。こういうものは error にして止めます。メールの欠けが 4% あっても、その日の売上の数字は変わりません。こちらは持ち主に知らせれば足りるので warn です。

もう 1 つ決めるのが、閾値です。ゼロしか許さない確認(主キーの重複、参照先の欠落)と、割合で許す確認(メールの欠け、遅れて届く行)があります。閾値は、まず実測の値を見て決めます。ねぼすけ商店の `email` の欠けは約 4% でした。最初の閾値を 2% にして warn にすれば、通知が出て、持ち主が直すかどうかを話し合えます。逆に、確認を通すために閾値を現状に合わせて緩めると、確認は何も守らなくなります。閾値を変えるときは、理由を記録に残してください。

もう 1 つ大事なのは、「測れなかった」を合格にしないことです。たとえば `NULL` との比較は、真でも偽でもなく NULL になります(第5章)。`CASE WHEN 条件 THEN 1 ELSE 0 END` の条件が NULL になると、ELSE に落ちて 0(合格)になってしまいます。表が空だった、標準偏差が計算できなかった、というときに静かに通ります。この章の実行器は、測れなかった確認を不合格にします。

## まず SQL で確かめる

確認は、まず SQL で書いて、結果を目で見るところから始めます。クエリは `examples/b13/queries.sql` にあり、第5章の `run_sql.py` で 1 本ずつ流せます。`shop.duckdb` が無ければ、ねぼすけ商店のデータから作られます。

```bash
python examples/b05/run_sql.py examples/b13/queries.sql null_ratio dup_emails dup_events
```

最初は、メールの欠けです。

```sql
SELECT count(*) AS total,
       count(*) FILTER (WHERE email IS NULL) AS null_emails,
       round(100.0 * count(*) FILTER (WHERE email IS NULL) / count(*), 2) AS null_pct
FROM customers;
```

```text
┌───────┬─────────────┬──────────┐
│ total │ null_emails │ null_pct │
│ int64 │    int64    │  double  │
├───────┼─────────────┼──────────┤
│   505 │          20 │     3.96 │
└───────┴─────────────┴──────────┘
```

`FILTER (WHERE ...)` は集計関数の対象行を絞る書き方で、標準 SQL です。PostgreSQL と DuckDB で使えます。BigQuery には無く、`COUNTIF(条件)` か `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` で書きます。`count(列)` は NULL を数えず、`count(*)` は数える、という違いも使っています(第5章)。

次は、同じメールでの二重登録です。

```sql
SELECT email, count(*) AS n, list(customer_id ORDER BY customer_id) AS customer_ids
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING count(*) > 1
ORDER BY email;
```

```text
┌──────────────────────┬───────┬──────────────┐
│        email         │   n   │ customer_ids │
│       varchar        │ int64 │   int64[]    │
├──────────────────────┼───────┼──────────────┤
│ user0165@example.com │     2 │ [165, 505]   │
│ user0296@example.com │     2 │ [296, 501]   │
│ user0307@example.com │     2 │ [307, 502]   │
│ user0396@example.com │     2 │ [396, 503]   │
│ user0420@example.com │     2 │ [420, 504]   │
└──────────────────────┴───────┴──────────────┘
```

`list(... ORDER BY ...)` は DuckDB の書き方で、PostgreSQL では `array_agg(customer_id ORDER BY customer_id)` です。5 件の重複はどれも、古い顧客 ID と 501 以降の ID の組です。どちらを残すかは、機械では決められません(購入履歴が両方にあるかもしれません)。このため、あとで見る隔離ではなく、持ち主に確認する案件として扱います。

行動ログの二重配信は、行数と ID の種類数の差で見えます。

```sql
SELECT count(*) AS total, count(DISTINCT event_id) AS distinct_ids,
       count(*) - count(DISTINCT event_id) AS excess_rows
FROM events;
```

```text
┌───────┬──────────────┬─────────────┐
│ total │ distinct_ids │ excess_rows │
│ int64 │    int64     │    int64    │
├───────┼──────────────┼─────────────┤
│  4040 │         4000 │          40 │
└───────┴──────────────┴─────────────┘
```

表記ゆれは、値の種類ごとの件数を出して見ます。

```sql
SELECT status, count(*) AS n FROM orders GROUP BY status ORDER BY n DESC;
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

`SHIPPED` が 59 行あり、`shipped` と別の値として数えられます。`GROUP BY` で値の一覧を出すのは、許す値が分からないときの最初の一手です。

参照整合性は、LEFT JOIN で相手が NULL になる行を数えます。

```sql
SELECT count(*) AS orphan_orders
FROM orders AS o
LEFT JOIN customers AS c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;
```

```text
┌───────────────┐
│ orphan_orders │
│     int64     │
├───────────────┤
│             0 │
└───────────────┘
```

0 は正常で、参照先の無い注文はありません。最後に、遅れて届いた行の数です。受信時刻を文字列から TIMESTAMP に直して引き、1 日以上のものを数えます。`INTERVAL 1 DAY` は DuckDB の書き方で、PostgreSQL では `INTERVAL '1 day'` と書きます。

```sql
SELECT count(*) FILTER (WHERE CAST(received_at AS TIMESTAMP) - CAST(event_time AS TIMESTAMP)
                              >= INTERVAL 1 DAY) AS late_rows,
       count(*) AS total
FROM events;
```

```text
┌───────────┬───────┐
│ late_rows │ total │
│   int64   │ int64 │
├───────────┼───────┤
│       122 │  4040 │
└───────────┴───────┘
```

122 件で、全体の約 3.0% です。5 つの欠陥は、これですべて数字になりました。

## 確認を実行器にする

SQL を手で流すだけでは、毎日は続きません。確認を「流して、結果を残して、必要なら止める」仕組みにします。実行器は `examples/b13/quality.py` で、DuckDB で動かします。設計は 1 つの約束に絞りました。

> 確認は、「悪い行の数 bad」と「見た行の数 total」を返す SQL 1 本で表す。bad / total が上限以下なら合格。

件数を返すだけにすると、割合の閾値も、ゼロ許容も、同じ形で書けます。確認の定義は次のとおりです。

```python
@dataclass(frozen=True)
class Check:
    name: str
    dimension: str  # 完全性・一意性・鮮度など
    severity: str  # "error" か "warn"
    sql: str  # 1 行 2 列 (bad, total) を返す SELECT
    max_ratio: float = 0.0


class QualityError(Exception):
    """severity が error の確認が不合格だったときに投げます。"""
```

`@dataclass` は、フィールド名を並べるだけで `__init__` などを自動で作る印です。`frozen=True` は、作ったあとに値を書き換えられなくします。確認の定義が実行中に変わらないようにするためです。

よく使う確認は、作り方を関数にしておきます。dbt の `not_null` や `unique` と同じ名前にしました。

```python
def not_null(table, column, severity="error", max_ratio=0.0):
    return Check(f"{table}.{column}_not_null", "完全性", severity,
                 f"SELECT count(*) FILTER (WHERE {column} IS NULL), count(*) FROM {table}", max_ratio)


def unique(table, column, severity="error", max_ratio=0.0):
    # NULL は一意性ではなく完全性の話なので数えない。bad は「余分な行数」。
    return Check(f"{table}.{column}_unique", "一意性", severity,
                 f"SELECT count(*) - count(DISTINCT {column}), count(*) FROM {table} "
                 f"WHERE {column} IS NOT NULL", max_ratio)
```

表名と列名を f 文字列で SQL に埋めています。これは、利用者の入力を受けるコードでは SQL インジェクション(悪意のある文字列で SQL を書き換えられる攻撃)の原因になります。このファイルでは、コードに直接書いた信頼できる名前だけを渡す前提です。

ほかにも、`accepted_values`(許す値の一覧)・`relationships`(参照整合性)・`freshness`(鮮度)・`row_count_between`(量)・`late_arrival`(遅延の割合)・`schema_matches`(スキーマ)・`volume_zscore`(分布)を同じ形で用意しました。`freshness` は「今」を引数 `as_of` で受け取ります。現在時刻を中で読むと、テストの結果が実行する日によって変わってしまうからです。実行は次の 2 つの関数です。

```python
@dataclass(frozen=True)
class Result:
    check: Check
    bad: int
    total: int
    passed: bool
    detail: str = ""


def _evaluate(con, check):
    try:
        bad, total = con.execute(check.sql).fetchone()
    except duckdb.Error as e:  # 測れなかった確認は不合格にする
        return Result(check, 0, 0, False, f"{type(e).__name__}: {str(e).splitlines()[0]}")
    ratio = bad / total if total else 0.0
    return Result(check, bad, total, ratio <= check.max_ratio)
```

SQL が失敗したとき(表が無い、列名の打ち間違い)は、例外で全体を落とすのではなく、その確認だけを「不合格」にして理由を `detail` に残します。確認の書き間違いで他の確認まで止まる、という事態を避けつつ、測れていないことは必ず表に出ます。

```python
def run_checks(con, checks, run_id, now=None):
    """全部の確認を流し、結果を dq_results に追記して list[Result] を返します。"""
    now = now or datetime.now(timezone.utc)
    con.execute("""
        CREATE TABLE IF NOT EXISTS dq_results (
            run_id VARCHAR, run_at TIMESTAMPTZ, check_name VARCHAR, dimension VARCHAR,
            severity VARCHAR, bad BIGINT, total BIGINT, ratio DOUBLE, max_ratio DOUBLE,
            passed BOOLEAN, detail VARCHAR)""")
    results = [_evaluate(con, c) for c in checks]
    for r in results:
        ratio = r.bad / r.total if r.total else 0.0
        con.execute("INSERT INTO dq_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [run_id, now, r.check.name, r.check.dimension, r.check.severity,
                     r.bad, r.total, ratio, r.check.max_ratio, r.passed, r.detail])
    return results


def gate(con, checks, run_id, notify=print, now=None):
    """確認を流し、warn の不合格は notify で知らせ、error の不合格があれば止めます。"""
    results = run_checks(con, checks, run_id, now)
    failed = [r for r in results if not r.passed]
    for r in failed:
        if r.check.severity == "warn":
            notify(f"[WARN] {r.check.name}: {r.bad}/{r.total} {r.detail}".rstrip())
    errors = [r for r in failed if r.check.severity == "error"]
    if errors:
        names = ", ".join(r.check.name for r in errors)
        raise QualityError(f"品質確認で止めました: {names}")
    return results
```

ここに、これまで教えた決まりが入っています。`run_at` は `TIMESTAMPTZ`(タイムゾーン付きの時刻)の列に、UTC の現在時刻を入れます(第2章)。止める前に結果を表へ書き込むので、止まった回の記録も残ります。記録が無いと、あとで「いつから落ちていたか」が分からなくなるからです。`notify` は関数を引数で渡す形にしてあり、既定は `print` ですが、本番では Slack などへ送る関数に差し替えられます。テストでは、通知を溜めるリストの `append` を渡して中身を確かめています。

ねぼすけ商店の確認一覧は `shop_checks()` にあり、`main()` が流します。

```python
def main(db="shop.duckdb", run_id=None):
    """終了コード 0 = 先へ進んでよい、1 = error の不合格あり (cron や Airflow が止められる)。"""
    path = Path(db)
    if not path.exists():
        write_duckdb(path)
    con = duckdb.connect(str(path))
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        results = gate(con, shop_checks(), run_id)
    except QualityError as e:
        print(e)
        return 1
    finally:
        con.close()
    print(f"全 {len(results)} 件の確認を通りました (warn の不合格は上に表示)")
    return 0
```

終了コードで合否を返す形は、第3章で見た約束です。cron でもシェルスクリプトでも、第12章の Airflow のタスクでも、終了コード 1 を見て後続を止められます。流してみます。

```bash
python examples/b13/quality.py
echo "exit=$?"
```

```text
[WARN] customers.email_not_null: 20/505
[WARN] customers.email_unique: 5/485
[WARN] orders.status_accepted_values: 59/3000
品質確認で止めました: events.event_id_unique
exit=1
```

3 つの warn が通知され、行動ログの重複(error)で止まりました。この挙動はテスト(`test_b13_quality.py`)でも確かめています。5 つの欠陥のうち、遅れて届く行(3.0%)は閾値 5% の内側なので通知も出ません。

## 結果を残して見える化する

`dq_results` に溜めた結果は、それ自体がデータです。SQL で集計すれば、品質の状態が見えます。最新の実行について、観点ごとの合格率を出します。

```sql
SELECT dimension,
       count(*) AS checks,
       count(*) FILTER (WHERE passed) AS passed,
       round(100.0 * count(*) FILTER (WHERE passed) / count(*), 1) AS pass_pct
FROM dq_results
WHERE run_id = (SELECT run_id FROM dq_results ORDER BY run_at DESC LIMIT 1)
GROUP BY dimension
ORDER BY dimension;
```

```text
┌────────────┬────────┬────────┬──────────┐
│ dimension  │ checks │ passed │ pass_pct │
│  varchar   │ int64  │ int64  │  double  │
├────────────┼────────┼────────┼──────────┤
│ スキーマ   │      1 │      1 │    100.0 │
│ 一意性     │      3 │      1 │     33.3 │
│ 分布       │      1 │      1 │    100.0 │
│ 参照整合性 │      2 │      2 │    100.0 │
│ 完全性     │      2 │      1 │     50.0 │
│ 正確さ     │      1 │      0 │      0.0 │
│ 量         │      1 │      1 │    100.0 │
│ 鮮度       │      2 │      2 │    100.0 │
└────────────┴────────┴────────┴──────────┘
```

(並び順は、日本語の並べ替えの規則に依存します。)この表から、一意性と正確さに手を入れる必要があると分かります。ただし、合格率は確認の数に引きずられます。確認が 1 つしかない観点の 0% と、100 個ある観点の 90% は、重みが違います。数字は「どこを見るか」の目安で、品質のスコアとして比べるものではありません。

もう 1 つ大事なのは、「いつから落ちているか」です。

```sql
SELECT check_name, severity, min(run_at) AS first_seen, count(*) AS failed_runs
FROM dq_results
WHERE NOT passed
GROUP BY check_name, severity
ORDER BY first_seen, check_name;
```

```text
┌───────────────────────────────┬──────────┬───────────────────────────────┬─────────────┐
│          check_name           │ severity │          first_seen           │ failed_runs │
│            varchar            │ varchar  │   timestamp with time zone    │    int64    │
├───────────────────────────────┼──────────┼───────────────────────────────┼─────────────┤
│ customers.email_not_null      │ warn     │ 2026-11-13 06:16:39.989071+00 │           2 │
│ customers.email_unique        │ warn     │ 2026-11-13 06:16:39.989071+00 │           2 │
│ events.event_id_unique        │ error    │ 2026-11-13 06:16:39.989071+00 │           2 │
│ orders.status_accepted_values │ warn     │ 2026-11-13 06:16:39.989071+00 │           2 │
└───────────────────────────────┴──────────┴───────────────────────────────┴─────────────┘
```

(`quality.py` を 2 回流したあとの結果の一部です。時刻は実行ごとに変わります。)warn は放っておくと、いつの間にか半年落ち続けます。`first_seen` が古いのに `failed_runs` が増え続けている確認は、誰かが引き取る必要があります。実際の現場では、この表を BI ツールで見える化し、観点別の推移と「落ち続けている確認」の一覧を置くのが定番です。実行ごとの履歴を残すことで、「先週の火曜からだ」と日付で原因を絞れます。パイプライン全体の観測(遅延・リネージ・SLO)に広げた話は、応用編にあります。

## 分布の変化を見つける

ここまでの確認は、「規則に反しているか」でした。もう 1 つ、規則では書けない異常があります。「ある日だけ件数が半分になった」「急に倍になった」です。ルールに反する値は 1 つも無いのに、数字がおかしい。こういう異常は、過去との比較で見つけます。

一番簡単なのは前日比です。日別の件数を出し、`lag()`(第6章)で前日の値を横に並べます。

```sql
WITH daily AS (
    SELECT CAST(event_time AS DATE) AS d, count(*) AS n FROM events GROUP BY d
)
SELECT d, n,
       lag(n) OVER (ORDER BY d) AS prev_n,
       round(n / lag(n) OVER (ORDER BY d), 2) AS ratio_to_prev
FROM daily
ORDER BY d DESC
LIMIT 3;
```

```text
┌────────────┬───────┬────────┬───────────────┐
│     d      │   n   │ prev_n │ ratio_to_prev │
│    date    │ int64 │ int64  │    double     │
├────────────┼───────┼────────┼───────────────┤
│ 2026-06-29 │    20 │     23 │          0.87 │
│ 2026-06-28 │    23 │     23 │           1.0 │
│ 2026-06-27 │    23 │     27 │          0.85 │
└────────────┴───────┴────────┴───────────────┘
```

前日比には弱点があります。もともと 1 日ごとに 15% ほど上下する指標では、「前日比 0.85」で毎日警告が出ます。曜日やキャンペーンで大きく動く指標なら、さらに誤検知が増えます。そこで、「普段のばらつきの何個分離れているか」で見る Z スコアを使います。

Z スコア = (今日の値 − 直近の平均) ÷ 直近の標準偏差

値が平均から標準偏差 1 個分離れていれば Z は 1 です。値が釣り鐘型(正規分布)に近いとき、±3 を超えるのは 1000 回に 3 回ほどの出来事です。そこで、3 を超えたら「普段と違う」と見ます。SQL では、ウィンドウ関数のフレーム(第6章)で「直前 28 日、ただし当日は含めない」と書きます。

```sql
WITH daily AS (
    SELECT CAST(event_time AS DATE) AS d, count(*) AS n FROM events GROUP BY d
),
scored AS (
    SELECT d, n,
           avg(n) OVER w AS mu,
           stddev_samp(n) OVER w AS sd
    FROM daily
    WINDOW w AS (ORDER BY d ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING)
)
SELECT d, n, round(mu, 1) AS mu, round((n - mu) / sd, 2) AS z
FROM scored
WHERE abs((n - mu) / sd) > 3
ORDER BY d;
```

```text
┌────────────┬───────┬────────┬────────┐
│     d      │   n   │   mu   │   z    │
│    date    │ int64 │ double │ double │
├────────────┼───────┼────────┼────────┤
│ 2026-02-24 │    30 │   21.1 │   3.02 │
│ 2026-02-25 │    35 │   21.3 │   4.04 │
└────────────┴───────┴────────┴────────┘
```

180 日のうち 2 日が引っかかりました。ねぼすけ商店のデータは、行動ログの時刻を乱数で作っていて、この 2 日に意図した欠陥はありません。つまり、これは偶然のばらつきによる誤検知です。2 日連続になったのにも理由があります。24 日の大きな値が、25 日の基準(直前 28 日)に混ざって、基準そのものを動かすからです。Z スコアは、次の点を知って使います。

- 「±3 を超えたら異常」は、分布が釣り鐘型に近いときの目安です。1 日 20 件ほどの小さな件数は、きれいな釣り鐘型になりません。
- 日数を見れば、偶然でも超える日は出ます。だから分布の確認は、error ではなく warn にします。
- 0 件の日は、`GROUP BY` では行が出ません。上のクエリは、0 件の日を「その日の行が無い」という形でしか扱えず、検出できません。実行器の `volume_zscore` は、当日の行が無いときに件数 0 として扱います。日付の一覧を作って結合する(第6章の再帰 CTE)方法もあります。

実行器の確認として書くと、こうなります。

```python
def volume_zscore(table, column, day, z_max=3.0, severity="warn"):
    # day の件数が、直前 28 日の日別件数の平均から標準偏差 z_max 個分以上離れていれば bad。
    # 基準が作れない (標準偏差が NULL か 0) ときも bad にする。測れないものを合格にしない。
    return Check(f"{table}_volume_zscore", "分布", severity, f"""
        WITH daily AS (SELECT CAST({column} AS DATE) AS d, count(*) AS n FROM {table} GROUP BY d),
        base AS (SELECT avg(n) AS mu, NULLIF(stddev_samp(n), 0) AS sd FROM daily
                 WHERE d >= DATE '{day}' - 28 AND d < DATE '{day}'),
        today AS (SELECT coalesce(max(n), 0) AS n FROM daily WHERE d = DATE '{day}')
        SELECT CASE WHEN base.sd IS NULL OR abs((today.n - base.mu) / base.sd) > {z_max}
                    THEN 1 ELSE 0 END, 1
        FROM today, base""")
```

`NULLIF(x, 0)` は、x が 0 のとき NULL を返す関数です。標準偏差が 0 だと割り算できないので NULL にして、その場合は `base.sd IS NULL` の枠で「測れない」として不合格に倒します。テストでは、6 月 20 日の行を消して「件数 0 の日」を作ると不合格になること、200 件を足した「急増の日」でも不合格になること、空の表では不合格になることを確かめています。

## 隔離(quarantine)テーブル

error で止めたあと、データは放置できません。行動ログの重複は、ただ止めるのではなく、重複した行だけを避けて先へ進めたい。そのとき使うのが隔離(quarantine)テーブルです。悪い行を捨てず、理由を付けて別の表へ移します。

まず、各 `event_id` の最初に届いた 1 行を `events_clean` に残します。

```sql
CREATE OR REPLACE TABLE events_clean AS
SELECT event_id, customer_id, event_type, event_time, received_at
FROM (
    SELECT *, row_number() OVER (PARTITION BY event_id ORDER BY received_at) AS rn
    FROM events
)
WHERE rn = 1;
```

残りを、理由つきで `events_quarantine` に移します。

```sql
CREATE OR REPLACE TABLE events_quarantine AS
SELECT event_id, customer_id, event_type, event_time, received_at,
       'duplicate_event_id' AS reason
FROM (
    SELECT *, row_number() OVER (PARTITION BY event_id ORDER BY received_at) AS rn
    FROM events
)
WHERE rn > 1;
```

分け方が正しいか、件数で確かめます。元の行数は、残した行数と隔離した行数の合計に一致するはずです。

```sql
SELECT (SELECT count(*) FROM events) AS raw_rows,
       (SELECT count(*) FROM events_clean) AS clean_rows,
       (SELECT count(*) FROM events_quarantine) AS quarantined_rows;
```

```text
┌──────────┬────────────┬──────────────────┐
│ raw_rows │ clean_rows │ quarantined_rows │
│  int64   │   int64    │      int64       │
├──────────┼────────────┼──────────────────┤
│     4040 │       4000 │               40 │
└──────────┴────────────┴──────────────────┘
```

4040 = 4000 + 40 で、行が消えても増えてもいません。そのうえで、`shop_checks("_clean")` で `events_clean` に同じ確認を流すと、行動ログの重複は消え、error の不合格が無くなって先へ進めます(warn の 3 件は残ります)。流れは「生データ → 確認で重複を検出 → 隔離 → 清潔な表に再確認 → 提供」になります。ただし、どの行を残すかには判断があります。ここでは「最初に届いた行」を残しましたが、あとから届いた行のほうが新しい情報を持つデータでは、別の選び方になります(第6章の「各グループの最新 1 行」)。

ここで、隔離するもの・しないものの使い分けを決めておきます。

- **重複**: 同じ行なので、1 行を残して残りを隔離します。
- **表記ゆれ(`SHIPPED`)**: 直し方が分かっているので、隔離ではなく変換で直します。`lower(status)` にすれば、4 種類に収まります。
- **遅れて届いた行**: 正当なデータです。隔離せず、遅延の割合を warn で見ます。
- **二重登録の顧客**: どちらが正しいか機械では決められません。隔離ではなく、持ち主に聞きます。

隔離を作るときは、2 つ注意してください。1 つは、作り方を冪等(何度流しても同じ結果)にすることです。上の SQL は `CREATE OR REPLACE TABLE` で作り直しているので、再実行で重複が増えません(第12章)。もう 1 つは、隔離した行を誰かが見ることです。見る人がいない隔離テーブルは、データのごみ箱と同じです。隔離した件数は、確認として記録し、一定数を超えたら通知します。

## dbt のテストで書く

dbt の `unique`・`not_null`・`accepted_values`・`relationships` といった標準のテスト(generic test)と、`source freshness` の書き方は、第10章で見ました。この章では、その上に足せる 3 つを扱います。閾値付きの重大度、単発のテスト(singular test)、そして dbt のテストが何を数えているか、です。`examples/b13/dbt_demo/` に、`shop.duckdb` を直接の入力(source)にした小さなプロジェクトを置きました。

```yaml title="models/sources.yml" excerpt
sources:
  - name: shop
    schema: main
    tables:
      - name: customers
        columns:
          - name: email
            data_tests:
              # 欠けが 10 件を超えたら warn、40 件を超えたら error (件数で決める)
              - not_null:
                  config:
                    severity: error
                    warn_if: ">10"
                    error_if: ">40"
```

`severity` は、失敗したときの扱いです。`warn_if` と `error_if` は、失敗した行の件数が条件を満たすかで段階を分けます。上の設定は、欠けが 10 件以下なら合格、11〜40 件なら warn、41 件以上なら error です。この章の自作の実行器では「割合」で閾値を決めましたが、dbt の `warn_if` / `error_if` は件数の条件で決めます。割合で決めたい場合は、次の単発テストのように SQL に書きます。

単発のテストは、`tests/` に SELECT を 1 本置くだけです。返った行が 1 行でもあれば不合格になります。

```sql
-- 単発テスト (singular test): 返った行が 1 行でもあれば不合格。
-- 明細の単価が商品マスタの価格と食い違う行を探す (正確さ)。
select i.order_id, i.line_no, i.unit_price, p.price
from main.order_items as i
join main.products as p on i.product_id = p.product_id
where i.unit_price <> p.price
```

割合の閾値は、「割合を超えたときだけ 1 行返す」SELECT にして、`config(severity='warn')` を付けます。

```sql
{{ config(severity='warn') }}
-- 割合の閾値を SQL で書く単発テスト。遅れて届いた行が全体の 5% を超えたときだけ 1 行返す。
select late, total
from (
    select count(*) filter (
               where cast(received_at as timestamp) - cast(event_time as timestamp) >= interval 1 day
           ) as late,
           count(*) as total
    from {{ source('shop', 'events') }}
)
where late > 0.05 * total
```

流します。`cd` で dbt_demo に入り、プロジェクトの外の `shop.duckdb` を `SHOP_DB` で指します。

```bash
cd examples/b13/dbt_demo
SHOP_DB=../../../shop.duckdb dbt test --profiles-dir .
```

```text
06:09:56  3 of 8 WARN 1 source_accepted_values_shop_orders_status__placed__shipped__delivered__cancelled  [WARN 1 in 0.01s]
06:09:56  4 of 8 WARN 20 source_not_null_shop_customers_email ............................ [WARN 20 in 0.02s]
06:09:56  7 of 8 FAIL 40 source_unique_shop_events_event_id .............................. [FAIL 40 in 0.02s]
06:09:56  Done. PASS=5 WARN=2 ERROR=1 SKIP=0 NO-OP=0 REUSED=0 TOTAL=8
```

(一部の行です。dbt 1.12.7、dbt-duckdb 1.11.1 の出力で、時刻は実行ごとに変わります。)ここに、自作の実行器と違う点が 2 つ出ています。

1 つ目は、`accepted_values` が `WARN 1` なことです。`SHIPPED` は 59 行あるのに、dbt は「許されない値が何種類あったか」を数えるので 1 です。件数と行数は別物なので、`warn_if: ">10"` のような閾値は、テストごとに「何を数えているか」を確かめて決めます。`unique` の `FAIL 40` は、重複した `event_id` が 40 種類という意味で、たまたま超過行数と同じ数字です。

2 つ目は、終了コードです。error が 1 件あれば、この実行の終了コードは 1 になりました(上の実行では `ERROR=1`)。warn だけなら失敗扱いにならない、というのが dbt の文書の説明です(警告も失敗扱いにしたいときは `--warn-error` を付けます)。そのため、warn が出たことを人に伝えるには、dbt の外で通知の仕組みを足します。

書き方の補足です。テストの引数(`values` や `to`)を `arguments:` の下に書く形は、この本の dbt 1.12.7 で使いました。引数を直接並べる古い書き方も動きますが、警告(`MissingArgumentsPropertyInGenericTestDeprecation`)が出ます。結果を後から調べたいときは `store_failures`(失敗した行をデータベースの表に保存する設定)も使えます。

## Great Expectations・Soda・dbt-expectations

ここまで自作の実行器と dbt のテストを見ましたが、現場では既存の道具を使うことが多いです。名前と考え方だけ、押さえておきます。詳細は公式の文書で確かめてください(2026年11月時点の整理です)。

{{ table("b13-tools") }}

**Great Expectations** は、「期待(Expectation)」を宣言して検証し、結果を保存して HTML で見せる Python のライブラリです。**Soda** は、`checks for テーブル名:` のような YAML の短い言語(SodaCL)で確認を書きます。**dbt-expectations** は、Great Expectations に着想を得た確認を dbt のテストとして使えるようにしたパッケージです。どれも、この章の「確認 = 期待を宣言する + 流す + 結果を残す」の延長にあります。

選び方の目安は、(1) すでに dbt で変換しているなら、まず dbt のテストから始めて足りない部分を dbt-expectations で補う、(2) SQL の外にあるデータ(ファイルや Python の中のデータ)を見たいなら Great Expectations、(3) SQL を書かない人にも確認を書いてもらいたいなら Soda、です。ただし、道具を足す前に「どの観点を、どこで、どの重大度で」確かめるかを決めておかないと、どの道具でも同じ迷い方をします。この章の自作の実行器は、その決め方を試すための小さな模型です。

## データの持ち主と連絡の流れ

確認が落ちたとき、誰が何をするかが決まっていないと、通知は無視されます。次の順で動くと決めておきます。

1. **検知**: 確認が落ちる。error なら、処理が止まっている。
2. **影響の確認**: 落ちたテーブルを使っているダッシュボードやジョブを洗い出す(どこから先が汚れたかを追う仕組みは、応用編のリネージで扱います)。
3. **利用者への一報**: 「売上ダッシュボードは○時時点のデータで止まっています。原因は調査中、次の連絡は○時です」と、先に伝える。原因が分かるのを待たない。
4. **持ち主への連絡**: そのデータを作っている側(アプリのチーム、計測基盤の担当)に、再現できる形で伝える。
5. **恒久対応**: 持ち主が元を直す、変換で吸収する、確認の閾値の見直し、のどれかを決める。
6. **再発防止**: 今回見逃した種類の確認を足す。

連絡には、次の情報を毎回入れると、受け取る側が動けます。

```text
確認: events.event_id_unique (一意性 / error)
結果: 40 行が重複 (全 4040 行)
実行: 20261113T0600Z
影響: events を使う日次の行動集計が止まっています
再現: SELECT event_id, count(*) FROM events GROUP BY event_id HAVING count(*) > 1;
連絡先: 計測基盤チーム
```

「持ち主」は、確認ごとに決めておきます。ねぼすけ商店なら、メールの欠けと二重登録は会員登録フォームの担当、行動ログの二重配信は計測基盤の担当、表記ゆれは注文システムの担当、と仮に割り振れます。二重配信は、再送を許す配信方式で起きやすい現象です(ストリーミングは第15章で扱います)。確認の定義に `owner` を持たせるのも、有効な方法です。持ち主との合意を契約として文書にする方法は、応用編のデータ契約で扱います。

## よくある失敗

- **全部を error にする**: 止まる回数が増え、現場は「どうせ誤検知」と思い始めます。止めるのは、後から直せない数字の確認だけにします。
- **全部を warn にする**: 通知が山になり、誰も読まなくなります(通知疲れ)。warn には持ち主と期限を付け、古い warn は error に格上げするか、確認を捨てます。
- **確認を通すために閾値を緩める**: 閾値は現状に合わせるのではなく、業務の都合から決めます。変えるときは理由を記録に残します。
- **測れていない確認を合格にする**: NULL との比較、空の表、0 件の日は、静かに通ります。「測れなかった」を不合格に倒す実装にします。
- **結果を残さない**: ログに流すだけでは、「いつから」「どれだけ」が追えません。表に残します。
- **本番と違うデータでテストする**: 空に近いテスト用データでは、重複も欠けも出ません。確認のテストには、欠陥を入れたデータ(この章ではねぼすけ商店)を使い、確認が欠陥を見つけることを確かめます。
- **確認自体が重い**: 確認が毎回全表をスキャンすると、費用と時間がかさみます。大きな表では、当日のパーティションだけに絞ります(第11章)。
- **隔離テーブルを放置する**: 件数を記録し、見る人と頻度を決めます。

## まとめ

- 品質は、使う目的に対して足りているかで決まり、8 つの観点に分けて測る。
- 確認は、取り込み時・変換時・提供前の 3 か所に、役割を分けて置く。
- 止めるか知らせるかは、「後から直せるか」で決め、閾値には業務上の理由を付ける。
- 「測れなかった」を合格にしない。確認の結果は表に残す。
- 分布の変化は前日比と Z スコアで見る。ただし誤検知を前提にし、warn にする。
- 悪い行は捨てずに理由つきで隔離し、元の行数 = 残した行数 + 隔離した行数 を確かめる。
- 確認が落ちたら、検知 → 影響の確認 → 一報 → 持ち主 → 恒久対応 → 再発防止の順に動く。

## 練習問題

**問1.** `customers.email` の欠けを 3% まで許す error の確認を作り、`gate` に渡したときの挙動を答えてください。欠けの実測は 3.96% です。

??? note "解答例"
    `examples/b13/exercises.py` の `EMAIL_STRICT` です。

    ```python
    EMAIL_STRICT = not_null("customers", "email", severity="error", max_ratio=0.03)
    ```

    欠けの割合は 20 / 505 = 約 3.96% で、上限 0.03 を超えるので不合格です。severity が error なので、`gate` は `QualityError` を投げて止まります。上限を 0.05 にすれば合格します。割合に閾値を付けるときは、実測を先に見て決めます。

**問2.** `orders.status` の表記ゆれを `lower()` で直したあと、許していない値がまだ残っているかを数えるクエリを書いてください。

??? note "解答例"
    `queries.sql` の `status_values_lowered` です。

    ```sql
    SELECT count(*) AS still_bad
    FROM orders
    WHERE lower(status) NOT IN ('placed', 'shipped', 'delivered', 'cancelled');
    ```

    結果は 0 です。`SHIPPED` の 59 行が `shipped` に揃い、4 種類に収まります。確認は、直したあとに「直ったこと」を測るためにも使います。

**問3.** 注文明細の `quantity` が 1 以上であること(範囲の確認)を、`Check` を直接書いて作ってください。観点は「正確さ」、重大度は error とします。

??? note "解答例"
    `exercises.py` の `QUANTITY_POSITIVE` です。

    ```python
    QUANTITY_POSITIVE = Check(
        "order_items.quantity_positive", "正確さ", "error",
        "SELECT count(*) FILTER (WHERE quantity < 1), count(*) FROM order_items")
    ```

    実行すると、悪い行は 0、見た行は 7469 で、合格します。新しい種類の確認は、「悪い行を数える SELECT」を書いて `Check` に包むだけです。

**問4.** 遅れて届いた行の閾値を 5% から 2% に下げると、`events_late_arrival` はどうなりますか。そのとき、warn は誰に伝えるべきか、理由も含めて答えてください。

??? note "解答例"
    遅れた行は 122 / 4040 = 約 3.0% で、2% を超えるため不合格になり、warn なので通知が出て処理は続きます(`late_arrival(..., max_ratio=0.02)` でテストしています)。遅れて届く原因には、端末が通信できない時間があった、計測基盤の再送が遅れた、などが考えられますが、どちらも元のデータを作っている側(計測基盤の担当)の領域です。通知は、変換を作っている自分たちだけでなく、持ち主に届く宛先へ出します。閾値を下げるときは、「遅れが 2% を超えたら、日次の集計をやり直す」のように、通知のあとの行動も決めておくと、確認が意味を持ちます。

## 参考文献

- dbt Documentation, “Add data tests to your DAG”, <https://docs.getdbt.com/docs/build/data-tests>(2026年11月時点)
- dbt Documentation, “severity, error_if, and warn_if”, <https://docs.getdbt.com/reference/resource-configs/severity>
- dbt Documentation, “store_failures”, <https://docs.getdbt.com/reference/resource-configs/store_failures>
- DuckDB Documentation, “FILTER Clause”, <https://duckdb.org/docs/current/sql/query_syntax/filter.html>
- PostgreSQL Documentation, “Constraints”, <https://www.postgresql.org/docs/current/ddl-constraints.html>
- Google Cloud, “Use primary and foreign keys”(BigQuery の `NOT ENFORCED`), <https://cloud.google.com/bigquery/docs/primary-foreign-keys>
- Snowflake Documentation, “Constraints”(標準テーブルでは NOT NULL 以外を強制しない), <https://docs.snowflake.com/en/sql-reference/constraints-overview>
- Great Expectations Documentation, <https://docs.greatexpectations.io/docs/home/>
- Soda Documentation, <https://docs.soda.io/>
- dbt-expectations (Metaplane), <https://github.com/metaplane/dbt-expectations>

!!! tip "さらに深く"
    品質の確認を、実行履歴・遅延・リネージまで広げて継続的に見る方法は、応用編 第8章「観測性・SLO・リネージ」で、上流とデータの約束を契約として結ぶ方法は、応用編 第7章「データ契約とスキーマ進化」で扱います。

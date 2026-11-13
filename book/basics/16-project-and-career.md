# 第16章 実践プロジェクトとキャリア

## この章でできるようになること

- 取り込みから図までの流れ (取り込み → raw → 変換 → 品質チェック → 図) を、1 本のスクリプトで通して動かし、各工程が止まる条件を説明できる。
- 同じ日付で何度実行しても同じ結果になること、品質チェックの error で後ろの工程が止まることを、テストで確かめられる。
- 設計メモ (README) を、「何を決めたか・なぜか・何をやらなかったか」の順で書ける。
- ポートフォリオに何を見せ、何を入れてはいけないかを判断できる。
- 現場に入ってからの最初の 90 日の過ごし方、学び続ける方法、面接で聞かれることと答え方の型を持てる。
- 応用編 12 章の内容を、自分の次の学習計画に結びつけられる。

## 基礎編の総仕上げ: 日次売上と品質のダッシュボード

第1章で、店長から「売上ダッシュボードを作ってほしい」と頼まれる場面を取り上げました。あのとき作ったのは、SQL 1 本でした。この章では、同じ依頼を、仕事として通用する形で作り直します。これまでの章の部品を全部つないで、「日次売上」と「その数字を信じてよいか」を 1 枚の図にします。

流れは次のとおりです。

```mermaid
flowchart LR
    A[ねぼすけ商店の表] --> B["取り込み<br/>Parquet を landing に置く"]
    B --> C["raw<br/>DuckDB に読み込む"]
    C --> D["変換<br/>dbt で staging → mart"]
    D --> E["品質チェック<br/>error なら止める"]
    E --> F["図<br/>日次売上と品質の結果"]
```

{{ table("b16-steps") }}

この表で大事なのは、右端の列です。パイプラインは、動いているときより、壊れたときの振る舞いで価値が決まります。書きかけのファイルを読まない。変換のテストが落ちたら先へ進まない。売上の数字が合わなければ、図を作らない。間違った図が店長の目に触れるより、図が出ないほうがましだからです。

### 使う部品について

取り込み (第9章) と変換 (第10章) と品質チェック (第13章) は、それぞれの章で作った考え方を使います。ただし、この演習のコードは、章ごとのコードを `import` するのではなく、`examples/b16/` の中で完結するように書き直しました。章のコード例は、その章の説明に合わせた形で書かれていて、別の章から呼ぶ前提で作っていないためです。特に品質チェックは、第13章の仕組みを、この演習に要る分 (5 件の確認、error と warn の区別、結果の記録) だけに小さくした版です。第13章のものに置き換えるときは、`quality.py` の `run_checks` を呼んでいる 1 行を差し替えます。

### 動かす

WSL や Linux のシェルで、リポジトリの直下から動かします。MinIO (第14章) に置く場合は、`docker compose up -d --wait` で起動してからです。`S3_ENDPOINT` を渡さなければ、手元のフォルダに置きます。

```bash
# リポジトリの直下で動かします。MinIO を使うなら docker compose up -d --wait で起動しておきます。
# MinIO に置く場合 (S3_ENDPOINT を渡す)。--network host は、コンテナから localhost の MinIO に届かせるためです。
docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp -e S3_ENDPOINT=http://localhost:9000 -e S3_ACCESS_KEY=minioadmin -e S3_SECRET_KEY=minioadmin -v "$PWD":/w -w /w de-book-dev python examples/b16/pipeline.py --dt 2026-07-01 --workdir work/b16

# サービスなしで、手元のフォルダに置く場合 (S3_ENDPOINT を渡さない)
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev python examples/b16/pipeline.py --dt 2026-07-01 --workdir work/b16
```

実行すると、次のように表示されました (MinIO に置いた場合です。リポジトリの `work/b16/` に `warehouse.duckdb` と図の SVG ができます。確認が済んだら `work/` は消して構いません。図のパスは、実行した場所によって表示が変わります)。

```text
raw に読み込み: {'orders': 3000, 'order_items': 7469, 'events': 4040}
  OK    orders が空でない
  OK    日別売上の日付が NULL でも重複でもない
  OK    日別売上の合計が raw の明細と一致する
  WARN  events の event_id が重複していない
  OK    events の遅延到着 (翌日以降) が 5% 以下
図: work/b16/dashboard_2026-07-01.svg
```

`WARN` が 1 件出ています。ねぼすけ商店の行動ログには、重複して届く行を意図的に入れてあるためです (第13章)。重複は 4,040 行中の 40 行で、このチェックは「知らせて進む」(warn) の扱いです。売上の計算には events を使わないので、止める理由がありません。できあがる図は、次のようなものです。

![日次売上と品質チェックの結果](../assets/figures/b16_dashboard.svg)

上の図は、日別売上の棒と 7 日の移動平均線、下に品質チェックの結果の一覧です。図は `examples/figures/b16_dashboard.py` が、サービスなしのモード (手元のフォルダに置く形) で同じパイプラインを動かして作ります。数字を手で写していないので、データや定義を変えれば図も変わります。

## 中を読む

### 取り込みと raw

`land` は、表を Parquet にして置き、**最後に** `_SUCCESS` を置きます。第9章で見たとおり、全部置き終えた印です。

```python title="ingest.py"
def land(store, dt):
    """TABLES を Parquet にして置き、最後に _SUCCESS を置きます。"""
    data = generate()
    for name in TABLES:
        buf = io.BytesIO()
        pq.write_table(pa.Table.from_pylist(data[name]), buf)
        store.put(f"raw/dt={dt}/{name}.parquet", buf.getvalue())
    store.put(f"raw/dt={dt}/_SUCCESS", b"")
```

読む側の `load_raw` は、印が無ければ読みません。

```python title="ingest.py"
def load_raw(con, store, dt):
    """_SUCCESS のある dt だけを、DuckDB の raw 表 (main スキーマ) に読み込みます。件数の辞書を返します。"""
    if not store.exists(f"raw/dt={dt}/_SUCCESS"):
        raise RuntimeError(f"dt={dt} は _SUCCESS が無いので読みません (書きかけかもしれません)")
    counts = {}
    for name in TABLES:
        table = pq.read_table(io.BytesIO(store.get(f"raw/dt={dt}/{name}.parquet")))
        con.register("_t", table)
        con.execute(f"CREATE OR REPLACE TABLE main.{name} AS SELECT * FROM _t")
        con.unregister("_t")
        counts[name] = table.num_rows
    return counts
```

三つの決まりがコードに入っています。置く場所は `raw/dt=<取り込み日>/` で、同じ日付なら同じキーを上書きするので、何度実行しても結果は同じです (冪等)。印は最後に置きます。そして、raw 表は元の値のまま入れます。表記ゆれも重複も直しません。直す場所を変換に限ると、「元はどうだったか」がいつでも raw に残ります。

`dt` は本来「取り込んだ日」です。この演習の元データは固定のデータセットなので、`--dt` は取り込みの区分けの名前として渡しています。

### 変換

変換は dbt です (第10章)。staging で、状態の表記ゆれを小文字にそろえ、日時を型にします。

```sql
-- 状態の表記ゆれ (shipped / SHIPPED) を小文字にそろえ、日時を型にする
select
    order_id,
    customer_id,
    cast(ordered_at as timestamp) as ordered_at,
    lower(status) as status
from {{ source('raw', 'orders') }}
```

mart の `fct_daily_sales` は、キャンセル以外の注文の件数と売上を、日ごとに数えます。

```sql
-- 1 行 = 1 日。キャンセルを除いた注文の件数と売上
select
    cast(o.ordered_at as date) as order_date,
    count(distinct o.order_id) as orders,
    sum(i.line_amount) as sales
from {{ ref('stg_orders') }} as o
inner join {{ ref('stg_order_items') }} as i
    on o.order_id = i.order_id
where o.status <> 'cancelled'
group by 1
```

粒度は「1 行 = 1 日」です (第8章)。dbt のテストとして、`order_id` の一意と NULL なし、状態が 4 種類のどれかであること、日別売上の `order_date` の一意と NULL なしを書いてあります。

```yaml
version: 2

models:
  - name: fct_daily_sales
    columns:
      - name: order_date
        data_tests: [unique, not_null]
      - name: sales
        data_tests: [not_null]
```

dbt を呼ぶ部分は、プロジェクトを作業フォルダにコピーしてから実行します。dbt は実行すると `target/` と `logs/` を作るので、リポジトリの中を汚さないためです。

```python title="pipeline.py"
def dbt_build(workdir, db_path):
    """dbt のプロジェクトを workdir にコピーして build します (target と logs をリポジトリに残さないため)。"""
    project = Path(workdir) / "dbt"
    shutil.rmtree(project, ignore_errors=True)
    shutil.copytree(HERE / "dbt", project)
    env = {**os.environ, "DBT_DUCKDB_PATH": str(db_path), "DBT_SEND_ANONYMOUS_USAGE_STATS": "False"}
    result = subprocess.run(
        ["dbt", "build", "--project-dir", str(project), "--profiles-dir", str(project), "--no-use-colors"],
        capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError("dbt build が失敗しました:\n" + result.stdout[-2000:])
```

### 品質チェック

確認は、「悪い行の数」と「見た行の数」を返す SQL 1 本で表します。一覧は `quality.py` の `CHECKS` にあります。その中の 1 つ、売上の突合 (とつごう: 2 つの出どころの数字が合うかの確認) は、変換の結果を、raw から別の書き方で数え直した値と比べます。

実行して結果を残すのは `run_checks` です。

```python title="quality.py"
def run_checks(con, run_dt, checks=CHECKS):
    """全部の確認を実行して dq_results に残します。error が 1 つでも不合格なら、残したあとで止めます。"""
    con.execute("""CREATE TABLE IF NOT EXISTS dq_results (
        run_dt VARCHAR, check_name VARCHAR, severity VARCHAR, bad BIGINT, total BIGINT,
        passed BOOLEAN, checked_at TIMESTAMPTZ)""")
    con.execute("DELETE FROM dq_results WHERE run_dt = ?", [run_dt])  # 同じ日を再実行しても結果は 1 組だけ
    failed = []
    for check in checks:
        bad, total = con.execute(check.sql).fetchone()
        passed = total == 0 or bad / total <= check.max_ratio
        con.execute("INSERT INTO dq_results VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [run_dt, check.name, check.severity, bad, total, passed, datetime.now(timezone.utc)])
        if not passed and check.severity == "error":
            failed.append(check.name)
    if failed:
        raise QualityError("error の確認が不合格です: " + ", ".join(failed))
```

ここにも、教えた決まりが入っています。error の不合格があっても、**全部の確認を実行して結果を残してから**止めます。最初の不合格で止めると、ほかに何が壊れているかが見えないからです。また、同じ日を再実行したときに結果が二重に残らないよう、その日の結果を消してから入れます。

### 1 本につなぐ

全体をつなぐのは、`pipeline.py` の `run` です。

```python title="pipeline.py"
def run(store, dt, workdir):
    """全工程を実行して、図のパスを返します。"""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    db_path = workdir / "warehouse.duckdb"
    ingest.land(store, dt)
    con = duckdb.connect(str(db_path))
    try:
        print("raw に読み込み:", ingest.load_raw(con, store, dt))
    finally:
        con.close()  # dbt が同じファイルを開くので、いったん閉じる (DuckDB は同時に 1 つのプロセスしか書けない)
    dbt_build(workdir, db_path)
    con = duckdb.connect(str(db_path))
    try:
        try:
            quality.run_checks(con, dt)
        finally:
            for name, severity, passed in con.execute(
                    "SELECT check_name, severity, passed FROM dq_results WHERE run_dt = ? ORDER BY rowid", [dt]).fetchall():
                print(f"  {'OK  ' if passed else severity.upper():5} {name}")
        figure = workdir / f"dashboard_{dt}.svg"
        dashboard.draw(con, dt, figure)
    finally:
        con.close()
    return figure
```

`run` は、途中で例外が出れば、そこで止まります。その次の工程には進みません。`finally` の中で結果を表示しているので、`QualityError` で止まったときにも、どの確認が不合格だったかが表示に残ります。DuckDB は 1 つのファイルを同時に 1 つのプロセスしか書き込めないので、dbt を呼ぶ前に、こちらの接続をいったん閉じています。

## 止まり方と冪等さを確かめる

動かして「できた」で終わらせず、テストで確かめます。`examples/b16/test_b16_project.py` に、次の内容が入っています。

- 手元のフォルダ版と MinIO 版の両方で、最後まで通る。落ちた確認は、warn の 1 件だけ。
- 同じ日付で 2 回実行しても、売上の合計も `dq_results` も変わらない。
- `_SUCCESS` を消すと、`load_raw` が `RuntimeError` で拒否する。
- 売上の合計をわざと合わなくすると、`QualityError` で止まる。止まる前に、5 件すべての結果が記録されている。

パイプラインを書いたあと、「壊したときにどうなるか」を 1 回は確かめてください。確かめていない止まり方は、本番で初めて動くことになります。

## 設計メモ (README) を書く

作ったものを、他の人が (半年後の自分も) 引き継げるようにするのが、設計メモです。コードの説明ではなく、**決めたことと、その理由**を書きます。コードを読めば何をしているかは分かりますが、なぜそうしたか、何をやらなかったかは分からないからです。

書く項目の目安は、次の 7 つです。

1. 何のためか (誰が、何に使うか)
2. 決めたこと (数字の定義。「売上」にキャンセルを含めるか、など)
3. 全体の流れ (図か短い文)
4. 動かし方 (コピーして動く形で)
5. 品質チェックと、止める基準
6. 既知の限界
7. 次にやること

このプロジェクトの設計メモを、`examples/b16/DESIGN_MEMO.md` に置きました。

```text
# ねぼすけ商店 日次売上ダッシュボード 設計メモ

## 何のためか
店長が毎朝、前日までの日別売上と、その数字を信じてよいかを 1 枚で見られるようにする。

## 決めたこと (数字の定義)
- 売上 = キャンセル以外の注文の「数量 × 単価」の合計。注文日は ordered_at の日付 (UTC)。
- 状態の表記ゆれ (shipped / SHIPPED) は、変換 (staging) で小文字にそろえる。raw は直さない。
- 更新は 1 日 1 回。結果が出るまでの許容は翌朝まで (バッチで足りる。ストリームにはしない)。

## 全体の流れ
取り込み (Parquet を landing に置く) → raw (DuckDB) → dbt (staging → fct_daily_sales)
→ 品質チェック (5 件) → 図 (SVG)。どこかで失敗したら後ろの工程は動かない。

## 動かし方
    docker compose up -d --wait
    sh examples/b16/run.sh
同じ日付で何度実行しても同じ結果になる (landing のキーは上書き、raw と dbt は作り直し、dq_results は日付ごとに入れ替え)。

## 品質チェックと、止める基準
- error (止める): orders が空 / 日別売上の日付の NULL・重複 / 日別売上の合計が raw の明細と不一致。
- warn (知らせて進む): events の event_id 重複 (元データの既知の欠陥。現状 40 件) / 遅延到着が 5% 超。
- 基準の根拠: 売上の数字が壊れるものは error、集計に直接使わない events の欠陥は warn。

## 既知の限界
- 取り込みは毎回全件の置き直し (増分ではない)。件数が増えたら watermark 方式に変える。
- 実行はコマンド 1 本。スケジューラ (Airflow など) には載せていない。
- 通知は標準出力だけ。

## 次にやること
1. 増分取り込みにする。 2. Airflow から呼ぶ。 3. warn の件数が増えたら通知する。
```

特に「既知の限界」は、書くのに勇気がいる項目です。しかし、ここを書いていると、読む人は「この人は何ができて何ができないかを分かっている」と受け取ります。書かないと、読む人は自分で限界を探し当てることになり、そのときの印象はずっと悪くなります。

なお、判断の記録を 1 件ずつ短い文書にして残す書き方があります。Michael Nygard が提案した Architecture Decision Record (ADR) で、「状況・決めたこと・結果」を 1 枚に書きます (参考文献 2)。設計メモの「決めたこと」が増えてきたら、ADR に分けると読みやすくなります。

## ポートフォリオにするときのコツ

ポートフォリオは、「この人に仕事を任せられるか」を判断する材料です。派手さより、**再現できること**と、**判断が見えること**が大事です。

**何を見せるか。**

- 1 つの題材を、取り込みから使える形まで通したもの。この章の演習のように、止まり方と冪等さまで確かめてあるもの。
- 設計メモ。何を決めて何をやらなかったか。
- テスト。動くことを自動で確かめている証拠になります。
- 失敗と直した記録。「最初はこうして壊れ、こう直した」は、完成品より多くを伝えます。

**入れてはいけないもの。**

- 秘密 (API キー・パスワード・接続文字列・`.env`)。公開した瞬間に、悪用されるおそれがあります。一度でも commit した秘密は、履歴に残ります。消したつもりでも、キーは失効させて作り直します。第3章の `.gitignore` と環境変数の使い方を、そのまま使います。
- 勤務先や顧客のデータ・コード・社内の名前。守秘義務に触れます。題材は、公開データか、ねぼすけ商店のような架空のデータにします。
- 個人情報。氏名やメールアドレスが入ったデータは、架空のものであっても、本物と区別がつかない形では載せません。

**再現手順。** README の「動かし方」を、新しい環境で上から順に実行して、動くことを自分で確かめます。自分のマシンにだけある設定やファイルに頼っていないか、見つかるのはたいていここです。`docker compose up` とテストのコマンドを、そのまま貼れる形で書くと、見る人の手間が大きく減ります。

**見る人の時間は短い。** README の最初の数行で、何を作ったか、何が分かるかを書きます。細かい説明はその下です。

## 現場での最初の 90 日

入社(または異動)後の最初の 90 日は、新しいものを作るより、**読んで、聞いて、小さく直す**時間にします。経験豊富な人ほど、早く新しいものを作りたくなりますが、そこにある仕組みを知らないまま作ると、既にある別の仕組みと食い違います。

{{ table("b16-90days") }}

**聞くこと。** 次の質問は、どの職場でも役に立ちます。

- このデータは、誰が、何のために、どのくらいの頻度で見ていますか。止まると誰が困りますか。
- 過去に大きく壊れたことはありますか。そのとき何が原因でしたか。
- 「売上」「有効な顧客」のような言葉の定義は、どこに書いてありますか。人によって違いませんか。
- 夜中に壊れたとき、誰が気づいて、誰が直しますか。

**読むもの。** 動いているジョブの一覧と、直近の失敗の履歴、既存のドキュメント、レビューで指摘されている内容 (チームが大事にしている基準が見えます)、そして障害の振り返りです。振り返りは、責める文書ではなく、仕組みの弱点を読む文書として書かれているのが理想で、Google の SRE の本が「責めない振り返り」の考え方を説明しています (参考文献 3)。

**小さく直す。** 最初に直すのは、影響が小さく、確認しやすいものにします。たとえば、テストの無い重要な列にテストを足す。失敗しても誰にも通知されないジョブに通知を足す。実行手順の書かれていない作業を、手順書にする。小さく直して、レビューを受け、出す。この往復を、チームの流儀を知るために使います。

やってはいけないのは、読む前に「作り直したい」と言い出すことです。作り直したくなるのは、たいてい、まだ理由を知らない部分です。理由を聞いてから、それでも直したいなら、根拠を数字で示して提案します。

## 学び続ける

データエンジニアリングの道具は、数年で入れ替わります。そのため、道具の使い方より、**変わらない考え方**を土台にして、道具は必要になったときに調べて覚えるのが、長く続く方法です。

**公式ドキュメントを一次情報にする。** ブログの記事は、書かれた時点の版の話です。仕様は、公式ドキュメントで確かめます。PostgreSQL・DuckDB・dbt・Airflow・Kafka・Docker は、どれもドキュメントが充実しています (参考文献 5 から 10)。使っている版のページを開いているかを確かめる癖をつけてください。

**リリースノートを読む。** 使っている道具の新しい版が出たら、リリースノートの「破壊的な変更」と「非推奨」の項目だけでも読みます。ある日突然ジョブが落ちる原因の多くは、ここに書いてあります。PostgreSQL・Airflow・dbt・DuckDB は、どれも公開しています (参考文献 5 から 8)。

**手元の本。** この本の参考文献に挙げた、次の本がよい次の一冊になります。

{{ table("b16-books") }}

読み方は、章を最初から全部読むより、いま仕事で困っている段階の章を先に読み、必要なら戻る形が続きます。本に出てくるコードや構成は、自分で動かして初めて身につくので、小さくても手を動かしてください。

**自分の記録を残す。** 分からなかったことと、解決した方法を、短くメモにします。この本の設計メモと同じで、半年後の自分への手紙です。

## 面接でよく聞かれること

面接の質問は会社ごとに違うので、ここに書くのは「よく聞かれる分野」と「答えの型」です。型を持っていると、知らない質問が来たときにも、落ち着いて組み立てられます。

{{ table("b16-interview") }}

**SQL。** 手元で書く問題が出ることがあります。最初に粒度(1 行が何か)を確かめてから書き、書いたあとで件数で検算する、という順にすると、間違いに気づきやすくなります。`examples/b16/interview.sql` に、次の形の問題を置きました。

```sql
-- 面接でよく出る形の SQL。パイプラインを一度動かしたあとの warehouse.duckdb (DuckDB) で動かします。

-- 1. 顧客ごとの最初の注文 (同じ時刻のときは order_id の小さいほう)。標準 SQL の書き方
SELECT customer_id, order_id, ordered_at
FROM (
    SELECT customer_id, order_id, ordered_at,
           row_number() OVER (PARTITION BY customer_id ORDER BY ordered_at, order_id) AS rn
    FROM analytics.stg_orders
) AS t
WHERE rn = 1
ORDER BY customer_id;

-- 2. 日別売上の「直近 7 行」の平均。注文の無い日は行が無いので、7 行は 7 日とは限らない
SELECT order_date, sales,
       avg(sales) OVER (ORDER BY order_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS avg_last_7_rows
FROM analytics.fct_daily_sales
ORDER BY order_date;

-- 3. 検算: 注文の件数が、明細の無い注文を含めて合っているか (JOIN で行が消えていないか)
SELECT (SELECT count(*) FROM analytics.stg_orders) AS orders,
       (SELECT count(DISTINCT order_id) FROM main.order_items) AS orders_with_items;
```

1 つ目は `row_number` で、顧客ごとの先頭の行を取る定番の形です。DuckDB には `QUALIFY` という、窓関数の結果で絞る構文があり、サブクエリなしで書けます。ただし PostgreSQL や標準 SQL にはない書き方なので、面接で使うなら、どこで動くかを一言添えてください。2 つ目は、「直近 7 日」を `ROWS BETWEEN 6 PRECEDING` で書いたものです。これは直近の **7 行**であって、注文の無い日の行が無ければ、7 日ではありません。7 日にしたいなら、日付の表と結合して欠けた日を 0 で埋めるか、範囲指定 (`RANGE`) を使います(`RANGE` の間隔指定の書き方は製品で違います)。「この数字は本当に 7 日か」と自分から指摘できると、評価が上がります。

**モデリング。** 第8章の 4 つの手順をそのまま口に出します。「まず業務の質問を確かめ、粒度を決めて、ファクトとディメンションを分け、履歴の持ち方を決めます」。

**パイプラインの設計。** 「毎朝の売上レポートの基盤を設計してください」のような問いでは、いきなり道具の名前を並べないことです。鮮度(翌朝までか)、正しさ(どの定義か)、量(何行か)を、聞き返します。次に、取り込み・保存・変換・品質・運用の順に、選んだ理由と、**選ばなかった案**を言います。この章の設計メモの構成が、そのまま答えの骨組みになります。

**障害対応。** 「朝に数字がおかしいと言われたら」という問いには、順序で答えます。まず間違った数字が使われ続けないように止める(止血)。次に影響範囲(いつから、どのテーブルとレポートか)。原因を調べて直す。最後に、再発を防ぐテストと通知を足す。原因探しの前に止血を言えるかを、見られることが多いです。

答えるときの注意が 2 つあります。分からないことは「分かりません。こう調べます」と言うこと。経験していないことを、したように話さないこと。この本の演習で作ったものは、「自分で作って確かめた」と堂々と言える題材です。

## 応用編への案内

基礎編は、ここまでです。続く応用編は、全 12 章です。現場で出会う順や、興味のある順で読んで構いません。

{{ table("b16-advanced") }}

次に何を読むかは、いま困っていることで決めるのが一番です。たとえば、Spark のジョブが遅いなら第2章、秘密や個人情報の扱いが気になるなら第9章、コストが話題なら第10章です。迷ったら、この章の設計メモの「次にやること」を見てください。そこに書いたことに一番近い章が、次の一歩です。

## よくある失敗

- **全部を 1 つのスクリプトに詰めて、途中の結果を残さない。** 失敗したとき、どの工程が悪いか分からなくなります。この演習のように、工程ごとに置き場(landing・raw・mart)を分けます。
- **動いたところで終わって、壊れたときを試さない。** 止まり方も、再実行も、テストで確かめます。
- **品質チェックが全部 error、または全部 warn。** 全部 error だと、頻繁に止まって誰も見なくなり、全部 warn だと、何も止まりません。売上の数字が壊れるものだけを error にします。
- **README に動かし方だけがあって、理由が無い。** 引き継ぐ人が最初に知りたいのは、なぜそうなっているかです。
- **ポートフォリオに秘密や実データが入る。** 公開前に、履歴も含めて確かめます。
- **最初の 90 日で作り直そうとする。** 読む・聞く・小さく直すを先にします。
- **学ぶ対象を道具で追い続ける。** 新しい名前が出るたびに追うと終わりがありません。考え方を土台にして、道具は必要になったときに学びます。
- **面接で、経験していないことを経験したように話す。** 深く聞かれると崩れます。作って確かめたことを、そのまま話すほうが強いです。

## まとめ

- 基礎編の総仕上げとして、取り込み → raw → 変換 → 品質チェック → 図を 1 本で通しました。大事なのは、壊れたときに、どこで止まるかです。
- 書きかけを読まない (`_SUCCESS`)、同じ日付で再実行しても同じ (冪等)、error の不合格では図を作らない、という決まりを、コードとテストの両方に入れました。
- 設計メモは「決めたこと・理由・限界・次にやること」を書きます。ポートフォリオは再現できることと判断が見えることが大事で、秘密と実データは入れません。
- 最初の 90 日は、読む・聞く・小さく直す。学び続けるには、公式ドキュメントとリリースノートを一次情報にします。
- 面接では、分野ごとの答えの型 (粒度の確認、要件を聞き返す、止血から始める) を持ちます。

おつかれさまでした。基礎編はここまでです。次は、手元で動くものを 1 つ、自分の題材で作ってみてください。

!!! tip "さらに深く"
    パイプラインの健康を数字で見張る方法(SLO・リネージ)は、応用編 第8章「観測性・SLO・リネージ」で扱います。チームでの役割分担や基盤の運営は、応用編 第12章「プラットフォーム設計と組織」です。

## 練習問題

問1. `examples/b16/quality.py` の `CHECKS` に、「`fct_daily_sales` の売上に負の値が無い」という error の確認を 1 件足してください。足したあと、パイプラインが通ることを確かめ、そのうえで、どんな状況でその確認が不合格になるかを 1 つ挙げてください。

??? note "解答例"
    たとえば `Check("日別売上に負の値が無い", "error", "SELECT count(*) FILTER (WHERE sales < 0), count(*) FROM analytics.fct_daily_sales")` を足します。bad が 0 なら合格で、通ります。不合格になるのは、返品の行 (数量が負の明細) が raw に混ざり、日の合計が負になるような場合です。この確認が error なのは、売上の数字そのものが壊れるためです。なお、足したら `test_b16_project.py` の件数の確認 (`len(quality.CHECKS)`) は自動で追従しますが、「落ちたのは warn の 1 件だけ」の確認は、そのまま通ることを実行して確かめてください。

問2. この演習の `ingest.py` の `land` で、`_SUCCESS` を置く行を、表を置く前に移すと、何が起きますか。テストのうち、どれがそれを見つけますか。見つけない場合は、どんなテストを足しますか。

??? note "解答例"
    読む側は印があれば読むので、置いている途中の `dt` を、書きかけのまま読めてしまいます。既存のテストは、最後まで通った結果しか見ておらず、`test_load_refuses_partition_without_success_marker` は印が無いときの拒否だけを確かめるので、順序の入れ替えは見つけません。足すなら、テスト用の `store` に `put` の呼び出し順を記録させ、`_SUCCESS` のキーが最後であることを確かめます。

問3. 面接で「ダッシュボードの売上が、昨日と比べて半分になっている」と言われました。最初の 3 つの行動を、順序の理由とともに答えてください。

??? note "解答例"
    1 つ目は、間違った数字が使われ続けないようにする止血です(ダッシュボードに注意書きを出す、更新を止めるなど)。理由は、原因探しの間も、見た人が誤った判断をするためです。2 つ目は、影響範囲の確認です。いつから半分か、全体か特定の商品や地域だけか、ほかのレポートにも出ているか。範囲が分かると、原因の見当がつきます。3 つ目は、パイプラインの工程を遡ることです。品質チェックの結果、直近の取り込みの件数、変換のテストを、出口から入口の順に見ます。取り込みの件数が半分なら取り込み、そうでなければ変換や定義の変更です。原因を直したあとに、同じことを検知するテストと通知を足します。

問4. 自分のポートフォリオ用リポジトリを公開する前の点検として、第3章の道具を使い、秘密が入っていないかを確かめる手順を書いてください。

??? note "解答例"
    作業ツリーだけでなく履歴も調べます。たとえば `git log -p` の出力を `grep -i -E "password|secret|api[_-]?key|token"` にかける、`git ls-files` で `.env` やキーのファイルが追跡されていないかを見る、`.gitignore` に `.env` が入っているかを見る、の 3 つです。専用の検出ツールを使うこともできます。見つかったら、履歴から消すだけでなく、そのキーを失効させて作り直します。公開した後で消しても、すでにコピーされているおそれがあるためです。

## 参考文献

1. Joe Reis, Matt Housley. *Fundamentals of Data Engineering*. O'Reilly Media, 2022.（全体の設計判断、取り込み、変換、提供）
2. Michael Nygard. "Documenting Architecture Decisions". 2011. <https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions>（ADR）
3. Google. *Site Reliability Engineering*. "Postmortem Culture: Learning from Failure". <https://sre.google/sre-book/postmortem-culture/>（責めない振り返り）
4. Matt Palmer. *Understanding ETL*. O'Reilly Media (Databricks 提供版), 2024.（取り込み、変換、オーケストレーション、障害の対処）
5. PostgreSQL Documentation. "Release Notes". <https://www.postgresql.org/docs/release/>
6. Apache Airflow Documentation. "Release Notes". <https://airflow.apache.org/docs/apache-airflow/stable/release_notes.html>
7. dbt Documentation. "dbt release notes". <https://docs.getdbt.com/docs/dbt-versions/dbt-cloud-release-notes>
8. DuckDB. "News". <https://duckdb.org/news/>
9. Apache Kafka Documentation. <https://kafka.apache.org/documentation/>
10. Docker Documentation. <https://docs.docker.com/>
11. Gwen Shapira ほか. *Kafka: The Definitive Guide*, 2nd Edition (Early Release, 2020). O'Reilly Media. / Jules S. Damji ほか. *Learning Spark*, 2nd Edition. O'Reilly Media, 2020. / Russell Jurney. *Agile Data Science 2.0*. O'Reilly Media, 2017.（学び続けるための本の表）

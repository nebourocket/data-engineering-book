# 第12章 オーケストレーション

## この章でできるようになること

- cron だけでは足りなくなる場面を、具体的に挙げられる。
- 処理の依存を DAG（輪を持たない有向グラフ）で表し、失敗したときに何が動き、何が止まるかを説明できる。
- 日付を引数に取り、何度実行しても同じ結果になる（冪等な）日次ジョブを書ける。
- バックフィル（過去の期間を作り直すこと）を、安全に実行できる。
- リトライ・タイムアウト・SLA の役割を区別し、センサーでデータの到着を待てる。
- Airflow の DAG（TaskFlow API）を読み書きし、XCom に大きなデータを渡してはいけない理由を説明できる。
- Dagster・Prefect の考え方が Airflow とどう違うかを説明できる。

第3章で cron を使い、第4章で再試行を書き、第9章で取り込みを冪等にしました。この章は、それらの部品を束ねて、毎日安定して動かし続ける仕組みの話です。コードは `examples/b12/` にあります。リポジトリの直下で動かします。Airflow そのものは手元で動かさなくても、ジョブの本体は pytest で確かめられる形に分けてあります。

## なぜ cron だけでは足りないか

第3章の cron は、時刻になったらコマンドを動かす道具でした。1 本のジョブを毎日動かすだけなら、`flock` と組み合わせた cron で十分です。ところが、ジョブが増えると、次のことが困ります。

1. **依存を書けない。** 「取り込みが終わってから集計」を、cron では時刻をずらして表すしかありません。取り込みが長引いた日は、未完成のデータを集計してしまいます。
2. **失敗に気づけない。** cron は終了コードを見ません（第3章）。失敗しても、誰かがログを見るまで分かりません。
3. **再試行が無い。** 一時的な失敗でも、次の日まで待つことになります。
4. **過去分を作り直しにくい。** 「3 月 1 日から 7 日までをやり直す」を、日付を変えて手で 7 回流すことになります。
5. **データを待てない。** 元のデータが遅れた日に、空のまま処理が走ります。
6. **状況が見えない。** どのジョブがいつ動き、何分かかり、どこで止まっているかの一覧がありません。

Reis と Housley の *Fundamentals of Data Engineering* は、cron のような単純なスケジューラは時刻しか知らないのに対し、オーケストレーションの仕組みはジョブの依存関係を、DAG の形で持つと説明しています。さらに、実行履歴・可視化・アラート・バックフィルも備えます。この章のオーケストレーションは、この全体を指します。

## DAG と、タスクの依存と順序

**タスク**は、1 つの処理の単位です。「取り込む」「整える」「集計する」のように、失敗したときにそこだけやり直せる大きさに切ります。**DAG**（有向非巡回グラフ）は、タスクを点、「先にこれが終わっていること」を矢印にしたものです。矢印をたどって元の点に戻る輪が無いので、「非巡回」と呼びます。輪があると、どれから動かせばよいか決められません。

標準ライブラリの `graphlib` を使って、DAG の考え方だけを再現した小さな実行器を作りました。

```python
def run(tasks: dict[str, Callable[[], None]], deps: dict[str, set[str]]) -> dict[str, str]:
    """依存の順にタスクを動かし、{名前: 状態} を返します。

    状態は success / failed / upstream_failed のどれかです。
    先のタスクが成功していなければ動かさず（upstream_failed）、関係のない枝は動かし続けます。
    輪になった依存（A→B→A）は graphlib.CycleError になります。
    """
    graph = {name: deps.get(name, set()) for name in tasks}
    state: dict[str, str] = {}
    for name in TopologicalSorter(graph).static_order():
        if any(state[d] != "success" for d in graph[name]):
            state[name] = "upstream_failed"
            continue
        try:
            tasks[name]()
            state[name] = "success"
        except Exception as exc:
            print(f"{name} が失敗しました: {exc}")
            state[name] = "failed"
    return state
```

`TopologicalSorter` は、依存を満たす順にタスクを並べます（トポロジカルソート）。実行するとき、`quality_check` に失敗する例が入っています。

```bash
python examples/b12/mini_runner.py
```

```text
quality_check が失敗しました: 品質チェックに失敗
extract       success
clean         success
aggregate     success
quality_check failed
notify        success
publish       upstream_failed
```

`publish`（公開）は、`aggregate` と `quality_check` の両方が成功してから動く、と宣言してあります。品質チェックが失敗したので、公開は動きません（`upstream_failed`）。一方、`aggregate` だけに依存する `notify` は、関係がないので動きます。「壊れたデータを公開しない」を、実行器が順序で守ってくれます。cron の時刻ずらしでは、これができません。依存を輪にすると `CycleError` になることも、テストで確かめています（練習問題 3）。

## 冪等性と論理日付

日次ジョブでいちばん大事な決まりは、**日付を引数で受け取る**ことです。`datetime.now()` で「今日」を決めると、再実行したとき（たとえば 2 日後の復旧作業）に、別の日の結果ができてしまいます。処理する日を外から渡せば、「3 月 5 日の分」を、いつ実行しても同じ意味で作れます。この、実行した時刻ではなく処理の対象になる区間の日付を、**論理日付**（logical date）と呼びます。

もう 1 つの決まりは、**その日の結果を置き換える**ことです。追記すると、再実行のたびにデータが重なります。第4章で、再試行の前提は冪等（何度繰り返しても結果が変わらない）ことだと学びました。日次ジョブも同じで、冪等であれば、失敗したら安心して流し直せます。次が、その日の売上をカテゴリ別に集計するジョブの本体です。

```python
def process(day: str, source: Path, out_dir: Path) -> int:
    """day の売上をカテゴリ別に集計し、その日のファイルを丸ごと置き換えます。書いた行数を返します。

    追記はしません。書き出しは一時ファイルに行い、最後に os.replace で入れ替えるので、
    途中で失敗しても前回のファイルは壊れず、書きかけが公開されることもありません。
    """
    day = check_day(day)
    rows = duckdb.connect().execute(
        """
        SELECT CAST(? AS DATE) AS date, category, count(DISTINCT order_id) AS orders,
               sum(quantity * unit_price) AS revenue
        FROM read_csv(?)
        WHERE CAST(ordered_at AS DATE) = CAST(? AS DATE) AND lower(status) <> 'cancelled'
        GROUP BY category
        ORDER BY category
        """, [day, str(source), day]).fetchall()

    target = out_dir / "daily_sales" / f"date={day}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{day}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
            writer.writerows(rows)
        os.chmod(tmp, 0o644)  # mkstemp は本人しか読めない 0600 で作るので、読む側のために 0644 にする
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return len(rows)
```

読みどころは 4 つあります。

- **日付を検証する。** `check_day` は `2026-03-05` の形だけを受け付けます。`2026-3-5` や空文字は、ファイルを作る前に `ValueError` にします。壊れた日付で、おかしな名前のファイルができるのを防ぎます。
- **日付ごとに 1 ファイル。** 出力は `date=2026-03-05.csv` です。第11章のパーティションと同じ形で、その日だけを置き換えられます。
- **一時ファイルに書き、`os.replace` で入れ替える。** 第3章の「一時ファイルに書いて最後に `mv`」と同じ考え方です。同じフォルダの中でのファイル名の付け替えは、途中の状態が見えない形で行われます（Python の文書では、`os.replace` は成功すれば、置き換え先を入れ替えると説明されています。置き換えが不可分になるかどうかは、OS とファイルシステムによります）。失敗しても、前回のファイルは残ります。
- **`os.chmod` で権限を戻す。** `mkstemp` が作るファイルは本人しか読めない設定（0600）です。そのまま入れ替えると、読む側のプロセス（別のユーザーで動く BI など）が、ファイルを読めなくなります。テストで 0644 になることを確かめています。

なお、この例の出力先は CSV のファイルです。データベースへ入れる処理（第9章）では、日付の範囲を一度に消してから入れ直すか、主キーで upsert（あれば更新、なければ追加）して、同じ冪等の性質を保ちます。

入力の CSV を作って、動かします。

```bash
python examples/b12/make_source.py
```

```text
7469 行を work/source/sales.csv に書きました
```

```bash
python examples/b12/daily_job.py 2026-03-05
cat work/out/daily_sales/date=2026-03-05.csv
```

```text
2026-03-05: 5 行
date,category,orders,revenue
2026-03-05,寝具,6,16000
2026-03-05,朝食,8,84750
2026-03-05,目覚まし,6,16550
2026-03-05,雑貨,5,20100
2026-03-05,飲み物,12,119750
```

同じ日をもう一度流しても、ファイルの中身は変わりません。テストは 3 つの形で確かめています。同じ日を 3 回流してもバイト列が同じこと、遅れて届いた明細（元データに足した 1 行）が入った後の再実行では行が増えず売上だけが 2,000 円増えること、ほかの日のファイルが変わらないことです。

日付の区切りには、タイムゾーンが関わります。この例の元データは、日本時間の日付をそのまま持つ文字列で、`CAST(ordered_at AS DATE)` はその日付で区切ります。実際のデータが UTC で入っているなら、日本の 1 日の区切りは UTC の前日 15 時になるので、区切りの時刻を決めてから集計します（第3章）。

## バックフィル

**バックフィル**は、過去の区間を作り直すことです。ロジックの間違いを直したとき、元データが後から訂正されたとき、新しい集計を過去にさかのぼって作るときに使います。冪等な日次ジョブなら、バックフィルは「日付を変えて、同じジョブを繰り返す」だけです。

```python
def backfill(start: str, end: str, source: Path, out_dir: Path) -> dict[str, int]:
    """start から end までの各日を process で作り直します。{日付: 行数} を返します。"""
    return {day: process(day, source, out_dir) for day in days_between(start, end)}
```

`days_between` は、両端を含む日付の列を昇順で返します（`2026-03-01` と `2026-03-07` なら 7 日分）。終わりが始まりより前だと `ValueError` にします。実行します。

```bash
python examples/b12/daily_job.py 2026-03-01 2026-03-07
ls work/out/daily_sales
```

```text
2026-03-01: 5 行
2026-03-02: 5 行
2026-03-03: 5 行
2026-03-04: 5 行
2026-03-05: 5 行
2026-03-06: 5 行
2026-03-07: 5 行
date=2026-03-01.csv
date=2026-03-02.csv
date=2026-03-03.csv
date=2026-03-04.csv
date=2026-03-05.csv
date=2026-03-06.csv
date=2026-03-07.csv
```

注文のない日にも、見出しだけのファイルを作ります（テストで確かめています）。ファイルが無いのは「まだ動いていない」、見出しだけなのは「動いたが注文は 0 件だった」と区別するためです。

バックフィルで気をつけることは、次のとおりです。

- **一部だけやり直しても全体が変わらないこと。** 3 月 3 日から 5 日だけ流し直しても、ほかの日のファイルは同じ中身のままです（テスト済み）。
- **負荷。** 1 年分を一度に流すと、元のシステムや DWH に大きな負荷をかけます。同時に動かす日数に上限を付けます。Airflow では `max_active_runs` で設定します。
- **途中で止まったときの再開。** 冪等なので、止まった日から最後までを、もう一度流せば足ります。最初からやり直しても結果は同じですが、時間がかかります。
- **集計の依存。** 日次の結果を使う月次の集計があるなら、日次をすべて直してから月次を流します。DAG の依存で順序を守ります。

## リトライ・タイムアウト・SLA

3 つの言葉は、似ていますが別の役割です。

- **リトライ**は、失敗した処理を、時間を置いて自動でやり直すことです。一時的な失敗（ネットワークの切断、混雑）に効きます。何を再試行してよいか、待ち時間をどう延ばすかは第4章で学びました。冪等でない処理を再試行すると、データが重なります。
- **タイムアウト**は、処理の上限時間です。無限に待ち続けて、後ろのジョブをすべて止める事態を防ぎます。上限は、通常の実行時間より少し長めに決めます。
- **SLA**（サービス水準）は、「毎朝 9 時までにデータが揃っている」のような、利用者への約束です。タスクが失敗したかどうかではなく、約束の時刻に間に合ったかどうかを見ます。遅れたら通知します。Airflow 2.10 の DAG には SLA を指定する機能がありますが、版によって仕組みが変わるので、使う版の文書を確かめてください。

3 つは組み合わせて使います。たとえば、「30 分でタイムアウトし、5 分おいて 2 回まで再試行し、それでも 9 時に間に合わなければ通知する」という具合です。再試行の回数を増やしすぎると、復旧の遅れが目立たなくなります。失敗した回数は、再試行で直ったものも含めてログに残し、増えていないかを見ます。

## センサーとイベント起動: データの到着を待つ

時刻で動かすジョブは、元データがその時刻に揃っている、という前提で動きます。元データの出力が遅れた日に、空のデータから結果を作って「成功」にすると、気づかれない欠損になります。これを防ぐのが**センサー**です。センサーは、条件が整うまで待つタスクです。条件は、ファイルが届いたこと、テーブルに今日の行があること、などです。この章の `source_has_day` は、元の CSV があり、その日の明細が 1 行以上あれば True を返します。

```python
def source_has_day(day: str, source: Path) -> bool:
    """元の CSV があり、その日の明細が 1 行以上あれば True（データが届いた目印）。"""
    if not source.exists():
        return False
    count = duckdb.connect().execute(
        "SELECT count(*) FROM read_csv(?) WHERE CAST(ordered_at AS DATE) = CAST(? AS DATE)",
        [str(source), check_day(day)]).fetchone()[0]
    return count > 0
```

待ち方には 2 種類あります。ずっとワーカー（タスクを実行する枠）を占めたまま、一定間隔で調べ続ける poke と、調べるたびにいったん枠を空け、次の時刻にもう一度取り直す reschedule です。待ちが長くなるなら reschedule です。待つ時間には上限（タイムアウト）を付けます。上限を越えたらタスクは失敗し、通知が飛びます。「待ちっぱなしで誰も気づかない」を防ぐためです。

もう 1 つの方法は、時刻ではなくイベントで動かすことです。上流のジョブが終わったら、下流を起動します。Airflow 2.10 には、データセットの更新を起点に DAG を動かす仕組み（Dataset。3 系では呼び名が変わる場合があります）があります。時刻だけで動かすより、依存が分かりやすくなります。ただし、イベントの取りこぼしに備えて、時刻での実行も併用することが多くあります。

## Airflow の基本

Airflow は、Apache のオーケストレーターで、DAG を Python のファイルで書きます。主な用語を、次の表にまとめます。

{{ table("b12-airflow-terms") }}

この章の DAG ファイル（`examples/b12/neboske_daily_sales.py`）を、上から読みます。まず、準備とタスクです。

```python
"""ねぼすけ商店の日次売上を作る DAG（第 12 章）。処理の本体は daily_job.py にあります。"""
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily_job  # noqa: E402

WORK = Path(os.environ.get("NEBOSKE_WORK", "/tmp/neboske"))
SOURCE = WORK / "source" / "sales.csv"
OUT = WORK / "out"


def notify_failure(context) -> None:
    """失敗を通知する場所。ここではログに書くだけです（実際はチャットやメールに送ります）。"""
    ti = context["task_instance"]
    logging.getLogger(__name__).error("失敗: %s / %s (論理日付 %s)", ti.dag_id, ti.task_id, context["ds"])


@task.sensor(poke_interval=300, timeout=6 * 60 * 60, mode="reschedule")
def wait_for_source(ds=None) -> bool:
    """その日の元データが届くまで待つ。待っている間はワーカーを空けておく（reschedule）。"""
    return daily_job.source_has_day(ds, SOURCE)


@task
def build(ds=None) -> dict:
    """その日の分だけを作り直す。同じ日を再実行しても、結果は変わらない。"""
    return {"day": ds, "rows": daily_job.process(ds, SOURCE, OUT)}


@task
def report(result: dict) -> None:
    """前のタスクの結果は、小さな dict（日付と行数）だけを XCom で受け取る。"""
    logging.getLogger(__name__).info("%s: %d 行を書きました", result["day"], result["rows"])
```

これは **TaskFlow API** です。普通の Python の関数に `@task` を付けると、それが 1 つのタスクになります。関数の引数 `ds` には、実行の論理日付が `2026-03-05` の形で入ります。DAG の中身は、ジョブ本体（`daily_job.process`）を呼ぶだけです。本体は Airflow を知らないので、Airflow なしで pytest にかけられます。処理を DAG ファイルに直接書き込むと、テストのたびに Airflow が要ります。

`build` は小さな dict（日付と行数）を return し、`report` が受け取ります。この受け渡しが **XCom** です。XCom は、既定では Airflow のデータベースに値を保存します。Airflow の文書は、小さなデータ向けで、データフレームのような大きな値を渡さないよう書いています。大きなデータは、ファイルやテーブルに書いて、その場所（パスやテーブル名）だけを渡します。この例では、結果のファイルはすでに `OUT` の下にあり、XCom には件数だけを渡しています。次が DAG の定義です。

```python
@dag(
    dag_id="neboske_daily_sales",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(minutes=30),
        "on_failure_callback": notify_failure,
    },
    tags=["book"],
)
def neboske_daily_sales():
    ready = wait_for_source()
    result = build()
    ready >> result
    report(result)


neboske_daily_sales()
```

設定の意味は、次のとおりです。

- **`schedule="@daily"`**: 毎日 1 回、DAG Run（1 回分の実行）を作ります。日次の DAG Run は、対象の日（論理日付）が終わったあとに始まります。3 月 5 日の DAG Run は、3 月 6 日の 0 時（UTC）以降に動き、`ds` は `2026-03-05` です。「5 日に動くのに、5 日のデータ」ではなく、「5 日が終わってから、5 日のデータを処理する」と覚えます。
- **`start_date`**: スケジュールの始まりです。タイムゾーンを付けないと UTC として扱われます。日本の 1 日で区切りたいときは、タイムゾーン付きの開始日時を指定します。書き方は使う版の文書を確かめてください。
- **`catchup=False`**: 有効にしたときに、`start_date` から今までの取りこぼしの区間を、まとめて作らない設定です。True にすると、過去の何百日分もの DAG Run が一度に動き出すことがあります。過去分は、意図して、バックフィルとして流します。
- **`max_active_runs=1`**: 同じ DAG の DAG Run を、同時に 1 つまでにします。cron の `flock`（第3章）と同じ、重なり実行の防止です。
- **`retries` と `execution_timeout`**: 前の節の再試行とタイムアウトです。`on_failure_callback` は、失敗したときに呼ばれる関数で、ここに通知を書きます。
- **`ready >> result`**: `wait_for_source` が成功してから、`build` を動かす、という依存です。`report(result)` は `build` の結果を受け取るので、`build` のあとに動きます。

読み込みの確認は、CI の DagBag（Airflow が DAG ファイルを読み込む仕組み）で行います。本書のテストは、Airflow の部分だけを素通しにして、ファイルの文法、設定の値、タスクの中身を確かめます。手元に Airflow を入れて 1 回動かすなら、次のようにします（Linux・WSL・macOS 向けで、本書のテストでは実行していません）。

```bash
pip install "apache-airflow==2.10.5" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.12.txt"

export AIRFLOW_HOME="$PWD/work/airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/examples/b12"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export NEBOSKE_WORK="$PWD/work"

python examples/b12/make_source.py
airflow dags test neboske_daily_sales 2026-03-05
```

`--constraint` は、Airflow が動作確認した依存ライブラリの版を固定する指定です。Airflow は依存が多いので、公式はこの指定を勧めています。

## Dagster・Prefect との考え方の違い

Airflow は、「タスクを、いつ、どの順で動かすか」を中心に考えます。Dagster は、「作りたいデータ（アセット）」を中心に考えます。アセットは、テーブルやファイルなど、処理の結果として存在するデータです。「このアセットは、あのアセットから作る」と関数で宣言すると、依存と順序が決まります。画面にはタスクではなく、データの一覧が並び、どのデータがいつ最新になったかが見えます。第10章の dbt のモデルが、「このモデルはあのモデルを参照する」と書くことで依存が決まるのと、似た発想です。

Prefect は、Python の関数に `flow` や `task` を付けて、普通のコードのまま実行の状態を記録し、再試行などを付けられる道具です。DAG を先に宣言せず、関数を呼ぶ順で処理が決まります。条件分岐や繰り返しを、ふつうの Python で書きたいときに向きます。

{{ table("b12-orchestrators") }}

どれを選ぶかは、現場の既存の資産と、チームの慣れで決まります。Airflow は、使っている会社が多く、外部サービスとの連携部品が豊富です。アセット指向は、データの「いつの状態か」を中心に扱いたいときに向きます。考え方が分かっていれば、道具が変わっても、この章の冪等性・バックフィル・センサーはそのまま使えます。製品の機能は更新が早いので、選ぶときは公式の文書で、使う版を確かめてください。

## 監視とアラート

オーケストレーターを入れても、見ていなければ意味がありません。何を監視するかは、4 つに分けられます。

- **失敗**: タスクが失敗したか。再試行しても直らなかったか。
- **遅れ**: 約束の時刻（SLA）に間に合ったか。あるいは、いつもの実行時間より極端に長くないか。
- **中身**: 成功しているが、出力が空、または件数が急に減っていないか。オーケストレーターは「プログラムが正常に終わったか」しか知りません。中身の確認は、データ品質のチェックで行います（第13章）。
- **ログ**: 失敗の原因を、あとから追えるか。ログには、処理した日付と件数を残します（第4章）。

通知は、人が反応できる形に絞ります。失敗のたびに毎回通知すると、そのうち誰も見なくなります（アラート疲れ）。再試行で直ったものは通知せず、再試行をすべて使い切ったときと、約束の時刻に間に合わなかったときに通知します。通知の文面には、DAG の名前・論理日付・失敗したタスクと、再実行の手順へのリンクを入れます。この章の `notify_failure` は、その入口の例です。夜中に起こされた人が、何をすればよいか分かる通知が、よい通知です。

## よくある失敗

- 処理する日を `datetime.now()` で決めて、再実行や過去分のやり直しで、別の日の結果ができる。
- 結果を追記して、再実行のたびにデータが重なる。
- 書きかけのファイルを、読む側が見てしまう。一時ファイルに書いて、最後に入れ替える。
- `catchup=True` のまま有効にして、過去の DAG Run が一斉に動く。
- 元データの到着を待たず、空のデータから「成功」の結果を作る。
- XCom にデータフレームや大きな JSON を渡して、Airflow のデータベースを膨らませる。
- 再試行の回数だけ増やして、本当の障害が隠れる。
- 失敗の通知が多すぎて、誰も見なくなる。
- DAG ファイルに処理を全部書き込み、Airflow なしでテストできなくなる。

## まとめ

- cron は時刻しか知りません。依存・失敗の検知・再試行・過去分の作り直し・待機・履歴が要るようになったら、オーケストレーターの出番です。
- DAG は、タスクの依存を、輪の無い矢印で表します。上流が失敗すれば、下流は動かず、関係のない枝は動き続けます。
- 日付を引数に取り、その日の結果を置き換えると、ジョブは冪等になります。再実行とバックフィルが安全になります。
- リトライは一時的な失敗、タイムアウトは待ちすぎ、SLA は利用者への約束に対応します。
- センサーで、データの到着を待ちます。待ちには上限を付けます。
- Airflow では、DAG ファイルは薄くし、本体を別ファイルに置いてテストします。XCom には小さな値だけを渡します。
- Dagster は「データ（アセット）」、Prefect は「Python の関数」を中心に考えます。冪等性などの原則は、どの道具でも同じです。
- 監視は、失敗・遅れ・中身・ログの 4 つです。通知は人が反応できる数に絞ります。

## 練習問題

問 1. 3 月 1 日から 7 日をバックフィルしたあと、3 月 5 日の元データだけに、訂正の明細が足されました。何をすれば、3 月 5 日の結果だけを直せますか。ほかの日は変わりますか。

??? note "解答例"
    3 月 5 日だけを、もう一度流します。

    ```bash
    python examples/b12/daily_job.py 2026-03-05
    ```

    `process` は、その日のファイルを丸ごと置き換えるので、訂正が反映されます。ほかの日のファイルは、同じ中身のままです（`test_other_days_are_untouched` が確かめています）。全期間をやり直しても結果は同じですが、時間がかかります。

問 2. cron で「3 時に取り込み、3 時 30 分に集計」と設定していました。取り込みが 4 時まで長引いた日に、何が起きますか。オーケストレーターでは、どう防げますか。

??? note "解答例"
    3 時 30 分の集計は、取り込みの途中の（未完成の）データを読んで動き、欠けた集計を作ります。cron は、取り込みが終わったかどうかを知りません。オーケストレーターでは、集計のタスクが取り込みのタスクに依存すると宣言します。取り込みが終わるまで集計は動かず、取り込みが失敗したら、集計は動かずに失敗が通知されます。時刻は、DAG 全体の開始の目安にすぎません。

問 3. `mini_runner.run` に、`{"a": lambda: None, "b": lambda: None}` と、`a` が `b` に、`b` が `a` に依存する依存関係を渡すと、どうなりますか。

??? note "解答例"
    `graphlib.CycleError` になり、どのタスクも動きません。`a` が先に必要なのに、その `a` が `b` を待っている、という輪になっていて、順序が決められないからです。DAG の「非巡回」の意味はこれで、`test_runner_rejects_cycles` が確かめています。Airflow でも、輪のある DAG は読み込みの段階でエラーになります。

問 4. `quality_check` が失敗した日でも、`publish` を動かしたいという要望がありました。依存はどう変えられますか。そうすべきでしょうか。

??? note "解答例"
    `publish` の依存から `quality_check` を外せば（`deps["publish"] = {"aggregate"}`）、品質チェックの結果に関係なく動きます。Airflow では、上流が失敗しても動かす設定（トリガールール）がありますが、ここは勧めません。品質チェックの目的は、壊れたデータを公開しないことで、それを外すと目的が失われます。公開を止めて通知し、直してから再実行するのが基本です。どうしても見せる必要があるなら、「品質未確認」と分かる形で別の場所に出す、といった設計にします。

## 参考文献

- Joe Reis, Matt Housley, *Fundamentals of Data Engineering*, O'Reilly, 2022. 第2章 “Orchestration”（スケジューラとオーケストレーションの違い、DAG、バックフィル、アラート）。
- Apache Airflow 2.10.5 Documentation, “DAGs”, <https://airflow.apache.org/docs/apache-airflow/2.10.5/core-concepts/dags.html> ／ “Tasks”（再試行・タイムアウト・SLA）, <https://airflow.apache.org/docs/apache-airflow/2.10.5/core-concepts/tasks.html> ／ “DAG Runs”（論理日付・catchup・バックフィル）, <https://airflow.apache.org/docs/apache-airflow/2.10.5/core-concepts/dag-run.html>
- Apache Airflow 2.10.5 Documentation, “Tutorial: Pythonic DAGs with the TaskFlow API”, <https://airflow.apache.org/docs/apache-airflow/2.10.5/tutorial/taskflow.html> ／ “XComs”, <https://airflow.apache.org/docs/apache-airflow/2.10.5/core-concepts/xcoms.html> ／ “Sensors”, <https://airflow.apache.org/docs/apache-airflow/2.10.5/core-concepts/sensors.html> ／ “Data-aware scheduling (Datasets)”, <https://airflow.apache.org/docs/apache-airflow/2.10.5/authoring-and-scheduling/datasets.html> ／ “Best Practices”, <https://airflow.apache.org/docs/apache-airflow/2.10.5/best-practices.html> ／ “Callbacks”, <https://airflow.apache.org/docs/apache-airflow/2.10.5/administration-and-deployment/logging-monitoring/callbacks.html>
- Dagster Documentation, “Concepts”（アセット）, <https://docs.dagster.io/getting-started/concepts>
- Prefect Documentation, “Flows”, <https://docs.prefect.io/v3/concepts/flows>
- Python Documentation, “graphlib — Functionality to operate with graph-like structures”, <https://docs.python.org/3/library/graphlib.html> ／ “os.replace”, <https://docs.python.org/3/library/os.html>

!!! tip "さらに深く"
    失敗や遅れの検知を、SLO（サービス水準の目標）とリネージ（データの来歴）まで広げる話は、応用編 第8章「観測性・SLO・リネージ」で扱います。

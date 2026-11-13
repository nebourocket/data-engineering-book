# 第12章 オーケストレーション

## この章でできるようになること

- cron だけでは足りなくなる場面を、具体的に挙げられる。
- 処理の依存を DAG（輪を持たない有向グラフ）で表し、失敗したときに何が動き、何が止まるかを説明できる。
- 日付を引数に取り、何度実行しても同じ結果になる（冪等な）日次ジョブを書ける。ファイルにも、データベースにも。
- バックフィル（過去の期間を作り直すこと）を、安全に実行できる。
- リトライ・タイムアウト・SLA の役割を区別し、センサーでデータの到着を待てる。
- Airflow 3 の DAG（TaskFlow API）を読み書きし、データの区間と、XCom に大きなデータを渡してはいけない理由を説明できる。
- Dagster・Prefect の考え方が Airflow とどう違うかを説明できる。

第3章で cron を使い、第4章で再試行を書き、第9章で取り込みを冪等にしました。この章は、それらの部品を束ねて、毎日安定して動かし続ける仕組みの話です。コードは `examples/b12/` にあり、リポジトリの直下で動かします（出力は `work/` に作られます）。Airflow は、この本を書いた時点（2026年11月）の最新の 3 系（3.4.0）で動かして確かめました。ジョブの本体は Airflow を使わずに pytest で確かめられる形に分けてあります。

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
    輪になった依存（A→B→A）は graphlib.CycleError、tasks にない名前が deps にあれば ValueError です。
    """
    unknown = (set(deps) | {d for ds in deps.values() for d in ds}) - set(tasks)
    if unknown:  # 名前の書き間違いは、動かす前に分かるようにする
        raise ValueError(f"tasks にない名前が deps にあります: {sorted(unknown)}")
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

`TopologicalSorter` は、依存を満たす順にタスクを並べます（トポロジカルソート）。`tasks` に無い名前が `deps` にあると、動かす前に `ValueError` にします（名前の書き間違いに早く気づくためです）。実行するとき、`quality_check` に失敗する例が入っています。

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

`publish`（公開）は、`aggregate` と `quality_check` の両方が成功してから動く、と宣言してあります。品質チェックが失敗したので、公開は動きません（`upstream_failed`）。一方、`aggregate` だけに依存する `notify` は、関係がないので動きます。「壊れたデータを公開しない」を、実行器が順序で守ってくれます。cron の時刻ずらしでは、これができません。依存を輪にすると `CycleError` になることも、テストで確かめています。

## 冪等性と論理日付

日次ジョブでいちばん大事な決まりは、**日付を引数で受け取る**ことです。`datetime.now()` で「今日」を決めると、再実行したとき（たとえば 2 日後の復旧作業）に、別の日の結果ができてしまいます。処理する日を外から渡せば、「3 月 5 日の分」を、いつ実行しても同じ意味で作れます。この、実行した時刻ではなく、処理の対象になる日を、**論理日付**と呼ぶことがあります。ただし Airflow では、同じ言葉が別の意味を持つので、後の節で整理します。

もう 1 つの決まりは、**その日の結果を置き換える**ことです。追記すると、再実行のたびにデータが重なります。第4章で、再試行の前提は冪等（何度繰り返しても結果が変わらない）ことだと学びました。日次ジョブも同じで、冪等であれば、失敗したら安心して流し直せます。次が、その日の売上をカテゴリ別に集計するジョブの本体です。入力は、日付ごとのフォルダ（`work/source/date=2026-03-05/sales.csv`）で、送る側が書き終えると最後に `_SUCCESS` という空のファイルを置きます。

ジョブの本体は、「計算する段」と「安全に書く段」に分けてあります。まず計算の段です。

```python
def summarize(day: str, source_root: Path) -> list[tuple]:
    """第 1 段（計算）: その日の売上をカテゴリ別に集計し、(日付, カテゴリ, 注文数, 売上) の行のリストを返す。

    ここではファイルを書かない。失敗しても、出力側には何も起きない。
    """
    day = check_day(day)
    if not source_ready(day, source_root):
        raise FileNotFoundError(f"{day} の元データがまだ届いていません（_SUCCESS がありません）")
    # read_csv は DuckDB の関数で、CSV を表として読みます（PostgreSQL にはありません）。
    # 注文のない日は見出しだけの CSV なので、型を指定して数値の列を数値として読みます。
    # SQL の ? は「値の差し込み口」で、後ろのリストの値が順に入る（文字列を直接つなぐより安全です）。
    return duckdb.connect().execute(
        """
        SELECT CAST(? AS DATE) AS date, category, count(DISTINCT order_id) AS orders,
               sum(quantity * unit_price) AS revenue
        FROM read_csv(?, types = {'quantity': 'INTEGER', 'unit_price': 'INTEGER'})
        WHERE lower(COALESCE(status, '')) <> 'cancelled'
        GROUP BY category
        ORDER BY category
        """, [day, str(source_root / f"date={day}" / "sales.csv")]).fetchall()
```

順に読みます。

1. `check_day` で日付の形を確かめます。`2026-03-05` の形だけを受け付け、`2026-3-5` や空文字は `ValueError` にします（壊れた日付で、おかしな名前のファイルができるのを防ぎます）。
2. `source_ready` で入力が揃っているかを確かめます。`_SUCCESS` が無い日は、書きかけかもしれないので、読まずに `FileNotFoundError` にします。
3. DuckDB で、その日の CSV をカテゴリごとに集計します。SQL の中の `?` は「値の差し込み口」で、`execute` に渡したリストの値が、先頭から順に入ります。日付やパスを文字列でつなぐより安全で、読みやすくなります。
4. 結果を、タプル（値の組）のリストとして返します。ここでは、まだ何も書いていません。計算の途中で失敗しても、出力には影響しません。

次が、書く段です。ここでファイルを「書きかけで公開しない」工夫をしています。

```python
def write_replace(day: str, out_dir: Path, rows: list[tuple]) -> None:
    """第 2 段（安全に書く）: その日のファイルを丸ごと置き換える。

    追記はしません。書き出しは一時ファイルに行い、最後に os.replace で入れ替えるので、
    途中で失敗しても前回のファイルは壊れず、書きかけが公開されることもありません。
    """
    target = out_dir / "daily_sales" / f"date={day}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp は、同じフォルダに一時ファイルを作り、(開いたファイルの番号, パス) を返す
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{day}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:  # 番号を普通のファイルオブジェクトにする
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
            writer.writerows(rows)
        os.chmod(tmp, 0o644)  # mkstemp は本人しか読めない 0600 で作るので、読む側のために 0644 にする
        os.replace(tmp, target)  # 名前の付け替え。これで初めて、読む側から新しいファイルが見える
    except BaseException:
        # Exception だけでなく、Ctrl+C（KeyboardInterrupt）のような中断でも、一時ファイルを消してから投げ直す
        Path(tmp).unlink(missing_ok=True)
        raise
```

順に読みます。

1. 出力先は `date=2026-03-05.csv` で、日付ごとに 1 ファイルです。第11章のパーティションと同じ形で、その日だけを置き換えられます。
2. `tempfile.mkstemp` は、同じフォルダに一時ファイルを作り、`(fd, tmp)` の 2 つを返します。`fd` は「開いたファイルの番号」（ファイルディスクリプタ）、`tmp` は一時ファイルのパスです。
3. `os.fdopen(fd, "w", ...)` は、その番号を、いつもの `open` と同じファイルオブジェクトに変えます。`with` を抜けると閉じられます。
4. `os.chmod(tmp, 0o644)` で権限を直します。`mkstemp` が作るファイルは本人しか読めない設定（0600）なので、そのままでは、別のユーザーで動く読む側が読めません。
5. `os.replace(tmp, target)` が、一時ファイルを本来の名前に付け替えます。同じフォルダの中の名前の付け替えは、読む側から「古いファイルか、新しいファイルのどちらか」としか見えない形で行われます（Python の文書では、成功すれば置き換え先が入れ替わると説明されています。不可分になるかは OS とファイルシステムによります）。
6. `except BaseException` は、途中で何が起きても（`Exception` だけでなく、Ctrl+C の `KeyboardInterrupt` のような中断も）一時ファイルを消し、`raise` で同じ例外をもう一度投げます。消すだけで黙ってしまうと、失敗に誰も気づけません。ただし、プロセスが強制終了（SIGKILL）されると、この後片付けは動かず、`.tmp` が残ることがあります。読む側は `date=*.csv` のような名前で絞って読みます。

この 2 つを呼ぶのが `process` です。

```python
def process(day: str, source_root: Path, out_dir: Path) -> int:
    """day の売上を集計し、その日のファイルを置き換える。書いた行数を返す（冪等）。"""
    day = check_day(day)
    rows = summarize(day, source_root)
    write_replace(day, out_dir, rows)
    return len(rows)
```

コードの中の `read_csv` は DuckDB の関数で、CSV を表として読みます（PostgreSQL にはありません）。注文のない日は見出しだけの CSV なので、型を指定して数値の列を数値として読んでいます。`lower(COALESCE(status, ''))` の `COALESCE` は、`status` が空（NULL）の行を、キャンセル扱いで落とさないためです（`NULL <> 'cancelled'` は NULL になり、`WHERE` で落ちてしまいます。第5章）。

入力の CSV を作って、動かします。

```bash
python examples/b12/make_source.py
```

```text
7469 行を work/source/ に書きました
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

同じ日をもう一度流しても、ファイルの中身は変わりません。テストは、同じ日を 3 回流してもバイト列が同じこと、遅れて届いた明細（元データに足した 1 行）の後の再実行で行が増えず売上だけが 2,000 円増えること、ほかの日のファイルが変わらないことを確かめています。

**悪い例も見ておきます。** 結果を 1 つのファイルに追記するジョブ（`naive_job.py`）を、同じ日に 2 回流します。

```bash
python examples/b12/naive_job.py 2026-03-05
python examples/b12/naive_job.py 2026-03-05
```

```text
売上の合計: 257,150
売上の合計: 514,300
```

2 回目で売上が倍になりました。再試行や再実行のたびに、数字が静かにずれていきます。これが、冪等でない処理の怖さです。

**データベースに入れるとき。** 結果を PostgreSQL に入れるなら、同じ日の行を 1 つのトランザクションの中で `DELETE` してから `INSERT` します。途中で失敗すれば、両方が取り消され、前回の行が残ります（`MERGE` や主キーでの upsert も同じ目的に使えます。第9章）。

```python
def replace_day(con: psycopg.Connection, day: str, csv_path: Path) -> int:
    """その日の行を消して入れ直します。DELETE と INSERT は 1 つのトランザクションなので、
    途中で失敗すれば両方が取り消され、前回の行がそのまま残ります。入れた行数を返します。"""
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = [(r["date"], r["category"], int(r["orders"]), int(r["revenue"])) for r in csv.DictReader(f)]
    with con.transaction():
        con.execute("DELETE FROM b12.daily_sales WHERE date = %s", [day])
        with con.cursor() as cur:
            cur.executemany("INSERT INTO b12.daily_sales (date, category, orders, revenue) VALUES (%s, %s, %s, %s)",
                            rows)
    return len(rows)
```

`python examples/b12/pg_replace.py 2026-03-05` を 2 回流しても、`b12.daily_sales` の行は 5 行のままです（PostgreSQL を起動して `PG_DSN` を設定した状態で。テストで確かめています。同じ主キーの行が 2 つ入った CSV でわざと失敗させると、前回の行が残ります）。

**日付の区切りとタイムゾーン。** この例の元データの日付は、日本時間の日付です。UTC で保存する決まり（第3章）と食い違うように見えますが、ここでの日付は「事業上の日」を表すパーティションのキーで、時刻そのものではありません。実際のデータが UTC の時刻で入っているなら、日本の 1 日は UTC の前日 15 時から始まるので、日付に直す前に区切りの時刻を決めます。

## バックフィル

**バックフィル**は、過去の区間を作り直すことです。ロジックの間違いを直したとき、元データが後から訂正されたとき、新しい集計を過去にさかのぼって作るときに使います。冪等な日次ジョブなら、バックフィルは「日付を変えて、同じジョブを繰り返す」だけです。

```python
def backfill(start: str, end: str, source_root: Path, out_dir: Path) -> dict[str, int]:
    """start から end までの各日を process で作り直します。{日付: 行数} を返します。"""
    return {day: process(day, source_root, out_dir) for day in days_between(start, end)}
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
- **負荷。** 1 年分を一度に流すと、元のシステムや DWH に大きな負荷をかけます。同時に動かす日数に上限を付けます。
- **途中で止まったときの再開。** 冪等なので、止まった日から最後までを、もう一度流せば足ります。
- **集計の依存。** 日次の結果を使う月次の集計があるなら、日次をすべて直してから月次を流します。DAG の依存で順序を守ります。

Airflow では、過去の期間の作り直しに 2 つの方法があります。1 つは**バックフィル**の機能で、3 系では `airflow backfill create --dag-id ... --from-date ... --to-date ...` のコマンド（や画面）を使います（2 系の `airflow dags backfill` は 3 系で廃止されました）。`--max-active-runs` で同時に動かす数を、`--reprocess-behavior` で、まだ無い実行だけ作るか、失敗したものも、完了したものも作り直すかを選びます。もう 1 つは、既に動いた DAG Run やタスクを画面やコマンドで**クリア**して、もう一度動かす方法です。少数の日を直すだけなら、クリアのほうが手軽です。どちらも、タスクが冪等だからこそ、安心して使えます。

## リトライ・タイムアウト・SLA

3 つの言葉は、似ていますが別の役割です。

- **リトライ**は、失敗した処理を、時間を置いて自動でやり直すことです。一時的な失敗（ネットワークの切断、混雑）に効きます。何を再試行してよいか、待ち時間をどう延ばすかは第4章で学びました。冪等でない処理を再試行すると、データが重なります。
- **タイムアウト**は、処理の上限時間です。無限に待ち続けて、後ろのジョブをすべて止める事態を防ぎます。上限は、通常の実行時間より少し長めに決めます。
- **SLA**（サービス水準）は、「毎朝 9 時までにデータが揃っている」のような、利用者への約束です。タスクが失敗したかどうかではなく、約束の時刻に間に合ったかどうかを見ます。遅れたら通知します。Airflow 2 では、タスクごとに `sla`（`timedelta`）を指定し、DAG の `sla_miss_callback` で通知する機能がありましたが、3 系では削除されました。代わりに、3 系の新しい機能である Deadline Alerts（期限を過ぎたら通知する仕組み）を使います。まだ新しい機能なので、使う版の文書で書き方と制限を確かめてください。

3 つは組み合わせて使います。たとえば、「30 分でタイムアウトし、5 分おいて 2 回まで再試行し、それでも 9 時に間に合わなければ通知する」という具合です。再試行の回数を増やしすぎると、復旧の遅れが目立たなくなります。失敗した回数は、再試行で直ったものも含めてログに残し、増えていないかを見ます。

## センサーとイベント起動: データの到着を待つ

時刻で動かすジョブは、元データがその時刻に揃っている、という前提で動きます。元データの出力が遅れた日に、空のデータから結果を作って「成功」にすると、気づかれない欠損になります。これを防ぐのが**センサー**です。センサーは、条件が整うまで待つタスクです。

「その日のデータが 1 行でもあれば届いたとみなす」のは危険です。ファイルが書きかけで、半分しか入っていない状態でも、1 行はあるからです。送る側が、書き終えたあとに**完了の印**（この章では空の `_SUCCESS` ファイル）を置き、受ける側はその印を待ちます。

```python
def source_ready(day: str, source_root: Path) -> bool:
    """その日のフォルダに、完了の印（_SUCCESS）があれば True。

    ファイルがあるだけでは、書きかけかもしれません。送る側が書き終えたあとに置く印を見て、
    半分しか入っていないデータを読まないようにします。
    """
    return (source_root / f"date={check_day(day)}" / "_SUCCESS").exists()
```

待ち方には 2 種類あります。ずっとワーカー（タスクを実行する枠）を占めたまま、一定間隔で調べ続ける poke と、調べるたびにいったん枠を空け、次の時刻にもう一度取り直す reschedule です。待ちが長くなるなら reschedule です。待つ時間には上限（タイムアウト）を付けます。上限を越えたらタスクは失敗し、通知が飛びます。「待ちっぱなしで誰も気づかない」を防ぐためです。さらに、多くのセンサーには、待つ処理を専用の軽いプロセス（トリガー）に任せる deferrable（遅延可能）という方式があり、待っている間にワーカーを一切使いません。待ちが長い、待つ対象が多い、という場面で検討します。

もう 1 つの方法は、時刻ではなくイベントで動かすことです。上流のジョブが終わったら、下流を起動します。Airflow 3 では、データの更新を起点に DAG を動かす仕組みを `Asset`（2 系では `Dataset`）と呼びます。Dagster のアセットに近い考え方です。時刻だけで動かすより、依存が分かりやすくなります。ただし、イベントの取りこぼしに備えて、時刻での実行も併用することが多くあります。

## Airflow の基本

Airflow は、Apache のオーケストレーターで、DAG を Python のファイルで書きます。主な用語を、次の表にまとめます。

{{ table("b12-airflow-terms") }}

表の **Operator** は、タスクの型です。「ファイルを待つ」「SQL を流す」「Python の関数を動かす」といった、やることごとに用意された部品で、DAG の中のタスクは、どれかの Operator のインスタンスです。この章で使う TaskFlow API は、普通の Python の関数に `@task` を付けると、関数を動かす Operator が自動で作られる書き方です。

この章の DAG ファイル（`examples/b12/neboske_daily_sales.py`）を、上から読みます。まず、準備です。

```python
"""ねぼすけ商店の日次売上を作る DAG（第 12 章）。処理の本体は daily_job.py にあります。"""
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from airflow.sdk import dag, task
from airflow.timetables.interval import CronDataIntervalTimetable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily_job  # noqa: E402

WORK = Path(os.environ.get("NEBOSKE_WORK", "/tmp/neboske"))
SOURCE = WORK / "source"
OUT = WORK / "out"
TZ = "Asia/Tokyo"  # 日付の区切りに使うタイムゾーン（元データの日付は日本時間）
```

`from airflow.sdk import dag, task` は 3 系の書き方です（2 系では `airflow.decorators` からでした）。日付の区切りに使うタイムゾーン `TZ` を、1 か所にまとめます。次に、補助の関数です。

```python
def day_of(data_interval_start: datetime) -> str:
    """処理する日（区間の始まりの日付）を '2026-03-05' の形にする。

    data_interval_start は UTC で渡ってくるので、スケジュールと同じタイムゾーンに直してから日付にする。
    """
    return data_interval_start.astimezone(ZoneInfo(TZ)).strftime("%Y-%m-%d")


def notify_failure(context) -> None:
    """失敗を通知する場所。ここではログに書くだけです（実際はチャットやメールに送ります）。"""
    ti = context["task_instance"]
    logging.getLogger(__name__).error("失敗: %s / %s", ti.dag_id, ti.task_id)
```

`day_of` は、実行の「データの区間」の始まりから、処理する日を作ります。ここが 3 系を使うときのいちばんの注意点なので、少し丁寧に説明します。

**データの区間と、論理日付。** Airflow 3 では、日次の DAG の「いつ」を決める方法（スケジュールのタイムテーブル）が 2 つあります。`"0 0 * * *"` のような cron 式を文字列で渡すと、3 系の既定では `CronTriggerTimetable` になります。これは「その時刻に起動する」だけで、`logical_date`（実行を区別する日時）は起動時刻、データの区間の幅は 0 です。「昨日の分を処理する」という意図は、タスク側で自分で計算することになります。この章は、もう一方の `CronDataIntervalTimetable("0 0 * * *", timezone=TZ)` を使います。毎日 0 時（日本時間）を境にした区間を持ち、区間が終わったあとに実行が作られます。3 月 4 日の実行は、`data_interval_start` が 3 月 4 日 0 時、`data_interval_end` が 3 月 5 日 0 時（どちらも日本時間）で、3 月 5 日の 0 時過ぎに動きます。タスクは、`data_interval_start` を受け取って、処理する日を決めます。受け取る値は UTC なので、`TZ` に直してから日付にします。

次の表で、実行の時刻・区間・処理する日を並べます（表は `examples/b12/interval_table.py` が計算して書き出したものです。区間は日本時間で表しています）。

{{ table("b12-interval-timeline") }}

手動で実行したとき（画面や `airflow dags test`）は、区間は「実行を指定した日時の直前の、終わった区間」になります。この章の DAG を `airflow dags test neboske_daily_sales 2026-03-05` で動かしたところ、処理されたのは 3 月 5 日ではなく **3 月 4 日**の分でした（Airflow 3.4.0 で確かめました）。
**なぜ 3 月 5 日を指定して 3 月 4 日が動いたのか。** 引数の `2026-03-05` は、論理日付（UTC の 3 月 5 日 0 時）です。これは日本時間の 3 月 5 日 9 時にあたります。日本時間で「その時刻より前に終わった最後の区間」は、3 月 4 日 0 時から 3 月 5 日 0 時までの区間で、`data_interval_start` は 3 月 4 日 0 時です。だから、処理される日は 3 月 4 日になります。「手動で指定した日の分が動く」と思い込むと、1 日ずれます。手動で動かしたあとは、どの日が処理されたかをログで確かめます。

次が、タスクです。

```python
@task.sensor(poke_interval=300, timeout=6 * 60 * 60, mode="reschedule")
def wait_for_source(data_interval_start=None) -> bool:
    """その日の元データの完了の印（_SUCCESS）が届くまで待つ。待っている間はワーカーを空けておく（reschedule）。"""
    return daily_job.source_ready(day_of(data_interval_start), SOURCE)


@task
def build(data_interval_start=None) -> dict:
    """その日の分だけを作り直す。同じ日を再実行しても、結果は変わらない。"""
    day = day_of(data_interval_start)
    return {"day": day, "rows": daily_job.process(day, SOURCE, OUT)}


@task
def report(result: dict) -> None:
    """前のタスクの結果は、小さな dict（日付と行数）だけを XCom で受け取る。"""
    logging.getLogger(__name__).info("%s: %d 行を書きました", result["day"], result["rows"])
```

これは **TaskFlow API** です。普通の Python の関数に `@task` を付けると、それが 1 つのタスクになります。`@task.sensor` は、関数が True を返すまで待つセンサーです。

関数の引数 `data_interval_start=None` に、Airflow が実行のたびに値を入れてくれます。**引数の名前で決まります**。Airflow は、タスクの関数の引数の名前を見て、その名前の実行情報（`data_interval_start`、`data_interval_end`、`logical_date` など）があれば、渡します。名前を書き間違えると、値は入らず、既定値の `None` のままです（すると `day_of` が失敗します）。`=None` は、手元で関数を直接呼ぶ人のための既定値の形です。DAG の中身は、ジョブ本体（`daily_job`）を呼ぶだけです。本体は Airflow を知らないので、Airflow なしで pytest にかけられます。処理を DAG ファイルに直接書き込むと、テストのたびに Airflow が要ります。

`build` は小さな dict（日付と行数）を return し、`report` が受け取ります。DAG の定義の中の `report(result)` という 1 行には、2 つの働きがあります。1 つは依存で、`report` は `build` が終わってから動きます。もう 1 つは受け渡しで、`build` の戻り値が `result` に入り、`report` の引数 `result` に渡ります。この受け渡しが **XCom** です。XCom は、既定では Airflow のデータベースに値を保存します。Airflow の文書は、小さなデータ向けで、データフレームのような大きな値を渡さないよう書いています。大きなデータは、ファイルやテーブルに書いて、その場所（パスやテーブル名）だけを渡します。この例では、結果のファイルはすでに `OUT` の下にあり、XCom には件数だけを渡しています。次が DAG の定義です。

```python
@dag(
    dag_id="neboske_daily_sales",
    schedule=CronDataIntervalTimetable("0 0 * * *", timezone=TZ),
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

- **`schedule`**: 上で説明した、区間のあるタイムテーブルです。
- **`start_date`**: スケジュールの始まりです。
- **`catchup=False`**: 有効にしたときに、`start_date` から今までの取りこぼしの区間を、まとめて作らない設定です。2 系の既定は True でしたが、3 系の既定は False です。True にすると、過去の何百日分もの実行が一度に動き出すことがあります。過去分は、意図して、バックフィルとして流します。
- **`max_active_runs=1`**: 同じ DAG の実行を、同時に 1 つまでにします。cron の `flock`（第3章）と同じ、重なり実行の防止です。
- **`retries` と `execution_timeout`**: 前の節の再試行とタイムアウトです。`on_failure_callback` は、失敗したときに呼ばれる関数で、ここに通知を書きます。
- **`ready >> result`**: `wait_for_source` が成功してから、`build` を動かす、という依存です。`report(result)` は `build` の結果を受け取るので、`build` のあとに動きます。

実行条件を細かく決める設定も、短く挙げておきます。`trigger_rule` は、上流の状態に応じてタスクを動かすかの規則で、既定は「上流がすべて成功」です（`all_done` にすると、失敗しても動き、後片付けのタスクに使います）。`depends_on_past` は、前の日の同じタスクが成功していないと動かさない設定です（日が前の結果に依存するときに使います。1 日の失敗が連鎖して止まるので注意します）。`pool` は、同時に動かすタスクの数に上限を付ける枠で、外部のシステムへの同時接続数を絞りたいときに使います。

接続情報やパスワードは、DAG ファイルに書きません。Airflow には、接続情報を保存する **Connection** と、設定値を保存する **Variable** があり、秘密は専用の保管サービス（シークレットバックエンド）にも置けます。本番の Airflow は、自分でサーバを立てて運用する方法のほか、マネージドサービス（AWS の MWAA、Google Cloud の Cloud Composer など）を使う方法があります。運用の手間を減らせる代わりに、使える Airflow の版や設定に制限があります。

ここで、Airflow の部品の名前を整理します。**スケジューラ**は、「いつ、どの実行を作るか」を決めて、動かす指示を出す常駐のプログラムです。**ワーカー**は、タスクの関数を実際に動かすプログラムです。**メタデータのデータベース**は、DAG の実行状況やタスクの状態、XCom の値を保存する場所で、手元では SQLite、本番では PostgreSQL などを使います。`airflow dags test` は、スケジューラとワーカーを起動せずに、DAG の 1 回分を手元の 1 プロセスで動かすコマンドです。

手元で動かすときの手順は、次のとおりです。Airflow は、Windows の上では直接動きません。Windows の読者は、WSL（Ubuntu）を開き、WSL の中の Linux のフォルダ（`~/` の下など。`/mnt/c/` の下は避けます）にこのリポジトリを置いて、実行してください（Linux・WSL・macOS 向けです）。

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install "apache-airflow==3.4.0" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.4.0/constraints-3.12.txt"

export AIRFLOW_HOME="$PWD/work/airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/examples/b12"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export NEBOSKE_WORK="$PWD/work"

python examples/b12/make_source.py
airflow db migrate
airflow dags test neboske_daily_sales 2026-03-05
```

`python3 -m venv .venv` は、このフォルダの中だけに Python のパッケージを入れる仮想環境を作る命令で、`source .venv/bin/activate` で有効にします（ほかのプロジェクトのパッケージと混ざりません）。`--constraint` は、Airflow が動作確認した依存ライブラリの版の一覧を指定して、その版で入れる、という指定で、公式が勧めています（Airflow は依存が多く、版が合わないと動かないためです）。`export` で決めている環境変数のうち、`AIRFLOW_HOME` は Airflow が設定ファイルやデータベースを置くフォルダ、`AIRFLOW__CORE__DAGS_FOLDER` は DAG ファイルを探すフォルダ、`AIRFLOW__CORE__LOAD_EXAMPLES` は付属のサンプル DAG を読み込むかどうかです。`AIRFLOW__<節>__<キー>` の形（アンダースコアが 2 つ）で、設定ファイルの項目を環境変数で上書きできます。`NEBOSKE_WORK` は、この章の DAG が作業フォルダを知るための、この本だけの変数です。`airflow db migrate` は、メタデータのデータベースを作る手順です。Docker の Python 3.12 イメージで実際に動かしたところ、ログの主な行は次のとおりでした（時刻などは省いています）。

```text
[DAG TEST] starting task_id=wait_for_source
[DAG TEST] end task task_id=wait_for_source
[DAG TEST] starting task_id=build
[DAG TEST] end task task_id=build
[DAG TEST] starting task_id=report
2026-03-04: 5 行を書きました
[DAG TEST] end task task_id=report
```

`work/out/daily_sales/date=2026-03-04.csv` ができ、`wait_for_source` → `build` → `report` の順に動いたことが分かります。バックフィルのコマンド（前の節）も同じスクリプトの末尾に書いてありますが、スケジューラが要るので、この本では実行していません。

CI では、DAG ファイルを Airflow に読み込ませて、構造を確かめています（`.github/workflows/pages.yml`）。DAG が 1 つ以上読み込まれていること（読み込み対象から外されていないこと）、タスクが 3 つで `build` の上流が `wait_for_source` であること、`catchup` が False で `retries` が 2 であることです。手元の pytest は、Airflow の部分だけを素通しにして、タスクの中身とファイルの文法・設定を確かめます。

!!! warning "Airflow 2 系との違い"
    ネットや古い本の記事は、2 系で書かれていることが多くあります。主な違いは次のとおりです。
    `import` は `airflow.decorators` から `airflow.sdk` へ。`schedule="@daily"` は、3 系の既定では区間を持たず、起動時刻が論理日付になります。`catchup` の既定は True から False へ。`execution_date` など、古い名前の多くは廃止されました。`airflow dags backfill` は、`airflow backfill create` へ。SLA は削除され、Deadline Alerts へ。`Dataset` は `Asset` へ。記事を読むときは、どの版の話かを最初に確かめます。

## Dagster・Prefect との考え方の違い

Airflow は、「タスクを、いつ、どの順で動かすか」を中心に考えます。Dagster は、「作りたいデータ（アセット）」を中心に考えます。アセットは、テーブルやファイルなど、処理の結果として存在するデータです。「このアセットは、あのアセットから作る」と関数で宣言すると、依存と順序が決まります。画面にはタスクではなく、データの一覧が並び、どのデータがいつ最新になったかが見えます。第10章の dbt のモデルが、「このモデルはあのモデルを参照する」と書くことで依存が決まるのと、似た発想です。

Prefect は、Python の関数に `flow` や `task` を付けて、普通のコードのまま実行の状態を記録し、再試行などを付けられる道具です。DAG を先に宣言せず、関数を呼ぶ順で処理が決まります。条件分岐や繰り返しを、ふつうの Python で書きたいときに向きます。

{{ table("b12-orchestrators") }}

どれを選ぶかは、現場の既存の資産と、チームの慣れで決まります。Airflow は、連携部品（プロバイダー）が豊富で、運用の情報も多くあります。アセット指向は、データの「いつの状態か」を中心に扱いたいときに向きます。考え方が分かっていれば、道具が変わっても、この章の冪等性・バックフィル・センサーはそのまま使えます。製品の機能は更新が早いので、選ぶときは公式の文書で、使う版を確かめてください。

## 監視とアラート

オーケストレーターを入れても、見ていなければ意味がありません。何を監視するかは、4 つに分けられます。

- **失敗**: タスクが失敗したか。再試行しても直らなかったか。
- **遅れ**: 約束の時刻に間に合ったか（SLA、3 系では Deadline Alerts）。あるいは、いつもの実行時間より極端に長くないか。
- **中身**: 成功しているが、出力が空、または件数が急に減っていないか。オーケストレーターは「プログラムが正常に終わったか」しか知りません。中身の確認は、データ品質のチェックで行います（第13章）。
- **ログ**: 失敗の原因を、あとから追えるか。ログには、処理した日付と件数を残します（第4章）。

通知は、人が反応できる形に絞ります。失敗のたびに毎回通知すると、そのうち誰も見なくなります（アラート疲れ）。再試行で直ったものは通知せず、再試行をすべて使い切ったときと、約束の時刻に間に合わなかったときに通知します。通知の文面には、DAG の名前・処理する日・失敗したタスクと、再実行の手順へのリンクを入れます。この章の `notify_failure` は、その入口の例です。夜中に起こされた人が、何をすればよいか分かる通知が、よい通知です。

## よくある失敗

- 処理する日を `datetime.now()` で決めて、再実行や過去分のやり直しで、別の日の結果ができる。
- 結果を追記して、再実行のたびにデータが重なる。
- 書きかけのファイルを、読む側が見てしまう。一時ファイルに書いて、最後に入れ替える。
- 元データの到着を、「1 行でもあれば OK」で判断して、半分しか入っていないデータを読む。
- `catchup=True` のまま有効にして、過去の実行が一斉に動く。
- 手動実行で指定した日と、実際に処理される日がずれていることに気づかない。
- 元データの到着を待たず、空のデータから「成功」の結果を作る。
- XCom にデータフレームや大きな JSON を渡して、Airflow のデータベースを膨らませる。
- 再試行の回数だけ増やして、本当の障害が隠れる。
- 失敗の通知が多すぎて、誰も見なくなる。
- DAG ファイルに処理を全部書き込み、Airflow なしでテストできなくなる。
- 2 系の記事の書き方を、そのまま 3 系に貼る。

## まとめ

- cron は時刻しか知りません。依存・失敗の検知・再試行・過去分の作り直し・待機・履歴が要るようになったら、オーケストレーターの出番です。
- DAG は、タスクの依存を、輪の無い矢印で表します。上流が失敗すれば、下流は動かず、関係のない枝は動き続けます。
- 日付を引数に取り、その日の結果を置き換えると、ジョブは冪等になります。データベースでは、1 つのトランザクションで削除して入れ直します。
- リトライは一時的な失敗、タイムアウトは待ちすぎ、SLA は利用者への約束に対応します。
- センサーで、データの到着を、完了の印で待ちます。待ちには上限を付けます。
- Airflow 3 では、処理する日を、データの区間（`data_interval_start`）から決めます。手動実行では、指定した日の直前の区間が動く点に注意します。DAG ファイルは薄くし、XCom には小さな値だけを渡します。
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

問 3. `mini_runner.run` の `deps` に、`tasks` にない名前（たとえば `{"a": {"typo"}}`）を書くとどうなりますか。なぜ、動かす前に分かるほうがよいのですか。

??? note "解答例"
    `ValueError` になり、どのタスクも動きません（`test_runner_rejects_unknown_names` が確かめています）。名前の書き間違いのまま動かすと、依存が効かず、本来は待つはずのタスクが先に動いてしまいます。実行の途中で分かる失敗より、動かす前に分かる失敗のほうが、被害が小さくて済みます。なお、輪になった依存は `graphlib.CycleError` になります。

問 4. `quality_check` が失敗した日でも、`publish` を動かしたいという要望がありました。依存はどう変えられますか。そうすべきでしょうか。

??? note "解答例"
    `publish` の依存から `quality_check` を外せば（`deps["publish"] = {"aggregate"}`）、品質チェックの結果に関係なく動きます。Airflow では、上流が失敗しても動かす設定（`trigger_rule`）がありますが、ここは勧めません。品質チェックの目的は、壊れたデータを公開しないことで、それを外すと目的が失われます。公開を止めて通知し、直してから再実行するのが基本です。どうしても見せる必要があるなら、「品質未確認」と分かる形で別の場所に出す、といった設計にします。

問 5. `naive_job.py`（追記するジョブ）を同じ日に 2 回流すと、売上の合計が 2 倍になりました。`daily_job.py` はなぜ 2 倍にならないのですか。再試行が付いたジョブに、追記が危険なのはなぜですか。

??? note "解答例"
    `daily_job.py` は、その日のファイルを丸ごと置き換えます（`os.replace`）。何回流しても、最後に書いた 1 つの結果が残るだけです。追記のジョブは、流した回数だけ行が増えます（257,150 が 514,300 になる）。再試行は、失敗したように見えても、実は途中まで書けていた処理を、もう一度流すことがあります。そのとき追記だと、同じ日の行が重なります。再試行を付ける前に、冪等にしておくことが先です。

## 参考文献

- Joe Reis, Matt Housley, *Fundamentals of Data Engineering*, O'Reilly, 2022. 第2章 “Orchestration”（スケジューラとオーケストレーションの違い、DAG、バックフィル、アラート）。
- Apache Airflow 3.4.0 Documentation, “Dags”, <https://airflow.apache.org/docs/apache-airflow/3.4.0/core-concepts/dags.html> ／ “Dag Runs”（データの区間・論理日付）, <https://airflow.apache.org/docs/apache-airflow/3.4.0/core-concepts/dag-run.html> ／ “Timetables”, <https://airflow.apache.org/docs/apache-airflow/3.4.0/authoring-and-scheduling/timetable.html> ／ “Backfill”, <https://airflow.apache.org/docs/apache-airflow/3.4.0/core-concepts/backfill.html>
- Apache Airflow 3.4.0 Documentation, “Working with TaskFlow”, <https://airflow.apache.org/docs/apache-airflow/3.4.0/tutorial/taskflow.html> ／ “XComs”, <https://airflow.apache.org/docs/apache-airflow/3.4.0/core-concepts/xcoms.html> ／ “Sensors”, <https://airflow.apache.org/docs/apache-airflow/3.4.0/core-concepts/sensors.html> ／ “Deferring”, <https://airflow.apache.org/docs/apache-airflow/3.4.0/authoring-and-scheduling/deferring.html> ／ “Asset-Aware Scheduling”, <https://airflow.apache.org/docs/apache-airflow/3.4.0/authoring-and-scheduling/assets.html> ／ “Tasks”, <https://airflow.apache.org/docs/apache-airflow/3.4.0/core-concepts/tasks.html> ／ “Best Practices”, <https://airflow.apache.org/docs/apache-airflow/3.4.0/best-practices.html> ／ “Upgrading to Airflow 3”, <https://airflow.apache.org/docs/apache-airflow/3.4.0/installation/upgrading_to_airflow3.html> ／ “Managing Connections”, <https://airflow.apache.org/docs/apache-airflow/3.4.0/howto/connection.html>
- Dagster Documentation, “Concepts”（アセット）, <https://docs.dagster.io/getting-started/concepts>
- Prefect Documentation, “Flows”, <https://docs.prefect.io/v3/concepts/flows>
- Python Documentation, “graphlib — Functionality to operate with graph-like structures”, <https://docs.python.org/3/library/graphlib.html> ／ “os.replace”, <https://docs.python.org/3/library/os.html>
- PostgreSQL Documentation, “MERGE”, <https://www.postgresql.org/docs/current/sql-merge.html>

!!! tip "さらに深く"
    失敗や遅れの検知を、SLO（サービス水準の目標）とリネージ（データの来歴）まで広げる話は、応用編 第8章「観測性・SLO・リネージ」で扱います。

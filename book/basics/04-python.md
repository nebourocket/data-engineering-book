# 第4章 データエンジニアのための Python

## この章でできるようになること

- 仮想環境を作り、依存パッケージの版を固定して、他の人の機械でも同じ結果を再現できる。
- 型ヒント・dataclass・独自の例外で、壊れたデータを境界で止める。
- 再試行・ログ・設定・秘密の扱いを、現場で任せられる水準で書ける。
- ジェネレータと `pathlib` で、大きなファイルを少しずつ安全に扱える。
- pytest でテストを書き、ねぼすけ商店の注文 CSV を検証して Parquet に変える ETL スクリプトを、段階的に作れる。

この章のコードは `examples/b04/` にあり、`pytest` で動かしています。出力例は実際に実行した結果です（2026年11月時点、Python 3.12）。

## 「動く」スクリプトと「任せられる」スクリプト

データエンジニアが書く Python の多くは、数十行から数百行の地味なスクリプトです。ファイルを読み、直し、どこかに書く。難しいアルゴリズムはほとんど出てきません。それでも、書いた本人が不在のときに夜間に動き、失敗したら誰かが原因を探します。「動く」と「任せられる」の差は、この場面で現れます。

まず、誰もが最初に書く版を見ます。注文 CSV から、金額の合計と、発送済みの件数を数えます。

```python
import csv

total = 0
shipped = 0
for row in csv.DictReader(open("orders.csv")):
    print(row["order_id"])
    order_id = int(row["order_id"])
    total += int(row["total_amount"])
    if row["status"] == "shipped":
        shipped += 1
print(total, shipped)
```

サンプルの CSV には、わざと悪い行が 4 つ混ざっています（`make_sample.py` が作ります）。この版を動かすと、こうなります。

```text
40
abc
Traceback (most recent call last):
  File "/w/examples/b04/step1_naive.py", line 7, in <module>
    order_id = int(row["order_id"])
               ^^^^^^^^^^^^^^^^^^^^
ValueError: invalid literal for int() with base 10: 'abc'
```

問題は 4 つあります。

1. **どの行で、なぜ落ちたのかが分からない。**行番号も、注文 ID も出ません。`print` が 40 行出た後で落ちたことから、41 行目だと推測するしかありません。
2. **静かに間違える行がある。**`"SHIPPED"` と大文字で書かれた行は、`== "shipped"` に合わず数えられません。エラーにもなりません。金額がマイナスの行も、合計にそのまま入ります。
3. **ファイルを閉じていない。**`open` の結果を `with` で包んでいません。
4. **再現できない。**どの版の Python で動かしたか、どのパッケージが必要かが、どこにも書かれていません。

この章は、この 4 つを順に直します。

## 仮想環境と依存の固定

Python のパッケージは、`pip` で入れます。何も考えずに入れると、機械全体で共有する場所に入ります。プロジェクト A は pyarrow の新しい版、プロジェクト B は古い版を必要とすると、どちらかが壊れます。

**仮想環境**（venv）は、プロジェクトごとの独立した Python の置き場所です。`python3 -m venv .venv` で `.venv/` というディレクトリが作られ、`source .venv/bin/activate` で、そのディレクトリの Python と pip が優先して使われるようになります（Python 公式の venv の説明）。環境を壊しても、`.venv` を消して作り直せば済みます。`.venv` は再生成できるので、Git には入れません。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "pyarrow==26.0.1" "boto3==1.44.2" "pytest==8.3.4"
python -m pip freeze > requirements.txt
python -m pip install -r requirements.txt
```

`pip freeze` は、今の環境に入っているパッケージと版を `名前==版` の形で書き出します。

```text
boto3==1.44.2
botocore==1.44.2
iniconfig==2.3.1
jmespath==1.1.0
packaging==26.3
pluggy==1.7.0
pyarrow==26.0.1
pytest==8.3.4
python-dateutil==2.9.0.post0
s3transfer==0.19.3
six==1.17.0
urllib3==2.8.0
```

直接入れたのは 3 つだけですが、そのパッケージが必要とするものも含めて全部書き出されます。このファイルがあれば、`pip install -r requirements.txt` で、同じ版の環境を作り直せます。

依存の書き方には 2 通りあり、目的が違います。

- **固定**（`==`）: 動かす側のアプリケーションやバッチ向き。昨日動いたものが今日も動きます。上の `requirements.txt` です。
- **範囲**（`>=26,<27`）: 他のコードから使われるライブラリ向き。利用者が他のパッケージと共存できる余地を残します。`pyproject.toml` に書きます。

```toml
[project]
name = "neboske-etl"
version = "0.1.0"
description = "ねぼすけ商店の注文 CSV を検証して Parquet にする"
requires-python = ">=3.12"
dependencies = [
    "pyarrow>=26,<27",
    "boto3>=1.44,<2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8,<9",
]
```

`requires-python` は、動かせる Python の版です。Python 本体の版もチームで合わせます。Docker を使うなら、イメージの名前（`python:3.12-slim` のように）で固定するのが確実です。固定した版は、放置せずに、定期的に上げます。古い版に残ると、セキュリティの修正を受けられません。`uv` のように、仮想環境の作成と依存の解決を速くする新しいツールもあります。考え方は同じで、どのツールでも「版を固定して書き出す」ことが肝心です。

## 型ヒントと dataclass

CSV から読んだ値は、すべて文字列です。`"3400"` は金額ではなく 4 文字の文字列で、`"2026-01-01 09:00:00"` も日時ではありません。文字列のまま `dict` で持ち回ると、処理のずっと後ろで `"3400" + 1` のようなエラーが出たり、`row["totl_amount"]` のような打ち間違いで落ちたりします。

そこで、データの入口（境界）で 1 回だけ、文字列を正しい型に直します。その型を表すのが **dataclass** です。

```python
@dataclass(frozen=True, slots=True)
class Order:
    order_id: int
    customer_id: int
    ordered_at: datetime
    status: str
    item_count: int
    total_amount: int
```

`: int` のような書き方が**型ヒント**です。Python は実行時にはこれを検査しません（typing の公式ドキュメントにも、実行時には強制されないとあります）。しかし、エディタや `mypy` のような型検査ツールが、型の食い違いを実行前に見つけます。人間にとっても、「この関数は何を受け取って何を返すか」の説明になります。

`frozen=True` は、作った後に値を書き換えられなくします。`slots=True` は、属性の打ち間違いによる代入をエラーにし、メモリも少し節約します。検証済みのデータが、後の処理で勝手に変わらないという保証は、バグの探索範囲を狭めます。

## 例外と検証

行が悪いときの扱いを決めます。大切なのは、失敗を種類で分けることです。

{{ table("b04-error-kinds") }}

「行の失敗」と「ファイル全体の失敗」を分けるのが、データの仕事の特徴です。1 行の日付が読めないからといって、3000 行の処理を全部止めると、現場は動きません。かといって、黙って捨てると、数字が静かにずれます。方針は「隔離して、記録して、割合が上限を超えたら止める」です。

行の失敗を表す例外を作ります。

```python
class ValidationError(ValueError):
    """1 行の検証の失敗。どの項目が、なぜ悪いかを持ちます。"""

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason
```

`ValueError` を継承しているので、`except ValueError` を書いた既存のコードでも受け取れます。どの項目が悪いかを `field` に持たせると、除外した行の理由を後から集計できます。

検証は、文字列の `dict` を `Order` に変える関数にまとめます。

```python
def _to_int(row: dict[str, str], field: str, minimum: int) -> int:
    raw = (row.get(field) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        raise ValidationError(field, f"整数ではありません: {raw!r}") from None
    if value < minimum:
        raise ValidationError(field, f"{minimum} 以上でなければなりません: {value}")
    return value
```

```python
def parse_order(row: dict[str, str]) -> Order:
    """正しければ Order を返し、悪ければ ValidationError を投げます。"""
    status = (row.get("status") or "").strip().lower()  # "SHIPPED" の表記ゆれをそろえる
    if status not in VALID_STATUSES:
        raise ValidationError("status", f"知らない値です: {row.get('status')!r}")
    try:
        ordered_at = datetime.strptime((row.get("ordered_at") or "").strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ValidationError("ordered_at", f"日時として読めません: {row.get('ordered_at')!r}") from None
    return Order(
        order_id=_to_int(row, "order_id", minimum=1),
        customer_id=_to_int(row, "customer_id", minimum=1),
        ordered_at=ordered_at,
        status=status,
        item_count=_to_int(row, "item_count", minimum=1),
        total_amount=_to_int(row, "total_amount", minimum=0),
    )
```

3 点を見てください。

- `raise ... from None` は、`int()` が出した元のエラーを隠します。読む人に必要なのは「どの項目が、どう悪いか」だけだからです。元のエラーを残したいときは、`from exc` と書きます。
- `.lower()` で、`"SHIPPED"` の表記ゆれを直しています。値を捨てるのでなく正規化できるものは、境界で正規化します。
- `except` は、起きると分かっている例外だけに絞ります。`except Exception: pass` は、プログラムの誤りまで握りつぶすので、書きません。

## 再試行

ネットワーク越しの処理は、ときどき失敗します。失敗には、時間を置けば直るものと、直らないものがあります（先ほどの表の最初の 2 行です）。再試行してよいのは、前者だけです。パスワードが違うのに 3 回試すと、アカウントが凍結されるかもしれません。

```python
def retry(attempts: int = 3, wait: float = 1.0, on: tuple[type[Exception], ...] = (OSError,)):
    """on に挙げた例外のときだけ、待ち時間を倍にしながら attempts 回まで試します。"""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            delay = wait
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except on as exc:
                    if attempt == attempts:
                        raise
                    logger.warning("%s が失敗しました (%d/%d 回目): %s。%.1f 秒後に再試行します",
                                   func.__name__, attempt, attempts, exc, delay)
                    time.sleep(delay)
                    delay *= 2
            raise AssertionError("到達しません")

        return wrapper

    return decorator
```

ポイントは次のとおりです。

- 再試行する例外を、`on` で明示して絞る。
- 待ち時間を倍にしていく（指数バックオフ）。相手が混んでいるとき、全員が同じ間隔で押しかけるのを避けるためです。実運用では、待ち時間にランダムなゆらぎ（ジッター）を足すのが定石です（AWS Builders' Library の解説を参考文献に挙げました）。
- 回数の上限を決め、使い切ったら元の例外を投げ直す。呼び出し側が失敗を知れます。
- 再試行のたびに警告をログに残す。これが無いと、遅い原因が分かりません。

再試行の前提は、同じ処理を繰り返しても結果が変わらないこと（冪等）です。途中まで書いたファイルを追記する処理を再試行すると、データが重なります。3 章の「一時ファイルに書いて最後に `mv`」は、この前提を満たすための形でもありました。ライブラリ側にも再試行の仕組みがあることが多く、二重にかけると回数が掛け算になります。この章の `upload` では、boto3 側の再試行を 1 回（試行は 1 度きり）に設定して、`retry` に一本化しています。

## logging

`print` で進み具合を出すのは、手元で試すときだけにします。本番のジョブでは、次の理由で `logging` を使います。

{{ table("b04-log-levels") }}

- **レベルで出し分けられる。**普段は `INFO` 以上だけを出し、障害のときだけ `DEBUG` にして詳しく見られます。コードを書き換える必要がありません。
- **時刻・名前・レベルが付く。**「いつ、どのモジュールが言ったか」が残ります。
- **出力先が分かれる。**`logging` は標準エラー出力に書きます。標準出力は、次のコマンドに渡すデータのために空けておけます（3 章のパイプの考え方です）。
- **設定を 1 か所にまとめられる。**出力先やフォーマットを変えても、呼び出し側のコードは変わりません。

```python
import logging

logger = logging.getLogger("neboske_etl.demo")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logger.debug("INFO より下のレベルなので、表示されません")
    logger.info("読み込み %d 行", 3000)
    logger.warning("除外 %d 行", 4)
    try:
        int("abc")
    except ValueError:
        logger.exception("整数に直せない値がありました")


if __name__ == "__main__":
    main()
```

```text
INFO neboske_etl.demo 読み込み 3000 行
WARNING neboske_etl.demo 除外 4 行
ERROR neboske_etl.demo 整数に直せない値がありました
Traceback (most recent call last):
  File "/w/examples/b04/logging_demo.py", line 12, in main
    int("abc")
ValueError: invalid literal for int() with base 10: 'abc'
```

`debug` は、レベルが `INFO` より低いので出ません。`logger.exception` は、`except` の中で呼ぶと、ERROR のログとスタックトレース（どこで起きたかの経路）を一緒に出します。

使い方の決まりを 3 つ挙げます。

1. **ログの設定（`basicConfig`）は、プログラムの入口で 1 回だけ行う。**各モジュールは `logging.getLogger(__name__)` で受け取るだけにします。ライブラリ側が勝手に設定すると、使う人の設定とぶつかります（logging の公式 HOWTO の方針です）。
2. **`logger.info("件数: %d", n)` のように、引数を別に渡す。**f 文字列で先に文字列にすると、出さないレベルでも組み立てる分だけ無駄になります。
3. **秘密を出さない。**接続文字列やトークンを含む値を丸ごと `logger.info("設定: %s", settings)` に渡さないでください。後述の `Settings` は、そのための工夫をしています。

## ジェネレータで大きなファイルを少しずつ

3000 行の CSV なら、全部をメモリに読んでも困りません。しかし本番では、数千万行になることがあります。`list(csv.DictReader(f))` は、全行を一度にメモリに載せます。

**ジェネレータ**は、値を 1 つずつ作って返す関数です。`yield` を含む関数が、ジェネレータになります。`next()` で呼ばれるまで動かず、呼ばれた分だけ進みます。

```python
def iter_rows(path: Path) -> Iterator[dict[str, str]]:
    """CSV の行を、見出しをキーにした dict として 1 行ずつ返します。"""
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in EXPECTED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name}: 必要な列がありません: {', '.join(missing)}")
        yield from reader
```

`yield from reader` は、`reader` の行を 1 つずつ外に渡します。動きを見ます。

```python
import tempfile
from pathlib import Path

from neboske_etl.reader import iter_rows

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "orders.csv"
    path.write_text(
        "order_id,customer_id,ordered_at,status,item_count,total_amount\n"
        "1,10,2026-01-01 09:00:00,placed,1,1200\n"
        "2,11,2026-01-01 09:05:00,shipped,2,3400\n"
        "3,12,2026-01-01 09:10:00,delivered,1,800\n",
        encoding="utf-8",
    )
    rows = iter_rows(path)
    print(type(rows).__name__)
    print(next(rows)["order_id"])
    print(next(rows)["order_id"])
    print([row["order_id"] for row in rows])
```

```text
generator
1
2
['3']
```

型は `generator` で、`next` を 2 回呼んだ分だけ読み、残りを `list` の内包表記が使い切っています。ファイルは、最後の行を返すまで `with` の中で開いたままです。途中で呼び出し側が止まっても、ジェネレータが閉じられるとき、ファイルは閉じられます。

もう 1 つ、同じ考え方の道具として、`itertools.batched` があります（Python 3.12 以降）。要素を n 個ずつのまとまり（タプル）にして返します。1 行ずつ Parquet に書くより、1000 行ずつまとめて書くほうが、はるかに効率的です。ジェネレータを使うと、「1000 行ずつ読む→直す→書く」を、全体をメモリに載せずにできます。

## pathlib でパスを扱う

ファイルの場所は、文字列でなく `pathlib.Path` で扱います。

- `/` で連結できる: `output_dir / f"{stem}.parquet"`。文字列の連結と違い、区切りの重複や欠落を気にしなくてよく、Windows でも動きます。
- 部品が取り出せる: `path.stem`（拡張子なしの名前）、`path.suffix`、`path.name`、`path.parent`。
- 作成と読み書きが短い: `mkdir(parents=True, exist_ok=True)`（3 章の `mkdir -p` と同じ）、`read_text()`、`write_text()`、`unlink(missing_ok=True)`。
- `replace()` は、移動先に同名のファイルがあっても置き換える。3 章の `mv` による入れ替えと同じ役割です。

`open("orders.csv")` のように相対パスを直接書く癖は、実行場所を変えると壊れます。パスは設定から受け取るようにします。

## 設定と秘密

接続先、入力ファイル、バッチの大きさなど、環境によって変わる値は、コードに書かず、環境変数で受け取ります。3 章の `.env` の考え方です。

```python
@dataclass(frozen=True)
class Settings:
    input_path: Path
    output_dir: Path
    batch_size: int = 1000
    max_reject_ratio: float = 0.05
    log_level: str = "INFO"
    s3_bucket: str | None = None
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        """環境変数から読みます。必須の変数が無ければ KeyError で止まります。"""
        return cls(
            input_path=Path(env["ETL_INPUT"]),
            output_dir=Path(env["ETL_OUTPUT_DIR"]),
            batch_size=int(env.get("ETL_BATCH_SIZE", "1000")),
            max_reject_ratio=float(env.get("ETL_MAX_REJECT_RATIO", "0.05")),
            log_level=env.get("LOG_LEVEL", "INFO"),
            s3_bucket=env.get("S3_BUCKET"),
            s3_endpoint=env.get("S3_ENDPOINT"),
            s3_access_key=env.get("S3_ACCESS_KEY"),
            s3_secret_key=env.get("S3_SECRET_KEY"),
        )
```

ここには 4 つの工夫があります。

1. **設定を 1 つの型にまとめる。**コードのあちこちで `os.environ` を読むと、どんな設定があるのか分からなくなります。
2. **必須の値は `env["ETL_INPUT"]` で読む。**無ければ、処理を始める前に `KeyError` で止まります。半分まで進んでから落ちるより、ずっと安全です。
3. **既定値のある値は `env.get(名前, 既定値)` で読む。**
4. **秘密の項目は `repr=False`。**`print(settings)` や、例外の表示、ログに、秘密が出なくなります。

`from_env` が環境変数の辞書を引数で受け取るのは、テストで本物の環境変数を触らずに済むためです。

## 小さな ETL を段階的に作る

ここまでの部品をつないで、**注文 CSV → 検証 → Parquet** の ETL（取り出して、直して、書き込む処理）を作ります。Parquet は、列ごとにまとめて圧縮して保存する形式で、分析に向きます（後の章で詳しく扱います）。

段階は次のとおりです。

1. 入力の形を決める（`make_sample.py`）。
2. 型と例外を決める（`models.py`）。
3. 1 行ずつ読む（`reader.py`）。
4. 1 行を検証する（`validate.py`）。
5. バッチで書く（`pipeline.py`）。
6. ログと設定をつないで入口を作る（`__main__.py`）。

ステップ 1 は、サンプルの作成です。ねぼすけ商店の注文から、明細を合計して注文 1 行にし、悪い行を 4 つ混ぜます。

```python
def write_sample_csv(path: Path, defects: bool = True) -> int:
    """注文 CSV を書き、書いた行数を返します。defects=True で 4 種類の悪い行を足します。"""
    data = neboske_shop.generate()
    totals: dict[int, list[int]] = {}
    for item in data["order_items"]:
        count_total = totals.setdefault(item["order_id"], [0, 0])
        count_total[0] += 1
        count_total[1] += item["quantity"] * item["unit_price"]
    rows = [[o["order_id"], o["customer_id"], o["ordered_at"], o["status"], *totals[o["order_id"]]]
            for o in data["orders"]]
    if defects:
        rows[10][5] = -500             # 金額がマイナス
        rows[20][2] = "2026-13-45"     # 日付として読めない
        rows[30][3] = "returned"       # 知らない状態
        rows[40][0] = "abc"            # 注文 ID が整数でない
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["order_id", "customer_id", "ordered_at", "status", "item_count", "total_amount"])
        writer.writerows(rows)
    return len(rows)
```

ステップ 2〜4 は、すでに見たとおりです。ステップ 5 が中心です。まず、Parquet の列の型を決めます。

```python
SCHEMA = pa.schema([
    ("order_id", pa.int64()),
    ("customer_id", pa.int64()),
    ("ordered_at", pa.timestamp("ms")),  # Parquet に秒単位は無いのでミリ秒
    ("status", pa.string()),
    ("item_count", pa.int32()),
    ("total_amount", pa.int64()),
])
```

型を明示するのは、データが少ない日や、全部が null の列があった日でも、列の型が変わらないようにするためです。型が日によって変わると、後で読む側が壊れます。Parquet には秒単位の時刻の型が無いので、ミリ秒にしています。

本体の `run` です。

```python
def run(settings: Settings) -> Result:
    """変換を 1 回実行します。同じ入力なら何度動かしても同じ出力になります。"""
    stem = settings.input_path.stem
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = settings.output_dir / f"{stem}.parquet"
    rejects_path = settings.output_dir / f"{stem}.rejects.csv"
    tmp_parquet = parquet_path.with_suffix(".parquet.tmp")
    read = written = rejected = 0
    logger.info("開始: %s (バッチ %d 行)", settings.input_path, settings.batch_size)

    try:
        with (pq.ParquetWriter(tmp_parquet, SCHEMA) as writer,
              rejects_path.open("w", encoding="utf-8", newline="") as rej_file):
            rejects = csv.writer(rej_file)
            rejects.writerow([*EXPECTED_COLUMNS, "error"])
            for batch in batched(iter_rows(settings.input_path), settings.batch_size):
                good: list[Order] = []
                for row in batch:
                    read += 1
                    try:
                        good.append(parse_order(row))
                    except ValidationError as exc:
                        rejected += 1
                        rejects.writerow([*(row[c] for c in EXPECTED_COLUMNS), str(exc)])
                        logger.debug("行を除外: %s", exc)
                if good:
                    writer.write_table(_to_table(good))
                    written += len(good)
        tmp_parquet.replace(parquet_path)  # 書き終えてから本番の名前にする
    finally:
        tmp_parquet.unlink(missing_ok=True)

    logger.info("完了: 読み込み %d 行、書き込み %d 行、除外 %d 行", read, written, rejected)
    return Result(read, written, rejected, parquet_path, rejects_path)
```

読み方を順に示します。

- `batched(iter_rows(...), settings.batch_size)` で、`batch_size` 行ずつ取り出す。ファイル全体はメモリに載りません。
- 行ごとに `parse_order` を呼び、`ValidationError` なら `rejects` の CSV に、元の行と理由を書いて続ける。除外した行は消えず、後から調べられます。
- 正しい行は、バッチごとに Parquet に書く。
- Parquet は、ファイルの末尾にメタデータ（フッター）を書く構造なので、書き終えていないファイルは読めません。それでも途中のファイルを本番の名前に置くと、読む側が混乱します。そこで、`.tmp` に書き、最後に `replace` で入れ替えます。失敗したら `finally` で `.tmp` を消します。3 章の `daily_report.sh` と同じ形です。
- 出力ファイル名を入力ファイルの名前から決めるので、同じ入力に対して、何度動かしても同じ場所に同じ結果を置きます（冪等）。

ステップ 6 は、入口です。

```python
def main() -> int:
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    result = run(settings)
    if result.reject_ratio > settings.max_reject_ratio:
        logger.error("除外が多すぎます: %.1f%% (上限 %.1f%%)",
                     result.reject_ratio * 100, settings.max_reject_ratio * 100)
        return 1
    if settings.s3_bucket:
        upload(settings, result.parquet_path)
    return 0
```

設定を読み、ログを設定し、`run` を呼び、除外の割合が上限を超えたら終了コード 1 で終わります。3 章で見た、「失敗したら非 0 で終わる」の実装です。S3 互換のストレージ（MinIO など）に置く `upload` は、`S3_BUCKET` があるときだけ呼びます。

```python
@retry(attempts=3, wait=1.0, on=(OSError, EndpointConnectionError, ConnectionClosedError))
def upload(settings: Settings, path: Path) -> None:
    """S3 互換のストレージに置きます。つながらないなどの一時的な失敗は再試行します。"""
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
        config=Config(retries={"total_max_attempts": 1}),  # 再試行は retry だけに任せる
    )
    client.upload_file(str(path), settings.s3_bucket, f"orders/{path.name}")
    logger.info("アップロード: s3://%s/orders/%s", settings.s3_bucket, path.name)
```

実行します。3 つの実行を続けています。普通に、`DEBUG` で、除外の上限を厳しくして。

```bash
#!/usr/bin/env bash
# サンプルの注文 CSV を作り、ETL を動かします (リポジトリの直下から実行します)。
set -euo pipefail
export PYTHONPATH=.
python -m examples.b04.make_sample /tmp/orders.csv

cd examples/b04
export ETL_INPUT=/tmp/orders.csv ETL_OUTPUT_DIR=/tmp/out
python -m neboske_etl
LOG_LEVEL=DEBUG python -m neboske_etl
ETL_MAX_REJECT_RATIO=0.0001 python -m neboske_etl || echo "終了コード: $?"
```

```text
3000 行を書きました
2026-11-13 00:52:38,235 INFO neboske_etl.pipeline 開始: /tmp/orders.csv (バッチ 1000 行)
2026-11-13 00:52:38,260 INFO neboske_etl.pipeline 完了: 読み込み 3000 行、書き込み 2996 行、除外 4 行
```

1 回目は、3000 行を読み、2996 行を書き、4 行を除外しました。ログの時刻は、実行ごとに変わります。

```text
2026-11-13 00:52:38,396 INFO neboske_etl.pipeline 開始: /tmp/orders.csv (バッチ 1000 行)
2026-11-13 00:52:38,402 DEBUG neboske_etl.pipeline 行を除外: total_amount: 0 以上でなければなりません: -500
2026-11-13 00:52:38,403 DEBUG neboske_etl.pipeline 行を除外: ordered_at: 日時として読めません: '2026-13-45'
2026-11-13 00:52:38,403 DEBUG neboske_etl.pipeline 行を除外: status: 知らない値です: 'returned'
2026-11-13 00:52:38,403 DEBUG neboske_etl.pipeline 行を除外: order_id: 整数ではありません: 'abc'
2026-11-13 00:52:38,422 INFO neboske_etl.pipeline 完了: 読み込み 3000 行、書き込み 2996 行、除外 4 行
```

`LOG_LEVEL=DEBUG` にすると、除外した 1 行ごとの理由が見えます。最初に落ちた `step1_naive.py` と違って、どの項目が、なぜ悪いかが分かります。

```text
2026-11-13 00:52:38,519 INFO neboske_etl.pipeline 開始: /tmp/orders.csv (バッチ 1000 行)
2026-11-13 00:52:38,549 INFO neboske_etl.pipeline 完了: 読み込み 3000 行、書き込み 2996 行、除外 4 行
2026-11-13 00:52:38,549 ERROR neboske_etl 除外が多すぎます: 0.1% (上限 0.0%)
終了コード: 1
```

除外の割合（0.1%）が上限を超えたので、ERROR を出して終了コード 1 で終わります。cron やオーケストレーターは、この終了コードで失敗に気づきます。

除外された行は、CSV に残っています。

```text
order_id,customer_id,ordered_at,status,item_count,total_amount,error
11,398,2026-03-25 20:34:47,delivered,4,-500,total_amount: 0 以上でなければなりません: -500
21,338,2026-13-45,placed,1,6150,ordered_at: 日時として読めません: '2026-13-45'
```

書き出された Parquet の中身も、読み直して確かめます。

```text
2996
order_id: int64
customer_id: int64
ordered_at: timestamp[ms]
status: string
item_count: int32
total_amount: int64
```

2996 行、列の型は指定どおりです。

## pytest でテストを書く

テストは、「こう動くはず」をコードにして、自動で確かめる仕組みです。データの処理では、特に次の 4 つを確かめます。

- 正しい入力が、正しい出力になる。
- 悪い入力が、狙いどおりに除外される・失敗する。
- 同じ入力で 2 回動かしても、結果が変わらない（冪等）。
- 失敗したときに、書きかけのファイルが残らない。

pytest は、`test_` で始まる関数を集めて実行し、`assert` が偽なら失敗とします。

```python
def test_parse_order_returns_typed_order():
    order = parse_order(GOOD_ROW)
    assert order == Order(1, 10, datetime(2026, 1, 1, 9, 0), "shipped", 2, 3400)


def test_status_case_is_normalized():
    assert parse_order({**GOOD_ROW, "status": " SHIPPED "}).status == "shipped"
```

`pytest.raises` は、指定した例外が起きることを確かめます。同じ形のテストに、入力だけ変えて繰り返すときは、`parametrize` を使います。

```python
@pytest.mark.parametrize("field,value,reason", [
    ("order_id", "abc", "整数ではありません"),
    ("order_id", "0", "1 以上"),
    ("total_amount", "-500", "0 以上"),
    ("ordered_at", "2026-13-45", "日時として読めません"),
    ("status", "returned", "知らない値"),
    ("customer_id", "", "整数ではありません"),
])
def test_parse_order_rejects_bad_values(field, value, reason):
    with pytest.raises(ValidationError) as info:
        parse_order({**GOOD_ROW, field: value})
    assert info.value.field == field
    assert reason in info.value.reason
```

6 通りの悪い入力を、1 つのテスト関数で確かめています。どの組み合わせが落ちたかも、別々に表示されます。

ファイルを扱うテストでは、`tmp_path` を使います。pytest がテストごとに作る一時ディレクトリで、本物のデータを汚しません。

```python
def test_run_splits_good_and_bad_rows(sample_csv, tmp_path):
    result = run(make_settings(sample_csv, tmp_path / "out"))
    assert (result.read, result.written, result.rejected) == (3000, 2996, 4)
    table = pq.read_table(result.parquet_path)
    assert table.num_rows == 2996
    assert str(table.schema.field("ordered_at").type) == "timestamp[ms]"
    assert set(table.column("status").to_pylist()) <= {"placed", "shipped", "delivered", "cancelled"}
    assert min(table.column("total_amount").to_pylist()) >= 0
    rejects = result.rejects_path.read_text(encoding="utf-8").splitlines()
    assert len(rejects) == 1 + 4
    assert rejects[0].endswith(",error")
    assert any("total_amount" in line for line in rejects[1:])
```

このテストは、サンプルの全体を通して、読んだ行、書いた行、除外した行の数と、Parquet の型、除外ファイルの中身を確かめます。冪等と、残骸が無いことも確かめます。

```python
def test_run_is_idempotent_and_leaves_no_temp_file(sample_csv, tmp_path):
    settings = make_settings(sample_csv, tmp_path / "out")
    first = run(settings)
    second = run(settings)
    assert pq.read_table(first.parquet_path).num_rows == pq.read_table(second.parquet_path).num_rows
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["orders.parquet", "orders.rejects.csv"]
```

再試行のテストには、困りごとがあります。本当に待つと、テストが遅くなります。`monkeypatch` で `time.sleep` を差し替え、待った秒数を記録するだけにします。

```python
@pytest.fixture
def no_sleep(monkeypatch):
    waits = []
    monkeypatch.setattr(retry_module.time, "sleep", waits.append)
    return waits


def test_retry_succeeds_after_transient_failures(no_sleep):
    calls = []

    @retry(attempts=3, wait=1.0)
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise OSError("一時的な失敗")
        return "ok"

    assert flaky() == "ok"
    assert no_sleep == [1.0, 2.0]  # 待ち時間は倍になる
```

待ち時間が `[1.0, 2.0]` と倍になっていくことまで、確かめられます。設定のテストも、環境変数に触らずにできます。

```python
def test_settings_missing_required_variable_fails_fast():
    with pytest.raises(KeyError, match="ETL_INPUT"):
        Settings.from_env({"ETL_OUTPUT_DIR": "out"})


def test_secret_is_not_in_repr():
    settings = Settings.from_env({"ETL_INPUT": "i", "ETL_OUTPUT_DIR": "o", "S3_SECRET_KEY": "dummy-secret-xyz"})
    assert "dummy-secret-xyz" not in repr(settings)
    assert settings.s3_secret_key == "dummy-secret-xyz"
```

秘密が `repr` に出ないことも、テストとして固定しています。誰かが `repr=False` を消したら、このテストが落ちます。

接続できない相手への `upload` が、決めた回数で諦めることも、確かめています。

```python
def test_upload_retries_connection_errors(sample_csv, tmp_path, no_sleep):
    from botocore.exceptions import EndpointConnectionError

    result = run(make_settings(sample_csv, tmp_path / "out"))
    settings = make_settings(sample_csv, tmp_path / "out", s3_bucket="nowhere",
                             s3_endpoint="http://127.0.0.1:1", s3_access_key="x", s3_secret_key="y")
    with pytest.raises(EndpointConnectionError):
        upload(settings, result.parquet_path)
    assert no_sleep == [1.0, 2.0]  # 3 回試して、2 回待った
```

実行は、リポジトリの直下からです。

```bash
pytest -q examples/b04
```

何をテストするかの判断が、いちばん難しいところです。目安は、「壊れたら困るところ」と「過去に壊れたところ」です。1 行の `return` を確かめるようなテストを積み上げるより、境界（空、最大、悪い値）と、失敗の後の状態を確かめるほうが、役に立ちます。テストの数やカバレッジの数字を、目的にしないでください。

## よくある失敗

- **`except Exception:` で何もせず続ける。**プログラムの誤りまで隠れて、数字が静かにずれます。
- **ログに秘密を出す。**設定や HTTP のヘッダーを丸ごと出すと、鍵が載ります。
- **`print` を残す。**標準出力にログを混ぜると、パイプでつなぐ後続のコマンドが壊れます。
- **モジュールの先頭で `basicConfig` を呼ぶ。**他のコードのログ設定を上書きします。
- **全行をリストに読んでから処理する。**手元の小さなファイルでは動き、本番でメモリが尽きます。
- **版を固定しない。**昨日動いたものが、今日は新しい版の影響で動かなくなります。
- **悪い行を黙って捨てる。**件数と理由を残し、割合で止めます。
- **相対パスの決め打ち。**cron など、実行場所が違うと壊れます。
- **再試行を、何にでもかける。**直らない失敗を何度も試して、時間と相手の負荷を増やします。
- **テストが本物の時刻・ネットワーク・環境変数に依存する。**ときどき落ちるテストは、やがて無視されます。

## まとめ

- 仮想環境で環境を分け、アプリは版を固定、ライブラリは範囲で書く。
- 境界で 1 回、文字列を型に直す。dataclass と独自の例外で、悪いデータを入口で止める。
- 失敗は種類で分ける。行は隔離して割合で止め、一時的な失敗だけを再試行する。
- ログは `logging` で、設定は入口の 1 か所で。秘密は出さない。
- ジェネレータとバッチで、メモリを抑える。パスは `pathlib`。
- 結果は一時ファイルに書いて入れ替え、何度動かしても同じ結果になるようにする。
- pytest で、悪い入力・冪等・失敗後の状態を確かめる。

## 練習問題

問1. `parse_order` に、「`item_count` が 100 を超える注文は、入力ミスの疑いがあるので `ValidationError` にする」ルールを足すとき、どこをどう変えますか。テストも 1 つ書いてください。

??? note "解答例"
    `validate.py` の `parse_order` で `item_count` を読む直後に、100 を超えたら `ValidationError("item_count", ...)` を投げる処理を足します。`_to_int` に `maximum` の引数を足して、`minimum` と同じ形で検査する方法もあります。テストは `test_parse_order_rejects_bad_values` の `parametrize` に `("item_count", "101", "100 以下")` の 1 行を足すのが最小です。上限の値は、コードに直接書かず、定数か設定に出しておくと、後で変えやすくなります。

問2. 除外の割合が上限以内でも、除外が普段の 10 倍に増えた日を、運用で気づけるようにしたいです。この章のコードのどこに、何を足しますか。

??? note "解答例"
    `run` の最後の `logger.info("完了: ...")` の近くで、除外の割合が一定以上なら `logger.warning` を出します。WARNING は「動いているが気になる」という意味なので、ここに合います。さらに、実行ごとの件数を、ログではなく、表やファイルに記録しておくと、過去との比較ができます（データ品質の監視は 13 章で扱います）。割合の上限を超えたときに終了コード 1 で止める仕組みは、すでに `__main__.py` にあります。

問3. `upload` が 3 回とも失敗したとき、ジョブ全体はどうなりますか。呼び出し側ではどう扱うべきですか。

??? note "解答例"
    `retry` は使い切ると元の例外を投げ直すので、`main` の中で捕まえなければ、プログラムは例外で止まり、終了コードは 0 以外になります。Parquet は出力先に残っているので、原因を直してから、同じ入力で動かし直せます（冪等）。呼び出し側で捕まえて別の処理に切り替える場合も、失敗を黙って成功にしてはいけません。ログに ERROR を出し、終了コードで知らせます。

問4. 次のコードの問題点を 2 つ以上挙げてください。

```python
def load(path):
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        try:
            save(int(r["id"]))
        except:
            pass
```

??? note "解答例"
    (1) `open` を `with` で閉じていない。(2) `list(...)` で全行をメモリに載せている。ジェネレータで 1 行ずつ処理できる。(3) `except:` で全部を握りつぶし、`pass` で何も残さない。`id` が整数でない行も、`save` のバグも区別がつかず、失敗した件数も分からない。`ValueError` だけを捕まえ、理由をログと除外ファイルに残すべき。(4) 型ヒントが無く、`path` や戻り値の型が分からない。(5) テストを書きにくい。

## 参考文献

- Python 公式ドキュメント: venv <https://docs.python.org/3/library/venv.html> ／ チュートリアル「仮想環境とパッケージ」<https://docs.python.org/3/tutorial/venv.html>
- pip ドキュメント: `pip freeze` <https://pip.pypa.io/en/stable/cli/pip_freeze/> ／ 再現可能なインストール <https://pip.pypa.io/en/stable/topics/repeatable-installs/>
- Python Packaging User Guide「Writing your pyproject.toml」<https://packaging.python.org/en/latest/guides/writing-pyproject-toml/>
- uv: <https://docs.astral.sh/uv/>
- typing <https://docs.python.org/3/library/typing.html> ／ PEP 484 <https://peps.python.org/pep-0484/> ／ mypy <https://mypy.readthedocs.io/en/stable/>
- dataclasses <https://docs.python.org/3/library/dataclasses.html>
- チュートリアル「エラーと例外」<https://docs.python.org/3/tutorial/errors.html> ／ 組み込み例外 <https://docs.python.org/3/library/exceptions.html>
- logging <https://docs.python.org/3/library/logging.html> ／ Logging HOWTO <https://docs.python.org/3/howto/logging.html>
- Python HOWTO「Functional Programming」（ジェネレータ）<https://docs.python.org/3/howto/functional.html> ／ itertools（`batched`）<https://docs.python.org/3/library/itertools.html>
- pathlib <https://docs.python.org/3/library/pathlib.html> ／ csv <https://docs.python.org/3/library/csv.html>
- The Twelve-Factor App「III. 設定」<https://12factor.net/ja/config>
- pytest ドキュメント <https://docs.pytest.org/en/stable/> ／ parametrize <https://docs.pytest.org/en/stable/how-to/parametrize.html> ／ tmp_path <https://docs.pytest.org/en/stable/how-to/tmp_path.html> ／ monkeypatch <https://docs.pytest.org/en/stable/how-to/monkeypatch.html>
- Apache Parquet ドキュメント（ファイル形式）<https://parquet.apache.org/docs/file-format/> ／ PyArrow `ParquetWriter` <https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetWriter.html>
- AWS Builders' Library「Timeouts, retries and backoff with jitter」<https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/>

!!! tip "さらに深く"
    応用編 第7章「データ契約とスキーマ進化」では、この章の検証を、チーム間で取り決める契約として扱います。

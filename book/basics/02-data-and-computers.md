# 第2章 データとコンピュータの基礎

## この章でできるようになること

- CPU・メモリ・SSD・ネットワークの速さの桁の違いを言え、それがデータ処理の設計にどう効くかを説明できる。
- 行指向と列指向の違いと、圧縮が効く理由を説明できる。
- CSV・JSON・Parquet を、同じデータで書き出して比べ、場面に応じて使い分けられる。
- 文字コード（UTF-8 と BOM）、日時とタイムゾーン、数値の型（整数・浮動小数・decimal）で起きる典型的な事故を、先回りして避けられる。

## なぜ土台から始めるのか

データエンジニアの仕事は、データを動かすことです。ソースシステムから取り込み、置き場所に書き、変換のために読み、利用者に届けます。動かす先々で、データは CPU、メモリ、ディスク、ネットワークのどこかを通ります。そして、それぞれの速さは何桁も違います。

この違いを知らないと、「なぜこのクエリは遅いのか」「なぜこのファイルは大きいのか」「なぜ集計結果が 1 円ずれるのか」に答えられません。この章は、後の章で何度も戻ってくる土台です。

## 速さの桁

まず、操作ごとの所要時間を見ます。次の表は、Peter Norvig と Jeff Dean が広めた「プログラマが知っておくべき遅延の数字」の一部です。2012 年ごろの数字として知られていて、出典は参考文献 1 と 2 にあります。

{{ table("b02-latency") }}

右の列は、「0.5 ナノ秒（0.0000000005 秒）」のような人間に実感しにくい時間を、1 ナノ秒を 1 秒に引き延ばして読み替えたものです。L1 キャッシュ（CPU の中の一番近い記憶）の参照が 0.5 秒だとすると、メモリの参照は 2 分弱、SSD からのランダム読み込みは 1 日半以上、大陸をまたぐ通信は数年かかる計算になります。

同じ数字を、横軸を対数にして描いたのが次の図です。目盛りが一つ進むごとに 10 倍です。

![操作ごとの時間の桁（対数軸）](../assets/figures/b02_latency.svg)

注意が二つあります。ひとつは、この数字は古いことです。SSD もネットワークも当時より速くなっているので、個々の値は目安として扱ってください。もうひとつは、実際の値が機種や条件で変わることです。ここから読み取るのは、桁の関係です。

読み取れることを整理します。

**メモリとディスクの差は大きい。** 1 MB を順に読む時間は、表の値ではメモリで 250 マイクロ秒、SSD で 1 ミリ秒、ディスクで 20 ミリ秒です。同じデータでも、どこに置かれているかで読む時間が桁で変わります。データベースやウェアハウスの多くが、よく使うデータをメモリに置こうとする（キャッシュ）のはこのためです。

**順に読むほうがはるかに速い。** ディスクのシーク（読む位置への移動）に 10 ミリ秒かかるのに対して、そこから 1 MB を順に読むのは 20 ミリ秒です。つまり、データを散らばった場所から少しずつ読むと、ほとんどの時間が位置の移動に消えます。ひとかたまりで読めるように並べておくことが、速さに直結します。この考え方は、次の行指向と列指向、第11章のパーティションの話の根っこにあります。

**ネットワークは近いほど速い。** 同じデータセンター内の往復が 500 マイクロ秒、地球の反対側とのやりとりが 150 ミリ秒です。つまり 300 倍の差があります。データのある場所に処理を持っていく（データを動かさず計算を動かす）設計が好まれる理由です。クラウドで「同じリージョン内に置く」ことが料金と速さの両方に効くのも、同じ理由です。

**動かすデータは少ないほど速い。** 以上のすべてから、結論はひとつにまとまります。必要のないデータを読まず、運ばないことです。この本のほぼすべての最適化は、この一文の言い換えです。

表の値から、簡単な見積もりもできます。SSD から 1 MB を順に読むのに約 1 ミリ秒なら、1 GB（1,000 MB）はおよそ 1 秒です。1 TB なら 1,000 秒で、17 分弱です。ただし、これは 1 台の SSD を順に読み続けた場合の机上の計算です。実際には、複数のディスクで並列に読む、読まなくてよい部分を飛ばす、といった工夫で大きく変わります。それでも、「全部読むと 17 分かかるデータに、毎回全件の集計をかけてよいか」という問いが立てられるようになります。これが、桁を知る意味です。

## 行指向と列指向

表形式のデータを、ディスクやメモリの上にどう並べるか。大きく 2 つの流儀があります。

**行指向**は、1 件ずつ、すべての項目をひとまとめにして並べます。注文 1 件の注文番号・商品・単価・数量が隣り合います。1 件を丸ごと読み書きするのが得意で、アプリケーションのデータベース（注文を 1 件登録して、その注文を 1 件表示する）に向きます。

**列指向**は、項目ごとに、全件分の値をまとめて並べます。単価だけが全件分続き、次に数量だけが全件分続きます。分析では「全注文の単価の合計」のように、多くの件数に対して少数の項目だけを使う集計が多いので、必要な列だけを読めば済む列指向が向きます。

Python の list と dict で、両者の違いを再現してみます。ねぼすけ商店の注文明細を 5 件だけ取った例です（`examples/b02/row_vs_column.py`）。

```python
rows = [
    {"order_id": 1, "category": "寝具", "unit_price": 3200, "quantity": 1},
    {"order_id": 2, "category": "寝具", "unit_price": 1800, "quantity": 2},
    {"order_id": 3, "category": "飲み物", "unit_price": 900, "quantity": 3},
    {"order_id": 4, "category": "飲み物", "unit_price": 650, "quantity": 1},
    {"order_id": 5, "category": "飲み物", "unit_price": 700, "quantity": 2},
]
```

`rows` が行指向です。これを項目ごとの並びに組み替える関数を書きます。

```python
def to_columns(rows: list[dict]) -> dict[str, list]:
    """行の並びを、項目ごとの並びに組み替えます。"""
    return {key: [row[key] for row in rows] for key in rows[0]}
```

```python
columns = to_columns(rows)
# 行指向で unit_price の合計を出すには、全行をたどって 1 項目ずつ取り出す
total_from_rows = sum(row["unit_price"] for row in rows)
# 列指向なら unit_price の並びだけを読めばよい
total_from_columns = sum(columns["unit_price"])
```

結果は同じですが、触るデータの量が違います。5 件では差が見えなくても、10 億件で 50 項目ある表なら、列指向は 50 分の 1 の項目だけを読みます。これは、先ほどの「動かすデータは少なく」と同じ話です。

もうひとつ、列指向には利点があります。同じ種類の値が隣り合うので、圧縮が効きやすいのです。たとえば `category` 列は、「寝具」が続いたあと「飲み物」が続いています。続いている値を、(値, 続く回数) の組にまとめる方法を、ランレングス符号化と言います。

```python
def run_length_encode(values: list) -> list[tuple]:
    """同じ値が続く部分を (値, 続く回数) にまとめます。列指向の圧縮の考え方の一例です。"""
    encoded: list[tuple] = []
    for v in values:
        if encoded and encoded[-1][0] == v:
            encoded[-1] = (v, encoded[-1][1] + 1)
        else:
            encoded.append((v, 1))
    return encoded
```

`category` 列に使うと、`[('寝具', 2), ('飲み物', 3)]` になります。5 個の文字列が 2 個の組に縮みました。行指向の並びでは、「寝具」の隣に別の項目の値が来るので、この方法は使えません。

一方で、列指向は 1 件を丸ごと読み書きするのが苦手です。1 件の注文を登録するたびに、すべての列の末尾に書き足す必要があるからです。そのため、アプリの DB（第7章）は行指向、分析用のウェアハウス（第11章）は列指向、という分担が一般的です。この分担の詳しい理由は、第11章で改めて扱います。

## 圧縮

圧縮は、同じ情報を、より少ないバイト数で表す工夫です。データエンジニアリングで使うのは、元に戻せる圧縮（可逆圧縮）です。圧縮の効果は、保存のコストだけではありません。ディスクからもネットワークからも、読む量が減るので、読み込み時間そのものが縮むことがあります。速さの桁の節で見たように、ディスクやネットワークは CPU よりずっと遅いので、読む量を減らす利益のほうが、展開に使う CPU の時間を上回ることが多いのです。

圧縮には 2 つのレベルがあります。

1. **データの並びを使った符号化**: ランレングス符号化のように、「同じ値が続く」「種類が少ない」といった性質を使います。Parquet では、辞書符号化（文字列を番号に置き換える）やランレングス符号化といった方式が定義されています（参考文献 6）。
2. **汎用の圧縮**: gzip、Snappy、Zstandard など。バイト列の繰り返しを探して縮めます。圧縮率が高いが遅いもの、率はほどほどで速いものがあり、用途で選びます。

選ぶときの考え方は単純です。速さと小ささが引き換えになっています。頻繁に読むデータには速い方式、めったに読まないが長く置くデータには小さくなる方式を選びます。ただし、どちらが良いかは実測で決まります。この章の後半で、同じデータを 5 通りの形で書き、実際に測ります。

## CSV・JSON・Parquet を同じデータで比べる

データを受け渡すファイルの形式は、実際には数種類に絞られます。3 つの特徴を整理します。

**CSV**（カンマ区切り）は、1 行が 1 件、項目をカンマで区切ります。人が開いて読め、ほぼすべての道具が読めます。ただし、仕様はゆるく、RFC 4180 は実際に使われている書き方を文書にしたもので、標準規格ではありません（参考文献 3）。型の情報がなく、すべてが文字列です。区切り文字、引用符、改行、文字コードの方言が多く、空文字と欠損（NULL）の区別も決まっていません。

**JSON**（正確には、1 行に 1 件ずつ書く JSON Lines）は、入れ子の構造を持てます。Web API の返答やログの標準的な形です。JSON の仕様は RFC 8259 にあります（参考文献 4）。構造を持てる代わりに、キー名を毎行繰り返すので大きくなります。数値は 1 種類しかなく、整数か小数かの区別は読む側に任されています。

**Parquet** は、列指向のファイル形式です。列ごとに型がつき、スキーマ（列の名前と型）がファイルに入っています。列ごとの圧縮と、辞書符号化などの符号化が使え、各列の最小値・最大値といった統計も持ちます（参考文献 5）。人は直接開けませんが、機械が読むには最も効率のよい形式のひとつです。

ねぼすけ商店のデータで、実際に比べます。注文・明細・商品・顧客をつないだ平らな売上明細を作り、seed を変えて 60 回分つなげて、約 45 万行にします。1 回分では小さすぎて差が見えないためです。このデータを CSV、gzip 圧縮した CSV、JSON Lines、Parquet（snappy と zstd）の 5 通りで書き出します。書き出しは、DuckDB の `COPY` で行います（`examples/b02/file_formats.py`）。

```python
    con.execute(f"COPY t TO '{paths['CSV']}' (FORMAT csv, HEADER)")
    with open(paths["CSV"], "rb") as src, gzip.open(paths["CSV (gzip)"], "wb") as dst:
        shutil.copyfileobj(src, dst)
    con.execute(f"COPY t TO '{paths['JSON Lines']}' (FORMAT json)")
    con.execute(f"COPY t TO '{paths['Parquet (snappy)']}' (FORMAT parquet, COMPRESSION snappy)")
    con.execute(f"COPY t TO '{paths['Parquet (zstd)']}' (FORMAT parquet, COMPRESSION zstd)")
```

読み込み時間は、DuckDB で 2 通りを測ります。ひとつは全部の列を読んでテーブルにする場合、もうひとつは 1 列（`unit_price`）の合計だけを取る場合です。時間は、毎回新しい接続で 3 回測って最短を取り、ファイルは OS のキャッシュに載った状態です。

```python
def best_of(sql: str, repeat: int = 3) -> float:
    """新しい接続で sql を repeat 回流し、最短の秒数を返します。"""
    times = []
    for _ in range(repeat):
        con = duckdb.connect()
        t0 = time.perf_counter()
        con.execute(sql).fetchall()
        times.append(time.perf_counter() - t0)
        con.close()
    return min(times)
```

実行すると、筆者の環境（WSL2 上の Docker）では次のように出ました。

```console
$ python examples/b02/file_formats.py
```

```text
CSV                   39.1 MB  load_all 0.112 s  sum_one_col 0.054 s  (449,587 rows)
CSV (gzip)             5.1 MB  load_all 0.273 s  sum_one_col 0.173 s  (449,587 rows)
JSON Lines           104.3 MB  load_all 0.114 s  sum_one_col 0.060 s  (449,587 rows)
Parquet (snappy)       5.8 MB  load_all 0.019 s  sum_one_col 0.001 s  (449,587 rows)
Parquet (zstd)         3.7 MB  load_all 0.019 s  sum_one_col 0.001 s  (449,587 rows)
```

数字は計測の出力であり、機械や実行のたびに変わります。手元で動かして、桁と順序を確かめてください。同じ計測をグラフにしたのが、次の図です（ビルドのたびに計測し直して描くので、本文の出力とは数字が少し違うことがあります）。

![5 通りの形式のファイルサイズと読み込み時間](../assets/figures/b02_formats.svg)

この出力から言えることを順に見ます。

- **サイズ**: JSON Lines が最大で、CSV の 2.7 倍ほどです。キー名と引用符を 45 万行ぶん繰り返しているからです。Parquet（zstd）は CSV の 10 分の 1 前後です。列ごとに同じ種類の値を並べて圧縮できるうえ、`category` や `prefecture` のような種類の少ない列は辞書符号化が効きます。
- **圧縮した CSV は小さいが遅い**: gzip した CSV は Parquet に近い大きさですが、読み込みは CSV より遅くなっています。gzip は途中から展開できず、先頭から順に展開するしかないからです。ファイルが小さいことと、読むのが速いことは別です。
- **1 列だけ使うなら列指向が圧倒的に速い**: 1 列の合計は、CSV や JSON ではファイル全体を読み、全部の項目を解釈してから 1 列を使います。Parquet は、その列の部分だけを読みます。この実行例では、CSV の数十分の 1 の時間でした。
- **全列を読んでも Parquet のほうが速い**: Parquet は、型がファイルに入っているので文字列の解釈が要らず、列ごとにまとめて読めるためです。

使い分けの目安を、表にします。

{{ table("b02-format-choice") }}

実務の指針としては、外とのやりとり（人や他社との受け渡し、API）には CSV と JSON、自分たちの基盤の中で分析に使うデータは Parquet、という分担が基本です。取り込みの最初の段階では生のまま（CSV や JSON）で保存し、変換の結果を Parquet にして持つ、という使い方もよくあります。

## 文字コード

文字を数字（バイト列）に置き換える決まりが、文字コードです。同じ文字でも、決まりが違えばバイト列が違います。日本語を扱うなら避けて通れない話題です。

現在の標準は **UTF-8** です。Unicode の全ての文字を、1〜4 バイトで表します（参考文献 7）。英数字は 1 バイトで、ひらがなや漢字は 3 バイトです。Windows の日本語環境では長く Shift_JIS 系（Python の名前では `cp932`）が使われ、ひらがなや漢字は 2 バイトです。この 2 つは互換性がありません。実験してみます（`examples/b02/text_encoding.py`）。

```python
text = "ねぼすけ商店"
utf8 = text.encode("utf-8")
cp932 = text.encode("cp932")  # Windows の日本語環境が使う Shift_JIS 系
print(len(text), "文字", len(utf8), "バイト(UTF-8)", len(cp932), "バイト(cp932)")

# 書いた文字コードと違う文字コードで読むと文字化けする（読めないバイトは ? に置き換える）
print(utf8.decode("cp932", errors="replace"))
print(cp932.decode("utf-8", errors="replace"))
```

```text
6 文字 18 バイト(UTF-8) 12 バイト(cp932)
縺ｭ縺ｼ縺吶￠蝠�蠎�
�˂ڂ������X
```

同じ 6 文字が、UTF-8 では 18 バイト、cp932 では 12 バイトです。違う方式で読むと、意味の通らない文字が並びます。これが文字化けです。取り込みでは、ファイルを受け取るたびに「どの文字コードで書かれているか」を確かめる必要があります。ファイルの中には文字コードを書く場所がないので、取り決めか推測に頼るしかありません。可能なら、受け渡しの約束事として UTF-8 と決めておきます。

もうひとつの落とし穴が **BOM**（バイト順マーク）です。ファイルの先頭に付く 3 バイト（`EF BB BF`）で、UTF-8 で書かれていることの目印として使われます。UTF-8 にはバイト順の問題がないので、BOM は順序を示す役割は持たず、あくまで文字コードの目印です（参考文献 8）。Excel で開く前提のとき、BOM を付けて書く運用があります。問題は、BOM を考えずに読むプログラムです。

```python
# Excel で開きやすいように BOM 付き UTF-8 で書かれた CSV の先頭
csv_bytes = "order_id,商品名\n1,枕\n".encode("utf-8-sig")
print(csv_bytes[:3], csv_bytes[:3].hex())
print(repr(csv_bytes.decode("utf-8").splitlines()[0]))  # BOM が列名にくっつく
print(repr(csv_bytes.decode("utf-8-sig").splitlines()[0]))  # BOM を取り除く
```

```text
b'\xef\xbb\xbf' efbbbf
'﻿order_id,商品名'
'order_id,商品名'
```

`utf-8` で読むと、先頭の列名が `'﻿order_id'` になります。目で見ると `order_id` と同じなのに、プログラムは別の名前として扱います。「`order_id` という列が見つからない」というエラーが出て、画面を見ても原因がわからない、という典型的な事故です。Python では `utf-8-sig` で読むと、BOM があってもなくても読めます。

最後に、**正規化**です。見た目が同じ文字列でも、内部の並びが違うことがあります。たとえば「ガ」は、1 つの文字（U+30AC）でも、「カ」と濁点の 2 つの文字の並びでも表せます。前者を NFC、後者を NFD と呼びます（参考文献 9）。

```python
# 見た目が同じでも、並べ方の違う文字列（NFC と NFD）
composed = "ガ"  # 1 コードポイント（U+30AC）
decomposed = unicodedata.normalize("NFD", composed)  # カ + 濁点（2 コードポイント）
print(composed == decomposed, len(composed), len(decomposed))
print(unicodedata.normalize("NFC", decomposed) == composed)
```

```text
False 1 2
True
```

見た目が同じ 2 つの文字列が `==` で False になります。顧客名や商品名を別のシステムから取り込んで結合したら、一致するはずなのに一致しない、という形で表に出ます。複数のソースの文字列を突き合わせる前に、NFC などにそろえておくと安全です。

## 日時とタイムゾーン

日時は、データの欠陥が最も起きやすい項目のひとつです。理由は、「何時か」が、「どこで見るか」で変わるからです。

Python では、タイムゾーンの情報を持たない日時（naive）と、持つ日時（aware）が区別されます。ねぼすけ商店の `ordered_at` は `"2026-03-01 08:30:00"` のような文字列で、タイムゾーンが書かれていません。これは日本時間（JST）で記録されているとみなしますが、その約束が頭の中にしかないと、他の人が UTC として読んでしまいます。

安全な基本方針は 3 つです。

1. **保存は UTC にそろえる、または、タイムゾーン付きで保存する。** PostgreSQL の `timestamp with time zone` 型は、内部では UTC で持ち、表示のときに接続の設定に合わせて変換します（参考文献 10）。
2. **文字列で受け渡すなら、ISO 8601 / RFC 3339 の形式にする。** `2026-03-01T08:30:00+09:00` のように、オフセットを含めて書きます（参考文献 11）。
3. **日付の区切りは、業務の基準のタイムゾーンで決める。** 次の実験で理由を見ます。

```python
JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc
FORMAT = "%Y-%m-%d %H:%M:%S"


def daily_counts(orders: list[dict], tz) -> Counter:
    """注文を tz の暦の日付ごとに数えます。ordered_at は JST の時刻として読みます。"""
    counts: Counter = Counter()
    for o in orders:
        jst_time = datetime.strptime(o["ordered_at"], FORMAT).replace(tzinfo=JST)
        counts[jst_time.astimezone(tz).date().isoformat()] += 1
    return counts
```

`ZoneInfo("Asia/Tokyo")` は、IANA タイムゾーンデータベースにある名前を使います（参考文献 12）。まず、同じ瞬間を JST と UTC で書いてみます。

```python
# 同じ時刻を、UTC では前日になる例
moment = datetime(2026, 3, 1, 8, 30, tzinfo=JST)
print(moment.isoformat(), "->", moment.astimezone(UTC).isoformat())
```

```text
2026-03-01T08:30:00+09:00 -> 2026-02-28T23:30:00+00:00
```

日本時間の 3 月 1 日の朝 8 時半は、UTC では 2 月 28 日の夜 11 時半です。日本の午前 9 時より前の時間帯は、UTC では前の日になります。

この性質は、日別集計にそのまま響きます。ねぼすけ商店の注文を、JST の日付ごとに数えた場合と、UTC の日付ごとに数えた場合で、件数を比べます。

```python
# 同じ注文でも、日付の区切りを JST にするか UTC にするかで日ごとの件数が変わる
orders = generate()["orders"]
jst_counts = daily_counts(orders, JST)
utc_counts = daily_counts(orders, UTC)
differing = [d for d in sorted(jst_counts) if jst_counts[d] != utc_counts.get(d, 0)]
print(len(jst_counts), "日のうち件数が食い違う日:", len(differing))
day = max(differing, key=lambda d: jst_counts[d])  # 件数がいちばん多い日で見る
print(day, "JST:", jst_counts[day], "UTC:", utc_counts[day])
```

```text
172 日のうち件数が食い違う日: 145
2026-03-30 JST: 44 UTC: 33
```

172 日のうち 145 日で件数が食い違いました。同じ注文のデータなのに、2026 年 3 月 30 日の件数は JST で 44 件、UTC で 33 件です。店長が見て「昨日 44 件売れた」と思っている日に、ダッシュボードが 33 件と表示すれば、信頼を失います。対策は、どのタイムゾーンで日付を切るかを決めて、全員がそれに従うことです。

もうひとつ、夏時間（サマータイム）のある地域では、「1 日」が 24 時間とは限りません。米国東部では、2026 年 3 月 8 日に時計が 1 時間進みます。

```python
# 夏時間のある地域では、「1 日」が 24 時間とは限らない
NY = ZoneInfo("America/New_York")
start = datetime(2026, 3, 8, 0, 0, tzinfo=NY)
end = datetime(2026, 3, 9, 0, 0, tzinfo=NY)
print(end - start)  # 同じタイムゾーンの引き算は、壁の時計の差になる
print(end.astimezone(UTC) - start.astimezone(UTC))  # UTC にそろえると実際の経過時間
```

```text
1 day, 0:00:00
23:00:00
```

同じタイムゾーンの 2 つの日時を引くと、壁の時計の差の「1 日」が出ます。UTC にそろえてから引くと、実際に経過したのは 23 時間です。時間の長さを計算するときは、UTC にそろえてから引きます。日本には夏時間がありませんが、海外のデータを扱えば必ず出会います。

## 型: 整数・浮動小数・decimal

データの型は、「その値がどんな範囲と精度を持てるか」の約束です。型の選び間違いは、エラーにならずに値が少しずれる、という最も見つけにくい形で現れることが多くあります。

**整数**は、固定の幅（ビット数）で持つのが普通です。たとえば 32 ビットの整数は約 ±21 億まで、64 ビットは約 ±922 京までです。範囲を超えると、環境によってエラーになるか、値が回ってしまいます。DuckDB では、あふれるとエラーになります。

**浮動小数点数**（float や double）は、2 進数で小数を近似します。10 進数の 0.1 は、2 進数では循環小数になり、有限の桁では正確に表せません（参考文献 13）。

```python
# 浮動小数点数（float）は 2 進数で近似するので、10 進数の 0.1 を正確に持てない
print(0.1 + 0.2, 0.1 + 0.2 == 0.3)
total = 0.0
for _ in range(10):
    total += 0.1  # 0.1 円ではなく 0.1 を 10 回足す
print(total, total == 1.0)
print(Decimal(0.1))  # float の 0.1 が実際に持っている値
```

```text
0.30000000000000004 False
0.9999999999999999 False
0.1000000000000000055511151231257827021181583404541015625
```

`0.1 + 0.2` は 0.3 になりません。0.1 を 10 回足しても 1.0 になりません。`Decimal(0.1)` で、float が実際に持っている値が見えます。これはバグではなく、浮動小数点数の仕様（IEEE 754）どおりの動作です。科学計算や機械学習の特徴量では、この小さな誤差は問題になりません。一方、**金額**では問題になります。1 円単位の勘定が合わなくなるからです。

金額には、次のどちらかを使います。

1. **整数で持つ**: 円やセントといった最小の単位の整数にします。ねぼすけ商店の `unit_price` は円の整数です。
2. **decimal（固定小数点）で持つ**: 10 進数のまま計算する型です。Python の `decimal.Decimal`（参考文献 14）、DuckDB や PostgreSQL の `DECIMAL(18, 2)` などです。

```python
# decimal は 10 進数のまま計算する。文字列から作る（float から作ると誤差ごと取り込む）
print(Decimal("0.1") + Decimal("0.2"), Decimal("0.1") + Decimal("0.2") == Decimal("0.3"))
```

```text
0.3 True
```

`Decimal` は、文字列から作ります。`Decimal(0.1)` のように float から作ると、すでに近似されている値を取り込んでしまうからです。

float の誤差が実害になる例を、もうひとつ見ます。小数のドルを整数のセントに直す処理です。

```python
# 金額を「小数のドル」から「整数のセント」に直す: float だと 1 セントずれる金額がある
cents = range(1, 10000)
float_wrong = [c for c in cents if int(c / 100 * 100) != c]
print(float_wrong[:5], len(float_wrong), "/", len(cents))
print(int(0.29 * 100), int(Decimal("0.29") * 100))
```

```text
[29, 57, 58, 113, 114] 573 / 9999
28 29
```

1 セントから 9,999 セントまで、ドルに直して 100 倍し、整数に戻してみると、573 通りが元の値に戻りません。0.29 ドルは、float では 28 セントになります。原因は、ドルに直したときに入った誤差が、整数への切り捨てで表に出るためです。

丸め方も仕様のうちです。

```python
# 丸め方も仕様: Python の round() は偶数丸め（2.5 → 2）、請求書では四捨五入が多い
print(round(2.5), round(3.5))
print(Decimal("2.5").quantize(Decimal("1"), rounding=ROUND_HALF_UP))
```

```text
2 4
3
```

Python の `round()` は、ちょうど真ん中の値を偶数のほうへ丸めるので、2.5 が 2 に、3.5 が 4 になります。四捨五入のつもりで使うと、請求書の端数が合いません。どう丸めるかは、ビジネスの側と決めて明示します。

DuckDB でも同じ違いが出ます。

```python
# DuckDB の型: 固定長の整数はあふれるとエラーになり、DOUBLE は誤差が出る
con = duckdb.connect()
print(con.execute("SELECT 0.1::DOUBLE + 0.2::DOUBLE = 0.3::DOUBLE").fetchone())
print(con.execute("SELECT 0.1::DECIMAL(18,2) + 0.2::DECIMAL(18,2) = 0.3::DECIMAL(18,2)").fetchone())
try:
    con.execute("SELECT 2147483647::INTEGER + 1")
except duckdb.OutOfRangeException as e:
    print("あふれ:", str(e).splitlines()[0])
```

```text
(False,)
(True,)
あふれ: Out of Range Error: Overflow in addition of INT32 (2147483647 + 1)!
```

`DOUBLE` での比較は False、`DECIMAL(18,2)` では True です。32 ビット整数（`INTEGER`）の最大値に 1 を足すとエラーになります（参考文献 15）。エラーになるだけ親切で、黙ってずれる場合より安全です。

最後に、整数の大きさについての注意です。Python の整数は、桁数の上限がありません。ところが、JSON を読む側が JavaScript などの場合、数値は倍精度の浮動小数点数（double）として扱われ、2 の 53 乗を超える整数は正確に持てません（RFC 8259 も、この相互運用性の問題に触れています）。

```python
# 2**53 を超える整数は、JSON を double で読む環境（JavaScript など）で正確に持てない
big = 2**53 + 1
print(big, int(float(big)))
```

```text
9007199254740993 9007199254740992
```

ID が大きな整数のとき、JSON で渡すと末尾が 1 ずれることがあります。大きな ID は、文字列で渡すのが安全です。

## よくある失敗

**CSV をそのまま基盤の標準形式にする。** 手軽ですが、型の情報がなく、列の読み間違いが静かに起きます（`0123` が `123` になる、など）。分析で繰り返し読むデータは、型付きの形式（Parquet）に変換します。

**ファイルが小さい＝速い、と考える。** gzip した CSV は小さくなりますが、並列に読めず、遅くなることがあります。小ささと速さは別の指標です。実測で選びます。

**文字コードを確かめずに読む。** 受け取ったファイルが UTF-8 だと思い込んで読むと、文字化けか、BOM のせいで列名が合わない事故になります。受け渡しの約束に文字コードを書きます。

**タイムゾーンを書かない。** 日時の文字列にオフセットがないと、読み手が勝手に解釈します。保存は UTC かオフセット付きにして、日付の区切りは業務のタイムゾーンで決めます。

**金額を float で持つ。** 少額のずれが積み重なって、月末に数十円の差が出ます。整数か decimal にします。

**計測せずに最適化する。** 「Parquet が速いと聞いたので」だけで変えると、小さなファイルが大量にできて逆に遅くなることがあります。まず測ります。この章の `file_formats.py` のように、ごく短いコードで測れます。

## まとめ

- 操作の時間は、CPU のキャッシュ、メモリ、SSD、ディスク、ネットワークの順に桁で遅くなります。速くするとは、遅い場所を通る回数と量を減らすことです。
- 列指向は、必要な列だけを読め、同じ種類の値が並ぶので圧縮もよく効きます。行指向は 1 件の読み書きが得意です。
- 同じデータで比べると、Parquet は CSV よりずっと小さく、1 列だけの集計は桁違いに速く、JSON は最も大きくなります。小さいことと速いことは別です。
- 文字コードは UTF-8 を基本にし、BOM と NFC/NFD の違いを意識します。
- 日時は、タイムゾーンを明示し、UTC か業務の基準にそろえます。
- 金額は整数か decimal で持ち、丸め方を決めます。

## 練習問題

**問1.** ディスクから 1 MB を順に読む時間が 20 ミリ秒だとします。ディスク 1 台で 100 GB のファイルを順に読むとして、全部を読むのにどのくらいかかるか、概算してください（1 GB = 1,000 MB とします）。それを Parquet で 10 分の 1 に縮められたら、どうなりますか。

??? note "解答例"
    100 GB は 100,000 MB なので、20 ミリ秒 × 100,000 = 2,000 秒で、約 33 分です。10 分の 1 の 10 GB なら 200 秒（約 3 分 20 秒）です。さらに必要な列だけを読めれば、その分も減ります。実際の機械の速度とは異なる机上の計算ですが、「読む量を減らすと、時間がその比率で減る」ことを確かめられます。

**問2.** 次のデータに向く形式を、CSV・JSON Lines・Parquet から選び、理由を一言で書いてください。(a) 経理に渡す月次の請求一覧（経理は Excel で開く）。(b) 外部サービスの API から返ってくる、入れ子のあるイベント。(c) 3 年分の行動ログ（20 億行）に対する、毎日の集計の入力。

??? note "解答例"
    (a) CSV。人が表計算ソフトで開けることが優先です（文字コードは、Excel で開く運用なら BOM 付き UTF-8 にするなど、受け取る側と決めます）。(b) JSON Lines。入れ子をそのまま持て、1 行 1 件で追記しやすいためです。(c) Parquet。必要な列だけ読め、圧縮もよく効きます。日付で分けて置けば、読む範囲も絞れます（第11章）。

**問3.** `examples/b02/time_zones.py` の `daily_counts` に、`Asia/Kolkata`（インド標準時。UTC+5:30）を渡すと、JST の日別件数と何が変わるか、推測してから確かめてください。

??? note "解答例"
    JST とは 3 時間半の差があり、JST で 0 時から 3 時半までの注文が、Kolkata では前日の扱いになります。ZoneInfo("Asia/Kolkata") を作って `daily_counts(orders, ...)` に渡し、`jst_counts` と比べると、食い違う日があるはずです。JST と UTC の差（9 時間）より小さいため、食い違う日は UTC のときより少なくなります。時刻が 30 分ずれた地域では、日付の境目も 30 分刻みでずれることを確かめる問題です。

**問4.** ある CSV を `utf-8` で読んだところ、`KeyError: 'order_id'` が出ました。ヘッダーを `print` すると、見た目は `order_id` です。何を疑いますか。確かめる方法と直し方も書いてください。

??? note "解答例"
    BOM を疑います。`repr(header)` で出力すると、先頭に `'﻿'` が付いているのが見えます。バイト列で先頭 3 バイトが `EF BB BF` であることでも確かめられます。直し方は、読むときの文字コードを `utf-8-sig` にすることです。本文の `text_encoding.py` の例と同じ状況です。

## 参考文献

1. Peter Norvig. "Teach Yourself Programming in Ten Years" の「Answers」節. <http://norvig.com/21-days.html>（メモリやディスクの所要時間の桁。L1 キャッシュ 0.5 ns、メインメモリ 100 ns など）
2. "Latency Numbers Every Programmer Should Know"（Jeff Dean の表を jboner が gist にまとめたもの。原典は Peter Norvig）. <https://gist.github.com/jboner/2841832>（本章の表は、ここに載っている 2012 年ごろの値のうち、ハードウェアの行だけを使用。後から加えられた大規模言語モデルの行は使っていない）
3. Y. Shafranovich. RFC 4180: Common Format and MIME Type for Comma-Separated Values (CSV) Files. 2005. <https://www.rfc-editor.org/rfc/rfc4180>
4. T. Bray (ed.). RFC 8259: The JavaScript Object Notation (JSON) Data Interchange Format. 2017. <https://www.rfc-editor.org/rfc/rfc8259>
5. Apache Parquet Documentation, File Format. <https://parquet.apache.org/docs/file-format/>
6. Apache Parquet Documentation, Encodings. <https://parquet.apache.org/docs/file-format/data-pages/encodings/>
7. F. Yergeau. RFC 3629: UTF-8, a transformation format of ISO 10646. 2003. <https://www.rfc-editor.org/rfc/rfc3629>
8. Unicode Consortium. "Byte Order Mark (BOM) FAQ". <https://www.unicode.org/faq/utf_bom.html>
9. Unicode Standard Annex #15: Unicode Normalization Forms. <https://unicode.org/reports/tr15/>
10. PostgreSQL Documentation, Date/Time Types. <https://www.postgresql.org/docs/current/datatype-datetime.html>
11. G. Klyne, C. Newman. RFC 3339: Date and Time on the Internet: Timestamps. 2002. <https://www.rfc-editor.org/rfc/rfc3339>
12. Python Documentation, zoneinfo. <https://docs.python.org/3/library/zoneinfo.html>、IANA Time Zone Database. <https://www.iana.org/time-zones>
13. Python Tutorial, Floating Point Arithmetic: Issues and Limitations. <https://docs.python.org/3/tutorial/floatingpoint.html>
14. Python Documentation, decimal. <https://docs.python.org/3/library/decimal.html>
15. DuckDB Documentation, Numeric Types. <https://duckdb.org/docs/stable/sql/data_types/numeric.html>
16. Joe Reis, Matt Housley. *Fundamentals of Data Engineering*. O'Reilly Media, 2022. 第 6 章 Storage の "Raw Ingredients of Data Storage"（磁気ディスク、SSD、メモリ、ネットワークと CPU、シリアライゼーション、圧縮）と Appendix A。

!!! tip "さらに深く"
    分散処理で、データの移動と計算の置き場がどう性能を決めるかは、応用編 第1章「分散処理の内側」で扱います。

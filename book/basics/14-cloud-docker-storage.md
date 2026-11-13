# 第14章 クラウド・Docker・オブジェクトストレージ

## この章でできるようになること

- リージョン・ゾーン・IAM・責任共有モデルの意味を説明し、パイプラインに最小権限を渡す考え方を持てる。
- イメージ・コンテナ・レイヤの関係を説明し、決まりに沿った Dockerfile を書いて、ビルドと実行ができる。
- docker compose で、複数のサービスを起動順つきでまとめて動かす設定を読み書きできる。
- オブジェクトストレージ(バケット・キー・プレフィックス)の性質を説明し、MinIO と boto3 で置く・一覧する・分割して上げる・期限付き URL を作るができる。
- Hive 形式のパーティションと小さいファイル問題を説明し、まとめ直し(コンパクション)ができる。
- IaC(コードでインフラを管理する考え方)を Terraform の例で説明できる。
- 費用の入口(保存・リクエスト・データ転送)と、ローカルと本番の差を減らす方法を説明できる。

この本のコード例は、これまで Docker の中で動かしてきました。この章は、その Docker の中身と、データの置き場所であるクラウドのストレージを、手を動かして理解する章です。クラウドの契約は不要で、PostgreSQL・MinIO・Redpanda を動かす `compose.yaml` だけで試せます。MinIO は、S3 と同じ API を話す、手元で動くオブジェクトストレージです。

## クラウドの基本

クラウドは、サーバーやストレージを、必要な分だけ借りて使う仕組みです。データエンジニアの仕事では、データを置く場所(ストレージ)と、処理を動かす場所(計算)を借りることがほとんどです。最初に押さえる言葉は 6 つです。

{{ table("b14-cloud-terms") }}

**リージョン**は、データを置く地域の単位です。東京にデータを置けば、日本の利用者や社内システムから近く、国内に保管したいという要件にも合います。ただしリージョンを選ぶと、そのあとで変えるのは大変です。料金も地域で違います。**アベイラビリティゾーン(AZ)**は、同じリージョンの中の別々の施設で、片方が止まってももう片方が動き続けるようにするための単位です。データの保管は、ストレージの製品が複数の AZ に自動で複製してくれることが多く、利用者が AZ を選ぶ場面は主に計算(サーバー)のほうです。

**IAM**(Identity and Access Management)は、誰が何に対して何をしてよいかを決める仕組みです。ここで効く考え方が最小権限で、パイプラインには「そのパイプラインが必要な操作だけ」を渡します。S3 の読み取り専用のポリシーの例です。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOnlyEventsPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::deb-lake",
      "Condition": {"StringLike": {"s3:prefix": ["events/*"]}}
    },
    {
      "Sid": "ReadEventsObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::deb-lake/events/*"
    }
  ]
}
```

見落としやすいのは `Resource` です。一覧(`s3:ListBucket`)の対象は「バケット」なので、`arn:aws:s3:::deb-lake` と書きます。読み取り(`s3:GetObject`)の対象は「オブジェクト」なので、`.../events/*` と書きます。ListBucket に `/*` を付けたり、GetObject にバケットだけを書いたりすると、意図どおりに動きません。`examples/b14/static_checks.py` の `policy_problems` は、`Action` が `*` や `s3:*` になっていないか、`Resource` が `*` でないか、この取り違えがないかを、読むだけで確かめます。

人が使うユーザーと、処理が使う**ロール**は分けます。ロールは一時的な認証情報を発行する仕組みなので、コードや設定ファイルに長期の鍵を書かずに済みます。鍵の書き込みは、第3章で見たとおり、漏れたときの影響が最も大きい間違いの 1 つです。

**責任共有モデル**は、クラウド事業者が基盤(建物・ハードウェア・仮想化)を守り、利用者がその上の設定とデータを守る、という分担です(AWS の説明は参考文献)。バケットを公開にしてしまう、権限を広く付けすぎる、暗号化を選ばない、バックアップを取らない、は利用者の責任です。クラウドにあるから安全、ではありません。

## コンテナと Docker

アプリを動かすには、プログラム本体のほかに、言語の実行環境と、ライブラリと、設定が要ります。「自分の PC では動くのに、他の環境で動かない」の多くは、この環境の違いが原因です。コンテナは、アプリと必要な環境を 1 つにまとめ、どこでも同じように動かす仕組みです。

用語を 3 つ分けます。**イメージ**は、アプリと環境を固めた読み取り専用の雛形です。**コンテナ**は、イメージから起動した実行中の 1 つのプロセスです(同じイメージから何個でも起動できます)。**レイヤ**は、イメージを作る手順の 1 行 1 行が積み重ねた差分で、イメージはこのレイヤの積み重ねです。後で出てくるキャッシュは、このレイヤの単位で効きます。

仮想マシンが OS ごと丸ごと動かすのに対し、コンテナはホストの OS のカーネルを共有するので、軽くて速く起動します。そのかわり、分離の強さは仮想マシンより弱い面があります。

イメージの作り方を書いたファイルが Dockerfile です。この本の開発用イメージ(リポジトリ直下の `Dockerfile`)も、同じ形です。ここからは、行動ログを日付ごとの Parquet にして S3 互換のストレージへ置く小さな ETL(`examples/b14/etl/`)を例に、Dockerfile の書き方を見ます。

## Dockerfile の書き方の要点

{{ table("b14-dockerfile-rules") }}

実際の Dockerfile です。

```dockerfile
FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 依存だけ先にコピーして入れる。コードを直しても、この層はキャッシュが効く。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 普通のユーザーで動かす (root のままにしない)。
RUN useradd --create-home --uid 10001 etl
COPY --chown=etl:etl storage.py etl.py ./
USER etl

CMD ["python", "etl.py"]
```

表の 6 つの決まりを、この Dockerfile で確かめます。

**小さいベースイメージを固定したタグで選ぶ。** `python:3.12.8-slim-bookworm` は、Debian 12(bookworm)に Python 3.12.8 を入れた、`slim`(不要なものを省いた)版です。`python` や `python:latest` と書くと、ビルドする日によって中身が変わります。さらに厳密にするなら、イメージの中身を一意に指す「ダイジェスト」(`@sha256:...`)で固定する方法もあります。ビルドの出力にも、解決されたダイジェストが出ます。

**依存のバージョンを固定する。** `requirements.txt` には `boto3==1.44.2` のように `==` で書きます。書いていないと、ビルドし直したら新しい版が入って壊れた、ということが起きます。

**変わりにくいものを先に書く。** Docker はレイヤごとに結果をキャッシュし、ある行の入力(コピーしたファイルなど)が変わると、その行以降をすべて作り直します。このため、依存の一覧(めったに変わらない)を先にコピーして `pip install` し、コード(よく変わる)を後からコピーします。実際に、`etl.py` に 1 行足して再ビルドしてみると、こうなりました。

```text
#6 [2/6] WORKDIR /app
#6 CACHED
#7 [3/6] COPY requirements.txt .
#7 CACHED
#8 [4/6] RUN pip install --no-cache-dir -r requirements.txt
#8 CACHED
#9 [5/6] RUN useradd --create-home --uid 10001 etl
#9 CACHED
#10 [6/6] COPY --chown=etl:etl storage.py etl.py ./
```

(`docker build --progress=plain` の出力の一部です。)依存を入れる重い手順は再利用され、最後のコードのコピーだけが実行されます。`COPY . .` を最初に置くと、コードを 1 文字直しただけで `pip install` からやり直しです。

**root で動かさない。** `RUN useradd` で作ったユーザーに `USER etl` で切り替えます。確かめます。

```bash
docker run --rm --entrypoint id neboske-etl:dev
```

```text
uid=10001(etl) gid=10001(etl) groups=10001(etl)
```

コンテナが攻撃されたとき、root のままだと影響が大きくなります(これで十分とは限りませんが、最初の一手です)。

**秘密を焼き込まない。** `ENV API_KEY=...` や `COPY .env` でイメージに入れた秘密は、イメージを受け取った人に見えます。あとから消しても、前のレイヤには残ります。秘密は実行時に、環境変数やシークレットの仕組みで渡します(ビルド中に必要な秘密には BuildKit の `--mount=type=secret` があります。参考文献)。`.dockerignore` に `.env` を書き、ビルドに送るファイルから外すのも有効です。

**キャッシュを残さない。** `pip install --no-cache-dir` で、ダウンロードの控えをイメージに残しません。

ビルドして、実行時の設定は環境変数で渡します。

```bash
python examples/b14/make_input.py examples/b14/data/events.jsonl
docker build -t neboske-etl:dev examples/b14/etl
docker run --rm --network host -v "$PWD/examples/b14/data":/data:ro \
  -e S3_ENDPOINT=http://localhost:9000 -e S3_ACCESS_KEY=minioadmin -e S3_SECRET_KEY=minioadmin \
  -e BUCKET=lake-demo -e CREATE_BUCKET=1 neboske-etl:dev
```

```text
4040 行を 180 ファイルに書きました
```

`-v` は、手元のフォルダをコンテナの `/data` に読み取り専用(`:ro`)で見せる設定です。`--network host` は、コンテナを手元のネットワークにそのまま繋ぎ、`localhost:9000` の MinIO に届くようにします(Linux の Docker での書き方で、Docker Desktop では挙動が違うことがあります)。ここで鍵を `-e` で渡しているのはローカルの学習用の値で、本番ではロールやシークレットの仕組みを使います。

Dockerfile の決まりは、レビューで見落としやすいので、読むだけの検査も用意しました(`static_checks.dockerfile_problems`)。タグの固定、最後の `USER`、最初の `COPY` が requirements であること、`--no-cache-dir`、秘密らしい名前の `ENV`、`CMD` が配列形式であること、`requirements.txt` の `==` を確かめます。本物のビルドは重いので、テストでは回さず、この検査と、いまの Dockerfile が通ること、わざと間違えた Dockerfile が全部引っかかることを確かめています。これは安全網であって、`docker build` の代わりではありません。

## docker compose で複数のサービスを動かす

アプリは 1 つのコンテナで完結しないことが多いです。ETL と、その出力先のオブジェクトストレージ、というように複数が必要です。docker compose は、複数のコンテナの設定を 1 つの YAML に書き、まとめて起動する道具です。この本の `compose.yaml` は PostgreSQL・MinIO・Redpanda を動かします。それぞれ `image` のタグを固定し、`healthcheck`(動いているかを確かめるコマンド)を持ち、`ports` で手元に公開しています。

ETL と MinIO を一緒に動かす例です(`examples/b14/compose.etl.yaml`)。

```yaml
# 小さな ETL と MinIO を一緒に動かす compose の例。
# 使い方 (examples/b14 で): docker compose -f compose.etl.yaml up --build --abort-on-container-exit
services:
  minio:
    image: bitnamilegacy/minio:2025.7.23-debian-12-r3
    environment:
      MINIO_ROOT_USER: ${S3_ACCESS_KEY:-minioadmin}  # ローカル専用の値。本番の鍵は書かない
      MINIO_ROOT_PASSWORD: ${S3_SECRET_KEY:-minioadmin}
    ports:
      - "9000:9000"
    healthcheck:
      test: ["CMD-SHELL", "curl -fs http://localhost:9000/minio/health/live"]
      interval: 3s
      retries: 20

  etl:
    build: ./etl
    depends_on:
      minio:
        condition: service_healthy
    environment:
      S3_ENDPOINT: http://minio:9000  # サービス名がそのままホスト名になる
      S3_ACCESS_KEY: ${S3_ACCESS_KEY:-minioadmin}
      S3_SECRET_KEY: ${S3_SECRET_KEY:-minioadmin}
      BUCKET: lake
      CREATE_BUCKET: "1"
    volumes:
      - ./data:/data:ro
```

押さえる点は 3 つです。

- **起動順**: `depends_on` だけでは「起動した」までしか待ちません。`condition: service_healthy` を付けると、`healthcheck` が通るまで待ちます。付けないと、MinIO の準備前に ETL が接続して失敗します。
- **ホスト名**: 同じ compose の中では、サービス名(`minio`)がそのままホスト名になります。コンテナの中の `localhost` は、そのコンテナ自身を指すので、`http://localhost:9000` と書くと ETL からは届きません。
- **秘密**: `${S3_ACCESS_KEY:-minioadmin}` は、環境変数が無ければ既定値を使う書き方です。値を YAML に直書きせず、外から渡せる形にしておきます。

起動は次のコマンドです。

```bash
cd examples/b14
docker compose -f compose.etl.yaml up --build --abort-on-container-exit
```

この compose は 9000 番を使うので、本書の `compose.yaml` の MinIO など、別の MinIO が動いている間は起動できません。私の確認では、`docker compose config` で設定が読めることと、後述の検査で形が正しいことまでを確かめ、起動そのものは共有のサービスに影響するため実行していません。

形の検査も同じ考え方です。

```python
def compose_problems(spec):
    """spec は yaml.safe_load した compose.yaml。"""
    problems = []
    services = spec.get("services", {})
    for name, svc in services.items():
        image = svc.get("image")
        if image and (":" not in image or image.endswith(":latest")):
            problems.append(f"{name}: image {image} のタグが固定されていない")
        for dep, cond in (svc.get("depends_on") or {}).items():
            if not isinstance(cond, dict) or cond.get("condition") != "service_healthy":
                problems.append(f"{name}: {dep} の起動完了を待っていない (service_healthy が無い)")
            elif "healthcheck" not in services.get(dep, {}):
                problems.append(f"{name}: {dep} に healthcheck が無い")
        for key, value in (svc.get("environment") or {}).items():
            if SECRET_NAME.search(key) and not str(value).startswith("${"):
                problems.append(f"{name}: {key} の値が compose に直書きされている")
    return problems
```

この本の `compose.yaml` は、パスワード(`POSTGRES_PASSWORD`)を学習用に直書きしているので、この検査の「直書き」には引っかかります。テストは、それ以外の問題(タグの固定、`healthcheck`)が無いことだけを確かめています。ローカルの学習用の値は直書きでよく、本番では別の仕組みに変える、という線引きです。

## オブジェクトストレージ

オブジェクトストレージは、ファイルをディレクトリの階層ではなく、**バケット**(入れ物)の下に**キー**(名前)と**オブジェクト**(中身とメタデータ)の組で置く仕組みです。S3(AWS)が代表で、同じ API を話す互換品が多くあります(MinIO もその 1 つ)。

{{ table("b14-s3-vs-fs") }}

特に大事なのは「階層は見かけ」です。`events/dt=2026-03-01/part-0000.parquet` は、1 本の長い文字列がキーなだけで、`events` というフォルダが実在するわけではありません。AWS の文書も、バケットは階層のない平らな構造で、コンソールのフォルダは見やすさのための見せ方だと説明しています。このため、プレフィックス(キーの先頭の文字列)での絞り込みは、文字を前から比べるだけです。

接続は、環境変数だけで切り替えられるように書きました(`examples/b14/etl/storage.py`)。

```python
def make_client(env=None):
    env = os.environ if env is None else env
    kwargs = {"region_name": env.get("S3_REGION", "us-east-1")}
    if env.get("S3_ENDPOINT"):
        kwargs["endpoint_url"] = env["S3_ENDPOINT"]
        kwargs["config"] = Config(s3={"addressing_style": "path"})  # MinIO はパス形式
    if env.get("S3_ACCESS_KEY"):  # 無ければ boto3 の標準の探し方 (環境変数・ロール) に任せる
        kwargs["aws_access_key_id"] = env["S3_ACCESS_KEY"]
        kwargs["aws_secret_access_key"] = env["S3_SECRET_KEY"]
    return boto3.client("s3", **kwargs)
```

`S3_ENDPOINT` があれば MinIO、無ければ AWS の S3 に繋ぎます。コードは同じで、違いは環境変数だけです。boto3 は AWS の Python 用ライブラリです。

### 置く・一覧する

一覧には、`list_objects_v2` を使います。1 回のリクエストで返るのは最大 1000 件(AWS の API の文書)なので、それを超える場合は続きを取りに行く必要があります。boto3 の paginator が、その繰り返しを担います。

```python
def list_keys(client, bucket, prefix, page_size=1000):
    """prefix で始まるキーを全部返します。(キー一覧, LIST リクエストの回数)。"""
    paginator = client.get_paginator("list_objects_v2")
    keys, pages = [], 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, PaginationConfig={"PageSize": page_size}):
        pages += 1
        keys += [obj["Key"] for obj in page.get("Contents", [])]
    return keys, pages
```

「フォルダに見えるもの」だけが欲しいときは、区切り文字 `/` を指定すると、1 階層分の共通の接頭辞が返ります。

```python
def list_folders(client, bucket, prefix):
    """区切り文字 "/" で 1 階層分だけ見て、「フォルダに見えるもの」を返します。"""
    paginator = client.get_paginator("list_objects_v2")
    out = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        out += [p["Prefix"] for p in page.get("CommonPrefixes", [])]
    return out
```

実演です。3 日分の行動ログを、10 行ずつの小さなファイルにして置き、一覧します(`demo_storage.py`)。

```bash
S3_ENDPOINT=http://localhost:9000 S3_ACCESS_KEY=minioadmin S3_SECRET_KEY=minioadmin \
  python examples/b14/demo_storage.py
```

```text
置いたキー数: 7
フォルダに見えるもの: ['events/dt=2026-01-01/', 'events/dt=2026-01-02/', 'events/dt=2026-01-03/']
1 日分のキー: ['events/dt=2026-01-02/part-0000.parquet', 'events/dt=2026-01-02/part-0001.parquet'] (LIST は 1 回)
全部を 2 件ずつ一覧すると LIST は 4 回
まとめた後: ['events/dt=2026-01-02/compacted.parquet'] = events/dt=2026-01-02/compacted.parquet
```

4 行目に注目してください。同じ 7 件を、1 回の上限を 2 件に下げて一覧すると 4 回のリクエストが要ります。本番の上限は 1000 件なので、10 万件のキーを全部一覧するには、単純計算で 100 回の LIST です。LIST は、料金表では PUT・COPY・POST と同じ区分で、GET とは別に課金されます。一覧は「安い読み取り」ではなく、回数を意識する操作です。

### プレフィックスは文字の前方一致

テストで確かめた性質を 2 つ挙げます。

- `Prefix="events"` は、`events/...` だけでなく `events_old/...` や `events.csv` にも一致します。「フォルダ」を指したいときは、末尾に `/` を付けて `events/` と書きます。
- `Prefix="events/dt=2026-01-0"` は、`dt=2026-01-01` と `dt=2026-01-02` に一致しますが、`dt=2026-01-10` には一致しません(`0` の次の文字が違うため)。日付の範囲の指定を文字列でする場合は、このことを前提にします。

### 整合性

S3 は、新しいオブジェクトの書き込みも、上書きや削除も、直後の読み取りに反映される、強い整合性(strong read-after-write consistency)を提供しています(2026年11月時点の AWS の文書)。昔の「置いたのに読めない」を前提にした書き方は、いまは不要です。ただし、複数のオブジェクトを 1 つの操作でまとめて確定する仕組みはありません。たとえば 100 個のファイルを書き終える途中で読み手が一覧すると、書きかけが見えます。第9章で見た `_SUCCESS` のような完了マーカーが要るのは、このためです。名前の変更(rename)も、コピーしてから削除する 2 操作で、途中で失敗すると両方が残ります。

### 大きなファイルと期限付き URL

大きなファイルは、分割して上げる**マルチパートアップロード**が使えます(1 パートの最小は 5 MiB。参考文献)。boto3 の `upload_file` は、閾値を超えると自動で分割します。

```python
def upload_large(client, bucket, key, path, threshold=5 * MIB):
    """threshold を超えるファイルは自動でマルチパート (分割) アップロードになります。ETag を返します。"""
    config = TransferConfig(multipart_threshold=threshold, multipart_chunksize=threshold)
    client.upload_file(str(path), bucket, key, Config=config)
    return client.head_object(Bucket=bucket, Key=key)["ETag"].strip('"')
```

テストでは 11 MiB のファイルを 5 MiB ずつ 3 パートで上げ、ETag の末尾が `-3` になることを確かめています。分割して上げたオブジェクトの ETag は、中身のハッシュ(MD5)そのものではない形になるので、「ETag で中身が同じか調べる」ことはできません。

認証情報を渡さずに、1 つのオブジェクトだけを期限付きで読ませたいときは、**署名付き URL**を作ります。

```python
def presigned_get(client, bucket, key, seconds=60):
    """認証情報を渡さずに、期限付きで 1 つのオブジェクトだけ読める URL を作ります。"""
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=seconds)
```

テストでは、その URL で本文が読めること、別のキーに書き換えると 403 になること、期限が切れると 403 になることを確かめています。URL を知っている人は誰でも読めるので、有効期限は短くします。

### ライフサイクルと暗号化

一時ファイルが溜まり続けると、保存の費用が増えます。**ライフサイクル規則**で、プレフィックスごとに自動で消す(または安いクラスへ移す)ことができます。

```python
def expire_prefix_after(client, bucket, prefix, days):
    """prefix 配下のオブジェクトを days 日後に自動で消すライフサイクル規則を設定します。"""
    client.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={"Rules": [{
            "ID": f"expire-{prefix.strip('/').replace('/', '-')}",
            "Filter": {"Prefix": prefix},
            "Status": "Enabled",
            "Expiration": {"Days": days},
        }]})
```

**暗号化**には 2 つあります。通信の暗号化(https)と、保存時の暗号化(サーバー側暗号化)です。AWS の S3 は、保存時の暗号化が既定で有効です(文書の説明)。鍵の管理を自分で行いたいときは KMS(鍵管理サービス)を選びます。この本の旧版の MinIO は、鍵の管理サービスを設定していないため、暗号化の指定は試していません。次の IaC の例では、保存時の暗号化を設定として書きます。

### ローカルの MinIO にしかない癖

この本の MinIO(旧版・1 ドライブ)は、ファイルシステムの上にオブジェクトを置くと考えられます。実際に、`events` というキーと `events/dt=1/p` というキーを同じバケットに置くと、片方しか一覧に出ませんでした(`test_local_minio_hides_a_key_that_is_also_a_folder` で確かめています。原因は上のファイルシステムの性質と推測しています)。S3 では両方を別のキーとして置けます。ローカルと本番の差の実例なので、後の節で扱います。

## ファイルの置き方

### Hive 形式のパーティション

データを、`events/dt=2026-03-01/part-0000.parquet` のように、`列名=値` のフォルダに分けて置く形式を Hive 形式と呼びます。Spark・Hive・Athena・DuckDB など多くの道具が、このフォルダ名から列の値を読み取れます。日付で絞った検索のときに、条件に合うフォルダだけを読めば済みます(第11章のパーティションと同じ考え方を、ファイルの置き方で実現したものです)。

DuckDB では `hive_partitioning = true` を付けます。

```python
def hive_count(base, dt):
    """dt=YYYY-MM-DD のフォルダに分けて置き、パスの dt を列として読んで 1 日分だけ数えます。"""
    rows = generate()["events"]
    by_day = {}
    for row in rows:
        by_day.setdefault(row["event_time"][:10], []).append(row)
    for day, day_rows in by_day.items():
        write_files(day_rows, base / f"dt={day}", rows_per_file=len(day_rows))
    sql = (f"SELECT count(*) FROM read_parquet('{base}/*/*.parquet', hive_partitioning = true) "
           f"WHERE dt = '{dt}'")
    return duckdb.sql(sql).fetchall()[0][0], len(by_day)
```

ねぼすけ商店の行動ログを 180 個の `dt=` フォルダに分け、`dt = '2026-03-01'` の行を数えると 24 行でした(テストで確かめています)。`dt` はファイルの中の列ではなく、フォルダの名前から作られる列です。

パーティションの列は、検索でよく絞る列、かつ値の種類が多すぎない列を選びます。日付がよく使われるのはこのためです。顧客 ID のように種類が多い列で分けると、フォルダが何万もできて、次の問題を悪化させます。

### 小さいファイル問題

ファイルが小さく大量にあると、読む側は 1 ファイルごとに開く手間とリクエストが増え、Parquet には 1 ファイルごとにメタデータが付くので、全体のサイズも増えます。同じ 4,040 行を、1 ファイルで書いた場合と、100 行ずつ 41 ファイルで書いた場合を比べました(`small_files.py`)。

```python
def compare(base):
    rows = generate()["events"]
    write_files(rows, base / "one", rows_per_file=len(rows))
    write_files(rows, base / "small", rows_per_file=100)
    return {"one": summarize(base / "one"), "small": summarize(base / "small")}
```

```text
one {'files': 1, 'bytes': 108832, 'rows': 4040}
small {'files': 41, 'bytes': 197737, 'rows': 4040}
```

行数は同じなのに、合計サイズは約 1.8 倍です。ストリーミングの取り込みのように、短い間隔で少しずつ書く処理は、この形になりがちです。対策は、あとでまとめ直す**コンパクション**です。

```python
def compact(client, bucket, partition_prefix):
    """prefix 配下の小さな Parquet を 1 つにまとめます。先に書いてから古いものを消します。"""
    keys, _ = list_keys(client, bucket, partition_prefix)
    tables = [pq.read_table(io.BytesIO(client.get_object(Bucket=bucket, Key=k)["Body"].read()))
              for k in keys]
    merged = pa.concat_tables(tables)
    buf = io.BytesIO()
    pq.write_table(merged, buf)
    new_key = f"{partition_prefix}compacted.parquet"
    client.put_object(Bucket=bucket, Key=new_key, Body=buf.getvalue())
    old = [{"Key": k} for k in keys if k != new_key]
    for i in range(0, len(old), 1000):  # delete_objects は 1 回 1000 件まで
        client.delete_objects(Bucket=bucket, Delete={"Objects": old[i:i + 1000]})
    return new_key
```

「先に書いてから消す」順にしているのは、途中で失敗しても元のデータが残るからです。ただし、新旧が一瞬同時に見えるので、その間に読む人は重複を読みます。読み手が影響を受けない運用(コンパクションの時間帯を決める、完了のマーカーを使う)や、テーブルフォーマットでの扱いは、応用編で見ます。1 ファイルの大きさの目安として、数十〜数百 MB 程度にまとめるという説明がよく見られますが、最適な大きさは読む道具とデータの量で変わるので、実測で決めます。

## IaC の考え方

バケットや権限をコンソールの画面で作ると、誰が何をいつ変えたか分からなくなり、同じ環境を作り直せません。IaC(Infrastructure as Code)は、インフラの望ましい状態をコードに書いて管理する考え方です。コードなので、Git でレビューでき、履歴が残り、別の環境にも同じものを作れます。

Terraform は、その代表的な道具の 1 つです。書くのは「どうなっていてほしいか」(宣言)で、`terraform plan` が現状との差分を示し、`terraform apply` が差分を反映します。実際の状態は「state」というファイルに記録されます。S3 のバケットを作る例です(`examples/b14/infra/main.tf`。この言語は HCL という書式です)。

```ini title="main.tf"
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "ap-northeast-1"
}

variable "bucket_name" {
  type        = string
  description = "データレイク用のバケット名 (全 AWS で一意)"
}

resource "aws_s3_bucket" "lake" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    id     = "expire-tmp"
    status = "Enabled"
    filter {
      prefix = "tmp/"
    }
    expiration {
      days = 7
    }
  }
}
```

(本書の検査が扱える言語の都合で、ブロックの言語名は `ini` にしていますが、中身は Terraform の設定ファイルです。)読み方は、`resource "種類" "名前" { ... }` が 1 つのインフラの部品です。バケット本体、公開のブロック、保存時の暗号化、`tmp/` を 7 日で消すライフサイクル規則、の 4 つを書きました。バケット名は `var.bucket_name` として外から渡し、リージョンは `provider` に書きます。アクセスキーは書いていません。認証は、実行する人やロールの側に持たせます。

この環境には Terraform を入れていないので、`apply` も `validate` も実行していません。かわりに、読むだけの形の検査を書きました。

```python
def terraform_problems(text):
    problems = []
    # 文字列とコメントを消してから、括弧の釣り合いと resource の種類を見る
    bare = re.sub(r'"[^"\n]*"', '""', re.sub(r"(?m)^\s*(#|//).*$", "", text))
    if bare.count("{") != bare.count("}"):
        problems.append("波括弧 { } の数が合わない")
    kinds = set(re.findall(r'resource\s+"(\w+)"', text))
    for need in ("aws_s3_bucket", "aws_s3_bucket_public_access_block",
                 "aws_s3_bucket_server_side_encryption_configuration"):
        if need not in kinds:
            problems.append(f"{need} が無い")
    if re.search(r"AKIA[0-9A-Z]{16}|secret_key|access_key", text):
        problems.append("アクセスキーらしい文字列がある")
    if not re.search(r"bucket\s*=\s*var\.bucket_name", text):
        problems.append("バケット名が変数になっていない")
    for flag in ("block_public_acls", "block_public_policy",
                 "ignore_public_acls", "restrict_public_buckets"):
        if not re.search(rf"{flag}\s*=\s*true", text):
            problems.append(f"{flag} が true でない")
    return problems
```

括弧の釣り合い、必須の部品、公開のブロックが全部 `true` であること、鍵が書かれていないこと、を見ます。これは文法を理解した検査ではなく、手が滑ったときの安全網です。本物は、`terraform fmt -check`・`terraform validate`・`terraform plan` で、CI で毎回流します。また、`~> 6.0` のバージョン指定は 2026年11月時点で私が選んだ値なので、使うときは AWS プロバイダの最新の文書で確かめてください。

## 費用の入口

クラウドの費用は、使った分だけかかります。最初に知っておく種類は 4 つです。

{{ table("b14-cost") }}

データエンジニアが事故を起こしやすいのは、**リクエスト**と**データ転送**です。保存の費用は容量から見積もれますが、リクエストはファイルの数と読み方で決まります。小さいファイルを 100 万個置くと、読むたびに 100 万回の GET が走ります。データ転送は、リージョンの外やインターネットへ出る方向に課金されます(料金表で確かめてください)。別リージョンの計算から大きなデータを毎日読むような構成は、気づかないうちに費用が膨らみます。処理は、データのあるリージョンで動かします。

料金の数字は、事業者・リージョン・時期で変わるので、この本には書きません。見積もるときは、各社の料金表(参考文献)を見ます。予算のアラートを最初に設定しておくと、想定外の請求に早く気づけます。ここから先の、費用を設計で下げる方法は、応用編で扱います。

## ローカルと本番の差を減らす

手元の MinIO で動いたコードが、本番の S3 で動かないのは困ります。差が出る場所を分けて、減らします。

{{ table("b14-local-prod") }}

方針は 3 つです。(1) **差は設定に閉じ込める**。接続先・認証・リージョンは環境変数にして、コードは 1 つにします(`make_client` はその形です。テストでは、環境変数の違いで接続先が切り替わることを確かめています)。(2) **コードで認証を持たない**。ローカルは固定の値、本番はロール、という違いを、boto3 の標準の探し方に任せます。(3) **差が残る部分を知っておく**。暗号化・アクセス権・キーの衝突・性能は、ローカルでは試せない、あるいは違う動きをします。テストが通ったことを、本番でも動く証拠とは見なさず、本番に近い環境(本物の S3 の小さなバケット)での確認を、デプロイの前に 1 回入れます。

## よくある失敗

- **`latest` のイメージを使う**: ある日ビルドし直したら動かなくなります。タグと依存を固定します。
- **`COPY . .` を最初に書く**: コードを直すたびに依存が全部入れ直しになります。
- **root のまま動かす・秘密を `ENV` に書く**: どちらも、事故の被害を広げます。
- **コンテナの中で `localhost` に繋ぐ**: 自分自身を指します。compose ではサービス名を使います。
- **`depends_on` だけで待つ**: 起動しただけで準備前のサービスに繋ぎ、失敗します。`healthcheck` と `service_healthy` を使います。
- **ポリシーの `Resource` を取り違える**: ListBucket はバケット、GetObject はオブジェクトです。
- **プレフィックスをフォルダだと思う**: 文字の前方一致です。`events` は `events_old` にも一致します。
- **小さいファイルを大量に作る**: 費用も、読む時間も、ファイルのサイズも増えます。
- **一覧を何度も回す**: LIST は課金される操作です。必要な接頭辞に絞り、結果を使い回します。
- **署名付き URL の期限が長すぎる**: URL を知っていれば誰でも読めます。短くします。
- **ローカルの結果を本番の保証にする**: MinIO と S3 は、キーの扱いなどが違います。

## まとめ

- クラウドは、リージョンとゾーンで場所を選び、IAM で最小権限を渡し、設定とデータは自分で守る(責任共有)。
- イメージは雛形、コンテナはその実行、レイヤはキャッシュの単位。Dockerfile は固定・順番・root なし・秘密なしで書く。
- compose は起動順を `healthcheck` で待ち、サービス名をホスト名にして、複数のコンテナをまとめる。
- オブジェクトストレージの階層は見かけで、プレフィックスは前方一致。一覧は回数が費用になる。
- データは `dt=` のフォルダに分けて置き、小さいファイルはコンパクションでまとめる。
- インフラはコードで書いて(IaC)、レビューして差分から反映する。
- 費用の入口は保存・リクエスト・データ転送。ローカルと本番の差は、設定に閉じ込めて減らす。

## 練習問題

**問1.** 行動ログを 100 行ずつ 41 ファイルで書いた場合は、1 ファイルで書いた場合より、合計サイズが何倍になりますか。また、なぜ増えるのですか。

??? note "解答例"
    197,737 / 108,832 で、約 1.8 倍です(`small_files.compare` の実測)。Parquet はファイルごとにメタデータ(列の情報や統計)を持つので、同じ行数でも、ファイルが多いほど合計が大きくなります。読む側もファイルごとにリクエストが要るので、時間と費用も増えます。

**問2.** 次の Dockerfile の問題点を、できるだけ挙げてください。`requirements.txt` には `boto3` とだけ書かれているものとします。

```text
FROM python
COPY . .
RUN pip install -r requirements.txt
ENV API_KEY=abc123
CMD python etl.py
```

??? note "解答例"
    `static_checks.dockerfile_problems` で検査すると、次の問題が出ます(テストで確かめています)。(1) `FROM python` にタグが無く、中身が日によって変わる。(2) `USER` が無く root で動く。(3) 最初の `COPY` が requirements でなく `COPY . .` なので、コードの変更で依存の層が毎回作り直しになる。(4) `pip install` に `--no-cache-dir` が無い。(5) `ENV API_KEY=abc123` で秘密をイメージに焼き込んでいる。(6) `CMD python etl.py` がシェル形式で、配列(exec 形式)でない。(7) `requirements.txt` の `boto3` がバージョン固定されていない。

**問3.** `s3:GetObject` を `Resource: "arn:aws:s3:::deb-lake"`(バケットだけ)に付けたポリシーは、なぜ意図どおり動きませんか。直し方も答えてください。

??? note "解答例"
    `GetObject` の対象はバケットではなく、中のオブジェクトだからです。`arn:aws:s3:::deb-lake/events/*` のように、オブジェクトを指す形に直します。`policy_problems` は、この取り違えを検出します(`test_policy_checker_flags_getobject_on_bucket_only`)。逆に `s3:ListBucket` の対象は、バケットの ARN です。

**問4.** キーが `events/dt=2026-01-01/p`、`events/dt=2026-01-02/p`、`events/dt=2026-01-10/p` の 3 つのとき、`Prefix="events/dt=2026-01-0"` で一覧すると何が返りますか。また、10 万個のキーを 1 回 1000 件で全部一覧すると、LIST は最低何回ですか。

??? note "解答例"
    前の 2 つ(`dt=2026-01-01` と `dt=2026-01-02`)が返ります。プレフィックスは前から文字で比べるだけなので、`dt=2026-01-1` で始まる 10 日は一致しません(`test_prefix_match_is_character_by_character` で確かめています)。LIST の回数は 100000 ÷ 1000 で、最低 100 回です。

## 参考文献

- Docker Documentation, “Building best practices”, <https://docs.docker.com/build/building/best-practices/>(2026年11月時点)
- Docker Documentation, “Understanding image layers”, <https://docs.docker.com/get-started/docker-concepts/building-images/understanding-image-layers/>
- Docker Documentation, “Build cache”, <https://docs.docker.com/build/cache/>
- Docker Documentation, “Build secrets”, <https://docs.docker.com/build/building/secrets/>
- Docker Documentation, “Control startup order in Compose”, <https://docs.docker.com/compose/how-tos/startup-order/>
- Docker Documentation, “Dockerfile reference”, <https://docs.docker.com/reference/dockerfile/>
- AWS, “Shared Responsibility Model”, <https://aws.amazon.com/compliance/shared-responsibility-model/>
- AWS, “What is IAM?”, <https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction.html>
- AWS, “Policies and permissions in Amazon S3”, <https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-policy-language-overview.html>
- AWS, “What is Amazon S3?”(データ整合性モデル), <https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html>
- AWS, “Organizing objects in the Amazon S3 console by using folders”, <https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-folders.html>
- AWS, “ListObjectsV2”, <https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html>
- AWS, “Uploading and copying objects using multipart upload”, <https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html>
- AWS, “Sharing objects with presigned URLs”, <https://docs.aws.amazon.com/AmazonS3/latest/userguide/ShareObjectPreSignedURL.html>
- AWS, “Managing the lifecycle of objects”, <https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html>
- AWS, “Setting default server-side encryption behavior for Amazon S3 buckets”, <https://docs.aws.amazon.com/AmazonS3/latest/userguide/default-bucket-encryption.html>
- AWS, “Amazon S3 pricing”, <https://aws.amazon.com/s3/pricing/>
- boto3 Documentation, “Paginators”, <https://boto3.amazonaws.com/v1/documentation/api/latest/guide/paginators.html>
- HashiCorp, “What is Terraform?”, <https://developer.hashicorp.com/terraform/intro>
- Terraform Registry, “aws_s3_bucket”, <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket>
- DuckDB Documentation, “Hive Partitioning”, <https://duckdb.org/docs/current/data/partitioning/hive_partitioning.html>

!!! tip "さらに深く"
    ストレージ・リクエスト・転送の費用を設計で下げる方法は、応用編 第10章「コスト最適化」で、小さいファイルのまとめ直しをテーブルフォーマットで安全に行う方法は、応用編 第3章「レイクハウスとテーブルフォーマット」で扱います。

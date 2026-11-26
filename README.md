# データエンジニアの本 サンプルコード

Kindle 本『データエンジニアの本』シリーズ (著者: 寝坊ロケット / Nebou Rocket) のサンプルコードです。本の本文はここにはありません。本で説明しているコードを、手元で動かして確かめるためのリポジトリです。

| 巻 | フォルダ | 内容 |
| :--- | :--- | :--- |
| 1 準備編 | `examples/s01` 〜 `examples/s08` | ターミナル、Python、SQL、データの形、つまずいたときの進み方 |
| 2 基礎編 | `examples/b01` 〜 `examples/b17` | Linux・Git、Python、SQL、トランザクション、データモデリング、取り込み、dbt、DWH、Airflow、データ品質、Docker・オブジェクトストレージ、Kafka、提供、総まとめのプロジェクト |
| 3 応用編 | `examples/a01` 〜 `examples/a12` | 分散処理と Spark、レイクハウス (Delta Lake・Iceberg)、ストリーミング設計、CDC、データ契約、可観測性、ガバナンス、コスト、ML/AI 基盤 |

フォルダの番号は、本の章の番号と同じです (`examples/b09` は基礎編 第9章)。どの章も、架空のネット通販「ねぼすけ商店」のデータ (`examples/common/neboske_shop.py`、`seed=42` で毎回同じデータ) を使います。

## 動かし方 (Docker)

Docker があれば、パソコンに Python などを直接入れなくても動きます。

```bash
git clone https://github.com/nebourocket/data-engineering-book.git
cd data-engineering-book
docker build -t de-book-dev .
alias DEV='docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-dev'

DEV python examples/s02/01_hello.py   # 1 つのファイルを動かす (本文の「DEV python ファイル名」)
DEV pytest                            # 全部の章のテストを動かす (サービスが要るテストは飛ばされます)
```

### サービスを使う章

PostgreSQL・MinIO・Redpanda などを使う章 (基礎編 第7・9・14・15 章など) は、`compose.yaml` でサービスを起動してから動かします。

```bash
docker compose up -d --wait
docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD":/w -w /w de-book-dev pytest
docker compose down
```

## Advanced examples (応用編のコード)

応用編 (`examples/a01` 〜 `a12`) は Spark (Java 17 以上)、Delta Lake、Apache Iceberg を使うので、別の Docker イメージで動かします。

```bash
docker build -f Dockerfile.advanced -t de-book-advanced .
alias ADV='docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/w -w /w de-book-advanced'
ADV pytest -q examples/a01 examples/a02 examples/a03   # Spark・レイクハウスの章 (サービスは要りません)
ADV python examples/a01/demo.py                         # 各章にデモと run.sh があります
```

応用編の第4・5・9 章は、上の「サービスを使う章」と同じく `compose.yaml` のサービスを使います。

## Docker を使わずに動かす

Python 3.12 の仮想環境に、必要なパッケージを入れます。基礎編のシェルの章 (第3章) は bash・git・jq を、図を描くコードは日本語フォント (Noto CJK など) を使います。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt                 # 準備編・基礎編
pip install -r requirements-advanced.txt        # 応用編も動かすとき (Java 17 以上も要ります)
pytest
```

OS やツールの版の違いで、画面の出力を本と照らすテストがいくつか合わないことがあります (ファイルの権限・ツールの版・時刻の表示など)。本と同じ結果を確かめたいときは Docker で動かしてください。

## フォルダの中身

```text
examples/         章ごとのコードとテスト (sNN = 準備編、bNN = 基礎編、aNN = 応用編)
examples/common/  どの章も使う「ねぼすけ商店」のデータを作るコード
examples/figures/ 本の図を描くコード (matplotlib)
data/tables/      コードが作る表の CSV。テストが、コードの結果と同じかを確かめます
tests/            共通のテスト
compose.yaml      PostgreSQL・MinIO・Redpanda などのサービス
```

## 誤りの報告・質問

本やコードの誤り、質問は [Issues](https://github.com/nebourocket/data-engineering-book/issues) へお寄せください。

## ライセンス

`examples/` のコードは、学習やご自身のプロジェクトに自由に使ってかまいません。本の本文と図の著作権は著者にあります。

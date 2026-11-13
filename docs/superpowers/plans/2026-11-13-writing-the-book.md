# 本文の執筆 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基礎編16章 (公開) と応用編12章 (非公開リポジトリ → KV) を書き上げ、コード例・表・図・出典まで検証済みの状態にし、Payment Link を本番に差し替えるだけで販売できるようにする。

**Architecture:** 執筆の土台 (共通データ・サービス・章の検査・図の生成) を先に作り、その上で2章ずつ書く。各章は「書く → 事実チェック → 差分レビュー → 直す → PR でマージ」。応用編は非公開リポジトリで同じ流れを取り、最後に KV へ入れる。

**Tech Stack:** Python 3.12 / DuckDB / PyArrow / matplotlib / dbt-duckdb / psycopg / boto3 (MinIO) / confluent-kafka (Redpanda) / Apache Airflow (CI の別ジョブ) / PySpark・deltalake・pyiceberg (応用編)

**Spec:** `docs/superpowers/specs/2026-11-11-book-design.md`

## Global Constraints

- 本文は平易な日本語の「です・ます」。仕組み → 具体例 → 手を動かす、の順。`/mnt/c/knowledge/my-plugin/skills/writing-conventions/SKILL.md` と `de-ai-write/SKILL.md` に従う (AI 臭い言い回し・煽り・作り話の体験を書かない)。
- 章の型 (見出し名を固定): `## この章でできるようになること` / 本文の節 / `## よくある失敗` / `## まとめ` / `## 練習問題` / `## 参考文献`。練習問題は3問以上、`??? note "解答例"` で答えを付ける。
- 長さ (2026-11-13 ユーザー指定「有益かつ長めに」): コードと表を除いた本文で、基礎編 7,000〜14,000 字 (目標 9,000〜11,000)、応用編 10,000〜20,000 字 (目標 13,000〜16,000)。水増しはしない: 長さは「現場で迷う判断」「なぜそうするか」「失敗例と直し方」「手を動かす演習」で稼ぐ。
- 応用編は買ってよかったと思える中身にする: 各章に「設計の判断表 (CSV)」「本番のチェックリスト」「ケーススタディ (ねぼすけ商店が大きくなった想定で、問題 → 調査 → 対策 → 結果の数字はコードで出す)」「練習問題5問以上」を入れる。
- 基礎編の各章末に、関係する応用編の章を1行で案内する (売り込みの言葉は使わず「さらに深く: 応用編 第N章 …」)。
- 表は手で打たない。`data/tables/<bNN|aNN>-<名前>.csv` と `{{ table("名前") }}`。本文に `|---` の Markdown 表を書かない。
- 図: 構成や流れは Mermaid。数値のグラフは `examples/figures/<章>_<名前>.py` (matplotlib、SVG を `book/assets/figures/` に出力) で作り、手で数字を打たない。
- 本文のコード (```python ```sql ```bash ```yaml ```toml ```dockerfile ```ini) はすべて `examples/<bNN>/` に同じ内容で置き、pytest で動かす。出力例は ```text。設定ファイルは「読み込めること」をテストする。
- 数字・仕様の主張には出典 (公式ドキュメント・RFC・論文・書籍)。料金・性能など変わりやすい値は「(2026年11月時点)」を付ける。手元の本 (`/mnt/c/knowledge/books/INDEX.md`) を先に見る: Fundamentals of Data Engineering・Kafka The Definitive Guide・Learning Spark ほか。
- 共通の題材は架空の通販「ねぼすけ商店」。データは `examples/common/neboske_shop.py` の `generate(seed=42)` で毎回同じものを作る。実在の会社・人物の事例を作り話で書かない。
- 応用編の本文は公開リポジトリに入れない。応用編の章ファイルは H1 を書かず `##` から始める (公開側の紹介ページに H1 があるため)。
- 名義は寝坊ロケット。コミットに AI の帰属表示を入れない。Python は Docker (`de-book-dev`) で動かす。

## Review Focus

1. 本文のコードと `examples/` の中身がずれる → `tests/test_chapters.py` の「本文のコードが examples にある」検査で止める (Task 0)。
2. サービスが無い環境でテストが黙ってスキップされ、CI が緑になる → CI では `DE_BOOK_REQUIRE_SERVICES=1` でスキップを失敗にする (Task 0)。
3. 出典の URL が古い・存在しない → 事実チェックで URL を開いて確かめる (各執筆タスク)。
4. 章どうしで用語や表記が揺れる (例: 「冪等」と「べき等」) → `data/glossary.csv` を正とし、検査で旧表記を止める (Task 0)。
5. 応用編の文が公開側に混ざる → 応用編タスクの後に `check_no_paid_text.py` を回す (Task 11)。

---

### Task 0: 執筆の土台 (公開リポジトリ)

**Files:** `requirements.txt`, `Dockerfile` (git と bash を入れる), `compose.yaml` (postgres:16, minio, redpanda), `examples/common/neboske_shop.py`, `examples/conftest.py`, `hooks/figures.py`, `tests/test_chapters.py`, `data/glossary.csv`, `book/basics/01-…`〜`16-…md` (執筆中の仮ページ), `mkdocs.yml` (nav と hooks), `.github/workflows/pages.yml`, `docs/CHAPTER_GUIDE.md`, `.gitignore` (`book/assets/figures/`)

**Interfaces:**
- 章のファイル名 (固定): `01-what-is-data-engineering` `02-data-and-computers` `03-linux-shell-git` `04-python` `05-sql-basics` `06-sql-advanced` `07-rdb-transactions` `08-data-modeling` `09-ingestion` `10-etl-elt-dbt` `11-data-warehouse` `12-orchestration` `13-data-quality` `14-cloud-docker-storage` `15-streaming-intro` `16-project-and-career`
- 仮ページは front matter `status: draft`。検査は draft 以外に章の型・長さ・表・コードの一致を求める。`tests/test_chapters.py::test_no_drafts_left` は `DE_BOOK_FINAL=1` のときだけ draft が残っていると失敗。
- `neboske_shop.generate(seed=42) -> dict[str, list[dict]]` (customers・products・orders・order_items・events)。`write_duckdb(path)` と `write_parquet(dir)` も用意。
- `examples/conftest.py`: フィクスチャ `pg_dsn` `s3_client` `kafka_bootstrap`。環境変数 (`PG_DSN` `S3_ENDPOINT` `KAFKA_BOOTSTRAP`) が無ければ skip、`DE_BOOK_REQUIRE_SERVICES=1` なら fail。
- `hooks/figures.py`: `on_pre_build` で `examples/figures/*.py` をすべて実行する。
- 本文のコードの一致: 章 `bNN` の各コードブロックを空白を正規化して、`examples/bNN/` 以下のどれかのファイルに含まれることを確かめる。
- 表記の検査: `data/glossary.csv` (列 `正` `誤`) の「誤」が本文にあれば失敗。
- CI: build ジョブに services (postgres・minio・redpanda) と環境変数、`DE_BOOK_REQUIRE_SERVICES=1`。別ジョブ `airflow` で `apache-airflow==2.10.5` を constraints 付きで入れ、`examples/b12/` の DAG を `DagBag` で読み込んでエラー0を確かめる。

- [ ] テストを先に書く (章の型・長さ (基礎 7,000〜14,000 字・応用 10,000〜20,000 字)・表・コードの一致・表記・draft) → 失敗を確かめる → 実装 → `DEV pytest` と `mkdocs build --strict` が通る → `docker compose up -d` してサービス付きでテストが通る → PR でマージ

### Task 1〜8: 基礎編 (2章ずつ)

| Task | 章 |
| :--- | :--- |
| 1 | 01, 02 |
| 2 | 03, 04 |
| 3 | 05, 06 |
| 4 | 07, 08 |
| 5 | 09, 10 |
| 6 | 11, 12 |
| 7 | 13, 14 |
| 8 | 15, 16 |

各章でやること (章の中身は仕様書 4 章の「できるようになること」と下の要点):

- 01 役割・ライフサイクル (生成 → 取り込み → 保存 → 変換 → 提供)・他職種との違い・この本の地図
- 02 メモリ階層と遅延の桁・行指向と列指向・CSV/JSON/Parquet を同じデータで比べる (サイズと読み込み時間は図をコードで作る)
- 03 シェルの基本とパイプ・権限・cron・Git のブランチと PR の流れ
- 04 型ヒント・例外・logging・小さな ETL スクリプトと pytest
- 05 SELECT〜JOIN〜GROUP BY を DuckDB とねぼすけ商店で
- 06 ウィンドウ関数・CTE・EXPLAIN の読み方
- 07 正規化・ACID・分離レベルを PostgreSQL で再現 (2つの接続で異常を起こして見る)
- 08 スタースキーマ・粒度・SCD タイプ1/2 を DuckDB で
- 09 API (テスト内の http.server)・ファイル・DB からの差分取り込み、ウォーターマーク、CDC の考え方
- 10 ETL と ELT、dbt-duckdb でモデル・テスト・ドキュメント
- 11 列指向 DWH・パーティションとプルーニング・コストの考え方
- 12 DAG・冪等・再実行・バックフィル、Airflow の DAG (CI で読み込み確認)
- 13 品質の観点 (鮮度・量・スキーマ・分布・一意性)・SQL と dbt のテスト
- 14 Docker と compose・オブジェクトストレージ (MinIO)・IaC の考え方
- 15 ログ・トピック・パーティション・オフセット・コンシューマーグループを Redpanda で
- 16 取り込み → dbt → 品質 → 可視化の通しの演習・ポートフォリオ・学び続け方

- [ ] 書く: 実装役が章・CSV・examples・テストを作り、`DEV pytest` (サービス付き)・`mkdocs build --strict` を通してコミット
- [ ] 事実チェック: 調べ役が章の主張と出典を一次情報で確かめ、問題を一覧で返す
- [ ] レビュー: レビュー役が差分を章の型・正しさ・コード・文体で見る
- [ ] 直す (指摘があれば) → 再チェック
- [ ] PR でマージ (サイトに反映)

### Task 9: 応用編の土台 (非公開リポジトリ)

**Files (pro):** `Dockerfile` (de-book-dev + `default-jre-headless` + `pyspark==3.5.3` `deltalake` `pyiceberg[sql-sqlite]` `duckdb`)、`examples/`、`tests/test_chapters.py` (公開側と同じ検査 + H1 禁止、公開側の検査コードを import して使う)、`chapters/` の 01〜12 を draft で用意。

- [ ] テスト → 実装 → 通る → コミット・push

### Task 10: 応用編 (2章ずつ、6回)

| 回 | 章 | 要点 |
| :--- | :--- | :--- |
| 10a | 01, 02 | Spark の実行計画・シャッフル・AQE、偏り・小さいファイル・メモリ (PySpark ローカル) |
| 10b | 03, 04 | Delta / Iceberg のスナップショット・スキーマ進化・タイムトラベル (deltalake・pyiceberg)、イベント時刻・ウォーターマーク・状態・exactly-once (Structured Streaming の rate ソース) |
| 10c | 05, 06 | CDC と outbox (PostgreSQL で outbox、Debezium の設定は形の検査)、Data Vault・ワイドテーブル・セマンティックレイヤー |
| 10d | 07, 08 | データ契約 (JSON Schema で CI 判定)・スキーマ進化の互換性、SLO・鮮度/量の監視・OpenLineage の考え方 |
| 10e | 09, 10 | 権限・行列のマスキング・監査・個人情報保護法の要点 (法令は条文と個人情報保護委員会の資料を出典に)、費用の分解と削り方 |
| 10f | 11, 12 | 特徴量ストア・ベクトル検索・RAG のデータパイプライン (DuckDB の配列で類似検索)、Data Mesh・プラットフォームチーム・設計レビュー |

各回: 書く → 事実チェック → レビュー → 直す → pro に push。

### Task 11: 仕上げ

- [ ] `build_kv.py` → KV に12章を入れる、`check_no_paid_text.py` で漏れなし
- [ ] `DE_BOOK_FINAL=1` で draft が残っていないこと
- [ ] 本全体のレビュー (最も強いモデル): 章のつながり・難易度の階段・用語の揺れ・前の章で教えていない前提
- [ ] はじめに・基礎編/応用編の目次・README を本文に合わせて更新
- [ ] サンドボックスで通し確認 (購入 → 12章すべて読める)
- [ ] 本番への切り替え手順 (`docs/DEPLOY.md`) を、ユーザーがやる Payment Link・制限付きキー・署名鍵の作り直しだけが残る形に直す

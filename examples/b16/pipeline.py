"""ねぼすけ商店の日次売上ダッシュボードを、取り込みから図まで 1 本で通します。

  取り込み (ingest.land) → raw (ingest.load_raw) → dbt build (第10章のプロジェクト) → 品質チェック (checks + 第13章の gate) → 図 (dashboard)

どこかで失敗したら、そこで止まります (後ろの工程は動きません)。同じ dt で何度実行しても同じ結果です。
  python examples/b16/pipeline.py --dt 2026-07-01 --workdir work/b16 [--bucket neboske-lake]
S3_ENDPOINT (と S3_ACCESS_KEY / S3_SECRET_KEY) が設定されていれば MinIO に、無ければ workdir の中に置きます。
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from examples.b16 import checks, dashboard, ingest  # noqa: E402
from examples.b16.checks import dq  # noqa: E402
from examples.b16.store import LocalS3  # noqa: E402

DBT_PROJECT = Path(__file__).resolve().parents[1] / "b10"  # 第10章の dbt プロジェクトを、そのまま使う


def dbt_build(workdir, db_path):
    """第10章の dbt プロジェクトを workdir にコピーして build します (target と logs をリポジトリに残さないため)。
    既知の問題 (tag:known_issue のテスト) は、第10章のテストと同じく除きます。"""
    project = Path(workdir) / "dbt"
    shutil.rmtree(project, ignore_errors=True)
    shutil.copytree(DBT_PROJECT, project, ignore=shutil.ignore_patterns(
        "test_*.py", "__pycache__", "exercises", "ci-example.yml", "usage*.sh", "target", "logs", "*.duckdb"))
    env = {**os.environ, "DBT_DUCKDB_PATH": str(db_path), "DBT_SEND_ANONYMOUS_USAGE_STATS": "False"}
    try:
        result = subprocess.run(
            ["dbt", "build", "--full-refresh", "--exclude", "tag:known_issue", "--project-dir", str(project),
             "--profiles-dir", str(project), "--no-use-colors"], capture_output=True, text=True, env=env)
    except FileNotFoundError:
        raise RuntimeError("dbt コマンドが見つかりません (pip install dbt-duckdb か、開発用イメージで動かしてください)")
    if result.returncode != 0:
        raise RuntimeError("dbt build が失敗しました:\n" + result.stdout[-2000:] + result.stderr[-1000:])


def run(s3, bucket, dt, workdir):
    """全工程を実行して、図のパスを返します。"""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    db_path = workdir / "warehouse.duckdb"
    ingest.land(s3, bucket, dt)
    con = duckdb.connect(str(db_path))
    try:
        print("raw に読み込み:", ingest.load_raw(con, s3, bucket, dt))
    finally:
        con.close()  # dbt が同じファイルを開くので、いったん閉じる (DuckDB は同時に 1 つのプロセスしか書けない)
    dbt_build(workdir, db_path)
    con = duckdb.connect(str(db_path))
    try:
        if con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'dq_results'").fetchall()[0][0]:
            con.execute("DELETE FROM dq_results WHERE run_id = ?", [dt])  # 同じ日を再実行しても、結果は 1 組だけにする
        try:
            dq.gate(con, checks.sales_checks(), dt)  # warn の不合格は [WARN] と表示され、error の不合格は QualityError で止まる
        finally:
            for name, severity, passed in con.execute(
                    "SELECT check_name, severity, passed FROM dq_results WHERE run_id = ? ORDER BY rowid", [dt]).fetchall():
                print(f"  {'OK  ' if passed else severity.upper():5} {name}")
        figure = workdir / f"dashboard_{dt}.svg"
        dashboard.draw(con, dt, figure)
    finally:
        con.close()
    return figure


def make_client(workdir, bucket):
    """MinIO (S3_ENDPOINT があるとき) か、手元のフォルダ (LocalS3) のクライアントを返します。バケットが無ければ作ります。"""
    if not os.environ.get("S3_ENDPOINT"):
        client = LocalS3(Path(workdir) / "landing")
        client.create_bucket(Bucket=bucket)
        return client
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client(
        "s3", endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "minioadmin"), region_name="us-east-1")
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("404", "NoSuchBucket"):
            raise  # 権限が無い、などの別の失敗は、バケットが無いことにしない
        client.create_bucket(Bucket=bucket)
    return client


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dt", required=True, help="取り込み日 (YYYY-MM-DD)")
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--bucket", default="neboske-lake")
    args = parser.parse_args()
    print("図:", run(make_client(args.workdir, args.bucket), args.bucket, args.dt, args.workdir))

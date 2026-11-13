"""ねぼすけ商店の日次売上ダッシュボードを、取り込みから図まで 1 本で通します。

  取り込み (ingest.land) → raw (ingest.load_raw) → dbt build → 品質チェック (quality) → 図 (dashboard)

どこかで失敗したら、そこで止まります (後ろの工程は動きません)。同じ run_dt で何度実行しても同じ結果です。
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
from examples.b16 import dashboard, ingest, quality  # noqa: E402
from examples.b16.store import DirStore, S3Store  # noqa: E402

HERE = Path(__file__).resolve().parent


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


def make_store(workdir, bucket):
    if os.environ.get("S3_ENDPOINT"):
        import boto3

        client = boto3.client(
            "s3", endpoint_url=os.environ["S3_ENDPOINT"],
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "minioadmin"), region_name="us-east-1")
        return S3Store(client, bucket)
    return DirStore(Path(workdir) / "landing")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dt", required=True, help="取り込み日 (YYYY-MM-DD)")
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--bucket", default="neboske-lake")
    args = parser.parse_args()
    print("図:", run(make_store(args.workdir, args.bucket), args.dt, args.workdir))

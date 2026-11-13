"""CSV を読み、検証し、正しい行を Parquet に、悪い行を reject の CSV に書きます。"""
import csv
import logging
from dataclasses import dataclass, fields
from itertools import batched
from pathlib import Path

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.config import Config

from .config import Settings
from .models import Order, ValidationError
from .reader import EXPECTED_COLUMNS, iter_rows
from .validate import parse_order

logger = logging.getLogger(__name__)

SCHEMA = pa.schema([
    ("order_id", pa.int64()),
    ("customer_id", pa.int64()),
    ("ordered_at", pa.timestamp("ms", tz="UTC")),  # Parquet に秒単位は無いのでミリ秒
    ("status", pa.string()),
    ("item_count", pa.int32()),
    ("total_amount", pa.int64()),
])


@dataclass(frozen=True)
class Result:
    read: int
    written: int
    rejected: int
    parquet_path: Path
    rejects_path: Path

    @property
    def reject_ratio(self) -> float:
        return self.rejected / self.read if self.read else 0.0


class TooManyRejects(Exception):
    """除外の割合が上限を超えた。Parquet は公開せず、除外の CSV だけを残す。"""

    def __init__(self, result: Result, limit: float) -> None:
        super().__init__(f"除外が多すぎます: {result.reject_ratio:.2%} (上限 {limit:.2%})")
        self.result = result


def _to_table(orders: list[Order]) -> pa.Table:
    columns = {f.name: [getattr(o, f.name) for o in orders] for f in fields(Order)}
    return pa.table(columns, schema=SCHEMA)


def run(settings: Settings) -> Result:
    """変換を 1 回実行します。同じ入力なら何度動かしても同じ出力になります。"""
    stem = settings.input_path.stem
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = settings.output_dir / f"{stem}.parquet"
    rejects_path = settings.output_dir / f"{stem}.rejects.csv"
    tmp_parquet = parquet_path.with_suffix(".parquet.tmp")
    tmp_rejects = rejects_path.with_suffix(".csv.tmp")
    read = written = rejected = 0
    logger.info("開始: %s (バッチ %d 行)", settings.input_path, settings.batch_size)

    try:
        with (pq.ParquetWriter(tmp_parquet, SCHEMA) as writer,
              tmp_rejects.open("w", encoding="utf-8", newline="") as rej_file):
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
        result = Result(read, written, rejected, parquet_path, rejects_path)
        tmp_rejects.replace(rejects_path)  # 除外の記録は、失敗の原因調査のために必ず残す
        logger.info("完了: 読み込み %d 行、書き込み %d 行、除外 %d 行", read, written, rejected)
        if result.reject_ratio > settings.max_reject_ratio:
            raise TooManyRejects(result, settings.max_reject_ratio)
        tmp_parquet.replace(parquet_path)  # 上限以内のときだけ、本番の名前にする
    finally:
        tmp_parquet.unlink(missing_ok=True)
        tmp_rejects.unlink(missing_ok=True)
    return result


def upload(settings: Settings, path: Path) -> None:
    """S3 互換のストレージに置きます。再試行は boto3 に任せます（自前の再試行を重ねない）。"""
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
        config=Config(retries={"mode": "standard", "max_attempts": 5}),
    )
    client.upload_file(str(path), settings.s3_bucket, f"orders/{path.name}")
    logger.info("アップロード: s3://%s/orders/%s", settings.s3_bucket, path.name)

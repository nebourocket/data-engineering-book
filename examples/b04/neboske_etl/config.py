"""設定は環境変数から読みます。秘密は repr（ログ・例外の表示）に出しません。"""
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


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

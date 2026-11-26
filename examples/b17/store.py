"""手元のフォルダで動く、S3 のごく小さな代用品。

第9章の landing_files.py は、boto3 の S3 クライアント (put_object・get_object・get_paginator) を受け取って動きます。
LocalS3 は、その呼び出しだけを手元のフォルダで受け止めます。サービスが無い環境 (図のビルドなど) で、
同じパイプラインを動かすために使います。MinIO に置く場合は、本物の boto3 のクライアントを渡します。
"""
import io
from pathlib import Path


class LocalS3:
    def __init__(self, root):
        self.root = Path(root)

    def head_bucket(self, Bucket):
        return {}

    def create_bucket(self, Bucket):
        (self.root / Bucket).mkdir(parents=True, exist_ok=True)

    def put_object(self, Bucket, Key, Body):
        path = self.root / Bucket / Key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Body)

    def get_object(self, Bucket, Key):
        data = (self.root / Bucket / Key).read_bytes()
        return {"Body": io.BytesIO(data)}

    def delete_object(self, Bucket, Key):
        (self.root / Bucket / Key).unlink(missing_ok=True)

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix=""):
        base = self.root / Bucket
        keys = sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())
        yield {"Contents": [{"Key": k} for k in keys if k.startswith(Prefix)]}

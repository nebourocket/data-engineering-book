"""landing (取り込んだ生ファイルの置き場) の 2 つの実装。同じ 3 つの操作 (put・get・exists) を持ちます。

S3Store は MinIO / S3 に、DirStore は手元のフォルダに置きます。パイプラインはどちらでも同じように動くので、
サービスが無い環境 (図のビルドなど) では DirStore を使います。
"""
from pathlib import Path


class DirStore:
    def __init__(self, root):
        self.root = Path(root)

    def put(self, key, data):
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key):
        return (self.root / key).read_bytes()

    def exists(self, key):
        return (self.root / key).is_file()


class S3Store:
    def __init__(self, client, bucket):
        self.client, self.bucket = client, bucket
        try:
            client.head_bucket(Bucket=bucket)
        except Exception:  # 無ければ作る (学習用の MinIO 向け。本番のバケットはコードで作らず、インフラ側で用意する)
            client.create_bucket(Bucket=bucket)

    def put(self, key, data):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key):
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except self.client.exceptions.ClientError:
            return False
        return True

"""同じ仕事を「温まったプロセス」「新しいプロセス」「新しいコンテナ」で動かし、始まるまでの時間を比べます。"""
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

JOB = "import pyarrow.parquet as pq, sys; print(pq.read_table(sys.argv[1]).num_rows)"


def count_rows(path):
    return pq.read_table(path).num_rows


def warm_ms(path, repeat=20):
    """すでに動いているプロセスの中で、関数を呼ぶ時間 (1 回あたりの平均, ミリ秒)。"""
    count_rows(path)  # 1 回目は読み込みの準備に使う
    start = time.perf_counter()
    for _ in range(repeat):
        count_rows(path)
    return (time.perf_counter() - start) / repeat * 1000


def new_process_ms(path):
    """Python を起動し直して、ライブラリを読み込んでから同じ仕事をする時間。"""
    start = time.perf_counter()
    subprocess.run([sys.executable, "-c", JOB, str(path)], check=True, capture_output=True)
    return (time.perf_counter() - start) * 1000


def new_container_ms(path, image="de-book-dev"):
    """コンテナを起動して同じ仕事をする時間。docker か画像が無ければ None。"""
    if not shutil.which("docker"):
        return None
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode:
        return None
    start = time.perf_counter()
    done = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{path.parent}:/data:ro", image,
         "python", "-c", JOB, f"/data/{path.name}"], capture_output=True)
    if done.returncode:
        return None
    return (time.perf_counter() - start) * 1000


def main():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.parquet"
        pq.write_table(pa.table({"n": list(range(1000))}), path)
        print(f"温まったプロセス : {warm_ms(path):8.1f} ms")
        print(f"新しいプロセス   : {new_process_ms(path):8.1f} ms")
        container = new_container_ms(path)
        print("新しいコンテナ   : " + ("(docker なし)" if container is None else f"{container:8.1f} ms"))


if __name__ == "__main__":
    main()

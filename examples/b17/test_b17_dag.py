"""第17章の DAG (neboske_pipeline_dag.py) の形の確認。Airflow が入っていない環境では飛ばします。"""
from pathlib import Path

import pytest


def test_airflow_dag_shape():
    """Airflow が入っている環境でだけ: DAG が読み込め、取り込み → dbt → 品質チェックの順で、失敗の通知がある。"""
    pytest.importorskip("airflow")
    from airflow.dag_processing.dagbag import DagBag

    bag = DagBag(dag_folder=str(Path(__file__).parent))
    assert not bag.import_errors, bag.import_errors
    dag = bag.dags["neboske_pipeline"]
    assert sorted(dag.task_dict) == ["dbt_build", "ingest_raw", "quality_checks"]
    assert dag.task_dict["dbt_build"].upstream_task_ids == {"ingest_raw"}
    assert dag.task_dict["quality_checks"].upstream_task_ids == {"dbt_build"}
    assert dag.task_dict["ingest_raw"].retries == 2
    assert dag.catchup is False
    assert dag.default_args["on_failure_callback"].__name__ == "notify_failure"

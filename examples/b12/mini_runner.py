"""第 12 章: 依存関係の図（DAG）の考え方を、標準ライブラリだけで再現した小さな実行器。

使い方: python examples/b12/mini_runner.py
タスクは「名前 → 関数」、依存は「名前 → 先に成功しているべきタスクの集合」で渡します。
"""
from graphlib import TopologicalSorter
from typing import Callable


def run(tasks: dict[str, Callable[[], None]], deps: dict[str, set[str]]) -> dict[str, str]:
    """依存の順にタスクを動かし、{名前: 状態} を返します。

    状態は success / failed / upstream_failed のどれかです。
    先のタスクが成功していなければ動かさず（upstream_failed）、関係のない枝は動かし続けます。
    輪になった依存（A→B→A）は graphlib.CycleError になります。
    """
    graph = {name: deps.get(name, set()) for name in tasks}
    state: dict[str, str] = {}
    for name in TopologicalSorter(graph).static_order():
        if any(state[d] != "success" for d in graph[name]):
            state[name] = "upstream_failed"
            continue
        try:
            tasks[name]()
            state[name] = "success"
        except Exception as exc:
            print(f"{name} が失敗しました: {exc}")
            state[name] = "failed"
    return state


if __name__ == "__main__":
    def ok() -> None:
        pass

    def broken() -> None:
        raise RuntimeError("品質チェックに失敗")

    tasks = {"extract": ok, "clean": ok, "aggregate": ok, "quality_check": broken, "publish": ok, "notify": ok}
    deps = {"clean": {"extract"}, "aggregate": {"clean"}, "quality_check": {"clean"},
            "publish": {"aggregate", "quality_check"}, "notify": {"aggregate"}}
    for name, status in run(tasks, deps).items():
        print(f"{name:<14}{status}")

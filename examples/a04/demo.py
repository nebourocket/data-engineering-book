"""第4章の出力を順に表示します: KAFKA_BOOTSTRAP=localhost:19092 python examples/a04/demo.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import kafka_flow  # noqa: E402
import schema_change  # noqa: E402
import stream_sim as sim  # noqa: E402


def emit(key, value):
    """本文に差し込む行には、先頭に [キー] を付けます。"""
    print(f"[{key}] {value}")


def main():
    for model in sim.MODELS:
        emit("delay", f"{model}: {sim.delay_stats(sim.make_events(model))}")
    for row in sim.walkthrough():
        emit("walk", row)
    emit("windows", f"タンブリング: {sim.tumbling_start(125, 60)}  スライディング: {sim.sliding_starts(125, 60, 20)}"
         f"  セッション: {sim.sessionize([0, 10, 50, 400, 410], 60)}")
    events = sim.make_events("mixed")
    clean = sim.run_with_crash(events, 60, 10**9, 1000, idempotent=True)
    appended = sim.run_with_crash(events, 60, 2999, 1000, idempotent=False)
    upserted = sim.run_with_crash(events, 60, 2999, 1000, idempotent=True)
    emit("crash", f"落ちなかった場合の行数 {len(clean)}  追記だけの出力先 {len(appended)} 行 (重複を除くと {len(set(appended))})"
         f"  キーで上書きする出力先 {len(upserted)} 行 (落ちなかった場合と同じ: {upserted == clean})")
    for key, value in sim.crash_sweep(events).items():
        emit("sweep", f"{key}: {value}")
    for name, r in sim.three_tiers(events).items():
        emit("tiers", f"{name}: 誤差の中央値 {100 * r['rel_err_median']:.1f}% p95 {100 * r['rel_err_p95']:.0f}%"
             f" 合計の取りこぼし {r['missing_total_pct']:.2f}%")
    from spark_walk import run as spark_run  # PySpark が要るので、使うときだけ読み込みます
    for batch_id, rows in spark_run():
        emit("spark", f"バッチ {batch_id}: 出力 {rows}")
    for lateness in (10, 60, 300):
        r = sim.evaluate(events, lateness)
        emit("modes", f"ウォーターマーク {lateness} 秒: 追加モードの出力 {r['output_rows']} 行,"
             f" 更新モードの出力 {sim.update_rows(events, lateness)} 行, 状態の最大 {r['peak_state']} 件")
    for n_events in (6000, 60000):
        big = sim.make_events("mixed", n=n_events)
        for n_keys in (5, 500, 5000):
            emit("state", f"1 時間 {n_events} 件・キー {n_keys} 種類: ウォーターマーク 60 秒で {sim.peak_state_with_keys(big, 60, n_keys)} 件,"
                 f" 600 秒で {sim.peak_state_with_keys(big, 600, n_keys)} 件")
    emit("backlog", f"入る 120 件/秒・処理 100 件/秒を 10 分: 滞留 {sim.backlog_after(120, 100, 600)} 件,"
         f" 入る 80 件/秒に戻したあとの解消 {sim.seconds_to_drain(12000, 80, 100)} 秒,"
         f" 入る 100 件/秒のままなら {sim.seconds_to_drain(12000, 100, 100)}")
    messages = schema_change.make_messages()
    emit("schema", f"厳密な読み手の失敗 {schema_change.count_failures(messages, schema_change.read_strict)} 件,"
         f" 無視する読み手の失敗 {schema_change.count_failures(messages, schema_change.read_tolerant)} 件")
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP")
    if bootstrap:
        small = sim.make_events("mixed", n=300)
        topic = kafka_flow.new_topic(bootstrap)
        kafka_flow.produce_events(bootstrap, topic, small)
        emit("kafka", f"送った 300 件を読み戻すと同じ: {kafka_flow.read_events(bootstrap, topic, 300, 'g-read') == small}")
        emit("kafka", f"末尾・コミット済み・ラグ: {kafka_flow.consumer_lag(bootstrap, topic, 'g-lag', 120)}")
        tx_topic = kafka_flow.new_topic(bootstrap)
        emit("kafka", f"トランザクション (読み方別の件数): {kafka_flow.transaction_demo(bootstrap, tx_topic)}")
        kafka_flow.delete_topic(bootstrap, topic)
        kafka_flow.delete_topic(bootstrap, tx_topic)


if __name__ == "__main__":
    main()

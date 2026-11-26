"""単価を変えても結論が変わらないか: ケーススタディの測定値に、単価の倍率を掛けて合計を比べます。"""
from costlab_model import Rates, monthly_cost

GB = 1e9


def sensitivity_rows(result, scale=1000):
    """result は costlab_case.before_after の戻り値。(保存単価の倍率, スキャン単価の倍率) ごとに前後の合計を返します。"""
    rows = []
    for storage_x, scan_x in ((1, 1), (10, 1), (1, 0.2), (10, 0.2), (50, 0.2)):
        rates = Rates(storage_per_gb_month=0.02 * storage_x, scan_per_tb=5.0 * scan_x)
        total = {}
        for name in ("before", "after"):
            r = result[name]
            total[name] = monthly_cost(rates, storage_gb=r["stored"] * scale / GB, scan_tb=r["scan_tb"],
                                       egress_gb=0, requests=0, compute_hours=0)["total"]
        rows.append([f"{storage_x}", f"{scan_x}", f"{total['before']:.2f}", f"{total['after']:.2f}",
                     "変更後が安い" if total["after"] < total["before"] else "変更前が安い"])
    return rows

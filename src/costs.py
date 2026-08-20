"""
Учет расходов и себестоимости по принципу начисления (Урок 6 курса).
- Себестоимость товаров (COGS)
- Прямые операционные расходы (доставка, эквайринг, упаковка)
- Маркетинговые расходы и стоимость привлечения (CAC)
"""

import pandas as pd
from typing import Dict, Any


def calculate_costs_breakdown(df: pd.DataFrame, period_summary: pd.DataFrame) -> Dict[str, Any]:
    """
    Рассчитывает структуру затрат по когортам и периодам.
    """
    total_net_revenue = df["net_revenue"].sum()
    total_cogs = df["cogs"].sum()
    total_delivery = df["delivery_cost"].sum()
    # Эквайринг и транзакционные издержки (обычно ~2.5% от выручки)
    total_payment_fee = round(total_net_revenue * 0.025, 2)
    # Затраты на маркетинг / привлечение
    total_marketing_cac = df["acquisition_cost"].sum()

    initial_clients = period_summary.loc[period_summary["period"] == 0, "active_clients"].values[0] if not period_summary.empty else 1

    # Удельные затраты на одного привлеченного клиента (на единицу базы)
    cac_per_client = round(total_marketing_cac / initial_clients, 2) if initial_clients > 0 else 0.0
    cogs_per_client = round(total_cogs / initial_clients, 2) if initial_clients > 0 else 0.0
    delivery_per_client = round(total_delivery / initial_clients, 2) if initial_clients > 0 else 0.0
    payment_fee_per_client = round(total_payment_fee / initial_clients, 2) if initial_clients > 0 else 0.0

    cogs_pct = round((total_cogs / total_net_revenue) * 100, 2) if total_net_revenue > 0 else 0.0
    direct_ops_pct = round(((total_delivery + total_payment_fee) / total_net_revenue) * 100, 2) if total_net_revenue > 0 else 0.0

    return {
        "total_cogs": total_cogs,
        "total_delivery": total_delivery,
        "total_payment_fee": total_payment_fee,
        "total_marketing_cac": total_marketing_cac,
        "cac_per_client": cac_per_client,
        "cogs_per_client": cogs_per_client,
        "delivery_per_client": delivery_per_client,
        "payment_fee_per_client": payment_fee_per_client,
        "cogs_pct": cogs_pct,
        "direct_ops_pct": direct_ops_pct
    }


if __name__ == "__main__":
    from src.prepare import clean_orders_data
    from src.cohorts import build_cohort_matrices
    df = clean_orders_data("data/sample_orders.csv")
    _, _, summary = build_cohort_matrices(df)
    costs = calculate_costs_breakdown(df, summary)
    print(f"Себестоимость товаров: {costs['cogs_pct']}% от выручки")
    print(f"Средний CAC на клиента: {costs['cac_per_client']} руб.")

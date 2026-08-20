"""
Когортный анализ на Python/Pandas (Урок 3 курса).
- Группировка клиентов по когортам (месяц первой покупки YYYY-MM)
- Расчет матрицы удержания (клиенты по периодам M0, M1, ...)
- Расчет матрицы выручки (с округлением до 2 знаков для паритета с SQL)
- Сводная когорта на период
"""

import pandas as pd
from typing import Tuple


def build_cohort_matrices(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Возвращает:
    1. df_clients: матрица количества активных клиентов (когорта x период)
    2. df_revenue: матрица чистой выручки (когорта x период)
    3. df_summary: сводная таблица по периодам (сумма клиентов, средний чек, выручка)
    """
    # 1. Матрица уникальных клиентов
    cohort_clients = (
        df.groupby(["cohort_month", "period"])["client_uid"]
        .nunique()
        .unstack(fill_value=0)
        .astype(int)
    )
    cohort_clients.index = cohort_clients.index.astype(str)
    cohort_clients.columns = cohort_clients.columns.astype(int)

    # 2. Матрица выручки (округляем до 2 знаков для полного совпадения с SQL)
    cohort_revenue = (
        df.groupby(["cohort_month", "period"])["net_revenue"]
        .sum()
        .round(2)
        .unstack(fill_value=0.0)
    )
    cohort_revenue.index = cohort_revenue.index.astype(str)
    cohort_revenue.columns = cohort_revenue.columns.astype(int)

    # 3. Сводная статистика по периодам
    period_stats = df.groupby("period").agg(
        active_clients=("client_uid", "nunique"),
        orders_count=("order_id", "count"),
        total_net_revenue=("net_revenue", "sum"),
        total_cogs=("cogs", "sum"),
        total_delivery=("delivery_cost", "sum"),
        total_acquisition=("acquisition_cost", "sum")
    ).reset_index()

    period_stats["total_net_revenue"] = period_stats["total_net_revenue"].round(2)
    period_stats["total_cogs"] = period_stats["total_cogs"].round(2)
    period_stats["total_delivery"] = period_stats["total_delivery"].round(2)
    period_stats["total_acquisition"] = period_stats["total_acquisition"].round(2)

    period_stats["period"] = period_stats["period"].astype(int)
    initial_cohort_size = period_stats.loc[period_stats["period"] == 0, "active_clients"].values[0] if not period_stats.empty else 1
    period_stats["retention_rate"] = period_stats["active_clients"] / initial_cohort_size

    return cohort_clients, cohort_revenue, period_stats

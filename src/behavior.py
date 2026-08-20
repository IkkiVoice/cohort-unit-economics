"""
Метрики поведения клиентов и базовый LTV (Уроки 4 и 5 курса).
- Расчет отвала (Churn rate) и удержания (Retention rate)
- Средний чек (AOV), частота заказов (Purchase Frequency)
- Средний срок жизни клиента (Lifetime)
- Базовый LTV = AOV * Frequency * Lifetime
- Расчет удержания только по доступным (наступившим) периодам
"""

import pandas as pd
from typing import Dict, Any, Optional, Tuple


def compute_cohort_availability(
    cohort_matrix: pd.DataFrame,
    last_order_date: pd.Timestamp
) -> Dict[str, int]:
    """
    Для каждой когорты определяет максимально доступный индекс периода жизни (M0, M1, ...).
    """
    availability = {}
    last_year = last_order_date.year
    last_month = last_order_date.month

    for cohort_str in cohort_matrix.index:
        parts = str(cohort_str).split("-")
        c_year, c_month = int(parts[0]), int(parts[1])
        max_p = (last_year - c_year) * 12 + (last_month - c_month)
        availability[cohort_str] = max(0, max_p)

    return availability


def compute_retention_summary(
    cohort_clients: pd.DataFrame,
    availability: Dict[str, int],
    max_periods: int = 9
) -> Tuple[pd.Series, pd.Series]:
    """
    Считает среднее удержание и количество доступных когорт для каждого периода M0..M(max_periods-1).
    Усредняет ТОЛЬКО по когортам, у которых данный период уже наступил.
    """
    avg_retention = {}
    cohorts_count = {}

    for p in range(max_periods):
        eligible_cohorts = [c for c in cohort_clients.index if availability.get(c, 0) >= p]
        cohorts_count[p] = len(eligible_cohorts)
        
        if eligible_cohorts:
            retentions = [
                (cohort_clients.loc[c, p] / cohort_clients.loc[c, 0])
                for c in eligible_cohorts if cohort_clients.loc[c, 0] > 0
            ]
            avg_retention[p] = (sum(retentions) / len(retentions)) if retentions else 0.0
        else:
            avg_retention[p] = 0.0

    return pd.Series(avg_retention), pd.Series(cohorts_count)


def calculate_behavior_metrics(
    period_summary: pd.DataFrame,
    cohort_clients: Optional[pd.DataFrame] = None,
    last_order_date: Optional[pd.Timestamp] = None
) -> Dict[str, Any]:
    """
    Рассчитывает ключевые показатели поведения на основе сводной когортной статистики по периодам.
    """
    df = period_summary.copy()
    
    # 1. Метрики по каждому периоду
    df["aov"] = df["total_net_revenue"] / df["orders_count"].replace(0, 1)
    df["purchase_frequency"] = df["orders_count"] / df["active_clients"].replace(0, 1)
    df["revenue_per_client"] = df["total_net_revenue"] / df["active_clients"].replace(0, 1)

    # 2. Расчет отвала (Churn) между периодами
    df["prev_active"] = df["active_clients"].shift(1)
    df["churn_rate"] = 1.0 - (df["active_clients"] / df["prev_active"])
    df.loc[df["period"] == 0, "churn_rate"] = 0.0

    # 3. Средневзвешенные агрегаты
    total_orders = df["orders_count"].sum()
    total_revenue = df["total_net_revenue"].sum()
    total_initial_clients = df.loc[df["period"] == 0, "active_clients"].values[0] if not df.empty else 1

    overall_aov = round(total_revenue / total_orders, 2) if total_orders > 0 else 0.0
    overall_frequency = round(total_orders / total_initial_clients, 2)
    
    # Средний срок жизни (Lifetime в периодах/месяцах) как сумма retention по всем периодам
    lifetime_months = round(df["retention_rate"].sum(), 2)

    # Базовый LTV двумя эквивалентными способами:
    # Способ 1: Общая выручка на одного привлеченного клиента (M0)
    basic_ltv_cumulative = round(total_revenue / total_initial_clients, 2)
    
    # Способ 2: Через формулу AOV * (Заказов на клиента за период) * Lifetime
    avg_orders_per_active_period = df["purchase_frequency"].mean()
    basic_ltv_formula = round(overall_aov * avg_orders_per_active_period * lifetime_months, 2)

    # Расхождение между способами расчета LTV в процентах
    ltv_diff_pct = (
        round(abs(basic_ltv_cumulative - basic_ltv_formula) / basic_ltv_cumulative * 100, 2)
        if basic_ltv_cumulative > 0 else 0.0
    )

    availability = {}
    avg_retention_series = None
    cohorts_count_series = None

    if cohort_clients is not None and last_order_date is not None:
        availability = compute_cohort_availability(cohort_clients, last_order_date)
        avg_retention_series, cohorts_count_series = compute_retention_summary(cohort_clients, availability)

    return {
        "period_metrics_df": df,
        "overall_aov": overall_aov,
        "overall_frequency": overall_frequency,
        "lifetime_months": lifetime_months,
        "basic_ltv": basic_ltv_cumulative,
        "basic_ltv_formula_check": basic_ltv_formula,
        "ltv_discrepancy_pct": ltv_diff_pct,
        "initial_cohort_size": total_initial_clients,
        "total_revenue": total_revenue,
        "availability": availability,
        "avg_retention_series": avg_retention_series,
        "cohorts_count_series": cohorts_count_series
    }

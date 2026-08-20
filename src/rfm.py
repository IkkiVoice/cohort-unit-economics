"""
RFM-сегментация клиентской базы (Сверх курса, требование CRM-агентств WIM / Direct Service / Dau).
- R (Recency): дней с последнего заказа
- F (Frequency): количество заказов
- M (Monetary): суммарная чистая выручка
- Разбиение на 5 ключевых бизнес-сегментов:
  1. VIP / Champions (R: 4-5, F: 4-5, M: 4-5)
  2. Loyal Customers (R: 3-5, F: 3-4, M: 3-5)
  3. Potential Loyalists (R: 4-5, F: 1-2, M: 2-4)
  4. At Risk (R: 1-2, F: 3-5, M: 3-5)
  5. Lost / Inactive (R: 1-2, F: 1-2, M: 1-2)
"""

import pandas as pd
from typing import Tuple, Dict, Any


def calculate_rfm_segments(df: pd.DataFrame, reference_date: Any = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Рассчитывает RFM-скоры и сегменты для каждого клиента.
    """
    if reference_date is None:
        ref_date = df["order_date"].max()
    else:
        ref_date = pd.to_datetime(reference_date)

    # Агрегация по клиентам
    rfm_table = df.groupby("client_uid").agg(
        last_order_date=("order_date", "max"),
        frequency=("order_id", "nunique"),
        monetary=("net_revenue", "sum")
    ).reset_index()

    rfm_table["recency_days"] = (ref_date - rfm_table["last_order_date"]).dt.days

    # Расчет скоров (1-5) по квантилям
    # Для Recency: меньше дней -> выше скор (5)
    rfm_table["r_score"] = pd.qcut(rfm_table["recency_days"], q=5, labels=[5, 4, 3, 2, 1], duplicates="drop").astype(int)
    
    # Для Frequency и Monetary: больше -> выше скор
    rfm_table["f_score"] = pd.qcut(rfm_table["frequency"].rank(method="first"), q=5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm_table["m_score"] = pd.qcut(rfm_table["monetary"], q=5, labels=[1, 2, 3, 4, 5], duplicates="drop").astype(int)

    rfm_table["rfm_score"] = (
        rfm_table["r_score"].astype(str) + 
        rfm_table["f_score"].astype(str) + 
        rfm_table["m_score"].astype(str)
    )

    # Сегментация по правилам
    def assign_segment(row) -> str:
        r, f, m = row["r_score"], row["f_score"], row["m_score"]
        if r >= 4 and f >= 4 and m >= 4:
            return "1. VIP / Champions"
        elif r >= 3 and f >= 3:
            return "2. Loyal Customers"
        elif r >= 4 and f <= 2:
            return "3. Potential Loyalists"
        elif r <= 2 and f >= 3:
            return "4. Customers at Risk"
        else:
            return "5. Hibernating / Lost"

    rfm_table["segment"] = rfm_table.apply(assign_segment, axis=1)

    # Сводка по сегментам
    segment_summary = rfm_table.groupby("segment").agg(
        client_count=("client_uid", "count"),
        avg_recency=("recency_days", "mean"),
        avg_frequency=("frequency", "mean"),
        avg_monetary=("monetary", "mean"),
        total_revenue=("monetary", "sum")
    ).reset_index()

    total_clients = len(rfm_table)
    total_rev = rfm_table["monetary"].sum()
    
    segment_summary["client_share_pct"] = round((segment_summary["client_count"] / total_clients) * 100, 2)
    segment_summary["revenue_share_pct"] = round((segment_summary["total_revenue"] / total_rev) * 100, 2)
    segment_summary["avg_recency"] = segment_summary["avg_recency"].round(1)
    segment_summary["avg_frequency"] = segment_summary["avg_frequency"].round(2)
    segment_summary["avg_monetary"] = segment_summary["avg_monetary"].round(2)
    segment_summary["total_revenue"] = segment_summary["total_revenue"].round(2)

    return rfm_table, segment_summary


if __name__ == "__main__":
    from src.prepare import clean_orders_data
    df = clean_orders_data("data/sample_orders.csv")
    rfm_df, summary = calculate_rfm_segments(df)
    print("Сводка по RFM-сегментам:")
    print(summary[["segment", "client_count", "client_share_pct", "revenue_share_pct"]])

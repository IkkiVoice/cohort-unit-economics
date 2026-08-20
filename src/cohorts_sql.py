"""
Когортный анализ на чистом SQL через SQLite.
- Оконные функции для определения даты первой покупки: MIN(order_date) OVER (PARTITION BY client_uid)
- Расчет номеров периодов через разницу месяцев
- Формирование когортных матриц и сводки периодов напрямую из базы без искажения промежуточным округлением
"""

import sqlite3
import pandas as pd
from typing import Tuple


def build_cohort_matrices_sql(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Выполняет когортный расчет средствами SQL в базе SQLite с математическим паритетом к Pandas.
    """
    conn = sqlite3.connect(":memory:")
    
    orders_table = df[[
        "order_id", "order_date", "client_uid", "brand", "channel",
        "items_count", "gross_revenue", "discount_amount", "net_revenue",
        "cogs", "delivery_cost", "acquisition_cost"
    ]].copy()
    orders_table["order_date"] = pd.to_datetime(orders_table["order_date"]).dt.strftime("%Y-%m-%d")
    orders_table.to_sql("orders", conn, index=False, if_exists="replace")

    # Общее табличное выражение (CTE) с вычислением первой покупки и периода
    cte_base = """
    WITH first_orders AS (
        SELECT 
            order_id,
            client_uid,
            order_date,
            net_revenue,
            cogs,
            delivery_cost,
            acquisition_cost,
            MIN(order_date) OVER (PARTITION BY client_uid) AS first_order_date
        FROM orders
    ),
    cohort_orders AS (
        SELECT 
            order_id,
            client_uid,
            order_date,
            net_revenue,
            cogs,
            delivery_cost,
            acquisition_cost,
            strftime('%Y-%m', first_order_date) AS cohort_month,
            (
                (CAST(strftime('%Y', order_date) AS INTEGER) - CAST(strftime('%Y', first_order_date) AS INTEGER)) * 12 +
                (CAST(strftime('%m', order_date) AS INTEGER) - CAST(strftime('%m', first_order_date) AS INTEGER))
            ) AS period
        FROM first_orders
    )
    """

    # 1. Запрос для матриц (когорта x период)
    sql_matrices = cte_base + """
    SELECT 
        cohort_month,
        period,
        COUNT(DISTINCT client_uid) AS active_clients,
        ROUND(SUM(net_revenue), 2) AS total_net_revenue
    FROM cohort_orders
    GROUP BY cohort_month, period
    ORDER BY cohort_month, period;
    """
    res_matrices = pd.read_sql_query(sql_matrices, conn)

    # 2. Запрос для сводки периодов (агрегируется напрямую от исходных строк для исключения погрешности)
    sql_summary = cte_base + """
    SELECT 
        period,
        COUNT(DISTINCT client_uid) AS active_clients,
        COUNT(order_id) AS orders_count,
        ROUND(SUM(net_revenue), 2) AS total_net_revenue,
        ROUND(SUM(cogs), 2) AS total_cogs,
        ROUND(SUM(delivery_cost), 2) AS total_delivery,
        ROUND(SUM(acquisition_cost), 2) AS total_acquisition
    FROM cohort_orders
    GROUP BY period
    ORDER BY period;
    """
    period_summary = pd.read_sql_query(sql_summary, conn)
    conn.close()

    # Сводные матрицы (Pivot)
    cohort_clients_sql = res_matrices.pivot(index="cohort_month", columns="period", values="active_clients").fillna(0).astype(int)
    cohort_clients_sql.index = cohort_clients_sql.index.astype(str)
    cohort_clients_sql.columns = cohort_clients_sql.columns.astype(int)

    cohort_revenue_sql = res_matrices.pivot(index="cohort_month", columns="period", values="total_net_revenue").fillna(0.0)
    cohort_revenue_sql.index = cohort_revenue_sql.index.astype(str)
    cohort_revenue_sql.columns = cohort_revenue_sql.columns.astype(int)

    period_summary["period"] = period_summary["period"].astype(int)
    initial_size = period_summary.loc[period_summary["period"] == 0, "active_clients"].values[0] if not period_summary.empty else 1
    period_summary["retention_rate"] = period_summary["active_clients"] / initial_size

    return cohort_clients_sql, cohort_revenue_sql, period_summary

"""
Модуль очистки данных и дедупликации профилей (Урок 2 курса).
- Автоматически сопоставляет русские и английские названия колонок (1С, RetailCRM, Практикум, Mindbox)
- Гарантирует наличие всех обязательных и опциональных полей (brand, channel, items_count, costs)
- Надежно парсит даты любых форматов (ISO YYYY-MM-DD, DD.MM.YYYY, со временем) с контролем доли NaT
- Итеративный алгоритм Disjoint-Set (Union-Find) с защитой от RecursionError на длинных цепочках
- Транзитивная склейка профилей по контактам (телефон / email)
- Безопасное сопоставление через df.index.map
- Определение даты и месяца первой покупки клиента
- Фильтрация отмененных заказов
"""

import pandas as pd
import re
from typing import Any, Tuple, Dict


def normalize_phone(phone: Any) -> str:
    if pd.isna(phone) or not str(phone).strip():
        return ""
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return f"+{digits}" if len(digits) >= 10 else ""


def normalize_email(email: Any) -> str:
    if pd.isna(email) or not str(email).strip():
        return ""
    em = str(email).strip().lower()
    return em if "@" in em else ""


def clean_currency_value(val: Any) -> float:
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("\xa0", "").replace(" ", "").replace("руб.", "").replace("руб", "").replace("₽", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_dates_robustly(series: pd.Series, max_allowed_nat_pct: float = 5.0) -> pd.Series:
    def parse_single_date(val: Any) -> Any:
        if pd.isna(val):
            return pd.NaT
        s = str(val).strip()
        if not s:
            return pd.NaT
        if len(s) >= 4 and s[:4].isdigit() and (len(s) == 4 or s[4] in ["-", "/", "."]):
            return pd.to_datetime(s, format="ISO8601", errors="coerce")
        return pd.to_datetime(s, dayfirst=True, errors="coerce")

    clean_s = series.dropna().astype(str).str.strip()
    total_non_empty = len(clean_s)
    if total_non_empty == 0:
        return pd.to_datetime(series, errors="coerce")

    parsed = series.apply(parse_single_date)
    
    nat_count = parsed.isna().sum() - series.isna().sum()
    if total_non_empty > 0:
        nat_pct = (nat_count / total_non_empty) * 100.0
        if nat_pct > max_allowed_nat_pct:
            raise ValueError(
                f"Критическая ошибка парсинга дат: не удалось распознать {nat_count} из {total_non_empty} "
                f"строк ({nat_pct:.1f}% > порога {max_allowed_nat_pct}%). Проверьте форматы в файле."
            )
            
    return parsed


def map_columns_auto(df: pd.DataFrame) -> pd.DataFrame:
    col_map = {}
    for c in df.columns:
        c_clean = str(c).strip().lower()
        if c_clean in ["дата транзакции", "дата заказа", "дата", "order_date", "date"]:
            col_map[c] = "order_date"
        elif c_clean in ["id клиента", "клиент", "client_id", "customer_id", "user_id", "id"]:
            col_map[c] = "client_id"
        elif c_clean in ["сумма", "выручка", "net_revenue", "amount", "revenue", "сумма заказа"]:
            col_map[c] = "net_revenue"
        elif c_clean in ["статус", "статус заказа", "order_status", "status"]:
            col_map[c] = "order_status"
        elif c_clean in ["email клиента", "email", "e-mail", "почта"]:
            col_map[c] = "email"
        elif c_clean in ["телефон", "телефон клиента", "phone", "client_phone", "тел"]:
            col_map[c] = "phone"
        elif c_clean in ["себестоимость", "cogs", "cost"]:
            col_map[c] = "cogs"
        elif c_clean in ["доставка", "стоимость доставки", "delivery_cost", "delivery"]:
            col_map[c] = "delivery_cost"
        elif c_clean in ["привлечение", "маркетинг", "cac", "acquisition_cost"]:
            col_map[c] = "acquisition_cost"
        elif c_clean in ["номер операции", "№ операции", "order_id", "id заказа"]:
            col_map[c] = "order_id"
        elif c_clean in ["бренд", "brand"]:
            col_map[c] = "brand"
        elif c_clean in ["канал", "канал продаж", "channel"]:
            col_map[c] = "channel"
        elif c_clean in ["количество товаров", "кол-во товаров", "items_count", "qty"]:
            col_map[c] = "items_count"
            
    return df.rename(columns=col_map)


def build_identity_graph(df: pd.DataFrame) -> Dict[int, str]:
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        curr = x
        while parent[curr] != root:
            nxt = parent[curr]
            parent[curr] = root
            curr = nxt
        return root

    def union(x: str, y: str):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for idx, row in df.iterrows():
        cid = str(row.get("client_id", "")).strip()
        valid_cid = cid if (cid and cid.lower() not in ["nan", "none", "null"]) else ""
        ph = normalize_phone(row.get("phone", ""))
        em = normalize_email(row.get("email", ""))
        
        identifiers = []
        if valid_cid:
            identifiers.append(f"cid:{valid_cid}")
        if ph:
            identifiers.append(f"ph:{ph}")
        if em:
            identifiers.append(f"em:{em}")
            
        if not identifiers:
            identifiers.append(f"row:{idx}")
            
        base = identifiers[0]
        for other in identifiers[1:]:
            union(base, other)

    row_to_uid: Dict[int, str] = {}
    for idx, row in df.iterrows():
        cid = str(row.get("client_id", "")).strip()
        valid_cid = cid if (cid and cid.lower() not in ["nan", "none", "null"]) else ""
        ph = normalize_phone(row.get("phone", ""))
        em = normalize_email(row.get("email", ""))
        
        if valid_cid:
            target = f"cid:{valid_cid}"
        elif ph:
            target = f"ph:{ph}"
        elif em:
            target = f"em:{em}"
        else:
            target = f"row:{idx}"
            
        row_to_uid[idx] = find(target)

    return row_to_uid


def clean_orders_data(file_path: str) -> pd.DataFrame:
    df = pd.read_csv(file_path, sep=None, engine="python", encoding="utf-8-sig")
    df = map_columns_auto(df)

    df.columns = [str(c).strip() for c in df.columns]

    # Базовые поля
    if "order_id" not in df.columns or df["order_id"].isna().sum() > 0:
        df["order_id"] = [f"ORD-{i+1:07d}" for i in range(len(df))]
    if "client_id" not in df.columns:
        df["client_id"] = [f"CUST-{i+1:05d}" for i in range(len(df))]
    if "net_revenue" not in df.columns:
        df["net_revenue"] = 0.0

    # Заглушки для категориальных и количественных колонок (защита от KeyError в SQL-движке)
    for col in ["brand", "channel"]:
        if col not in df.columns:
            df[col] = "unknown"
    if "items_count" not in df.columns:
        df["items_count"] = 1

    df["net_revenue"] = df["net_revenue"].apply(clean_currency_value)
    
    for col in ["gross_revenue", "discount_amount", "cogs", "delivery_cost", "acquisition_cost"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_currency_value)
        else:
            df[col] = 0.0

    if df["gross_revenue"].sum() == 0 and df["net_revenue"].sum() > 0:
        df["gross_revenue"] = df["net_revenue"]

    df["order_date"] = parse_dates_robustly(df["order_date"])
    df = df.dropna(subset=["order_date"]).reset_index(drop=True)

    if "order_status" in df.columns:
        df = df[~df["order_status"].astype(str).str.lower().isin(["cancelled", "отменен", "отмена", "отменён"])].reset_index(drop=True)

    row_mapping = build_identity_graph(df)
    df["client_uid"] = df.index.map(row_mapping)

    first_orders = df.groupby("client_uid")["order_date"].min().reset_index()
    first_orders.columns = ["client_uid", "first_order_date"]
    first_orders["cohort_month"] = first_orders["first_order_date"].dt.strftime("%Y-%m")

    df = df.merge(first_orders, on="client_uid", how="left")
    df["order_month"] = df["order_date"].dt.strftime("%Y-%m")

    c_years = df["order_date"].dt.year - pd.to_datetime(df["cohort_month"]).dt.year
    c_months = df["order_date"].dt.month - pd.to_datetime(df["cohort_month"]).dt.month
    df["period"] = c_years * 12 + c_months

    return df

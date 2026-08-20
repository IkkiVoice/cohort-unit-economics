"""
Генератор синтетических данных розничной торговли (одежда и обувь).
Сохраняет CSV в кодировке UTF-8 с BOM (utf-8-sig) и разделителем точка с запятой для идеальной работы в Excel.
Калиброван под реалистичную юнит-экономику с LTV/CAC в диапазоне 3.5x - 4.5x.
"""

import csv
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any


def generate_retail_dataset(
    num_customers: int = 1500,
    start_date_str: str = "2025-01-01",
    end_date_str: str = "2026-06-30",
    output_path: str = "data/sample_orders.csv"
) -> str:
    random.seed(42)
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    total_days = (end_date - start_date).days

    brands = [
        {"name": "UrbanStyle", "base_aov": 6500, "cogs_pct": 0.42, "weight": 0.6},
        {"name": "SportActive", "base_aov": 8200, "cogs_pct": 0.48, "weight": 0.4}
    ]

    channels = ["online_site", "online_app", "offline_pos"]
    channels_weights = [0.45, 0.35, 0.20]

    customers = []
    for cid in range(1, num_customers + 1):
        first_day_offset = random.randint(0, int(total_days * 0.75))
        first_date = start_date + timedelta(days=first_day_offset)
        
        has_phone = random.random() > 0.15
        has_email = random.random() > 0.25
        
        phone_num = f"+7999{random.randint(1000000, 9999999)}" if has_phone else ""
        email_addr = f"user_{cid}_{random.randint(100,999)}@example.com" if has_email else ""
        
        preferred_brand = random.choices(brands, weights=[0.6, 0.4])[0]
        loyalty_tier = random.choices(["one_off", "occasional", "loyal"], weights=[0.55, 0.30, 0.15])[0]
        
        customers.append({
            "client_id": f"CUST_{cid:05d}",
            "phone": phone_num,
            "email": email_addr,
            "first_date": first_date,
            "preferred_brand": preferred_brand,
            "loyalty_tier": loyalty_tier
        })

    orders: List[Dict[str, Any]] = []
    order_counter = 1

    for cust in customers:
        tier = cust["loyalty_tier"]
        first_date = cust["first_date"]
        
        if tier == "one_off":
            num_orders = 1
        elif tier == "occasional":
            num_orders = random.randint(2, 4)
        else:
            num_orders = random.randint(5, 10)

        current_date = first_date

        for o_idx in range(num_orders):
            if current_date > end_date:
                break

            month = current_date.month
            season_mult = 1.25 if month in [3, 4, 5, 9, 10, 11] else 0.95

            brand_info = cust["preferred_brand"] if random.random() > 0.2 else random.choice(brands)
            channel = random.choices(channels, weights=channels_weights)[0]

            order_phone = cust["phone"] if (channel == "offline_pos" or random.random() > 0.2) else ""
            order_email = cust["email"] if (channel != "offline_pos" or random.random() > 0.5) else ""

            if not order_phone and not order_email:
                order_phone = cust["phone"] or f"+7999{random.randint(1000000, 9999999)}"

            items_cnt = random.randint(1, 4)
            gross_amount = round(brand_info["base_aov"] * items_cnt * random.uniform(0.8, 1.3) * season_mult, 2)
            
            discount_pct = random.choice([0.0, 0.05, 0.10, 0.15, 0.20])
            discount_amount = round(gross_amount * discount_pct, 2)
            net_amount = round(gross_amount - discount_amount, 2)
            
            cogs = round(net_amount * brand_info["cogs_pct"], 2)
            delivery_cost = 350.0 if channel == "online_site" else (250.0 if channel == "online_app" else 0.0)
            
            # Калибровка CAC под реалистичный норматив окупаемости LTV/CAC ~ 3.5x - 4.5x
            cac_cost = round(random.uniform(4800, 5800), 2) if o_idx == 0 else 0.0

            status = "completed"
            r_val = random.random()
            if r_val < 0.04:
                status = "cancelled"
            elif r_val < 0.08:
                status = "refunded"

            orders.append({
                "order_id": f"ORD_{order_counter:06d}",
                "order_date": current_date.strftime("%Y-%m-%d"),
                "client_id": cust["client_id"],
                "phone": order_phone,
                "email": order_email,
                "brand": brand_info["name"],
                "channel": channel,
                "items_count": items_cnt,
                "gross_revenue": gross_amount,
                "discount_amount": discount_amount,
                "net_revenue": net_amount,
                "cogs": cogs,
                "delivery_cost": delivery_cost,
                "acquisition_cost": cac_cost,
                "order_status": status
            })

            order_counter += 1
            interval_days = random.randint(15, 75)
            current_date += timedelta(days=interval_days)

    fieldnames = [
        "order_id", "order_date", "client_id", "phone", "email",
        "brand", "channel", "items_count", "gross_revenue", "discount_amount",
        "net_revenue", "cogs", "delivery_cost", "acquisition_cost", "order_status"
    ]

    with open(output_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(orders)

    return output_path


if __name__ == "__main__":
    out = generate_retail_dataset()
    print(f"Сгенерирован реалистичный датасет: {out}")

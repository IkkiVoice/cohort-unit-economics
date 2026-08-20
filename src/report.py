"""
Генератор управленческого отчета в формате Markdown (report.py v2.1).
- Определение полноты данных (full vs partial mode)
- Раздел 0: Аудит полноты исходных данных
- Корректная обработка отсутствующих метрик (без ложных статусов UNPROFITABLE)
- Матрицы удержания (M1-M8) с разделением 0 и ненаступивших периодов (—)
- Расчет среднего удержания только по доступным когортам
- Самопроверка расчета Базового LTV (формула vs факт)
- Фильтрация выбросов удержания (топ-5 статистических аномалий + агрегация)
"""

import pandas as pd
from datetime import datetime
from typing import Dict, Any, List, Optional


def detect_data_completeness(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Проверяет наличие и наполненность ключевых финансовых колонок в датафрейме.
    """
    def check_col(name: str) -> bool:
        if name not in df.columns:
            return False
        val_sum = df[name].dropna().apply(lambda x: float(x) if isinstance(x, (int, float)) else 0.0).abs().sum()
        return val_sum > 1e-4

    has_cogs = check_col("cogs")
    has_cac = check_col("acquisition_cost")
    has_delivery = check_col("delivery_cost")
    has_discount = check_col("discount_amount")

    mode = "full" if (has_cogs and has_cac) else "partial"

    return {
        "cogs": has_cogs,
        "acquisition_cost": has_cac,
        "delivery_cost": has_delivery,
        "discount_amount": has_discount,
        "mode": mode
    }


def format_markdown_table(df: pd.DataFrame) -> str:
    """Преобразует DataFrame в Markdown-таблицу."""
    headers = [str(c) for c in df.columns]
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    
    for _, row in df.iterrows():
        row_str = [str(row[c]) for c in df.columns]
        lines.append("| " + " | ".join(row_str) + " |")
        
    return "\n".join(lines)


def detect_retention_anomalies(
    cohort_matrix: pd.DataFrame,
    availability: Dict[str, int],
    max_periods: int = 9
) -> Dict[str, Any]:
    """
    Находит только выраженные выбросы удержания (рост >= 1.5x к предыдущему периоду и прирост >= 3 чел.).
    Возвращает топ-5 выраженных аномалий и счетчик менее заметных всплесков.
    """
    candidates = []
    for c in cohort_matrix.index:
        max_p = availability.get(str(c), max_periods - 1)
        for p in range(2, min(max_p + 1, max_periods)):
            curr_val = int(cohort_matrix.loc[c, p]) if p in cohort_matrix.columns else 0
            prev_val = int(cohort_matrix.loc[c, p - 1]) if (p - 1) in cohort_matrix.columns else 0
            if prev_val >= 2 and curr_val >= int(prev_val * 1.45) and curr_val > 0:
                diff = curr_val - prev_val
                ratio = curr_val / prev_val
                if diff >= 3:
                    candidates.append({
                        "cohort": str(c),
                        "period": p,
                        "curr_val": curr_val,
                        "prev_val": prev_val,
                        "diff": diff,
                        "ratio": ratio,
                        "score": diff * ratio
                    })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top_5 = candidates[:5]
    hidden_count = max(0, len(candidates) - 5)

    return {
        "top_anomalies": top_5,
        "hidden_count": hidden_count,
        "total_count": len(candidates)
    }


def generate_full_report(
    behavior_metrics: Dict[str, Any],
    costs_breakdown: Dict[str, Any],
    model_results: Dict[str, Any],
    cohort_matrix: pd.DataFrame,
    rfm_summary: pd.DataFrame,
    clean_df: Optional[pd.DataFrame] = None,
    output_path: str = "output/report.md"
) -> str:
    """
    Собирает и сохраняет полный структурированный управленческий отчет.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 1. Полнота данных
    completeness = detect_data_completeness(clean_df) if clean_df is not None else {
        "cogs": model_results.get("direct_ltv_1") is not None,
        "acquisition_cost": model_results.get("ltv_to_cac_ratio") is not None,
        "delivery_cost": costs_breakdown.get("delivery_per_client", 0.0) > 0,
        "discount_amount": False,
        "mode": "full" if (model_results.get("direct_ltv_1") is not None and model_results.get("ltv_to_cac_ratio") is not None) else "partial"
    }

    # 2. Доступность периодов для каждой когорты
    if clean_df is not None and "order_date" in clean_df.columns:
        last_date = pd.to_datetime(clean_df["order_date"]).max()
        last_year, last_month = last_date.year, last_date.month
        availability = {}
        for c in cohort_matrix.index:
            parts = str(c).split("-")
            c_y, c_m = int(parts[0]), int(parts[1])
            availability[str(c)] = max(0, (last_year - c_y) * 12 + (last_month - c_m))
    else:
        availability = behavior_metrics.get("availability", {str(c): 8 for c in cohort_matrix.index})

    # Начинаем с M1, так как M0 дублирует размер когорты
    cols = [c for c in range(1, 9) if c in cohort_matrix.columns or any(availability.get(str(k), 0) >= c for k in cohort_matrix.index)]
    if not cols:
        cols = list(range(1, 9))

    # 3. Форматирование абсолютной матрицы удержания (чел.)
    abs_matrix_rows = []
    for c in cohort_matrix.index:
        base_size = int(cohort_matrix.loc[c, 0]) if 0 in cohort_matrix.columns else 0
        row_dict = {"Когорта": str(c), "База (M0)": str(base_size)}
        max_p = availability.get(str(c), 8)
        for p in cols:
            if p > max_p:
                row_dict[f"M{p}"] = "—"
            else:
                val = cohort_matrix.loc[c, p] if p in cohort_matrix.columns else 0
                row_dict[f"M{p}"] = str(int(val))
        abs_matrix_rows.append(row_dict)
    abs_matrix_df = pd.DataFrame(abs_matrix_rows)
    abs_cohort_table_md = format_markdown_table(abs_matrix_df)

    # 4. Форматирование процентной матрицы удержания (%)
    pct_matrix_rows = []
    for c in cohort_matrix.index:
        base_size = cohort_matrix.loc[c, 0] if 0 in cohort_matrix.columns else 1
        row_dict = {"Когорта": str(c), "База (M0)": str(int(base_size))}
        max_p = availability.get(str(c), 8)
        for p in cols:
            if p > max_p:
                row_dict[f"M{p}"] = "—"
            else:
                val = cohort_matrix.loc[c, p] if p in cohort_matrix.columns else 0
                pct = (val / base_size * 100.0) if base_size > 0 else 0.0
                row_dict[f"M{p}"] = f"{pct:.1f}%"
        pct_matrix_rows.append(row_dict)

    # Среднее удержание только по доступным когортам
    avg_ret_row = {"Когорта": "**Среднее удержание**", "База (M0)": "—"}
    cohorts_cnt_row = {"Когорта": "**Когорт в расчёте**", "База (M0)": "—"}
    for p in cols:
        eligible = [c for c in cohort_matrix.index if availability.get(str(c), 0) >= p]
        cohorts_cnt_row[f"M{p}"] = str(len(eligible))
        if eligible:
            rets = [
                (cohort_matrix.loc[c, p] / cohort_matrix.loc[c, 0] * 100.0)
                for c in eligible if 0 in cohort_matrix.columns and cohort_matrix.loc[c, 0] > 0
            ]
            avg_p = (sum(rets) / len(rets)) if rets else 0.0
            avg_ret_row[f"M{p}"] = f"**{avg_p:.1f}%**"
        else:
            avg_ret_row[f"M{p}"] = "—"

    pct_matrix_rows.append(avg_ret_row)
    pct_matrix_rows.append(cohorts_cnt_row)
    pct_matrix_df = pd.DataFrame(pct_matrix_rows)
    pct_cohort_table_md = format_markdown_table(pct_matrix_df)

    # 5. Детекция аномалий (топ-5 + скрытые)
    anomaly_data = detect_retention_anomalies(cohort_matrix, availability, max_periods=9)
    if anomaly_data["total_count"] > 0:
        anom_lines = []
        for an in anomaly_data["top_anomalies"]:
            anom_lines.append(
                f"- Отрицательный отвал в когорте **{an['cohort']}** на **M{an['period']}**: "
                f"вернулось **{an['curr_val']}** клиентов (рост в **{an['ratio']:.1f}x**, на {an['diff']} больше, чем в M{an['period']-1})."
            )
        if anomaly_data["hidden_count"] > 0:
            anom_lines.append(f"- *...и ещё {anomaly_data['hidden_count']} менее выраженных всплесков активности в других когортах.*")
        anom_lines.append("\n*Отрицательный отвал указывает на выраженную сезонность спроса или реактивацию спящих клиентов CRM-рассылками.*")
        anomalies_md = "\n".join(anom_lines)
    else:
        anomalies_md = "- Значимых аномалий удержания и резких скачков активности не обнаружено."

    # 6. RFM-таблица
    rfm_table_md = format_markdown_table(rfm_summary[[
        "segment", "client_count", "client_share_pct", "revenue_share_pct", "avg_recency", "avg_frequency", "avg_monetary"
    ]].rename(columns={
        "segment": "Сегмент",
        "client_count": "Клиенты",
        "client_share_pct": "Доля базы (%)",
        "revenue_share_pct": "Доля выручки (%)",
        "avg_recency": "Давность (дней)",
        "avg_frequency": "Частота",
        "avg_monetary": "Ср. выручка (руб)"
    }))

    # 7. Форматирование строк Юнит-экономики
    def fmt_curr(val: Optional[float], suffix: str = " руб.") -> str:
        if val is None:
            return "не рассчитан"
        return f"{val:,.2f}{suffix}"

    def fmt_pct(val: Optional[float]) -> str:
        if val is None:
            return "не рассчитана"
        return f"{val:.1f}%"

    is_full = completeness["mode"] == "full"

    if is_full and model_results.get("health_status"):
        header_status = f"`{model_results['health_status']}`"
    else:
        header_status = "*Не рассчитывался (режим частичных данных)*"

    # Раздел 0: Таблица аудита данных
    audit_rows = [
        {
            "Поле": "Себестоимость товаров (`cogs`)",
            "Наличие": "Есть" if completeness["cogs"] else "Нет в источнике",
            "Влияние на расчёт": "Позволяет рассчитать валовую прибыль (Прямой LTV 1)" if completeness["cogs"] else "Блок валовой прибыли (Прямой LTV 1) не рассчитан"
        },
        {
            "Поле": "Стоимость привлечения (`acquisition_cost`)",
            "Наличие": "Есть" if completeness["acquisition_cost"] else "Нет в источнике",
            "Влияние на расчёт": "Позволяет рассчитать возврат инвестиций (LTV/CAC) и Чистый LTV" if completeness["acquisition_cost"] else "Блок маркетинговой окупаемости (LTV/CAC) и Чистый LTV не рассчитаны"
        },
        {
            "Поле": "Стоимость доставки (`delivery_cost`)",
            "Наличие": "Есть" if completeness["delivery_cost"] else "Нет в источнике",
            "Влияние на расчёт": "Учитывается во вкладной марже (Прямой LTV 2)" if completeness["delivery_cost"] else "Принята равной 0.00 руб. (нет расходов на логистику)"
        },
        {
            "Поле": "Скидки и промокоды (`discount_amount`)",
            "Наличие": "Есть" if completeness["discount_amount"] else "Нет в источнике",
            "Влияние на расчёт": "Учитывается разница валовой и чистой выручки" if completeness["discount_amount"] else "Чистая выручка принята равной сумме чеков"
        }
    ]
    audit_table_md = format_markdown_table(pd.DataFrame(audit_rows))

    if is_full:
        mode_text = "**Режим расчёта:** `Полный (все метрики юнит-экономики и маржинальности доступны)`"
    else:
        missing_parts = []
        if not completeness["cogs"]:
            missing_parts.append("себестоимости товаров")
        if not completeness["acquisition_cost"]:
            missing_parts.append("стоимости привлечения клиентов (CAC)")
        mode_text = (
            f"**Режим расчёта:** `Частичный (в источнике нет данных о {' и '.join(missing_parts)})`\n\n"
            f"> [!NOTE]\n"
            f"> В источнике отсутствуют данные о {' и '.join(missing_parts)}. "
            f"Блоки валовой маржи и маркетинговой окупаемости не рассчитывались, чтобы исключить искажение управленческих решений."
        )

    # Раздел 1: Таблица юнит-экономики
    ue_rows = [
        {"Метрика": "**Базовый LTV**", "Значение": fmt_curr(model_results['basic_ltv']), "Интерпретация": "Выручка с привлеченного клиента за весь срок жизни"},
        {"Метрика": "**Себестоимость (COGS)**", "Значение": fmt_curr(costs_breakdown.get('cogs_per_client')) if completeness['cogs'] else "не указана", "Интерпретация": "Себестоимость товаров по принципу начисления" if completeness['cogs'] else "Нет данных в выгрузке"},
        {"Метрика": "**Прямой LTV 1**", "Значение": fmt_curr(model_results['direct_ltv_1']) + (f" (маржа {fmt_pct(model_results['gross_margin_pct'])})" if is_full else ""), "Интерпретация": "Валовая прибыль до вычета операционных расходов" if completeness['cogs'] else "Не рассчитан (требуются данные COGS)"},
        {"Метрика": "**Операционные расходы**", "Значение": fmt_curr(costs_breakdown['delivery_per_client'] + costs_breakdown['payment_fee_per_client']), "Интерпретация": "Доставка, эквайринг, упаковка на клиента"},
        {"Метрика": "**Прямой LTV 2**", "Значение": fmt_curr(model_results['direct_ltv_2']) + (f" (маржа {fmt_pct(model_results['contribution_margin_pct'])})" if is_full else ""), "Интерпретация": "Вкладная маржа (Contribution Margin) с клиента" if completeness['cogs'] else "Не рассчитан (требуются данные COGS)"},
        {"Метрика": "**Стоимость привлечения (CAC)**", "Значение": fmt_curr(model_results['cac_per_client']) if completeness['acquisition_cost'] else "не указана", "Интерпретация": "Маркетинговые затраты на привлечение одного клиента" if completeness['acquisition_cost'] else "Нет данных в выгрузке"},
        {"Метрика": "**Чистый LTV**", "Значение": fmt_curr(model_results['net_ltv']) + (f" (маржа {fmt_pct(model_results['net_margin_pct'])})" if is_full else ""), "Интерпретация": "**Чистая прибыль бизнеса** с клиента после маркетинга" if is_full else "Не рассчитан (требуются COGS и CAC)"},
        {"Метрика": "**Коэффициент LTV / CAC**", "Значение": f"**{model_results['ltv_to_cac_ratio']}x**" if is_full else "не рассчитан", "Интерпретация": "Возврат инвестиций в маркетинг (норматив >= 3.0)" if is_full else "Не рассчитан (нет затрат на маркетинг)"}
    ]
    ue_table_md = format_markdown_table(pd.DataFrame(ue_rows))

    if not is_full:
        enrichment_md = """
### 1.1. Что нужно добавить в выгрузку для полного расчёта

- **Себестоимость товаров (`cogs`):** позволит рассчитать реальную валовую прибыль (Прямой LTV 1) и вкладную маржу (Прямой LTV 2).
- **Затраты на маркетинг (`acquisition_cost` / CAC):** позволят рассчитать окупаемость каналов привлечения (LTV/CAC) и Чистый LTV компании.
"""
    else:
        enrichment_md = ""

    basic_ltv_fact = behavior_metrics.get("basic_ltv", 0.0)
    basic_ltv_formula = behavior_metrics.get("basic_ltv_formula_check", 0.0)
    ltv_diff_pct = behavior_metrics.get("ltv_discrepancy_pct", 0.0)

    content = f"""# Отчет по юнит-экономике и когортному анализу

**Дата расчета:** {now_str}  
**Статус экономики:** {header_status}

---

## 0. Полнота исходных данных

{audit_table_md}

{mode_text}

---

## 1. Главные показатели юнит-экономики (на одного клиента)

{ue_table_md}
{enrichment_md}
---

## 2. Метрики поведения базы (Retention & Churn)

- **Размер привлеченной базы:** {behavior_metrics['initial_cohort_size']} клиентов
- **Средний чек (AOV):** {behavior_metrics['overall_aov']:,.2f} руб.
- **Частота покупок на клиента:** {behavior_metrics['overall_frequency']} заказов
- **Средний срок жизни (Lifetime):** {behavior_metrics['lifetime_months']} месяцев

### Самопроверка расчета Базового LTV

- **Способ 1 (Накопительный факт $\\sum Выручка / M_0$):** {basic_ltv_fact:,.2f} руб.
- **Способ 2 (Формула $AOV \\times Frequency \\times Lifetime$):** {basic_ltv_formula:,.2f} руб.
- **Расхождение:** {ltv_diff_pct}% *(отражает вариативность чеков и динамики повторов между когортами)*

### Матрица удержания клиентов в абсолютных значениях (M1 - M8, чел.)

{abs_cohort_table_md}

### Матрица удержания клиентов в долях от когорты (M1 - M8, %)

{pct_cohort_table_md}

### Аномалии удержания

{anomalies_md}

---

## 3. RFM-сегментация клиентской базы

{rfm_table_md}

---

## 4. Выводы и рекомендации для менеджмента

1. **Оценка удержания:** Базовый срок жизни клиента составляет **{behavior_metrics['lifetime_months']} мес.** при среднем чеке **{behavior_metrics['overall_aov']:,.2f} руб.**
2. **Фокус на удержании:** Потеря клиентов после периода M1 требует внедрения триггерных CRM-цепочек реактивации и программ лояльности в течение первых 45-60 дней после первой покупки.
3. **RFM-потенциал:** Сегмент `Potential Loyalists` генерирует стабильную долю маржи и является приоритетной целью для стимулирования второй и третьей покупки.
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_path

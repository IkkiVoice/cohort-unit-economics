"""
Сборка юнит-экономики и расчет видов LTV (Урок 7 курса).
- Прямой LTV 1 = Выручка - Себестоимость товара (COGS)
- Прямой LTV 2 = Прямой LTV 1 - Прямые операционные расходы (доставка, эквайринг)
- Чистый LTV = Прямой LTV 2 - Затраты на привлечение (CAC)
- Метрика возврата инвестиций: Вкладная маржа (Прямой LTV 2) / CAC (норматив >= 3.0)
- Поддержка режима частичных данных (partial mode): возвращает None для неполных метрик
"""

from typing import Dict, Any, Optional


def build_unit_economics_model(
    behavior_metrics: Dict[str, Any],
    costs_breakdown: Dict[str, Any],
    completeness: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Формирует итоговую экономическую модель на одного привлеченного клиента.
    Если передан словарь completeness и в нем отсутствуют cogs или acquisition_cost,
    соответствующие метрики возвращаются как None (не искажая модель нулями).
    """
    basic_ltv = behavior_metrics.get("basic_ltv", 0.0)
    cogs_per_client = costs_breakdown.get("cogs_per_client", 0.0)
    delivery_per_client = costs_breakdown.get("delivery_per_client", 0.0)
    payment_fee_per_client = costs_breakdown.get("payment_fee_per_client", 0.0)
    cac_per_client = costs_breakdown.get("cac_per_client", 0.0)

    # Проверка доступности данных
    has_cogs = completeness.get("cogs", True) if completeness else (cogs_per_client > 0)
    has_cac = completeness.get("acquisition_cost", True) if completeness else (cac_per_client > 0)

    # 1. Прямой LTV 1 (Валовая прибыль)
    if has_cogs:
        direct_ltv_1 = round(basic_ltv - cogs_per_client, 2)
        gross_margin_pct = round((direct_ltv_1 / basic_ltv) * 100, 2) if basic_ltv > 0 else 0.0
        
        # 2. Прямой LTV 2 (Вкладная маржа / Contribution Margin)
        direct_ltv_2 = round(direct_ltv_1 - (delivery_per_client + payment_fee_per_client), 2)
        contribution_margin_pct = round((direct_ltv_2 / basic_ltv) * 100, 2) if basic_ltv > 0 else 0.0
    else:
        direct_ltv_1 = None
        gross_margin_pct = None
        direct_ltv_2 = None
        contribution_margin_pct = None

    # 3. Чистый LTV (Чистая прибыль после маркетинга)
    if has_cogs and has_cac and direct_ltv_2 is not None:
        net_ltv = round(direct_ltv_2 - cac_per_client, 2)
        net_margin_pct = round((net_ltv / basic_ltv) * 100, 2) if basic_ltv > 0 else 0.0
    else:
        net_ltv = None
        net_margin_pct = None

    # 4. Коэффициент LTV / CAC (Вкладная маржа / CAC)
    if has_cac and cac_per_client > 0 and direct_ltv_2 is not None:
        ltv_to_cac_ratio = round(direct_ltv_2 / cac_per_client, 2)
        if ltv_to_cac_ratio >= 3.0:
            health_status = "HEALTHY (Бизнес устойчив, высокая отдача от маркетинга)"
        elif ltv_to_cac_ratio >= 2.0:
            health_status = "WARNING (Приемлемо, но маржинальность под давлением)"
        elif ltv_to_cac_ratio >= 1.0:
            health_status = "CRITICAL (Маркетинг окупается в ноль, нет прибыли на масштабе)"
        else:
            health_status = "UNPROFITABLE (Привлечение убыточно, LTV не покрывает CAC)"
    else:
        ltv_to_cac_ratio = None
        health_status = None

    return {
        "basic_ltv": basic_ltv,
        "direct_ltv_1": direct_ltv_1,
        "gross_margin_pct": gross_margin_pct,
        "direct_ltv_2": direct_ltv_2,
        "contribution_margin_pct": contribution_margin_pct,
        "net_ltv": net_ltv,
        "net_margin_pct": net_margin_pct,
        "cac_per_client": cac_per_client if has_cac else 0.0,
        "ltv_to_cac_ratio": ltv_to_cac_ratio,
        "health_status": health_status
    }

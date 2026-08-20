"""
Генератор автономного HTML-дашборда (report_html.py) в стиле Mindbox.
Поддерживает светлую и темную темы (Dark Mode) с переключателем и сохранением в localStorage.
- 100% самодостаточный HTML (инлайн CSS, SVG-графики, 0 внешних CDN-ссылок)
- Палитра Dark: #0B0F19 (фон), #151C2C (карточки), #232D42 (бордеры), #F1F5F9 (текст), #6366F1 (акцент)
- Палитра Light: #F7F8FA (фон), #FFFFFF (карточки), #E8EAEF (бордеры), #16182B (текст), #4A3AFF (акцент)
- Адаптивная тепловая карта через CSS color-mix (автоматически идеальна в обеих темах)
- Автономные SVG-графики со стилизацией через CSS-переменные
- Каскад маржинальности юнит-экономики и RFM-сегментация
"""

import pandas as pd
import math
from datetime import datetime
from typing import Dict, Any, List, Optional
from src.report import detect_data_completeness, detect_retention_anomalies


def generate_retention_curve_svg(avg_ret_series: pd.Series, cols: List[int]) -> str:
    """Генерирует чистый SVG-график кривой среднего удержания, адаптирующийся под тему."""
    w, h = 480, 220
    pad_l, pad_r, pad_t, pad_b = 45, 20, 25, 35
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    points = []
    max_val = 100.0
    for i, p in enumerate(cols):
        val = avg_ret_series.get(p, 0.0)
        x = pad_l + (i / max(1, len(cols) - 1)) * plot_w
        y = pad_t + plot_h - (val / max_val) * plot_h
        points.append((x, y, val, p))

    grid_lines = []
    for y_val in [0, 25, 50, 75, 100]:
        y_pos = pad_t + plot_h - (y_val / max_val) * plot_h
        grid_lines.append(
            f'<line x1="{pad_l}" y1="{y_pos}" x2="{w - pad_r}" y2="{y_pos}" stroke="var(--border)" stroke-width="1" stroke-dasharray="3,3" />'
            f'<text x="{pad_l - 8}" y="{y_pos + 4}" font-size="11" fill="var(--text-dim)" text-anchor="end">{y_val}%</text>'
        )

    for x, y, val, p in points:
        grid_lines.append(f'<text x="{x}" y="{h - 12}" font-size="11" fill="var(--text-dim)" text-anchor="middle">M{p}</text>')

    pts_str = " ".join([f"{x},{y}" for x, y, _, _ in points])
    area_pts = f"{pad_l},{pad_t + plot_h} " + pts_str + f" {points[-1][0]},{pad_t + plot_h}"

    dots = []
    for x, y, val, p in points:
        dots.append(
            f'<circle cx="{x}" cy="{y}" r="4" fill="var(--accent)" stroke="var(--surface)" stroke-width="2" />'
            f'<title>M{p}: {val:.1f}%</title>'
        )

    return f"""
    <svg viewBox="0 0 {w} {h}" width="100%" height="{h}" class="chart-svg">
        {''.join(grid_lines)}
        <polygon points="{area_pts}" fill="var(--accent)" fill-opacity="0.15" />
        <polyline points="{pts_str}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
        {''.join(dots)}
    </svg>
    """


def generate_revenue_bars_svg(cohort_rev_df: pd.DataFrame) -> str:
    """Генерирует чистый SVG-график выручки по когортам."""
    w, h = 480, 220
    pad_l, pad_r, pad_t, pad_b = 60, 20, 25, 45
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    rev_by_cohort = cohort_rev_df.sum(axis=1)
    cohorts = list(rev_by_cohort.index)
    if not cohorts:
        return "<svg></svg>"
    
    max_rev = max(rev_by_cohort.max(), 1.0)
    bar_width = min(28, max(8, plot_w / (len(cohorts) * 1.6)))
    gap = plot_w / len(cohorts)

    grid_lines = []
    for step in range(4):
        val = (max_rev / 3) * step
        y_pos = pad_t + plot_h - (val / max_rev) * plot_h
        grid_lines.append(
            f'<line x1="{pad_l}" y1="{y_pos}" x2="{w - pad_r}" y2="{y_pos}" stroke="var(--border)" stroke-width="1" stroke-dasharray="3,3" />'
            f'<text x="{pad_l - 8}" y="{y_pos + 4}" font-size="11" fill="var(--text-dim)" text-anchor="end">{int(val/1000)}k</text>'
        )

    bars = []
    for i, c in enumerate(cohorts):
        r_val = rev_by_cohort[c]
        b_h = (r_val / max_rev) * plot_h
        x = pad_l + i * gap + (gap - bar_width) / 2
        y = pad_t + plot_h - b_h
        label = str(c)[2:]
        bars.append(
            f'<rect x="{x}" y="{y}" width="{bar_width}" height="{b_h}" rx="3" fill="var(--accent)" fill-opacity="0.85">'
            f'<title>{c}: {r_val:,.0f} руб.</title></rect>'
            f'<text x="{x + bar_width/2}" y="{h - 18}" font-size="10" fill="var(--text-dim)" text-anchor="middle" transform="rotate(-30 {x + bar_width/2} {h - 18})">{label}</text>'
        )

    return f"""
    <svg viewBox="0 0 {w} {h}" width="100%" height="{h}" class="chart-svg">
        {''.join(grid_lines)}
        {''.join(bars)}
    </svg>
    """


def generate_rfm_donut_svg(rfm_summary: pd.DataFrame) -> str:
    """Генерирует кольцевую SVG диаграмму RFM-сегментов."""
    size = 220
    cx, cy, r_out, r_in = 110, 110, 85, 55
    colors = ["var(--accent)", "var(--positive)", "#3B82F6", "var(--warning)", "var(--negative)"]
    
    total_clients = rfm_summary["client_count"].sum()
    if total_clients == 0:
        return "<svg></svg>"

    paths = []
    current_angle = -90.0

    for idx, row in rfm_summary.iterrows():
        pct = row["client_share_pct"] / 100.0
        angle = pct * 360.0
        if angle <= 0:
            continue
            
        start_rad = math.radians(current_angle)
        end_rad = math.radians(current_angle + angle - 0.5)
        
        x1_out = cx + r_out * math.cos(start_rad)
        y1_out = cy + r_out * math.sin(start_rad)
        x2_out = cx + r_out * math.cos(end_rad)
        y2_out = cy + r_out * math.sin(end_rad)
        
        x1_in = cx + r_in * math.cos(end_rad)
        y1_in = cy + r_in * math.sin(end_rad)
        x2_in = cx + r_in * math.cos(start_rad)
        y2_in = cy + r_in * math.sin(start_rad)
        
        large_arc = 1 if angle > 180 else 0
        color = colors[idx % len(colors)]
        
        d = (
            f"M {x1_out} {y1_out} "
            f"A {r_out} {r_out} 0 {large_arc} 1 {x2_out} {y2_out} "
            f"L {x1_in} {y1_in} "
            f"A {r_in} {r_in} 0 {large_arc} 0 {x2_in} {y2_in} Z"
        )
        paths.append(
            f'<path d="{d}" fill="{color}">'
            f'<title>{row["segment"]}: {row["client_share_pct"]}% ({row["client_count"]} чел.)</title></path>'
        )
        current_angle += angle

    return f"""
    <svg viewBox="0 0 {size} {size}" width="{size}" height="{size}">
        {''.join(paths)}
        <text x="{cx}" y="{cy - 4}" font-size="16" font-weight="600" fill="var(--text)" text-anchor="middle">{total_clients}</text>
        <text x="{cx}" y="{cy + 14}" font-size="11" fill="var(--text-dim)" text-anchor="middle">клиентов</text>
    </svg>
    """


def generate_html_report(
    behavior_metrics: Dict[str, Any],
    costs_breakdown: Dict[str, Any],
    model_results: Dict[str, Any],
    cohort_matrix: pd.DataFrame,
    rfm_summary: pd.DataFrame,
    clean_df: Optional[pd.DataFrame] = None,
    output_path: str = "output/report.html",
    source_filename: str = "sample_orders.csv",
    engine_name: str = "Pandas Core Engine"
) -> str:
    """
    Формирует красивый автономный HTML-отчет в дизайн-системе Mindbox с поддержкой Dark Mode.
    """
    now_str = datetime.now().strftime("%d.%m.%Y в %H:%M")
    total_orders = len(clean_df) if clean_df is not None else 0

    # 1. Полнота данных
    completeness = detect_data_completeness(clean_df) if clean_df is not None else {
        "cogs": model_results.get("direct_ltv_1") is not None,
        "acquisition_cost": model_results.get("ltv_to_cac_ratio") is not None,
        "delivery_cost": True,
        "discount_amount": True,
        "mode": "full" if model_results.get("direct_ltv_1") is not None else "partial"
    }
    is_full = completeness["mode"] == "full"

    # 2. Доступность когорт
    if clean_df is not None and "order_date" in clean_df.columns:
        last_date = pd.to_datetime(clean_df["order_date"]).max()
        last_y, last_m = last_date.year, last_date.month
        availability = {}
        for c in cohort_matrix.index:
            parts = str(c).split("-")
            availability[str(c)] = max(0, (last_y - int(parts[0])) * 12 + (last_m - int(parts[1])))
    else:
        availability = behavior_metrics.get("availability", {str(c): 8 for c in cohort_matrix.index})

    cols = [c for c in range(9) if c in cohort_matrix.columns or any(availability.get(str(k), 0) >= c for k in cohort_matrix.index)]
    if not cols:
        cols = list(range(9))

    # 3. Карточки KPI
    kpi_cards_html = []
    if is_full:
        ratio = model_results["ltv_to_cac_ratio"]
        ratio_color = "var(--positive)" if ratio >= 3.0 else ("var(--warning)" if ratio >= 2.0 else "var(--negative)")
        
        cards_data = [
            {"title": "Базовый LTV", "val": f"{model_results['basic_ltv']:,.0f} ₽", "sub": "Выручка с привлеченного клиента за весь срок жизни", "color": "var(--text)"},
            {"title": "Чистый LTV", "val": f"{model_results['net_ltv']:,.0f} ₽", "sub": f"Чистая прибыль (маржинальность {model_results['net_margin_pct']:.1f}%)", "color": "var(--text)"},
            {"title": "Стоимость привлечения (CAC)", "val": f"{model_results['cac_per_client']:,.0f} ₽", "sub": "Маркетинговые затраты на привлечение 1 клиента", "color": "var(--text)"},
            {"title": "Отношение LTV к CAC", "val": f"{ratio:.2f}x", "sub": "Возврат инвестиций (норматив ≥ 3.0x)", "color": ratio_color}
        ]
    else:
        cards_data = [
            {"title": "Базовый LTV", "val": f"{model_results['basic_ltv']:,.0f} ₽", "sub": "Выручка с привлеченного клиента за весь срок жизни", "color": "var(--text)"},
            {"title": "Средний чек (AOV)", "val": f"{behavior_metrics['overall_aov']:,.0f} ₽", "sub": "Средняя сумма одной покупки", "color": "var(--text)"},
            {"title": "Частота покупок", "val": f"{behavior_metrics['overall_frequency']:.2f}", "sub": "Среднее число заказов на одного клиента", "color": "var(--text)"},
            {"title": "Срок жизни (Lifetime)", "val": f"{behavior_metrics['lifetime_months']:.1f} мес.", "sub": "Взвешенный период покупательской активности", "color": "var(--text)"}
        ]

    for cd in cards_data:
        kpi_cards_html.append(f"""
        <div class="kpi-card">
            <div class="kpi-title">{cd['title']}</div>
            <div class="kpi-value" style="color: {cd['color']}">{cd['val']}</div>
            <div class="kpi-sub">{cd['sub']}</div>
        </div>
        """)

    # 4. Тепловая карта удержания (Heatmap M0-M8) с адаптивным color-mix
    heatmap_rows = []
    for c in cohort_matrix.index:
        max_p = availability.get(str(c), 8)
        base_size = cohort_matrix.loc[c, 0] if 0 in cohort_matrix.columns else 1
        cells_html = [f'<td class="cohort-name">{c}</td>', f'<td class="cohort-base">{int(base_size)}</td>']
        
        for p in cols:
            if p > max_p:
                cells_html.append('<td class="heat-cell heat-empty">—</td>')
            else:
                val = cohort_matrix.loc[c, p] if p in cohort_matrix.columns else 0
                pct = (val / base_size * 100.0) if base_size > 0 else 0.0
                mix_pct = min(100.0, pct * 1.1)
                text_cls = "text-white" if pct > 38.0 else ""
                cells_html.append(f"""
                <td class="heat-cell {text_cls}" style="background-color: color-mix(in srgb, var(--accent) {mix_pct:.1f}%, var(--heat-base));">
                    <div class="pct-val">{pct:.1f}%</div>
                    <div class="abs-val">{int(val)}</div>
                </td>
                """)
        heatmap_rows.append(f"<tr>{''.join(cells_html)}</tr>")

    # Строки средних
    avg_cells = ['<td class="cohort-name" style="font-weight:600;">Среднее удержание</td>', '<td class="cohort-base">—</td>']
    cnt_cells = ['<td class="cohort-name" style="font-weight:600;">Когорт в расчёте</td>', '<td class="cohort-base">—</td>']
    
    avg_ret_series = {}
    for p in cols:
        eligible = [c for c in cohort_matrix.index if availability.get(str(c), 0) >= p]
        cnt_cells.append(f'<td class="summary-cell">{len(eligible)}</td>')
        if eligible:
            rets = [
                (cohort_matrix.loc[c, p] / cohort_matrix.loc[c, 0] * 100.0)
                for c in eligible if 0 in cohort_matrix.columns and cohort_matrix.loc[c, 0] > 0
            ]
            avg_p = sum(rets) / len(rets) if rets else 0.0
            avg_ret_series[p] = avg_p
            avg_cells.append(f'<td class="summary-cell" style="font-weight:600; color: var(--accent);">{avg_p:.1f}%</td>')
        else:
            avg_ret_series[p] = 0.0
            avg_cells.append('<td class="summary-cell">—</td>')

    # SVG Графики
    ret_curve_svg = generate_retention_curve_svg(avg_ret_series, cols)
    cohort_rev_df = cohort_matrix.copy()
    rev_bars_svg = generate_revenue_bars_svg(cohort_rev_df)
    rfm_donut_svg = generate_rfm_donut_svg(rfm_summary)

    # Блок аномалий
    anomalies = detect_retention_anomalies(cohort_matrix, availability, max_periods=len(cols))
    if anomalies:
        anomalies_items = "".join([f"<li>{a}</li>" for a in anomalies])
        anomalies_html = f'<ul class="anomalies-list">{anomalies_items}</ul>'
    else:
        anomalies_html = '<div class="text-dim">Значимых скачков удержания (отрицательного отвала) не обнаружено.</div>'

    # Таблица RFM
    rfm_rows_html = []
    colors_rfm = ["var(--accent)", "var(--positive)", "#3B82F6", "var(--warning)", "var(--negative)"]
    for idx, row in rfm_summary.iterrows():
        dot_color = colors_rfm[idx % len(colors_rfm)]
        rfm_rows_html.append(f"""
        <tr>
            <td><span class="rfm-dot" style="background: {dot_color};"></span><strong>{row['segment']}</strong></td>
            <td class="tabular">{row['client_count']:,}</td>
            <td class="tabular">{row['client_share_pct']:.1f}%</td>
            <td class="tabular" style="font-weight:600;">{row['revenue_share_pct']:.1f}%</td>
            <td class="tabular">{row['avg_recency']:.0f} дн.</td>
            <td class="tabular">{row['avg_frequency']:.1f}</td>
            <td class="tabular">{row['avg_monetary']:,.0f} ₽</td>
        </tr>
        """)

    # Каскад юнит-экономики (Водопад)
    if is_full:
        cogs_val = costs_breakdown.get('cogs_per_client', 0.0)
        opex_val = costs_breakdown.get('delivery_per_client', 0.0) + costs_breakdown.get('payment_fee_per_client', 0.0)
        cac_val = model_results.get('cac_per_client', 0.0)
        net_val = model_results.get('net_ltv', 0.0)
        basic_val = model_results.get('basic_ltv', 1.0)
        
        cogs_pct = (cogs_val / basic_val * 100) if basic_val > 0 else 0
        opex_pct = (opex_val / basic_val * 100) if basic_val > 0 else 0
        cac_pct = (cac_val / basic_val * 100) if basic_val > 0 else 0
        net_pct = (net_val / basic_val * 100) if basic_val > 0 else 0

        cascade_bar_html = f"""
        <div class="waterfall-bar-container">
            <div class="w-segment" style="width: {net_pct}%; background: var(--positive);" title="Чистый LTV: {net_val:,.0f} ₽ ({net_pct:.1f}%)"></div>
            <div class="w-segment" style="width: {cac_pct}%; background: var(--warning);" title="CAC: {cac_val:,.0f} ₽ ({cac_pct:.1f}%)"></div>
            <div class="w-segment" style="width: {opex_pct}%; background: #3B82F6;" title="Операционные: {opex_val:,.0f} ₽ ({opex_pct:.1f}%)"></div>
            <div class="w-segment" style="width: {cogs_pct}%; background: var(--negative);" title="Себестоимость COGS: {cogs_val:,.0f} ₽ ({cogs_pct:.1f}%)"></div>
        </div>
        <div class="waterfall-legend">
            <div><span class="w-dot" style="background: var(--positive);"></span>Чистая прибыль ({net_pct:.1f}%)</div>
            <div><span class="w-dot" style="background: var(--warning);"></span>Маркетинг CAC ({cac_pct:.1f}%)</div>
            <div><span class="w-dot" style="background: #3B82F6;"></span>Доставка и эквайринг ({opex_pct:.1f}%)</div>
            <div><span class="w-dot" style="background: var(--negative);"></span>Себестоимость COGS ({cogs_pct:.1f}%)</div>
        </div>
        """
        ue_rows_html = f"""
        <tr><td><strong>Базовый LTV</strong></td><td class="tabular" style="font-weight:600;">{basic_val:,.2f} ₽</td><td class="tabular">100.0%</td><td>Выручка с привлеченного клиента за весь срок жизни</td></tr>
        <tr><td>Себестоимость товаров (COGS)</td><td class="tabular">−{cogs_val:,.2f} ₽</td><td class="tabular">{cogs_pct:.1f}%</td><td>Себестоимость по принципу начисления</td></tr>
        <tr class="row-subtotal"><td><strong>Прямой LTV 1 (Валовая прибыль)</strong></td><td class="tabular" style="font-weight:600;">{model_results['direct_ltv_1']:,.2f} ₽</td><td class="tabular">{model_results['gross_margin_pct']:.1f}%</td><td>Валовая прибыль до вычета логистики и эквайринга</td></tr>
        <tr><td>Операционные расходы (логистика + эквайринг)</td><td class="tabular">−{opex_val:,.2f} ₽</td><td class="tabular">{opex_pct:.1f}%</td><td>Прямые переменные расходы на обслуживание заказов</td></tr>
        <tr class="row-subtotal"><td><strong>Прямой LTV 2 (Вкладная маржа)</strong></td><td class="tabular" style="font-weight:600;">{model_results['direct_ltv_2']:,.2f} ₽</td><td class="tabular">{model_results['contribution_margin_pct']:.1f}%</td><td>Вкладная маржа (Contribution Margin)</td></tr>
        <tr><td>Стоимость привлечения (CAC)</td><td class="tabular">−{cac_val:,.2f} ₽</td><td class="tabular">{cac_pct:.1f}%</td><td>Маркетинговые затраты на 1 клиента</td></tr>
        <tr class="row-highlight"><td><strong>Чистый LTV</strong></td><td class="tabular" style="font-weight:700; color: var(--positive);">{net_val:,.2f} ₽</td><td class="tabular" style="font-weight:700; color: var(--positive);">{net_pct:.1f}%</td><td><strong>Чистая прибыль бизнеса</strong> с клиента после маркетинга</td></tr>
        """
        enrichment_box_html = ""
    else:
        cascade_bar_html = """
        <div class="waterfall-bar-container" style="background:var(--border);">
            <div class="w-segment" style="width: 100%; background: var(--text-dim);" title="Только Базовая Выручка (нет данных о COGS/CAC)"></div>
        </div>
        <div class="text-dim" style="margin-top:8px;">* Водопад маржинальности доступен только при наличии полей себестоимости и маркетинга.</div>
        """
        ue_rows_html = f"""
        <tr><td><strong>Базовый LTV</strong></td><td class="tabular" style="font-weight:600;">{model_results['basic_ltv']:,.2f} ₽</td><td class="tabular">100.0%</td><td>Выручка с привлеченного клиента за весь срок жизни</td></tr>
        <tr class="row-disabled"><td>Себестоимость товаров (COGS)</td><td class="tabular">—</td><td class="tabular">—</td><td>Нет данных в выгрузке</td></tr>
        <tr class="row-disabled"><td>Прямой LTV 1 (Валовая прибыль)</td><td class="tabular">—</td><td class="tabular">—</td><td>Требуются данные COGS</td></tr>
        <tr><td>Операционные расходы</td><td class="tabular">{costs_breakdown['delivery_per_client'] + costs_breakdown['payment_fee_per_client']:,.2f} ₽</td><td class="tabular">—</td><td>Эквайринг и обработка</td></tr>
        <tr class="row-disabled"><td>Прямой LTV 2 (Вкладная маржа)</td><td class="tabular">—</td><td class="tabular">—</td><td>Требуются данные COGS</td></tr>
        <tr class="row-disabled"><td>Стоимость привлечения (CAC)</td><td class="tabular">—</td><td class="tabular">—</td><td>Нет данных в выгрузке</td></tr>
        <tr class="row-disabled"><td>Чистый LTV</td><td class="tabular">—</td><td class="tabular">—</td><td>Требуются COGS и CAC</td></tr>
        """
        enrichment_box_html = """
        <div class="enrichment-card">
            <div class="card-title" style="font-size:15px;">Что добавить в выгрузку для полного расчёта:</div>
            <ul style="margin: 8px 0 0 18px; font-size: 13px; color: var(--text-dim);">
                <li><strong>Себестоимость товаров (COGS):</strong> позволит рассчитать реальную валовую прибыль (Прямой LTV 1) и вкладную маржу.</li>
                <li><strong>Затраты на маркетинг (CAC):</strong> позволят рассчитать окупаемость рекламы (LTV/CAC) и Чистый LTV компании.</li>
            </ul>
        </div>
        """

    # Предупреждающая плашка в режиме partial
    if not is_full:
        warning_banner_html = """
        <div class="warning-banner">
            <div class="warning-icon">⚠️</div>
            <div>
                <strong>Режим частичных данных:</strong> в исходном файле отсутствуют сведения о себестоимости и стоимости привлечения (CAC).
                Блоки валовой маржи и маркетинговой окупаемости не рассчитывались, чтобы исключить искажение управленческих решений.
            </div>
        </div>
        """
    else:
        warning_banner_html = ""

    html_content = f"""<!DOCTYPE html>
<html lang="ru" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Дашборд юнит-экономики | {source_filename}</title>
    <style>
        :root {{
            --bg: #0B0F19;
            --surface: #151C2C;
            --border: #232D42;
            --text: #F1F5F9;
            --text-dim: #94A3B8;
            --accent: #6366F1;
            --accent-hover: #4F46E5;
            --positive: #10B981;
            --warning: #F59E0B;
            --negative: #EF4444;
            --heat-base: #151C2C;
            --banner-bg: #422006;
            --banner-border: #78350F;
            --banner-text: #FDE68A;
            --badge-bg: #1E1B4B;
            --subtotal-bg: #1E293B;
            --highlight-bg: #064E3B;
            --enrichment-bg: #0F172A;
        }}
        [data-theme="light"] {{
            --bg: #F7F8FA;
            --surface: #FFFFFF;
            --border: #E8EAEF;
            --text: #16182B;
            --text-dim: #6B7280;
            --accent: #4A3AFF;
            --accent-hover: #3B2ECC;
            --positive: #00B856;
            --warning: #F5A623;
            --negative: #E5484D;
            --heat-base: #F7F8FA;
            --banner-bg: #FFFBEB;
            --banner-border: #FDE68A;
            --banner-text: #92400E;
            --badge-bg: #EEF2FF;
            --subtotal-bg: #F7F8FA;
            --highlight-bg: #F0FDF4;
            --enrichment-bg: #F8FAFC;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; transition: background-color 0.2s, border-color 0.2s, color 0.1s; }}
        body {{
            font-family: -apple-system, "Segoe UI", Roboto, Inter, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            font-size: 14px;
            line-height: 1.5;
            padding: 32px 16px;
        }}
        .tabular {{ font-variant-numeric: tabular-nums; }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        /* Header */
        .header-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .header-title {{ font-size: 22px; font-weight: 600; color: var(--text); }}
        .header-meta {{ font-size: 13px; color: var(--text-dim); margin-top: 4px; }}
        .header-controls {{ display: flex; gap: 12px; align-items: center; }}
        .engine-badge {{
            background: var(--badge-bg);
            color: var(--accent);
            padding: 6px 12px;
            border-radius: 6px;
            font-weight: 500;
            font-size: 13px;
        }}
        .theme-toggle {{
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .theme-toggle:hover {{ background: var(--border); }}
        /* Banner */
        .warning-banner {{
            background: var(--banner-bg);
            border: 1px solid var(--banner-border);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 20px;
            display: flex;
            align-items: flex-start;
            gap: 12px;
            color: var(--banner-text);
            font-size: 13px;
        }}
        .warning-icon {{ font-size: 18px; }}
        /* Cards & Grids */
        .grid-4 {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 20px;
        }}
        .grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        .kpi-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }}
        .kpi-title {{ font-size: 13px; color: var(--text-dim); }}
        .kpi-value {{ font-size: 28px; font-weight: 600; margin: 6px 0 4px 0; font-variant-numeric: tabular-nums; }}
        .kpi-sub {{ font-size: 12px; color: var(--text-dim); }}
        .card-title {{ font-size: 17px; font-weight: 600; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; }}
        .card-expl {{ font-size: 13px; color: var(--text-dim); margin-top: 14px; line-height: 1.4; }}
        /* Tables */
        table.data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        table.data-table th {{
            text-align: left;
            padding: 10px 12px;
            color: var(--text-dim);
            font-weight: 500;
            border-bottom: 1px solid var(--border);
        }}
        table.data-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid var(--border);
        }}
        table.data-table tr:last-child td {{ border-bottom: none; }}
        .row-subtotal {{ background: var(--subtotal-bg); }}
        .row-highlight {{ background: var(--highlight-bg); border-top: 2px solid var(--positive); }}
        .row-disabled {{ color: var(--text-dim); opacity: 0.6; }}
        /* Heatmap */
        .heatmap-table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 3px;
            font-size: 12px;
            text-align: center;
        }}
        .heatmap-table th {{
            padding: 8px 4px;
            color: var(--text-dim);
            font-weight: 500;
            font-size: 12px;
        }}
        .cohort-name {{ text-align: left; font-weight: 500; padding: 6px 8px; }}
        .cohort-base {{ font-weight: 500; color: var(--text-dim); padding: 6px; font-variant-numeric: tabular-nums; }}
        .heat-cell {{
            padding: 6px 4px;
            border-radius: 4px;
            min-width: 52px;
            font-variant-numeric: tabular-nums;
            color: var(--text);
        }}
        .heat-cell.text-white {{ color: #FFFFFF !important; }}
        .heat-empty {{ color: var(--text-dim); background: var(--surface); }}
        .pct-val {{ font-size: 12px; font-weight: 600; }}
        .abs-val {{ font-size: 10px; margin-top: 2px; opacity: 0.85; }}
        .summary-cell {{ padding: 8px 4px; font-size: 12px; font-variant-numeric: tabular-nums; border-top: 1px solid var(--border); }}
        /* Waterfall */
        .waterfall-bar-container {{
            display: flex;
            height: 24px;
            border-radius: 6px;
            overflow: hidden;
            margin: 14px 0 10px 0;
            background: var(--border);
        }}
        .w-segment {{ height: 100%; transition: width 0.3s ease; }}
        .waterfall-legend {{
            display: flex;
            gap: 16px;
            font-size: 12px;
            color: var(--text-dim);
            flex-wrap: wrap;
        }}
        .w-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }}
        .rfm-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; }}
        .anomalies-list {{ margin: 8px 0 0 18px; font-size: 13px; color: var(--text); }}
        .anomalies-list li {{ margin-bottom: 4px; }}
        .enrichment-card {{ background: var(--enrichment-bg); border: 1px dashed var(--border); border-radius: 8px; padding: 14px; margin-top: 14px; }}
        @media (max-width: 900px) {{
            .grid-4 {{ grid-template-columns: 1fr 1fr; }}
            .grid-2 {{ grid-template-columns: 1fr; }}
        }}
        @media (max-width: 600px) {{
            .grid-4 {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header-card">
            <div>
                <div class="header-title">Аналитический дашборд юнит-экономики</div>
                <div class="header-meta">Файл: <strong>{source_filename}</strong> • Обработано: <strong>{total_orders:,}</strong> заказов • Дата: {now_str}</div>
            </div>
            <div class="header-controls">
                <button class="theme-toggle" id="themeBtn" onclick="toggleTheme()">🌙 Тёмная</button>
                <div class="engine-badge">⚡ {engine_name}</div>
            </div>
        </div>

        {warning_banner_html}

        <!-- 4 KPI Cards -->
        <div class="grid-4">
            {''.join(kpi_cards_html)}
        </div>

        <!-- Heatmap & Retention Curve -->
        <div class="card">
            <div class="card-title">
                <span>Матрица удержания клиентов (M0 – M8)</span>
                <span style="font-size: 12px; color: var(--text-dim); font-weight: normal;">% доля / абс. чел.</span>
            </div>
            <div style="overflow-x: auto;">
                <table class="heatmap-table">
                    <thead>
                        <tr>
                            <th style="text-align:left;">Когорта</th>
                            <th>M0 База</th>
                            {''.join([f'<th>M{p}</th>' for p in cols])}
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(heatmap_rows)}
                        <tr>{''.join(avg_cells)}</tr>
                        <tr>{''.join(cnt_cells)}</tr>
                    </tbody>
                </table>
            </div>
            <div class="card-expl">
                Тепловая карта показывает процент клиентов когорты, вернувшихся за повторными покупками в последующие месяцы.
                Прочерк (—) означает, что период для когорты еще не наступил на момент последней даты в базе.
            </div>
        </div>

        <!-- 2 Charts Grid -->
        <div class="grid-2">
            <div class="card">
                <div class="card-title">Динамика удержания (Retention Curve)</div>
                {ret_curve_svg}
                <div class="card-expl">Средневзвешенный процент повторных покупок. Наибольший отвал происходит на интервале M0 → M1.</div>
            </div>
            <div class="card">
                <div class="card-title">Выручка по когортам</div>
                {rev_bars_svg}
                <div class="card-expl">Суммарная выручка, сгенерированная каждой когортой за все доступные периоды жизни.</div>
            </div>
        </div>

        <!-- Unit Economics Cascade -->
        <div class="card">
            <div class="card-title">Каскад юнит-экономики (на 1 привлеченного клиента)</div>
            {cascade_bar_html}
            <div style="margin-top: 14px;">
                <table class="data-table">
                    <thead>
                        <tr><th>Уровень маржинальности</th><th>Значение</th><th>Доля</th><th>Интерпретация</th></tr>
                    </thead>
                    <tbody>
                        {ue_rows_html}
                    </tbody>
                </table>
            </div>
            {enrichment_box_html}
            <div class="card-expl">
                Показывает пошаговое вычитание затрат из Базового LTV. 
                Отношение Вкладной маржи (Прямого LTV 2) к CAC выше 3.0x считается безопасным нормативом для масштабирования рекламы.
            </div>
        </div>

        <!-- RFM Segmentation & Anomalies -->
        <div class="grid-2">
            <div class="card">
                <div class="card-title">RFM-сегментация клиентской базы</div>
                <div style="display:flex; justify-content:center; margin-bottom:14px;">
                    {rfm_donut_svg}
                </div>
                <table class="data-table">
                    <thead>
                        <tr><th>Сегмент</th><th>Клиенты</th><th>Доля базы</th><th>Выручка</th><th>Давность</th><th>Частота</th><th>Ср. чек</th></tr>
                    </thead>
                    <tbody>
                        {''.join(rfm_rows_html)}
                    </tbody>
                </table>
                <div class="card-expl">Разбивка клиентов по давности (R), частоте (F) и суммарной выручке (M). VIP и Loyal формируют ядро маржи.</div>
            </div>

            <div class="card">
                <div class="card-title">Самопроверка и детекция аномалий</div>
                <div style="margin-bottom: 16px;">
                    <div style="font-size:13px; font-weight:600; margin-bottom:6px;">Самопроверка расчета Базового LTV:</div>
                    <div style="font-size:13px; color:var(--text); line-height:1.6;">
                        • Накопительный факт (Σ Выручка / M0): <strong>{behavior_metrics['basic_ltv']:,.2f} ₽</strong><br>
                        • По формуле (AOV × Freq × Lifetime): <strong>{behavior_metrics['basic_ltv_formula_check']:,.2f} ₽</strong><br>
                        • Расхождение: <strong>{behavior_metrics['ltv_discrepancy_pct']}%</strong>
                    </div>
                </div>
                <div>
                    <div style="font-size:13px; font-weight:600; margin-bottom:6px;">Всплески удержания (отрицательный отвал):</div>
                    {anomalies_html}
                </div>
                <div class="card-expl">
                    Отрицательный отвал указывает на сезонные всплески повторных покупок или реактивацию спящих клиентов CRM-рассылками.
                </div>
            </div>
        </div>
    </div>

    <script>
        function applyTheme(theme) {{
            document.documentElement.setAttribute('data-theme', theme);
            const btn = document.getElementById('themeBtn');
            if (btn) {{
                btn.innerHTML = theme === 'dark' ? '🌙 Тёмная' : '☀️ Светлая';
            }}
            try {{ localStorage.setItem('theme_preference', theme); }} catch(e) {{}}
        }}
        function toggleTheme() {{
            const current = document.documentElement.getAttribute('data-theme') || 'dark';
            const next = current === 'dark' ? 'light' : 'dark';
            applyTheme(next);
        }}
        (function initTheme() {{
            try {{
                const saved = localStorage.getItem('theme_preference');
                if (saved) {{
                    applyTheme(saved);
                }} else {{
                    applyTheme('dark');
                }}
            }} catch(e) {{
                applyTheme('dark');
            }}
        }})();
    </script>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_path

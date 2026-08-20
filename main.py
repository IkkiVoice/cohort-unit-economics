"""
Точка входа в проект cohort-unit-economics.
Запуск полного пайплайна расчета юнит-экономики, когортного анализа и RFM-сегментации.
Поддерживает генерацию Markdown и автономного HTML-дашборда (--html, --open).
"""

import argparse
import os
import sys
import webbrowser
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.generate import generate_retail_dataset
from src.prepare import clean_orders_data
from src.cohorts import build_cohort_matrices
from src.cohorts_sql import build_cohort_matrices_sql
from src.behavior import calculate_behavior_metrics
from src.costs import calculate_costs_breakdown
from src.model import build_unit_economics_model
from src.rfm import calculate_rfm_segments
from src.report import generate_full_report, detect_data_completeness
from src.report_html import generate_html_report


def run_pipeline(
    input_csv: str = None,
    output_report: str = "output/report.md",
    use_sql: bool = False,
    gen_html: bool = False,
    open_in_browser: bool = False
):
    print("=" * 60)
    print("   COHORT & UNIT ECONOMICS ENGINE (Retail / E-Commerce)")
    print("=" * 60)

    # 1. Генерация или проверка данных
    if not input_csv or not os.path.exists(input_csv):
        print("[*] Входной файл не указан или не найден. Генерируем синтетический датасет...")
        os.makedirs("data", exist_ok=True)
        input_csv = generate_retail_dataset(output_path="data/sample_orders.csv")
        print(f"[+] Синтетические данные созданы: {input_csv}")

    # 2. Очистка и склейка профилей
    print(f"[*] 1. Подготовка и дедупликация данных ({input_csv})...")
    clean_df = clean_orders_data(input_csv)
    print(f"[+] Обработано заказов: {len(clean_df)}, Уникальных клиентов: {clean_df['client_uid'].nunique()}")

    # 3. Определение полноты исходных данных
    completeness = detect_data_completeness(clean_df)
    print(f"[*] 2. Аудит полноты данных: режим '{completeness['mode']}' (COGS: {completeness['cogs']}, CAC: {completeness['acquisition_cost']})")

    # 4. Расчет когорт (Python или SQL)
    engine_name = "SQLite" if use_sql else "Pandas"
    if use_sql:
        print(f"[*] 3. Расчет когорт через движок {engine_name}...")
        cohort_clients, cohort_revenue, period_summary = build_cohort_matrices_sql(clean_df)
    else:
        print(f"[*] 3. Расчет когорт через движок {engine_name}...")
        cohort_clients, cohort_revenue, period_summary = build_cohort_matrices(clean_df)

    # 5. Метрики поведения (Retention / Churn / AOV)
    print("[*] 4. Расчет поведенческих метрик (Retention / Churn / AOV)...")
    last_date = pd.to_datetime(clean_df["order_date"]).max()
    behavior_metrics = calculate_behavior_metrics(period_summary, cohort_clients, last_date)

    # 6. Себестоимость и расходы
    print("[*] 5. Расчет себестоимости и затрат на привлечение (CAC)...")
    costs_breakdown = calculate_costs_breakdown(clean_df, period_summary)

    # 7. Сборка модели юнит-экономики
    print("[*] 6. Сборка модели юнит-экономики...")
    model_results = build_unit_economics_model(behavior_metrics, costs_breakdown, completeness=completeness)

    # 8. RFM-сегментация
    print("[*] 7. RFM-сегментация клиентской базы...")
    rfm_df, rfm_summary = calculate_rfm_segments(clean_df)

    # 9. Генерация Markdown-отчета
    os.makedirs(os.path.dirname(output_report) or ".", exist_ok=True)
    report_file = generate_full_report(
        behavior_metrics=behavior_metrics,
        costs_breakdown=costs_breakdown,
        model_results=model_results,
        cohort_matrix=cohort_clients,
        rfm_summary=rfm_summary,
        clean_df=clean_df,
        output_path=output_report
    )
    print(f"[+] Markdown-отчет: {report_file}")

    # 10. Генерация автономного HTML-дашборда
    if gen_html or open_in_browser:
        html_out = output_report.replace(".md", ".html") if output_report.endswith(".md") else output_report + ".html"
        html_file = generate_html_report(
            behavior_metrics=behavior_metrics,
            costs_breakdown=costs_breakdown,
            model_results=model_results,
            cohort_matrix=cohort_clients,
            rfm_summary=rfm_summary,
            clean_df=clean_df,
            cohort_revenue=cohort_revenue,
            output_path=html_out,
            source_filename=os.path.basename(input_csv),
            engine_name=engine_name
        )
        print(f"[+] HTML-дашборд:  {html_file}")
        if open_in_browser:
            print(f"[*] Открываем HTML-дашборд в браузере: {os.path.abspath(html_file)}")
            webbrowser.open(f"file:///{os.path.abspath(html_file)}")

    print("=" * 60)
    print(f"[SUCCESS] Обработка завершена.")
    if model_results["health_status"]:
        print(f"Статус бизнеса: {model_results['health_status']}")
    else:
        print(f"Статус бизнеса: Не рассчитывался (режим частичных данных)")
    print(f"Базовый LTV:    {model_results['basic_ltv']:,.2f} руб.")
    if model_results["direct_ltv_2"] is not None:
        print(f"Прямой LTV 2:   {model_results['direct_ltv_2']:,.2f} руб.")
    if model_results["net_ltv"] is not None:
        print(f"Чистый LTV:     {model_results['net_ltv']:,.2f} руб.")
    if model_results["ltv_to_cac_ratio"] is not None:
        print(f"LTV / CAC:      {model_results['ltv_to_cac_ratio']}x")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Аналитический движок когорт и юнит-экономики")
    parser.add_argument("--input", type=str, default=None, help="Путь к исходному CSV файлу заказов")
    parser.add_argument("--output", type=str, default="output/report.md", help="Путь для сохранения отчета")
    parser.add_argument("--sql", action="store_true", help="Использовать SQLite SQL движок вместо Pandas")
    parser.add_argument("--html", action="store_true", help="Сгенерировать автономный HTML-дашборд")
    parser.add_argument("--open", action="store_true", help="Открыть сгенерированный HTML-дашборд в браузере")
    parser.add_argument("--generate-only", action="store_true", help="Только сгенерировать синтетический датасет")

    args = parser.parse_args()

    if args.generate_only:
        out = generate_retail_dataset(output_path=args.input or "data/sample_orders.csv")
        print(f"Сгенерирован датасет: {out}")
    else:
        run_pipeline(
            input_csv=args.input,
            output_report=args.output,
            use_sql=args.sql,
            gen_html=args.html,
            open_in_browser=args.open
        )

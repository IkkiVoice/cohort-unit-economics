"""
Тесты целостности пайплайна, строгого паритета SQL/Pandas, эталонной верификации Урока 3 и отчета v2.
"""

import unittest
import os
import shutil
import tempfile
import pandas as pd

from src.generate import generate_retail_dataset
from src.prepare import clean_orders_data
from src.cohorts import build_cohort_matrices
from src.cohorts_sql import build_cohort_matrices_sql
from src.behavior import calculate_behavior_metrics, compute_cohort_availability, compute_retention_summary
from src.costs import calculate_costs_breakdown
from src.model import build_unit_economics_model
from src.rfm import calculate_rfm_segments
from src.report import detect_data_completeness, generate_full_report


class TestCohortPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp()
        cls.sample_data = os.path.join(cls.test_dir, "test_orders.csv")
        generate_retail_dataset(num_customers=300, output_path=cls.sample_data)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_data_preparation_and_identity_resolution(self):
        df = clean_orders_data(self.sample_data)
        self.assertFalse(df.empty)
        self.assertIn("client_uid", df.columns)
        self.assertIn("cohort_month", df.columns)
        self.assertIn("period", df.columns)
        self.assertEqual((df["period"] < 0).sum(), 0)
        self.assertEqual((df["order_status"] == "cancelled").sum(), 0)

    def test_empty_client_id_isolation(self):
        """Проверка, что пустые client_id не склеивают независимых людей."""
        raw_rows = pd.DataFrame([
            {"order_date": "2025-01-10", "client_id": "", "phone": "+79991112233", "email": "", "net_revenue": 1000},
            {"order_date": "2025-01-12", "client_id": "", "phone": "+79994445566", "email": "", "net_revenue": 2000},
            {"order_date": "2025-01-15", "client_id": "", "phone": "", "email": "", "net_revenue": 3000},
            {"order_date": "2025-01-16", "client_id": "", "phone": "", "email": "", "net_revenue": 4000},
        ])
        t_file = os.path.join(self.test_dir, "test_empty_ids.csv")
        raw_rows.to_csv(t_file, index=False, sep=";", encoding="utf-8-sig")
        df_clean = clean_orders_data(t_file)
        self.assertEqual(df_clean["client_uid"].nunique(), 4)

    def test_transitive_identity_resolution(self):
        """
        Проверка транзитивной склейки профиля:
        Строка 1: телефон на кассе
        Строка 2: тот же телефон + email при регистрации
        Строка 3: тот же email при заказе на сайте
        Все 3 заказа обязаны объединиться в 1 client_uid.
        """
        raw_rows = pd.DataFrame([
            {"order_date": "2025-01-10", "client_id": "", "phone": "+79991112233", "email": "", "net_revenue": 1000},
            {"order_date": "2025-01-20", "client_id": "", "phone": "+79991112233", "email": "alex@shop.ru", "net_revenue": 2000},
            {"order_date": "2025-02-05", "client_id": "", "phone": "", "email": "alex@shop.ru", "net_revenue": 3000},
        ])
        t_file = os.path.join(self.test_dir, "test_transitive.csv")
        raw_rows.to_csv(t_file, index=False, sep=";", encoding="utf-8-sig")
        df_clean = clean_orders_data(t_file)
        self.assertEqual(df_clean["client_uid"].nunique(), 1)
        self.assertEqual(len(df_clean), 3)

    def test_deep_chain_union_find_no_recursion_error(self):
        """Проверка, что итеративный find выдерживает цепочку в 3 000 чеков кассира без RecursionError."""
        rows = [
            {"order_date": "2025-01-10", "client_id": f"C_{i}", "phone": "+79990000000", "email": "", "net_revenue": 100}
            for i in range(3000)
        ]
        t_file = os.path.join(self.test_dir, "test_deep_chain.csv")
        pd.DataFrame(rows).to_csv(t_file, index=False, sep=";", encoding="utf-8-sig")
        df_clean = clean_orders_data(t_file)
        self.assertEqual(df_clean["client_uid"].nunique(), 1)
        self.assertEqual(len(df_clean), 3000)

    def test_datetime_with_timestamp_and_mixed_formats(self):
        """Проверка корректного распознавания месяцев для дат со временем и европейского формата."""
        raw_rows = pd.DataFrame([
            {"order_date": "01.02.2021 14:30", "client_id": "C1", "net_revenue": 1000},
            {"order_date": "2021-02-05 09:15:00", "client_id": "C2", "net_revenue": 2000},
            {"order_date": "18.11.2021", "client_id": "C3", "net_revenue": 3000},
        ])
        t_file = os.path.join(self.test_dir, "test_dates.csv")
        raw_rows.to_csv(t_file, index=False, sep=";", encoding="utf-8-sig")
        df_clean = clean_orders_data(t_file)
        self.assertEqual(len(df_clean), 3)
        self.assertEqual(df_clean.loc[0, "cohort_month"], "2021-02")
        self.assertEqual(df_clean.loc[1, "cohort_month"], "2021-02")
        self.assertEqual(df_clean.loc[2, "cohort_month"], "2021-11")

    def test_sql_python_cohort_parity_matrices(self):
        """
        Строгая поэлементная сверка матриц клиентов И матриц выручки между Pandas и SQLite (синтетика).
        """
        df = clean_orders_data(self.sample_data)
        clients_py, rev_py, summary_py = build_cohort_matrices(df)
        clients_sql, rev_sql, summary_sql = build_cohort_matrices_sql(df)

        pd.testing.assert_frame_equal(
            clients_py.astype(int),
            clients_sql.astype(int),
            check_names=False,
            check_like=True
        )

        pd.testing.assert_frame_equal(
            rev_py.astype(float),
            rev_sql.astype(float),
            check_names=False,
            check_like=True,
            check_exact=False,
            rtol=0.0,
            atol=0.01
        )

        pd.testing.assert_series_equal(
            summary_py["total_net_revenue"].astype(float),
            summary_sql["total_net_revenue"].astype(float),
            check_names=False,
            check_exact=False,
            rtol=0.0,
            atol=0.01
        )

    def test_course_lesson_3_benchmark(self):
        """
        Главный верификационный тест: сверка с эталонным решением Урока 3 курса
        И проверка 100% паритета между Pandas и SQLite на реальных данных курса.
        Файл: data/course/sheet_02_15phCO86.csv
        """
        course_file = os.path.join(os.path.dirname(__file__), "..", "data", "course", "sheet_02_15phCO86.csv")
        if not os.path.exists(course_file):
            self.skipTest("Файл курса sheet_02 не найден")

        df = clean_orders_data(course_file)
        clients_py, rev_py, summary_py = build_cohort_matrices(df)
        clients_sql, rev_sql, summary_sql = build_cohort_matrices_sql(df)

        pd.testing.assert_frame_equal(clients_py, clients_sql, check_names=False, check_like=True)
        pd.testing.assert_frame_equal(rev_py.astype(float), rev_sql.astype(float), check_names=False, check_like=True, rtol=0.0, atol=0.01)
        pd.testing.assert_series_equal(summary_py["total_net_revenue"], summary_sql["total_net_revenue"], rtol=0.0, atol=0.01)

        self.assertEqual(len(df), 3996)
        self.assertEqual(len(clients_py), 13)
        self.assertEqual(clients_py.index[0], "2021-02")
        self.assertEqual(clients_py.index[-1], "2022-02")
        self.assertEqual(clients_py.loc["2021-02", 0], 149)
        self.assertEqual(clients_py.loc["2021-03", 0], 312)
        self.assertEqual(clients_py.loc["2021-04", 0], 250)
        self.assertEqual(clients_py.loc["2021-05", 0], 193)
        self.assertEqual(df["client_uid"].nunique(), 1791)

    def test_unit_economics_formulas(self):
        df = clean_orders_data(self.sample_data)
        _, _, summary = build_cohort_matrices(df)
        behavior = calculate_behavior_metrics(summary)
        costs = calculate_costs_breakdown(df, summary)
        model = build_unit_economics_model(behavior, costs)

        self.assertGreaterEqual(model["basic_ltv"], model["direct_ltv_1"])
        self.assertGreaterEqual(model["direct_ltv_1"], model["direct_ltv_2"])
        
        self.assertAlmostEqual(
            model["net_ltv"],
            model["direct_ltv_2"] - model["cac_per_client"],
            places=2
        )
        
        if model["cac_per_client"] > 0:
            expected_ratio = round(model["direct_ltv_2"] / model["cac_per_client"], 2)
            self.assertEqual(model["ltv_to_cac_ratio"], expected_ratio)

    def test_rfm_segmentation(self):
        df = clean_orders_data(self.sample_data)
        rfm_df, summary = calculate_rfm_segments(df)
        self.assertEqual(len(rfm_df), df["client_uid"].nunique())
        self.assertFalse(summary.empty)
        self.assertGreaterEqual(summary["client_share_pct"].sum(), 99.0)

    # --- НОВЫЕ ТЕСТЫ ПО ТЗ report v2 ---

    def test_partial_mode_returns_none(self):
        """
        Критерий приемки 6: В режиме неполных данных (курсовой файл без COGS и CAC)
        direct_ltv_1, direct_ltv_2, net_ltv, ltv_to_cac_ratio и health_status возвращают None.
        """
        course_file = os.path.join(os.path.dirname(__file__), "..", "data", "course", "sheet_02_15phCO86.csv")
        if not os.path.exists(course_file):
            self.skipTest("Файл курса sheet_02 не найден")

        df = clean_orders_data(course_file)
        completeness = detect_data_completeness(df)
        self.assertEqual(completeness["mode"], "partial")
        self.assertFalse(completeness["cogs"])
        self.assertFalse(completeness["acquisition_cost"])

        _, _, summary = build_cohort_matrices(df)
        behavior = calculate_behavior_metrics(summary)
        costs = calculate_costs_breakdown(df, summary)
        model = build_unit_economics_model(behavior, costs, completeness=completeness)

        self.assertIsNone(model["direct_ltv_1"])
        self.assertIsNone(model["direct_ltv_2"])
        self.assertIsNone(model["net_ltv"])
        self.assertIsNone(model["ltv_to_cac_ratio"])
        self.assertIsNone(model["health_status"])
        self.assertGreater(model["basic_ltv"], 0.0)

    def test_retention_matrix_marks_unavailable_periods(self):
        """
        Критерий приемки 7: Для когорты 2022-01 в sheet_02 доступно только 2 периода (M0 и M1).
        Для последней когорты 2022-02 доступен только 1 период (M0).
        """
        course_file = os.path.join(os.path.dirname(__file__), "..", "data", "course", "sheet_02_15phCO86.csv")
        if not os.path.exists(course_file):
            self.skipTest("Файл курса sheet_02 не найден")

        df = clean_orders_data(course_file)
        clients_m, _, _ = build_cohort_matrices(df)
        last_date = pd.to_datetime(df["order_date"]).max()
        availability = compute_cohort_availability(clients_m, last_date)

        # Когорта 2022-01: доступно 2 периода (M0, M1)
        self.assertEqual(availability["2022-01"], 1)
        # Когорта 2022-02: доступен 1 период (M0)
        self.assertEqual(availability["2022-02"], 0)
        # Когорта 2021-02: доступно 13 периодов (M0..M12)
        self.assertEqual(availability["2021-02"], 12)

    def test_average_retention_excludes_unavailable(self):
        """
        Критерий приемки 8: Среднее удержание по периоду M5 считается по меньшему числу когорт, чем по M1.
        """
        course_file = os.path.join(os.path.dirname(__file__), "..", "data", "course", "sheet_02_15phCO86.csv")
        if not os.path.exists(course_file):
            self.skipTest("Файл курса sheet_02 не найден")

        df = clean_orders_data(course_file)
        clients_m, _, _ = build_cohort_matrices(df)
        last_date = pd.to_datetime(df["order_date"]).max()
        availability = compute_cohort_availability(clients_m, last_date)
        avg_ret, cohorts_cnt = compute_retention_summary(clients_m, availability)

        # На M1 доступно больше когорт (12 когорт), чем на M5 (8 когорт)
        self.assertGreater(cohorts_cnt[1], cohorts_cnt[5])
        self.assertEqual(cohorts_cnt[0], 13)
        self.assertEqual(cohorts_cnt[1], 12)
        self.assertEqual(cohorts_cnt[5], 8)
        self.assertEqual(cohorts_cnt[8], 5)


if __name__ == "__main__":
    unittest.main()

"""
Тесты локального веб-сервера (web/app.py).
Проверяют загрузку, валидацию полей, обработку Excel/CSV и скачивание HTML.
"""

import unittest
import os
import io
from web.app import app


class TestWebApp(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_index_page_loads(self):
        """Проверка отдачи главной страницы с Drag-and-Drop зоной."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Когортный анализ заказов".encode("utf-8"), res.data)
        self.assertIn("dropZone".encode("utf-8"), res.data)

    def test_sample_dataset_processing(self):
        """Проверка кнопки запуска на тестовом датасете."""
        res = self.client.post("/use-sample", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("Аналитический дашборд юнит-экономики".encode("utf-8"), res.data)
        self.assertIn("Матрица удержания клиентов".encode("utf-8"), res.data)
        self.assertIn("Скачать HTML-отчет".encode("utf-8"), res.data)

    def test_validation_error_on_invalid_csv(self):
        """Проверка понятного сообщения об ошибке при отсутствии обязательных колонок."""
        invalid_csv = "col_a;col_b;col_c\n1;2;3\n4;5;6\n"
        data = {
            "file": (io.BytesIO(invalid_csv.encode("utf-8")), "invalid.csv")
        }
        res = self.client.post("/upload", data=data, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("Ошибка валидации файла".encode("utf-8"), res.data)
        self.assertIn("В файле не найдена колонка с датой заказа".encode("utf-8"), res.data)

    def test_valid_csv_upload_and_download(self):
        """Проверка успешной загрузки валидного CSV и скачивания отчета."""
        valid_csv = "order_date;client_id;net_revenue\n2025-01-10;C1;1000\n2025-01-15;C2;2000\n2025-02-10;C1;1500\n"
        data = {
            "file": (io.BytesIO(valid_csv.encode("utf-8")), "valid_orders.csv")
        }
        res = self.client.post("/upload", data=data, content_type="multipart/form-data", follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        report_url = res.headers["Location"]

        # Просмотр отчета
        view_res = self.client.get(report_url)
        self.assertEqual(view_res.status_code, 200)
        self.assertIn("valid_orders.csv".encode("utf-8"), view_res.data)

        # Скачивание отчета
        report_id = report_url.split("/")[-1]
        down_res = self.client.get(f"/download/{report_id}")
        self.assertEqual(down_res.status_code, 200)
        self.assertEqual(down_res.mimetype, "text/html")
        self.assertIn("attachment;filename=report_valid_orders.csv.html", down_res.headers["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()

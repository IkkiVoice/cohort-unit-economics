"""
Локальный веб-интерфейс (web/app.py) для загрузки выгрузок и мгновенного расчета когортного анализа.
Стек: Flask, без тяжелых внешних зависимостей.
Дизайн: Стиль Mindbox (#F7F8FA, #4A3AFF, карточки 12px).
"""

import os
import sys
import uuid
import tempfile
import pandas as pd
from flask import Flask, request, render_template_string, redirect, url_for, Response

# Добавляем корень проекта в sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.prepare import clean_orders_data
from src.cohorts import build_cohort_matrices
from src.behavior import calculate_behavior_metrics
from src.costs import calculate_costs_breakdown
from src.model import build_unit_economics_model
from src.rfm import calculate_rfm_segments
from src.report import detect_data_completeness
from src.report_html import generate_html_report

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB
TEMP_REPORTS = {}

UPLOAD_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Когортный анализ и юнит-экономика | Загрузка данных</title>
    <style>
        :root {
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
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, "Segoe UI", Roboto, Inter, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            font-size: 14px;
            line-height: 1.5;
            padding: 40px 16px;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .container {
            max-width: 640px;
            width: 100%;
        }
        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 32px;
            box-shadow: 0 4px 12px rgba(22, 24, 43, 0.03);
        }
        .logo-tag {
            display: inline-block;
            background: #EEF2FF;
            color: var(--accent);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 12px;
        }
        h1 { font-size: 24px; font-weight: 600; margin-bottom: 8px; }
        .subtitle { font-size: 14px; color: var(--text-dim); margin-bottom: 24px; }
        
        .drop-zone {
            border: 2px dashed #CBD5E1;
            border-radius: 12px;
            padding: 40px 20px;
            text-align: center;
            background: #FAFAFC;
            cursor: pointer;
            transition: all 0.2s ease;
            position: relative;
        }
        .drop-zone:hover, .drop-zone.dragover {
            border-color: var(--accent);
            background: #F5F3FF;
        }
        .drop-icon { font-size: 36px; margin-bottom: 12px; color: var(--accent); }
        .drop-text { font-size: 15px; font-weight: 500; color: var(--text); margin-bottom: 4px; }
        .drop-sub { font-size: 13px; color: var(--text-dim); }
        input[type="file"] {
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            opacity: 0; cursor: pointer;
        }
        
        .btn-sample {
            display: inline-block;
            margin-top: 16px;
            background: #F1F5F9;
            color: #334155;
            padding: 8px 16px;
            border-radius: 8px;
            text-decoration: none;
            font-size: 13px;
            font-weight: 500;
            border: none;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn-sample:hover { background: #E2E8F0; }

        .info-box {
            margin-top: 24px;
            padding: 16px;
            background: #F8FAFC;
            border: 1px solid var(--border);
            border-radius: 10px;
            font-size: 13px;
        }
        .info-title { font-weight: 600; margin-bottom: 6px; color: var(--text); }
        .cols-list { color: var(--text-dim); line-height: 1.6; }
        
        .error-card {
            background: #FEF2F2;
            border: 1px solid #FCA5A5;
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 20px;
            color: #991B1B;
            font-size: 13px;
        }
        .error-title { font-weight: 600; font-size: 15px; margin-bottom: 6px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <span class="logo-tag">⚡ Cohort & Unit Economics</span>
            <h1>Когортный анализ заказов</h1>
            <p class="subtitle">Перетащите CSV или XLSX выгрузку из 1C, RetailCRM или интернет-магазина для мгновенного расчета.</p>

            {% if error_msg %}
            <div class="error-card">
                <div class="error-title">⚠️ Ошибка валидации файла</div>
                <p>{{ error_msg }}</p>
                {% if found_cols %}
                <p style="margin-top:8px; color:#7F1D1D;"><strong>Найденные колонки:</strong> {{ found_cols }}</p>
                {% endif %}
            </div>
            {% endif %}

            <form action="/upload" method="POST" enctype="multipart/form-data" id="uploadForm">
                <div class="drop-zone" id="dropZone">
                    <div class="drop-icon">📊</div>
                    <div class="drop-text">Выберите файл или перетащите его сюда</div>
                    <div class="drop-sub">Поддерживаются форматы .csv и .xlsx до 64 МБ</div>
                    <input type="file" name="file" id="fileInput" accept=".csv,.xlsx" onchange="document.getElementById('uploadForm').submit();">
                </div>
            </form>

            <div style="text-align: center; margin-top: 14px;">
                <form action="/use-sample" method="POST" style="display:inline;">
                    <button type="submit" class="btn-sample">⚡ Проверить на тестовом датасете (3 300+ заказов)</button>
                </form>
            </div>

            <div class="info-box">
                <div class="info-title">Поддерживаемые поля:</div>
                <div class="cols-list">
                    • <strong>Обязательные:</strong> дата заказа (<code>order_date</code>), контакт клиента (<code>client_id</code> / <code>phone</code> / <code>email</code>), сумма (<code>net_revenue</code> / <code>gross_revenue</code>).<br>
                    • <strong>Опциональные:</strong> себестоимость (<code>cogs</code>), затраты на маркетинг (<code>acquisition_cost</code>), доставка (<code>delivery_cost</code>), скидка (<code>discount_amount</code>), бренд, канал.
                </div>
            </div>
        </div>
    </div>

    <script>
        const dropZone = document.getElementById('dropZone');
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropZone.classList.add('dragover');
            }, false);
        });
        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropZone.classList.remove('dragover');
            }, false);
        });
    </script>
</body>
</html>
"""

def validate_input_columns(df: pd.DataFrame):
    """
    Проверяет наличие минимально необходимых полей перед расчетом.
    Возвращает (is_valid, error_message, found_columns_str).
    """
    col_names = [str(c).lower().strip() for c in df.columns]
    
    # 1. Дата
    date_candidates = ["order_date", "date", "created_at", "order_datetime", "дата", "дата заказа"]
    has_date = any(c in col_names for c in date_candidates)
    
    # 2. Клиент
    client_candidates = ["client_id", "phone", "email", "client_uid", "телефон", "почта", "клиент", "user_id", "customer_id"]
    has_client = any(c in col_names for c in client_candidates)
    
    # 3. Сумма / выручка
    rev_candidates = ["net_revenue", "gross_revenue", "amount", "total_amount", "sum", "сумма", "выручка", "цена", "price"]
    has_rev = any(c in col_names for c in rev_candidates)

    found_str = ", ".join([f"'{c}'" for c in df.columns[:15]])
    if len(df.columns) > 15:
        found_str += " ..."

    if not has_date:
        return False, "В файле не найдена колонка с датой заказа (ожидается 'order_date', 'date' или 'дата').", found_str
    if not has_client:
        return False, "В файле не найдена колонка с идентификатором клиента (ожидается 'client_id', 'phone' или 'email').", found_str
    if not has_rev:
        return False, "В файле не найдена колонка с суммой заказа (ожидается 'net_revenue', 'gross_revenue' или 'сумма').", found_str

    return True, None, found_str


def process_dataset_and_generate_html(filepath: str, original_filename: str) -> str:
    """
    Прогоняет датасет через модули пайплайна и возвращает готовый HTML код с панелью навигации.
    """
    clean_df = clean_orders_data(filepath)
    completeness = detect_data_completeness(clean_df)
    cohort_clients, cohort_revenue, period_summary = build_cohort_matrices(clean_df)
    last_date = pd.to_datetime(clean_df["order_date"]).max()
    behavior_metrics = calculate_behavior_metrics(period_summary, cohort_clients, last_date)
    costs_breakdown = calculate_costs_breakdown(clean_df, period_summary)
    model_results = build_unit_economics_model(behavior_metrics, costs_breakdown, completeness=completeness)
    rfm_df, rfm_summary = calculate_rfm_segments(clean_df)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as tf:
        out_html_path = tf.name

    generate_html_report(
        behavior_metrics=behavior_metrics,
        costs_breakdown=costs_breakdown,
        model_results=model_results,
        cohort_matrix=cohort_clients,
        rfm_summary=rfm_summary,
        clean_df=clean_df,
        output_path=out_html_path,
        source_filename=original_filename,
        engine_name="Web Fast Engine (Pandas)"
    )

    with open(out_html_path, "r", encoding="utf-8") as f:
        html_code = f.read()

    try:
        os.remove(out_html_path)
    except Exception:
        pass

    return html_code


@app.route("/", methods=["GET"])
def index():
    return render_template_string(UPLOAD_HTML_TEMPLATE)


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return render_template_string(UPLOAD_HTML_TEMPLATE, error_msg="Файл не был передан в запросе.")
    
    file = request.files["file"]
    if file.filename == "":
        return render_template_string(UPLOAD_HTML_TEMPLATE, error_msg="Выберите файл для загрузки.")

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    if ext not in [".csv", ".xlsx"]:
        return render_template_string(UPLOAD_HTML_TEMPLATE, error_msg="Неподдерживаемый формат. Загрузите .csv или .xlsx файл.")

    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, filename)
    file.save(temp_path)

    try:
        if ext == ".xlsx":
            df_raw = pd.read_excel(temp_path)
            csv_path = os.path.join(temp_dir, "converted.csv")
            df_raw.to_csv(csv_path, sep=";", index=False, encoding="utf-8-sig")
            target_path = csv_path
        else:
            target_path = temp_path
            try:
                df_preview = pd.read_csv(target_path, sep=None, engine="python", nrows=10)
            except Exception:
                df_preview = pd.read_csv(target_path, sep=";", nrows=10)

        if ext == ".xlsx":
            is_valid, err_msg, found_cols = validate_input_columns(df_raw)
        else:
            is_valid, err_msg, found_cols = validate_input_columns(df_preview)

        if not is_valid:
            return render_template_string(UPLOAD_HTML_TEMPLATE, error_msg=err_msg, found_cols=found_cols)

        html_result = process_dataset_and_generate_html(target_path, filename)
        report_id = str(uuid.uuid4())
        TEMP_REPORTS[report_id] = {
            "html": html_result,
            "filename": filename
        }

        return redirect(url_for("view_report", report_id=report_id))

    except Exception as e:
        return render_template_string(UPLOAD_HTML_TEMPLATE, error_msg=f"Ошибка обработки данных: {str(e)}")
    finally:
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


@app.route("/use-sample", methods=["POST"])
def use_sample():
    sample_file = os.path.join(BASE_DIR, "data", "sample_orders.csv")
    if not os.path.exists(sample_file):
        from src.generate import generate_retail_dataset
        generate_retail_dataset(output_path=sample_file)

    html_result = process_dataset_and_generate_html(sample_file, "sample_orders.csv")
    report_id = str(uuid.uuid4())
    TEMP_REPORTS[report_id] = {
        "html": html_result,
        "filename": "sample_orders.csv"
    }
    return redirect(url_for("view_report", report_id=report_id))


@app.route("/report/<report_id>", methods=["GET"])
def view_report(report_id):
    if report_id not in TEMP_REPORTS:
        return redirect(url_for("index"))

    data = TEMP_REPORTS[report_id]
    html_code = data["html"]
    
    top_nav = f"""
    <div style="position: sticky; top: 0; z-index: 9999; background: #FFFFFF; border-bottom: 1px solid #E8EAEF; padding: 10px 24px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
        <a href="/" style="text-decoration: none; color: #4A3AFF; font-weight: 500; font-size: 13px; display: flex; align-items: center; gap: 6px;">
            ← Загрузить другой файл
        </a>
        <div style="display: flex; gap: 12px; align-items: center;">
            <span style="font-size: 13px; color: #6B7280;">Файл: <strong>{data['filename']}</strong></span>
            <a href="/download/{report_id}" style="text-decoration: none; background: #4A3AFF; color: #FFFFFF; padding: 6px 14px; border-radius: 6px; font-weight: 500; font-size: 13px; display: inline-block;">
                📥 Скачать HTML-отчет
            </a>
        </div>
    </div>
    """
    
    injected_html = html_code.replace("<body>", f"<body>\n{top_nav}")
    return Response(injected_html, mimetype="text/html")


@app.route("/download/<report_id>", methods=["GET"])
def download_report(report_id):
    if report_id not in TEMP_REPORTS:
        return redirect(url_for("index"))

    data = TEMP_REPORTS[report_id]
    return Response(
        data["html"],
        mimetype="text/html",
        headers={"Content-Disposition": f"attachment;filename=report_{data['filename']}.html"}
    )


if __name__ == "__main__":
    print("=" * 60)
    print("   COHORT & UNIT ECONOMICS LOCAL WEB SERVER")
    print("   Слушает: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False)

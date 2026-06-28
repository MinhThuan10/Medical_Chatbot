from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import os
import csv
import gc

# Thiết lập DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2025, 2, 25),
    'retries': 2,
    'retry_delay': timedelta(minutes=1),
}

dag = DAG(
    'crawl_tamanh_parallel',
    default_args=default_args,
    description='Crawl data song song',
    schedule_interval=None,
    catchup=False,
)

BATCH_DIR = "/opt/airflow/dags/batches"
CONTENT_FILE = "/opt/airflow/dags/content.csv"

# Đọc danh sách URL
def read_urls():
    df = pd.read_csv("/opt/airflow/dags/all_url.csv")
    return df["url"].tolist()

# Crawl 1 URL
def get_content_from_url(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        return [{"url": url, "title": "", "heading": "", "content": "", "error": str(e)}]

    soup = BeautifulSoup(response.text, "html.parser")
    elements = soup.find_all(["h1", "h2", "h3", "p", "li"])

    title = None
    data_content = []
    for i, e in enumerate(elements):
        if e.name == "h1":
            title = e.text.strip()
            content = []
            for e1 in elements[i + 1:]:
                if e1.name in ["h3", "p", "li"]:
                    content.append(e1.text.strip())
                if e1.name == 'h2':
                    break
            data_content.append({
                "url": url,
                "title": title or "",
                "heading": title,
                "content": " ".join(content),
                "error": None
            })
        if e.name == "h2":
            heading = e.text.strip()
            content = []
            for e1 in elements[i + 1:]:
                if e1.name in ["h3", "p", "li"]:
                    content.append(e1.text.strip())
                if e1.name == 'h2':
                    break
            data_content.append({
                "url": url,
                "title": title or "",
                "heading": heading,
                "content": " ".join(content),
                "error": None
            })
        

    
    if not data_content:
        return [{"url": url, "title": "", "heading": "", "content": "", "error": "No relevant content"}]
    
    return data_content

# Task 1: Chia URL thành batch và lưu thành file
def split_urls():
    urls = read_urls()
    os.makedirs(BATCH_DIR, exist_ok=True)
    batch_size = 200  # Số lượng URL mỗi batch
    for i in range(0, len(urls), batch_size):
        batch_urls = urls[i:i+batch_size]
        with open(f"{BATCH_DIR}/batch_{i // batch_size}.json", "w", encoding="utf-8") as f:
            json.dump(batch_urls, f)

# Task 2: Đọc từng file batch và crawl dữ liệu
def process_batch(batch_index):
    with open(f"{BATCH_DIR}/batch_{batch_index}.json", "r", encoding="utf-8") as f:
        batch_urls = json.load(f)

    results = []
    for url in batch_urls:
        results.extend(get_content_from_url(url))

    with open(CONTENT_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["url", "title", "heading", "content", "error"])
        if f.tell() == 0:
            writer.writeheader()
        writer.writerows(results)

    del results
    gc.collect()

# Tạo task chia URL
split_task = PythonOperator(
    task_id="split_urls",
    python_callable=split_urls,
    dag=dag,
)

# Tạo task crawl song song từ các batch file
TOTAL_URLS = 14933
BATCH_SIZE = 200
NUM_BATCHES = (TOTAL_URLS // BATCH_SIZE) + 1

crawl_tasks = []
for i in range(NUM_BATCHES):
    task = PythonOperator(
        task_id=f"crawl_batch_{i}",
        python_callable=process_batch,
        op_args=[i],
        dag=dag,
    )
    split_task >> task  # Tất cả task phụ thuộc split_urls
    crawl_tasks.append(task)

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import csv
import os

LINKS_FILE = '/opt/airflow/dags/medlatec/medlatec_links.csv'
OUTPUT_FILE = '/opt/airflow/dags/medlatec/medlatec_qa.csv'

def crawl_qa_from_links():
    all_qa = []

    if not os.path.exists(LINKS_FILE):
        print(f"File {LINKS_FILE} không tồn tại!")
        return

    with open(LINKS_FILE, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        urls = [row['Link'] for row in reader]

    print(f"Đang crawl {len(urls)} URL...")

    for idx, url in enumerate(urls, 1):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            faq_items = soup.find_all('div', class_='faq-item-desc')

            
            question = faq_items[0].get_text(strip=True)

            # answer = '\n'.join(item.get_text(strip=True) for item in faq_items[1])

            answer = ''
            for item in faq_items[1]:
                text = item.get_text(strip=True)
                if not any(kw in text.lower() for kw in ["chào", "cảm ơn", "thân mến", "kính gửi", "chúc", "lịch khám", "mọi", "medlatec", "địa chỉ", "liên hệ", "trân trọng", "hân hạnh"]):
                    answer += text + '\n'    

            all_qa.append((question, answer))
            print(f"[{idx}/{len(urls)}] OK: {url}")

        except Exception as e:
            print(f"[{idx}/{len(urls)}] Lỗi crawl {url}: {e}")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with open(OUTPUT_FILE, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Question', 'Answer'])  # Header
        for q, a in all_qa:
            writer.writerow([q, a])

    print(f"Đã lưu {len(all_qa)} cặp Question-Answer vào {OUTPUT_FILE}")

# Define DAG
with DAG(
    dag_id='crawl_medlatec_qa',
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=['crawler', 'medlatec', 'qa'],
) as dag:

    crawl_qa_task = PythonOperator(
        task_id='crawl_qa_from_links',
        python_callable=crawl_qa_from_links,
    )

    crawl_qa_task

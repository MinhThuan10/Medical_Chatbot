from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import csv
import os

OUTPUT_DIR = '/opt/airflow/dags/ivie_split'

def crawl_chunk(start_id, end_id, chunk_id):
    url = "https://ivie.vn/cong-dong?id="
    qa_data = []

    for i in range(start_id, end_id + 1):
        page_url = url + str(i)
        try:
            response = requests.get(page_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            descriptions = soup.find_all('p', class_='description')
            if descriptions:
                question = descriptions[0].get_text(strip=True)
                answer = ' '.join(p.get_text(strip=True) for p in descriptions[1:])
                qa_data.append((question, answer))
        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi truy cập {page_url}: {e}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, f'ivie_qa_chunk_{chunk_id}.csv')
    with open(output_file, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Question', 'Answer'])
        for q, a in qa_data:
            writer.writerow([q, a])
    print(f"✅ [chunk {chunk_id}] Ghi {len(qa_data)} QA vào {output_file}")

default_args = {
    'start_date': datetime(2024, 1, 1),
}

with DAG(
    dag_id='crawl_ivie_content_parallel',
    schedule_interval=None,
    catchup=False,
    default_args=default_args,
    tags=['crawler', 'ivie'],
) as dag:

    total_pages = 53683
    num_chunks = 100
    chunk_size = total_pages // num_chunks

    tasks = []
    for i in range(num_chunks):
        start = i * chunk_size + 1
        end = (i + 1) * chunk_size if i != num_chunks - 1 else total_pages
        task = PythonOperator(
            task_id=f'crawl_chunk_{i + 1}',
            python_callable=crawl_chunk,
            op_args=[start, end, i + 1],
        )
        tasks.append(task)

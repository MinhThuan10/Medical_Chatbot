from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import csv
import os

OUTPUT_DIR = '/opt/airflow/dags/bvthucuc'
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'bvthucuc_links.csv')

def crawl_medlatec_links():
    url = "https://benhvienthucuc.vn/hoi-dap-chuyen-gia/page/"
    all_links = []

    def get_links(page_url):
        response = requests.get(page_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        answer_links = soup.find_all('span', class_='span--reply')
        result = []
        for span in answer_links:
            a_tag = span.find('a')
            if a_tag and a_tag.get('href'):
                link = a_tag['href']
            result.append(link)
        return result

    for i in range(1, 156):
        new_url = url + str(i)
        print(f"Đang lấy link từ: {new_url}")
        links = get_links(new_url)
        all_links.extend(links)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(OUTPUT_FILE, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Link']) 
        for link in all_links:
            writer.writerow([link])

    print(f"Đã lưu link vào file {OUTPUT_FILE} thành công!")

with DAG(
    dag_id='crawl_bvthucuc_links',
    start_date=datetime(2024, 1, 1),
    schedule_interval=None, 
    catchup=False,
    tags=['crawler', 'medlatec'],
) as dag:

    crawl_task = PythonOperator(
        task_id='crawl_links',
        python_callable=crawl_medlatec_links,
    )

    crawl_task

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import csv
import os

OUTPUT_DIR = '/opt/airflow/dags/medlatec'
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'medlatec_links.csv')

def crawl_medlatec_links():
    url = "https://medlatec.vn/hoi-dap?pagenumber="
    all_links = []

    def get_links(page_url):
        try:
            response = requests.get(page_url, verify=False)
            response.raise_for_status()  
        except requests.exceptions.RequestException as e:
            print(f"Error while requesting page: {e}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        answer_links = soup.find_all('a', class_='action answer')
        
        result = []
        for link in answer_links:
            href = link.get('href')
            if href: 
                full_url = f"https://medlatec.vn{href}"
                result.append(full_url)
        return result

    for i in range(1, 603):
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
    dag_id='crawl_medlatec_links',
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

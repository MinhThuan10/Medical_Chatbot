from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import json
# from hdfs import InsecureClient
import boto3

# Cấu hình HDFS
HDFS_URL = "http://localhost:9870"
HDFS_DIR = "/tamanh/"

# Cấu hình MinIO
MINIO_ENDPOINT = "http://localhost:9000"
MINIO_ACCESS_KEY = "admin"
MINIO_SECRET_KEY = "password@123"
MINIO_BUCKET = "tamanh"

# Kết nối MinIO
s3_client = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
)

# Hàm load URL
def load_urls(**kwargs):
    import airflow
    # df = pd.read_csv('/opt/airflow/dags/url_test.csv')
    # df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    # split_index = len(df) // 2

    # hdfs_urls = df.iloc[:split_index].to_dict(orient="records")
    # minio_urls = df.iloc[split_index:].to_dict(orient="records")

    # kwargs['ti'].xcom_push(key='hdfs_urls', value=hdfs_urls)
    # kwargs['ti'].xcom_push(key='minio_urls', value=minio_urls)
    print(f"airflow version: {airflow.__version__}")

# Hàm crawl
def crawl_page(url_data):
    field, title, url = url_data['field'], url_data['title'], url_data['url']
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    
    data_content = []
    elements = soup.find_all(["h1", "h2", "h3", "p", "li"])

    for i, e in enumerate(elements):
        if e.name == "h1":
            title = e.text.strip()
        if e.name == "h2":
            heading = e.text.strip()
            content = []
            for e1 in elements[i+1:]:
                if e1.name in ["h3", "p", "li"]:
                    content.append(e1.text.strip())
                if e1.name == "h2":
                    break
            data_content.append({
                "field": field, "url": url, "title": title, 
                "heading": heading, "content": content
            })
    
    return data_content



# Thiết lập DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2025, 2, 25),
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'crawl_tamanh_split_storage',
    default_args=default_args,
    description='Crawl data and split storage between HDFS & MinIO',
    schedule_interval='@daily',
    catchup=False,
)

# Task 1: Chia danh sách URL
load_urls_task = PythonOperator(
    task_id='load_urls',
    python_callable=load_urls,
    provide_context=True,
    dag=dag,
)


load_urls_task
import requests
from bs4 import BeautifulSoup
import csv

def get_content_from_url(field, title, url):
    data_content = []
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    element = soup.find_all(["h1", "h2", "h3", "p", "li"])

    for i, e in enumerate(element):
        if e.name == "h1":  # title
            title = e.text.strip()
        if e.name == "h2":  # heading
            heading = e.text.strip()
            content = []
            
            for e1 in element[i+1:]:  
                if e1.name in ["h3", "p", "li"]:
                    content.append(e1.text.strip())  
                if e1.name == 'h2':
                    break
            data_content.append((field, url, title, heading, content))
            
    return data_content


import csv
import os
import itertools

file_path = './Data_LakeHouse/TamAnh_Hospital/all_url.csv'
output_file = './Data_LakeHouse/TamAnh_Hospital/content.csv'



with open(file_path, mode='r', newline='', encoding='utf-8') as in_file, \
     open(output_file, mode='a', newline='', encoding='utf-8') as out_file:

    reader = csv.reader(in_file)
    writer = csv.writer(out_file)

    next(reader)  # Bỏ qua header

    # Nếu output file chưa có dữ liệu, ghi header
    if os.stat(output_file).st_size == 0:
        writer.writerow(["field", "url", "title", "heading", "content"])

    # Duyệt qua tất cả URL và crawl dữ liệu
    for row in reader:
        field, url, title = row
        content_list = get_content_from_url(field, url, title)  
        writer.writerows(content_list)  # Ghi toàn bộ kết quả vào file
        print(f"Đã xử lý: {url}")  # Hiển thị tiến trình

print("🎉 Hoàn thành quá trình cào và lưu dữ liệu!")
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import re
import csv
import time
import pandas as pd

# Cấu hình Selenium
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

# Cài đặt ChromeDriver tự động
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

def access_url_xml(url):
    # Truy cập URL
    driver.get(url)

    # Chờ để JavaScript tải
    time.sleep(5)

    # Lấy nội dung trang sau khi JavaScript đã chạy
    xml_content = driver.page_source

    # Sử dụng BeautifulSoup để phân tích cú pháp HTML/XML
    soup = BeautifulSoup(xml_content, 'lxml')

    # Lọc tất cả các thẻ <a> và lấy thuộc tính href (liên kết) chứa tamanhhospital.vn
    links = [a['href'] for a in soup.find_all('a', href=True) if 'tamanhhospital.vn' in a['href']]

    return links

# Hàm để ghi dữ liệu vào file CSV
def save_to_csv(data):
    with open('./Data_LakeHouse/TamAnh_Hospital/all_url.csv', mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if file.tell() == 0:
            writer.writerow(["field","title", "url"])

        for field, title, url in data:
            writer.writerow([field, title, url])


df = pd.read_csv('./Data_LakeHouse/TamAnh_Hospital/all_url.csv', encoding='utf-8')

# Danh sách để chứa dữ liệu (field và url)
unique_urls = df['url'].tolist()
data_to_save = []  # Danh sách chứa dữ liệu cần ghi vào CSV


# Truy cập và lấy các liên kết từ post-sitemap1.xml
links = access_url_xml('https://tamanhhospital.vn/sitemap_index.xml')
for link in links:
    print(link)
    print("++++++++++++++++++++++++++++++++")
    # Trích xuất 'field' từ URL
    field = re.search(r'/([a-zA-Z]+)-', link)
    field_name = field.group(1) if field else 'Unknown'
    # Lấy các liên kết từ các URL con
    links_cld = access_url_xml(link)
    for link_cld in links_cld:
        print(link_cld)
        title = link_cld.rstrip("/").split("/")[-1]
        if link_cld not in unique_urls and link_cld != 'https://tamanhhospital.vn/sitemap_index.xml':
            unique_urls.append(link_cld)  # Thêm vào set để tránh trùng
            data_to_save.append((field_name, title, link_cld))  # Lưu dữ liệu



save_to_csv(data_to_save)

# Đóng trình duyệt
driver.quit()

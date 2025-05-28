import os
import csv

INPUT_DIR1 = './Data_lakeHouse/Qdrant/dags/ivie_split'
INPUT_DIR2 = './Data_lakeHouse/Qdrant/dags/bvthucuc/bvthucuc_qa.csv'
INPUT_DIR3 = './Data_lakeHouse/Qdrant/dags/medlatec/medlatec_qa.csv'
INPUT_DIR4 = './Data_lakeHouse/Qdrant/dags/vietnamese_medical_chat_data.csv'
INPUT_DIR5 = './Data_lakeHouse/Qdrant/dags/vietnamese_medical_qa.csv'


OUTPUT_FILE = 'finetune/dataset/question_answer.csv'

def merge_csv_files(input_dir, output_file):
    csv_files = [f for f in os.listdir(input_dir) if f.endswith('.csv')]
    csv_files.sort()  

    with open(output_file, 'w', newline='', encoding='utf-8') as fout:
        writer = csv.writer(fout)
        writer.writerow(['Question', 'Context'])  

        for file in csv_files:
            filepath = os.path.join(input_dir, file)
            with open(filepath, 'r', encoding='utf-8') as fin:
                reader = csv.reader(fin)
                next(reader) 
                for row in reader:
                    writer.writerow(row)

        with open(INPUT_DIR2, 'r', encoding='utf-8') as fin:
            reader = csv.reader(fin)
            next(reader)  
            for row in reader:
                writer.writerow(row)

        with open(INPUT_DIR3, 'r', encoding='utf-8') as fin:
            reader = csv.reader(fin)
            next(reader)  
            for row in reader:
                writer.writerow(row)

        with open(INPUT_DIR4, 'r', encoding='utf-8') as fin:
            reader = csv.reader(fin)
            next(reader)  
            for row in reader:
                writer.writerow(row)

        with open(INPUT_DIR5, 'r', encoding='utf-8') as fin:
            reader = csv.reader(fin)
            next(reader)  
            for row in reader:
                writer.writerow(row)
        

    print(f"Đã gộp {len(csv_files)} file thành công vào {output_file}.")

if __name__ == '__main__':
    merge_csv_files(INPUT_DIR1, OUTPUT_FILE)

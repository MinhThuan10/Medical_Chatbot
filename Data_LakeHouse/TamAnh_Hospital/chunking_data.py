import pandas as pd
import nltk
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import torch
import re
import json
BUFFER_SIZE = 1
SIM_THRESHOLD = 0.85

model = SentenceTransformer('dangvantuan/vietnamese-document-embedding', trust_remote_code=True, device="cuda")

df = pd.read_csv("./Medical_Chatbot/Data_LakeHouse/TamAnh_Hospital/data_cleaned.csv")

all_chunks = []


def split_vietnamese_sentences(text):
    text = re.sub(r'(?<=[.?!…])(?=[^\s])', r' ', text)
    sentence_endings = re.compile(r'(?<=[.?!…])\s+')
    sentences = sentence_endings.split(text)
    sentences = [s.strip() for s in sentences if s.strip()]

    return sentences


def process_row(row):
    url = row["url"]
    title = row["title"]
    heading = row["heading"]
    content = row["content"]

    sentences = split_vietnamese_sentences(content)

    grouped_sentences = []
    for i in range(len(sentences)):
        group = []
        for j in range(i - BUFFER_SIZE, i + BUFFER_SIZE + 1):
            if 0 <= j < len(sentences):
                group.append(sentences[j])
        grouped_sentences.append(" ".join(group))

    embeddings = model.encode(grouped_sentences)

    chunks = []
    current_chunk = [grouped_sentences[0]]
    current_embeddings = [embeddings[0]]

    for i in range(1, len(grouped_sentences)):
        sim = cosine_similarity(
            [embeddings[i - 1]], [embeddings[i]]
        )[0][0]

        if sim >= SIM_THRESHOLD:
            current_chunk.append(grouped_sentences[i])
            current_embeddings.append(embeddings[i])
        else:
            chunk_text = " ".join(current_chunk)
            avg_embedding = np.mean(current_embeddings, axis=0).tolist()
            chunks.append({
                "chunk": chunk_text,
                "url": url,
                "title": title,
                "heading": heading,
                "embedding": avg_embedding
            })
            current_chunk = [grouped_sentences[i]]
            current_embeddings = [embeddings[i]]

    if current_chunk:
        chunk_text = " ".join(current_chunk)
        avg_embedding = np.mean(current_embeddings, axis=0).tolist()
        chunks.append({
            "chunk": chunk_text,
            "url": url,
            "title": title,
            "heading": heading,
            "embedding": avg_embedding
        })

    return chunks

    # return grouped_sentences

# --- Xử lý toàn bộ file ---
for _, row in df.iterrows():
    chunks = process_row(row)
    print(row["url"])
    all_chunks.extend(chunks)

with open("./Medical_Chatbot/Data_LakeHouse/TamAnh_Hospital/all_chunks_with_embeddings.jsonl", "w", encoding="utf-8") as f:
    for chunk in all_chunks:
        f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

print(f"Đã lưu {len(all_chunks)} chunk với embedding vào 'all_chunks_with_embeddings.json'")



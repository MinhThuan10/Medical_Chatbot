import pandas as pd
import nltk
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import torch
import re
import json
BUFFER_SIZE = 1
SIM_THRESHOLD = 0.8

model = SentenceTransformer('bkai-foundation-models/vietnamese-bi-encoder', trust_remote_code=True, device="cuda")
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
    print(url)
    sentences = split_vietnamese_sentences(content)
    chunk_dicts = []

    grouped_sentences = []
    if len(sentences) > 0 and len(sentences) <= 3:
        chunk_text = " ".join(sentences)
        embeddings_chunk = model.encode([chunk_text])
        chunk_dict = {
            "chunk": chunk_text,
            "url": url,
            "title": title,
            "heading": heading,
            "embedding": embeddings_chunk[0].tolist()
        }
        chunk_dicts.append(chunk_dict)
        return chunk_dicts
    
    
    for i in range(1, len(sentences)):
        group = []
        for j in range(i - BUFFER_SIZE, i + BUFFER_SIZE + 1):
            if 0 <= j < len(sentences):
                group.append(sentences[j])
        grouped_sentences.append(" ".join(group))

    embeddings = model.encode(grouped_sentences)

    chunks = []
    current_chunk_sentences = split_vietnamese_sentences(grouped_sentences[0])

    for i in range(1, len(grouped_sentences)):
        sim = cosine_similarity(
            [embeddings[i - 1]], [embeddings[i]]
        )[0][0]

        next_sentences = split_vietnamese_sentences(grouped_sentences[i])
        if sim >= SIM_THRESHOLD:
            overlap = len(set(current_chunk_sentences).intersection(next_sentences))
            new_part = next_sentences[overlap:]  # skip overlapping part
            current_chunk_sentences.extend(new_part)
        else:
            # Save current chunk
            chunk_text = " ".join(current_chunk_sentences)
            chunks.append(chunk_text)
            # Reset for new chunk
            current_chunk_sentences = next_sentences
    # Save last chunk
    if current_chunk_sentences:
        chunk_text = " ".join(current_chunk_sentences)
        chunks.append(chunk_text)

    embeddings_chunk = model.encode(chunks)
    for i, chunk in enumerate(chunks):
        chunk_embedding = embeddings_chunk[i]
        chunk_dict = {
            "chunk": chunk,
            "url": url,
            "title": title,
            "heading": heading,
            "embedding": chunk_embedding.tolist()
        }
        chunk_dicts.append(chunk_dict)


    return chunk_dicts


for _, row in df.iterrows():
    chunks = process_row(row)
    all_chunks.extend(chunks)


with open("./Medical_Chatbot/Data_LakeHouse/TamAnh_Hospital/chunks_embeddings.jsonl", "w", encoding="utf-8") as f:
    for chunk in all_chunks:
        f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

print(f"Đã lưu {len(all_chunks)} chunk với embedding vào 'chunks_embeddings.json'")



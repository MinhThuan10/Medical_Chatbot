import pandas as pd
import re
import json
import random
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

BUFFER_SIZE = 1
SIM_THRESHOLD = 0.5
random.seed(42)

model = SentenceTransformer(
    "bkai-foundation-models/vietnamese-bi-encoder",
    trust_remote_code=True,
    device="cuda",
)

df = pd.read_csv("../data_cleaned.csv")

def split_vietnamese_sentences(text):
    text = re.sub(r"(?<=[.?!…])(?=[^\s])", r" ", text)
    sentence_endings = re.compile(r"(?<=[.?!…])\s+")
    sentences = sentence_endings.split(text)
    return [s.strip() for s in sentences if s.strip()]

def process_row(row):

    url = row["url"]
    title = row["title"]
    heading = row["heading"]
    content = str(row["heading"]) + " " + str(row["content"])
    sentences = split_vietnamese_sentences(content)
    print(url)
    
    if len(sentences) == 0:
        return []

    if len(sentences) <= 3:
        chunk_text = " ".join(sentences)
        embedding = model.encode([chunk_text])[0].tolist()
        return [{"chunk": chunk_text, "url": url, "title": title, "heading": heading, "embedding": embedding}]

    grouped_sentences = []
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
        sim = cosine_similarity([embeddings[i - 1]], [embeddings[i]])[0][0]
        next_sentences = split_vietnamese_sentences(grouped_sentences[i])

        if sim >= SIM_THRESHOLD:
            overlap = len(set(current_chunk_sentences).intersection(next_sentences))
            new_part = next_sentences[overlap:]
            current_chunk_sentences.extend(new_part)
        else:
            chunks.append(" ".join(current_chunk_sentences))
            current_chunk_sentences = next_sentences

    if current_chunk_sentences:
        chunks.append(" ".join(current_chunk_sentences))

    embeddings_chunk = model.encode(chunks)
    return [
        {
            "chunk": chunk,
            "url": url,
            "title": title,
            "heading": heading,
            "embedding": embeddings_chunk[i].tolist(),
        }
        for i, chunk in enumerate(chunks)
    ]


all_chunks = []
query_meta = {}
qrels = []

chunk_counter = 0
query_counter = 0

for _, row in df.iterrows():
    heading = str(row["heading"]).strip()
    answer = str(row["content"]).strip()
    if not heading or not answer:
        continue

    if heading not in query_meta:
        qid = f"q_{query_counter}"
        query_meta[heading] = {"id": qid, "question": heading, "answer": answer}
        query_counter += 1

    qid = query_meta[heading]["id"]
    chunks = process_row(row)

    for chunk in chunks:
        cid = chunk_counter
        chunk_counter += 1
        chunk["id"] = cid

        all_chunks.append(chunk)
        qrels.append({"query_id": qid, "chunk_id": cid, "relevance": 1})

# Chọn 1000 query nếu đủ
query_items = list(query_meta.values())
selected_query_items = (
    random.sample(query_items, k=1000)
    if len(query_items) >= 1000
    else query_items
)
selected_qids = {item["id"] for item in selected_query_items}

# Lưu corpus đầy đủ
with open("./chunks_embeddings.jsonl", "w", encoding="utf-8") as f:
    for item in all_chunks:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

# Lưu query
with open("./eval_queries.jsonl", "w", encoding="utf-8") as f:
    for item in selected_query_items:
        f.write(
            json.dumps({"id": item["id"], "text": item["question"]}, ensure_ascii=False)
            + "\n"
        )

# Lưu qrels cho query đã chọn
with open("./eval_qrels.jsonl", "w", encoding="utf-8") as f:
    for item in qrels:
        if item["query_id"] in selected_qids:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

# Lưu eval QA
with open("./eval_qa.jsonl", "w", encoding="utf-8") as f:
    for item in selected_query_items:
        f.write(
            json.dumps(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "answer": item["answer"],
                },
                ensure_ascii=False,
            )
            + "\n"
        )
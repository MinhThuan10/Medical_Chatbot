from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
import json
from qdrant_client.models import PointStruct
from tqdm import tqdm
import uuid


client = QdrantClient(host="localhost", port=6333) 

client.recreate_collection(
    collection_name="tamanh-crawl",
    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
)




batch = []
with open("./Medical_Chatbot/Data_LakeHouse/TamAnh_Hospital/all_chunks_with_embeddings.jsonl", "r", encoding="utf-8") as f:
    for i, line in enumerate(tqdm(f)):
        item = json.loads(line)
        point = PointStruct(
            id=str(uuid.uuid4()),  # random id
            vector=item["embedding"],
            payload={
                "chunk": item["chunk"],
                "url": item["url"],
                "title": item["title"],
                "heading": item["heading"]
            }
        )
        batch.append(point)

        # Insert theo batch size
        if len(batch) == 100:
            client.upsert(collection_name="tamanh-crawl", points=batch)
            batch = []

# Insert phần còn lại
if batch:
    client.upsert(collection_name="tamanh-crawl", points=batch)

print("✅ Đã lưu toàn bộ embedding vào Qdrant")

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
import numpy as np

model = SentenceTransformer('dangvantuan/vietnamese-document-embedding', trust_remote_code=True, device="cuda")

query = "Triệu chứng của bệnh viêm gan là gì?"

query_vector = model.encode(query).tolist()

client = QdrantClient(host="localhost", port=6333)  # Sửa lại nếu bạn dùng cloud

hits = client.search(
    collection_name="tamanh-crawl",
    query_vector=query_vector,
    limit=5
)

for i, hit in enumerate(hits):
    print(f"\n--- Kết quả #{i+1} ---")
    print("Score:", hit.score)
    print("Title:", hit.payload.get("title"))
    print("Heading:", hit.payload.get("heading"))
    print("URL:", hit.payload.get("url"))
    print("Chunk:", hit.payload.get("chunk"))

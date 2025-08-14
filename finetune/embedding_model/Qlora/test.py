import asyncio
from llama_index.core.llama_dataset import download_llama_dataset
from llama_index.core.llama_pack import download_llama_pack
from llama_index.core import VectorStoreIndex
from llama_index.llms.openai import OpenAI

async def main():
    # Tải dataset mẫu từ llama-index
    rag_dataset, documents = download_llama_dataset(
        "Uber10KDataset2021", "./uber10k_2021_dataset"
    )

    # Tạo index
    index = VectorStoreIndex.from_documents(documents=documents)
    query_engine = index.as_query_engine()

    # Tải bộ đánh giá RAG
    RagEvaluatorPack = download_llama_pack("RagEvaluatorPack", "./pack_stuff")
    judge_llm = OpenAI(model="gpt-3.5-turbo")
    rag_evaluator = RagEvaluatorPack(
        query_engine=query_engine, rag_dataset=rag_dataset, judge_llm=judge_llm
    )

    # Chạy benchmark
    benchmark_df = await rag_evaluator.arun(
        batch_size=20,
        sleep_time_in_seconds=1,
    )
    print(benchmark_df)

if __name__ == "__main__":
    asyncio.run(main())  # <-- Dùng asyncio.run thay cho loop.run_until_complete

import os
import json
import sys
import re
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# PROJECT SETUP
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


# ============================================================
# LOAD ENV
# ============================================================

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")


# ============================================================
# IMPORT RAG
# ============================================================

from app.src.services.langchains_graphRAG import LangChainRAG


# ============================================================
# CONFIG
# ============================================================

MAX_WORKERS = 2

INPUT_PATH = (
    Path(__file__).parent
    / "rag_benchmark.jsonl"
)

OUTPUT_PATH = (
    Path(__file__).parent
    / "evaluation_dataset_retrieved_graphrag.jsonl"
)


# ============================================================
# GLOBAL LOCK FOR PRINT
# ============================================================

print_lock = threading.Lock()

from enum import Enum

class SearchType(str, Enum):
    LOCAL = "local"
    GLOBAL = "global"
    DRIFT = "drift"
    CHAT = "chat"
    OTHER = "other"
# ============================================================
# PROCESS ONE QUESTION
# ============================================================

def process_one(
    index: int,
    item: dict,
    rag: LangChainRAG,
):
    """
    Process one evaluation sample.

    Steps:
    1. Retrieve documents
    2. Rerank documents
    3. Generate RAG answer
    4. Consume StreamingResponse
    """

    question = item["question"]

    with print_lock:
        print(
            f"\n[{index}] "
            f"Question: {question}"
        )

    try:

        # ----------------------------------------------------
        # 1. Retrieve documents
        # ----------------------------------------------------
        
        query_routing = rag.query_routing(
            question
        )

        context, chunk_map, raw_context = rag.search_documents(
            question,
            # query_routing.search_type,
            query_routing = SearchType.LOCAL,
            
        )

        # raw_contexts = [
        #     doc.page_content
        #     for doc in raw_docs
        # ]

        # # ----------------------------------------------------
        # # 2. Rerank retrieved documents
        # # ----------------------------------------------------

        # reranked_contexts = (
        #     rag.reranking_documents(
        #         question,
        #         raw_contexts,
        #     )
        # )

        item["retrieved_contexts"] = (
            raw_context
        )

        # ----------------------------------------------------
        # 3. Generate answer
        # ----------------------------------------------------

        # response = rag.answer_context(
        #     question,
        #     reranked_contexts,
        # )

        # # ----------------------------------------------------
        # # 4. Consume StreamingResponse
        # # ----------------------------------------------------

        # chunks = []

        # async def consume_response():
        #     async for chunk in response.body_iterator:

        #         if isinstance(chunk, bytes):
        #             chunks.append(
        #                 chunk.decode("utf-8")
        #             )
        #         else:
        #             chunks.append(chunk)

        # # Since process_one is synchronous,
        # # create an event loop for this thread.
        # import asyncio

        # asyncio.run(
        #     consume_response()
        # )

        # raw_answer = (
        #     "".join(chunks)
        #     .strip()
        # )

        # # ----------------------------------------------------
        # # 5. Remove <think>...</think>
        # # ----------------------------------------------------

        # rag_answer = re.sub(
        #     r"<think>.*?</think>",
        #     "",
        #     raw_answer,
        #     flags=re.DOTALL,
        # ).strip()

        # item["rag_answer"] = rag_answer

        # with print_lock:
        #     print(
        #         f"[{index}] "
        #         f"Retrieved contexts: "
        #         f"{len(reranked_contexts)}"
        #     )

        #     print(
        #         f"[{index}] "
        #         f"RAG Answer: "
        #         f"{rag_answer}"
        #     )

        return index, item, None

    except Exception as e:

        with print_lock:
            print(
                f"[{index}] "
                f"Error: {type(e).__name__}: {e}"
            )

        item["retrieved_contexts"] = []
        item["rag_answer"] = ""

        return index, item, e


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # Initialize RAG
    # --------------------------------------------------------

    print(
        "Initializing LangChainRAG..."
    )

    rag = LangChainRAG()

    # --------------------------------------------------------
    # Check input
    # --------------------------------------------------------

    if not INPUT_PATH.exists():

        print(
            f"Error: {INPUT_PATH} "
            "does not exist. "
            "Please run the data generation first."
        )

        return

    # --------------------------------------------------------
    # Load dataset
    # --------------------------------------------------------

    print(
        f"Reading questions from "
        f"{INPUT_PATH}..."
    )

    items = []

    with open(
        INPUT_PATH,
        "r",
        encoding="utf-8",
    ) as f:

        for line in f:

            if line.strip():

                items.append(
                    json.loads(line)
                )

    print(
        f"Loaded {len(items)} questions."
    )

    print(
        f"Running RAG retrieval and "
        f"answer generation with "
        f"{MAX_WORKERS} workers..."
    )

    # --------------------------------------------------------
    # Prepare results
    #
    # Use index to preserve original order.
    # --------------------------------------------------------

    results = [None] * len(items)

    # --------------------------------------------------------
    # Run threads
    # --------------------------------------------------------

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = []

        for index, item in enumerate(
            items,
            start=1,
        ):

            future = executor.submit(
                process_one,
                index,
                item,
                rag,
            )

            futures.append(
                future
            )

        # ----------------------------------------------------
        # Collect completed tasks
        # ----------------------------------------------------

        completed = 0

        for future in as_completed(
            futures
        ):

            index, item, error = (
                future.result()
            )

            # Convert 1-based index
            # to 0-based list index
            results[index - 1] = item

            completed += 1

            with print_lock:

                if error is None:

                    print(
                        f"Progress: "
                        f"{completed}/"
                        f"{len(items)} "
                        f"completed"
                    )

                else:

                    print(
                        f"Progress: "
                        f"{completed}/"
                        f"{len(items)} "
                        f"completed "
                        f"(with error)"
                    )

    # --------------------------------------------------------
    # Save results
    # --------------------------------------------------------

    print(
        f"\nSaving results to "
        f"{OUTPUT_PATH}..."
    )

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8",
    ) as f:

        for item in results:

            f.write(
                json.dumps(
                    item,
                    ensure_ascii=False,
                )
                + "\n"
            )

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    success_count = sum(
        1
        for item in results
        if item.get("rag_answer")
    )

    failed_count = (
        len(results)
        - success_count
    )

    print(
        "\nDone!"
    )

    print(
        f"Total: {len(results)}"
    )

    print(
        f"Success: {success_count}"
    )

    print(
        f"Failed: {failed_count}"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()

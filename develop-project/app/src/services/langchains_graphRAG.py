from langchain.memory import ConversationBufferWindowMemory
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.src.services.base_service import base_service
from app.src.services.search_document import local_search, global_search, drift_search
from enum import Enum
from langsmith import traceable
import re

REWRITE_QUESTION_PROMPT = """
Your tasks are:

1. Rewrite the user's question so that it is:
   - Self-contained.
   - Clear and unambiguous.
   - Complete by incorporating relevant context from the conversation history when necessary.
   - Suitable for knowledge retrieval.
Conversation history:
{chat_history}

Current user question:
{query}
"""


TRANSFORM_QUESTION_PROMPT = """
Your tasks are:

1. Analyze the user's question and classify it into exactly one of the following routing types based on its medical intent and the required retrieval method:

- local_search:
    The question focuses on specific, well-defined medical entities (e.g., a specific disease, a particular medication/drug name, a distinct symptom, a specific medical department, or a doctor) and requires detailed, narrow-scope information directly linked to those entities.
    Example: "What are the side effects of Metformin?", "Who is the head of the Cardiology department?", or "What are the primary symptoms of Type 2 Diabetes?"

- global_search:
    The question asks for high-level medical summaries, broad themes, epidemiological trends, comparisons across multiple disease categories, or overall medical guidelines across the entire dataset without focusing on one single entity.
    Example: "Summarize the general prevention strategies for chronic respiratory diseases mentioned in the guidelines", "What are the common health risks associated with aging according to these documents?", or "Provide an overview of the hospital's treatment protocols for infectious diseases."

- drift_search:
    The question is complex and requires multi-hop medical reasoning, connecting separate pieces of information, exploring cause-and-effect relationships, or understanding indirect clinical impacts (e.g., how a shortage of drug A affects the treatment outcome of disease B, or how disease X correlates with condition Y over time).
    Example: "How does a prolonged shortage of insulin indirectly affect the emergency admission rates for kidney failure patients?", or "Explain how untreated hypertension might over time lead to chronic kidney disease based on the case studies."

- chat:
    Casual conversation, small talk, greetings, expressions of gratitude, introductions, or questions about the chatbot identity itself.
    Example: "Hello Doctor!", "Thank you for explaining the diagnosis", or "Are you an AI medical assistant?"

- other:
    Any general question or informational query that is completely unrelated to the medical, healthcare, or pharmaceutical domain, and does not require graph-based medical retrieval.
    Example: "What is the capital city of France?" or "How do I fix a leaking water pipe?"
Question:
{question}
"""

ANSWER_QUESTION_PROMPT = """
You are an intelligent medical assistant. Your role is to answer ONLY medical-related questions using the provided context.

# Question
{question}

# Context
{context}

Instructions:

1. Answer ONLY based on the provided context.
2. Do not make up or infer information that is not supported by the context.
3. If the context does not contain enough information to answer the question, reply:

"Tôi chưa có đủ thông tin trong tài liệu hiện có để trả lời câu hỏi này."

4. Respond in Vietnamese.
5. Format the answer using clean and readable Markdown.
6. Remove unnecessary whitespace.
7. Identify the type of the provided context to apply the correct citation rule:

- CASE A: If the context consists of Text Chunks (each having a unique Chunk ID):
  You MUST append a citation tag on a new line immediately after every factual paragraph using exactly this format:
  <cite:0,1,2>
  (Replace 0,1,2 with the actual Chunk IDs used).

- CASE B: If the context consists of Community Summaries (or any format other than Text Chunks):
  Do NOT include any citation tags anywhere in the answer.

Rules for citations (Only applicable for CASE A):
- Only use Chunk IDs that explicitly appear in the provided context.
- Never invent a Chunk ID.
- Every factual paragraph must have exactly one citation tag.
- Do not explain the citation tags.
- Preserve the exact Chunk IDs as they appear in the context.

Return only the final answer.
"""


class SearchType(str, Enum):
    DRIFT = "drift"
    GLOBAL = "global"
    LOCAL = "local"
    CHAT = "chat"
    ORDER = "order"

class RoutingQuestion(BaseModel):
    search_type: SearchType = Field(
        description="The retrieval strategy that should be used."
    )


class RewriteQuestion(BaseModel):
    rewrite_question: str = Field(
        description="A rewritten standalone version of the user's question."
    )




    
class LangChainRAG():
    def __init__(self):
        self.memories = {}
        self.citation_memories = {}

    def get_memory(self, chat_id):
        chat_id = str(chat_id).strip()
        if chat_id not in self.memories:
            self.memories[chat_id] = ConversationBufferWindowMemory(
                memory_key="chat_history",
                return_messages=True, k=5
            )
        return self.memories[chat_id]

    def get_chunk_memory(self, conversation_id):
        if conversation_id not in self.citation_memories:
            self.citation_memories[conversation_id] = {}

        return self.citation_memories[conversation_id]

    @traceable(run_type="chain", name="Query Transform")
    def query_transform(self, question: str, history) -> str:
        structured_llm = base_service.llm_model_var.with_structured_output(RewriteQuestion)

        try:
            response = structured_llm.invoke([
                {
                    "role": "system",
                    "content": "You are an expert in Transform Question"
                },
                {
                    "role": "user",
                    "content": REWRITE_QUESTION_PROMPT.format(
                        chat_history=history,
                        query=question
                    )
                }
            ])
            return response
        except Exception as exc:
            print(f"[LLM_ERROR] query_transform failed: {exc}")
            return RewriteQuestion(
                rewrite_question=question
            )


    def query_routing(self, question: str):
        structured_llm = base_service.llm_model_var.with_structured_output(RoutingQuestion)
        try:
            response = structured_llm.invoke([
                {
                    "role": "system",
                    "content": "You are an expert in Routing Question."
                },
                {
                    "role": "user",
                    "content": TRANSFORM_QUESTION_PROMPT.format(
                        question=question
                    )
                }
            ])
            return response
        except Exception as exc:
            print(f"[LLM_ERROR] query_transform failed: {exc}")
            return RoutingQuestion(
                search_type=SearchType.CHAT,
            )
    @traceable(run_type="chain", name="Search Documents")
    def search_documents(self, query_transform, quwery_routing):
        print(f"Category: {query_transform}, {quwery_routing}")
        context = ''
        chunk_map = {}
        match quwery_routing:
            case SearchType.LOCAL:
                result = local_search.local_search(query_transform)
                context = result["context"]
                chunk_map = result["chunk_map"]
            case SearchType.GLOBAL:
                result = global_search.global_search(query_transform)
                context = result["context"]
            case SearchType.DRIFT:
                result = drift_search.drift_search(query_transform)
                context = result["context"]
                chunk_map = result["chunk_map"]
            case SearchType.CHAT:
                context = "Xin chào bạn, mình là trợ lý Medical AI. Mình có thể giúp gì cho bạn"
            case SearchType.OTHER:
                context = ""
                

        return context, chunk_map

    def answer_context(self, question, context):
        context = context[:8196]
        async def generate():
            messages = [
                {
                    "role": "system",
                    "content": "You are a physician's assistant; please answer the following question accurately."
                },
                {
                    "role": "user",
                    "content": ANSWER_QUESTION_PROMPT.format(
                        question=question,
                        context=context
                    )
                }
            ]

            try:
                async for chunk in base_service.llm_model_var.astream(messages):
                    if getattr(chunk, "content", None):
                        yield chunk.content
            except Exception as exc:
                print(f"[LLM_ERROR] answer_context streaming failed: {exc}")
                yield "Xin lỗi, hiện tại tôi không thể tạo câu trả lời do lỗi từ mô hình."

        return StreamingResponse(generate(), media_type="text/plain")


    def chat(self, question: str, chat_id):
        memory = self.get_memory(chat_id)
        history = memory.load_memory_variables({}).get("chat_history", "")
        self.get_chunk_memory(chat_id).clear()
        query_transform = self.query_transform(question, history)
        query_routing = self.query_routing(query_transform.rewrite_question)
        context = ''
        if query_transform:
            context, chunk_map = self.search_documents(query_transform.rewrite_question, query_routing.search_type)
            self.get_chunk_memory(chat_id).update(chunk_map)
        return self.answer_context(question, context)
    
    def save_menory(self, memory, question, answer):

        memory.chat_memory.add_user_message(question)
        memory.chat_memory.add_ai_message(answer)



    def parse_answer_and_citations(self, answer_text: str, chunk_map: dict):
        """
        Parse <cite:...> trong answer và sinh citations_json.

        Returns
        -------
        clean_answer : str
        citations_json : list
        """

        pattern = r"<cite:([^>]+)>"

        citations = []
        marker_index = 1

        def replace(match):
            nonlocal marker_index

            ids = [x.strip() for x in match.group(1).split(",")]

            sources = []

            for cid in ids:
                if cid in chunk_map:
                    sources.append({
                        "chunk_id": chunk_map[cid]["chunk_id"],
                        "title": chunk_map[cid]["title"],
                        "url": chunk_map[cid]["url"],
                        "text": chunk_map[cid]["text"]
                    })

            citations.append({
                "display": marker_index,
                "marker": f"[[{marker_index}]]",
                "sources": sources
            })

            current = marker_index
            marker_index += 1

            return f"[[{current}]]"

        clean_answer = re.sub(pattern, replace, answer_text)

        return clean_answer, citations


GraphRAG = LangChainRAG()

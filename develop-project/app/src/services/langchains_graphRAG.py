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
"""


TRANSFORM_QUESTION_PROMPT = """
Your task is to:

1. Analyze the user's question and classify it into exactly one of the following navigation categories, based on the medical intent and the required information retrieval method:

- drift_search (extended/linked search): Multi-part or complex questions requiring a multi-step medical reasoning process; questions necessitating the use of multiple information sources and an expanded search scope. This type of question involves connecting disparate pieces of information, exploring causal relationships, or understanding indirect clinical impacts.
Examples: "How does prolonged insulin deficiency indirectly affect emergency hospital admission rates for patients with renal failure?", "Based on case studies, explain how untreated hypertension can lead to chronic kidney disease over time," or comparing different issues.

- local_search:
Questions focusing on a specific, clearly defined medical entity (e.g., a specific disease, drug name, distinct symptom, medical specialty, or doctor) and requiring detailed, narrowly scoped information directly related to those entities.
Examples: "What are the side effects of Metformin?", "Who is the Head of Cardiology?", or "What are the main symptoms of type 2 diabetes?"

- global_search:
Questions requiring general medical summaries, broad topics, epidemiological trends, or overarching medical guidelines across the entire dataset, without focusing on any single entity.
Examples: "Summarize general prevention strategies for chronic respiratory diseases mentioned in the guidelines," "What are the common health risks associated with aging?", or "Provide an overview of the hospital's treatment protocols for infectious diseases."

- chat:
Casual conversations, pleasantries, greetings, or remarks. ...expressions of gratitude, self-introductions, or questions regarding the chatbot's own identity.
Examples: "Hello, Doctor!", "Thank you for explaining the diagnosis," or "Are you an AI medical assistant?"

- other:
Any general questions or information queries completely unrelated to the fields of medicine, healthcare, or pharmaceuticals, and which do not require graph-based medical information retrieval.
Examples: "What is the capital of France?" or "How do I fix a leaking pipe?"
Question:
"""


ANSWER_QUESTION_PROMPT = """
You are an intelligent medical assistant. Your role is to answer ONLY medical-related questions using the provided context.
Instructions:

1. Answer ONLY based on the provided context.
2. Do not make up or infer information that is not supported by the context.
3. If the context does not contain enough information to answer the question, reply:

"Tôi chưa có đủ thông tin trong tài liệu hiện có để trả lời câu hỏi này."

4. Respond in Vietnamese.
5. Format the answer using clean and readable Markdown.
6. Remove unnecessary whitespace.
7. Identify the type of the provided context to apply the correct citation rule:

- If Search Type: is "local_search" or "drift_search", use the citation format: <cite:0,1,2,..> where Chunk IDs correspond to the relevant context chunks.
- If Search Type: is "global_search", do not include any citations in the answer.
  You MUST append a citation tag on a new line immediately after every factual paragraph using exactly this format:
  <cite:0,1,2>
  (Replace 0,1,2 with the actual Chunk IDs used).

Return only the final answer.
"""


class SearchType(str, Enum):
    DRIFT = "drift"
    GLOBAL = "global"
    LOCAL = "local"
    CHAT = "chat"
    OTHER = "other"

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

    # @traceable(run_type="chain", name="Query Transform")
    def query_transform(self, question: str, history) -> str:
        structured_llm = base_service.llm_model_var.with_structured_output(RewriteQuestion)

        try:
            response = structured_llm.invoke([
                {
                    "role": "system",
                    "content": REWRITE_QUESTION_PROMPT
                },
                {
                    "role": "user",
                    "content": (f"Conversation history:\n{history}\n\nQuestion:\n{question}\n\n")
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
                    "content": TRANSFORM_QUESTION_PROMPT
                },
                {
                    "role": "user",
                    "content": (f"Question:\n{question}\n\n")
                }
            ])
            return response
        except Exception as exc:
            print(f"[LLM_ERROR] query_transform failed: {exc}")
            return RoutingQuestion(
                search_type=SearchType.CHAT,
            )

        
    @traceable(run_type="chain", name="Search Documents")
    def search_documents(self, query_transform, query_routing):
        print(f"Category: {query_transform}, {query_routing}")
        context = ''
        chunk_map = {}
        raw_context = []
        match query_routing:
            case SearchType.LOCAL:
                result = local_search.local_search(query_transform)
                context = result["context"]
                chunk_map = result["chunk_map"]
                raw_context = [
                    chunk["text"]
                    for chunk in result["raw_context"].get("chunks", [])
                    if chunk.get("text")
                ]
                
            case SearchType.GLOBAL:
                print("Search Global")
                result = global_search.global_search(query_transform)
                context = result["context"]
                raw_context = [
                    finding.summary
                    for finding in result["raw_context"]
                    if finding.summary
                ]



            case SearchType.DRIFT:
                result = drift_search.drift_search(query_transform)
                context = result["context"]
                chunk_map = result["chunk_map"]
                raw_context = [
                    chunk.get("text")
                    for chunk in result["raw_context"].chunks
                    if chunk.get("text")
                ]

            case SearchType.CHAT:
                context = "Xin chào bạn, mình là trợ lý Medical AI. Mình có thể giúp gì cho bạn"
            case SearchType.OTHER:
                context = "Mình không thể trả lời câu hỏi này vì nó không liên quan đến lĩnh vực y tế. Bạn có thể hỏi về các bệnh, thuốc, triệu chứng, chuyên khoa hoặc bác sĩ."
                

        return context, chunk_map, raw_context

    @traceable(run_type="chain", name="Answer Context")
    def answer_context(self, question, context, search_type):
        context = context[:16392]
        async def generate():
            messages = [
                {
                    "role": "system",
                    "content": ANSWER_QUESTION_PROMPT
                },
                {
                    "role": "user",
                    "content": (f"Search Type: {search_type}\n Question:\n{question}\n\nContext:\n{context}\n\n")
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
            context, chunk_map, _ = self.search_documents(query_transform.rewrite_question, query_routing.search_type)
            self.get_chunk_memory(chat_id).update(chunk_map)
        return self.answer_context(question, context, query_routing.search_type)
    
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

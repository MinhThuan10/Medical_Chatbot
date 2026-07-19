from langchain.memory import ConversationBufferWindowMemory
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.src.services.base_service import base_service
from app.src.services.search_document import local_search, global_search, drift_search
from enum import Enum
from langsmith import traceable

REWRITE_QUESTION_PROMPT = """
You are an expert query rewriting and routing assistant for a medical GraphRAG system.

Your tasks are:

1. Rewrite the user's question so that it is:
   - Self-contained.
   - Clear and unambiguous.
   - Complete by incorporating relevant context from the conversation history when necessary.
   - Suitable for knowledge retrieval.

2. Classify the question into exactly one of the following question types:

- medical
    Questions related to medicine, diseases, symptoms, drugs, diagnosis, treatment,
    healthcare, nutrition, laboratory tests, or medical procedures.

- chat
    Casual conversation such as greetings, thanks, introductions, or questions about the chatbot itself.

- other
    Any question that does not belong to the medical domain.

3. Choose exactly one retrieval strategy:

- local
    Use when the question asks about a specific medical entity, concept, disease, drug,
    symptom, laboratory test, treatment, guideline, or factual information.

- global
    Use when the question requires an overview, summary, statistics, trends,
    comparisons across multiple topics, or information aggregated from many documents.

- drift
    Use when answering the question requires multi-hop reasoning, progressive exploration,
    or connecting multiple related entities across the knowledge graph.

Conversation history:
{chat_history}

Current user question:
{query}
"""

ANSWER_QUESTION_PROMPT = """
Bạn là một trợ lý y tế thông minh, chỉ trả lời các câu hỏi liên quan đến y tế. Dưới đây là các câu hỏi từ người dùng và tài liệu được cung cấp:

#Question:
    {question}

#Context:
    {context}

Dựa trên câu hỏi và ngữ cảnh, hãy tổng hợp và đưa ra một câu trả lời rõ ràng, chính xác.
Nếu không có đủ thông tin trong ngữ cảnh, thì có thể đưa ra câu trả lời là tôi chưa có thông tin về câu hỏi của bạn nên hiện tại tôi không thể trả lời được. 
Trả lời bằng tiếng Việt và format câu trả lời theo dạng markdown một cách dễ đọc, không có các ký tự khoảng trắng thừa.
"""

class QuestionType(str, Enum):
    MEDICAL = "medical"
    CHAT = "chat"
    OTHER = "other"


class SearchType(str, Enum):
    DRIFT = "drift"
    LOCAL = "local"
    GLOBAL = "global"

class RewriteQuestion(BaseModel):
    rewrite_question: str = Field(
        description="A rewritten standalone version of the user's question."
    )

    question_type: QuestionType = Field(
        description="The category of the user's question."
    )

    search_type: SearchType = Field(
        description="The retrieval strategy that should be used."
    )



    
class LangChainRAG():
    def __init__(self):
        self.memories = {}

    def get_memory(self, chat_id):
        chat_id = str(chat_id).strip()
        if chat_id not in self.memories:
            self.memories[chat_id] = ConversationBufferWindowMemory(
                memory_key="chat_history",
                return_messages=True, k=5
            )
        return self.memories[chat_id]

    @traceable(run_type="chain", name="Query Transform")
    def query_transform(self, question: str, history) -> str:
        structured_llm = base_service.llm_model_var.with_structured_output(RewriteQuestion)

        try:
            response = structured_llm.invoke([
                {
                    "role": "system",
                    "content": "You are an expert in information extraction."
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
                rewrite_question=question,
                question_type=QuestionType.OTHER,
                search_type=SearchType.LOCAL,
            )

    @traceable(run_type="chain", name="Search Documents")
    def search_documents(self, query_transform):
        print(f"Category: {query_transform}")
        context = ''
        match query_transform.question_type:
            case QuestionType.MEDICAL:
                match query_transform.search_type:
                    case SearchType.LOCAL:
                        context = local_search.local_search(query_transform.rewrite_question)
                    case SearchType.GLOBAL:
                        context = global_search.global_search(query_transform.rewrite_question)
                    case SearchType.DRIFT:
                        context = drift_search.drift_search(query_transform.rewrite_question)
            case QuestionType.CHAT:
                context = ""
            case QuestionType.OTHER:
                context = ""
                

        return context

    def answer_context(self, question, context):
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
        query_transform = self.query_transform(question, history)
        context = ''
        if query_transform:
            context = self.search_documents(query_transform)

            print(context)
        return self.answer_context(question, context)
    
    def save_menory(self, memory, question, answer):

        memory.chat_memory.add_user_message(question)
        memory.chat_memory.add_ai_message(answer)

GraphRAG = LangChainRAG()
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from langchain.memory import ConversationBufferWindowMemory
from langchain_core.prompts import PromptTemplate
from langchain.schema import Document
import re
from fastapi.responses import StreamingResponse
from sentence_transformers import CrossEncoder
import json
import torch

class LangChainRAG:
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.qdrant_url = os.getenv("QDRANT_URL")

        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY or API_KEY is not set")

        os.environ["GOOGLE_API_KEY"] = self.api_key

        # Load 
        self.memories = {}
        self.llm_model_var = self.llm_model()
        self.rerank_model_var = self.rerank_model()
        self.embedding_model_var = self.embedding_model()


    def get_memory(self, chat_id):
        chat_id = str(chat_id).strip()
        if chat_id not in self.memories:
            self.memories[chat_id] = ConversationBufferWindowMemory(
                memory_key="chat_history",
                return_messages=True, k=5
            )
        return self.memories[chat_id]
    
    def llm_model(self):
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            temperature=0.2,
            convert_system_message_to_human=True,
        )

    def rerank_model(self):
        return CrossEncoder('itdainb/PhoRanker', max_length=256)
    

    def embedding_model(self):
        model_name = "dangvantuan/vietnamese-embedding"

        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"[Startup] Using device: {device}")
        
        model_kwargs = {'device': device}
        encode_kwargs = {'normalize_embeddings': False}
        hf = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs=model_kwargs,
            encode_kwargs=encode_kwargs
        )
        return hf

    def qdrant_client(self):
        return QdrantClient(url=self.qdrant_url)

    def query_transform(self, question: str, chat_id) -> str:
        memory = self.get_memory(chat_id)
        history = memory.load_memory_variables({}).get("chat_history", "")
        
        transform_prompt = PromptTemplate(
            input_variables=["question", "chat_history"],
            template="""Dưới đây là lịch sử hội thoại giữa người dùng và chatbot:
            {chat_history}

            Câu hỏi hiện tại của người dùng:
            {question}

            Nhiệm vụ của bạn:
            1. Viết lại câu hỏi sao cho rõ ràng, đầy đủ ngữ cảnh (dựa vào lịch sử hội thoại nếu cần), nhằm phục vụ tốt hơn cho việc truy vấn tri thức.
            2. Phân loại câu hỏi thành một trong ba loại sau:
            - 1: Câu hỏi thuộc lĩnh vực y tế (bệnh, thuốc, triệu chứng, khám chữa, dinh dưỡng...).
            - 2: Câu hỏi giao tiếp thông thường (chào hỏi, cảm ơn, hỏi về chatbot...).
            - 3: Câu hỏi thuộc lĩnh vực khác (công nghệ, tài chính, học tập...).

            Yêu cầu:
            - Chỉ trả về kết quả ở định dạng JSON như sau (không thêm bất kỳ văn bản nào khác):
            {{
                "rewritten_question": "<câu hỏi đã viết lại>",
                "category": "<1 | 2 | 3>"
            }}
            """
        )

        transform_chain = transform_prompt | self.llm_model()
        transformed_question = transform_chain.invoke({
            "question": question,
            "chat_history": history
        }).content.strip()
        return transformed_question


    def query_routing(self, re_questions) -> int:

        prompt = f"""
Bạn hãy phân loại câu hỏi sau thành 3 loại:
1 - Nếu câu hỏi thuộc lĩnh vực y tế.
2 - Nếu câu hỏi giao tiếp bình thường.
3 - Nếu câu hỏi Thuộc lĩnh vực khác.

Chỉ trả về số 1, 2 hoặc 3 tương ứng.

Câu hỏi như sau: 
"{re_questions}"
"""
        response = self.llm_model_var.invoke(prompt).content.strip()
        try:
            classification = int(response)
            if classification in [1, 2, 3]:
                return classification
            else:
                return 3
        except:
            return 3

    def search_documents(self, re_questions: str, lable):
        if lable == 1:
            embeddings = self.embedding_model_var.embed_documents(re_questions)
            client = self.qdrant_client()
            all_documents = []
            for embedding in embeddings:
                search_result = client.search(
                    collection_name="tamanh-hospital",
                    query_vector=embedding,
                    limit=10,
                    with_payload=True
                )

                if not search_result:
                    continue

                for hit in search_result:
                    payload = hit.payload or {}
                    content = payload.get("chunk")

                    if isinstance(content, str) and content.strip():
                        all_documents.append(Document(
                            page_content=content,
                            metadata={
                                "heading": payload.get("heading", ""),
                                "title": payload.get("title", ""),
                                "url": payload.get("url", "")
                            }
                        ))

            seen = set()
            unique_documents = []
            for doc in all_documents:
                if doc.page_content not in seen:
                    unique_documents.append(doc)
                    seen.add(doc.page_content)

            return unique_documents

        else:
            return []


    def reranking_documents(self, question, all_documents):
        rerank_model = self.rerank_model_var
        tokenized_pairs = [[question, document] for document in all_documents]
        scores = rerank_model.predict(tokenized_pairs)
        sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        sorted_documents = [all_documents[i] for i in sorted_indices]
        sorted_documents = sorted_documents[:10]

        return sorted_documents

    def answer_context(self, question, all_contexts):
        llm = self.llm_model_var
        combined_context = "\n".join(all_contexts)
        prompt = f"""
        Bạn là một trợ lý y tế thông minh. Dưới đây là các câu hỏi từ người dùng và ngữ cảnh được cung cấp từ cơ sở dữ liệu:

        Câu hỏi:
        {question}

        Ngữ cảnh:
        {combined_context}

        Dựa trên ngữ cảnh, hãy tổng hợp và đưa ra một câu trả lời chung, rõ ràng, ngắn gọn để trả lời tất cả các câu hỏi trên. Nếu ngữ cảnh không đủ nội dung thì có thể trả lời là do không đủ thông tin.
        """

        async def generate():
            async for chunk in llm.astream(prompt):  # Sử dụng `astream()` để đảm bảo async streaming
                yield chunk.content + "\n"  # Gửi từng phần phản hồi ngay lập tức

        return StreamingResponse(generate(), media_type="text/plain")




    def chat(self, question: str, chat_id):
        content = self.query_transform(question, chat_id)
        print("Transform Qestion:", content)

        if content.startswith("{") or content.startswith("```json"):
            # Xóa các dấu ```json ``` nếu có
            json_str = re.sub(r"^```json|```$", "", content.strip(), flags=re.MULTILINE).strip()
            try:
                data = json.loads(json_str)
                rewrite_question, category = data.get("rewritten_question", ""), data.get("category", None)
            except json.JSONDecodeError:
                pass    

        print("Rewritten Question:", rewrite_question)
        print("Category:", category)
        all_context = []

        if rewrite_question:
            all_documents = self.search_documents(rewrite_question, category)

            if all_documents:
                all_context = [doc.page_content for doc in all_documents]

            all_context = self.reranking_documents(question, all_context)
            # print(all_context)



        return self.answer_context(question, all_context)

    def save_menory(self, memory, question, answer):

        memory.chat_memory.add_user_message(question)
        memory.chat_memory.add_ai_message(answer)

rag = LangChainRAG()
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import PromptTemplate
from langchain.schema import Document
import re
from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse
from sentence_transformers import CrossEncoder

class LangChainRAG:
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.qdrant_url = os.getenv("QDRANT_URL")

        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY or API_KEY is not set")

        os.environ["GOOGLE_API_KEY"] = self.api_key

        self.memories = {}

    def get_memory(self, chat_id):
        if chat_id not in self.memories:
            self.memories[chat_id] = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True
            )
        return self.memories[chat_id]
    
    def llm_model(self):
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.2,
            convert_system_message_to_human=True,
        )

    def rerank_model(self):
        return CrossEncoder('itdainb/PhoRanker', max_length=256)
    

    def embedding_model(self):
        model_name = "dangvantuan/vietnamese-embedding"
        model_kwargs = {'device': 'cpu'}
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
            template="""Dưới đây là lịch sử hội thoại:
    {chat_history}

    Hãy viết lại câu hỏi sau để truy vấn tri thức tốt hơn: {question}"""
        )

        transform_chain = transform_prompt | self.llm_model()

        transformed_question = transform_chain.invoke({
            "question": question,
            "chat_history": history
        })

        return transformed_question


    def query_routing(self, re_questions) -> int:
        llm = self.llm_model()

        prompt = f"""
Bạn hãy phân loại câu hỏi sau thành 3 loại:
1 - Nếu câu hỏi thuộc lĩnh vực y.
2 - Nếu câu hỏi giao tiếp bình thường.
3 - Nếu câu hỏi Thuộc lĩnh vực khác.

Chỉ trả về số 1, 2 hoặc 3 tương ứng.

Câu hỏi như sau: 
"{re_questions}"
"""
        response = llm.invoke(prompt).content.strip()
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
            embedding_model = self.embedding_model()
            embeddings = embedding_model.embed_documents(re_questions)
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
        rerank_model = self.rerank_model()
        tokenized_pairs = [[question, document] for document in all_documents]
        scores = rerank_model.predict(tokenized_pairs)
        sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        sorted_documents = [all_documents[i] for i in sorted_indices]
        sorted_documents = sorted_documents[:10]

        return sorted_documents

    def answer_context(self, question, all_contexts):
        llm = self.llm_model()
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
        raw_transform = self.query_transform(question, chat_id)
        re_questions = re.findall(r'"(.*?)"', raw_transform.content)
        all_context = []

        re_questions = re_questions[:3]
        if re_questions:
            label = self.query_routing(re_questions[0])

            all_documents = self.search_documents(re_questions, label)

            if all_documents:
                all_context = [doc.page_content for doc in all_documents]

            all_context = self.reranking_documents(question, all_context)
            print(all_context)



        return self.answer_context(question, all_context)

    def save_menory(self, chat_id, question, answer):
        memory = self.get_memory(chat_id)

        memory.chat_memory.add_user_message(question)
        memory.chat_memory.add_ai_message(answer)
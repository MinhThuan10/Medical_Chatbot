# import google.generativeai as genai
# import os
# from sentence_transformers import SentenceTransformer
# from sklearn.metrics.pairwise import cosine_similarity
# from pyvi.ViTokenizer import tokenize
# from qdrant_client import QdrantClient
# import json
# import torch


# device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
# print(f"[Startup] Using device: {device}")

# API_KEY = os.getenv("API_KEY")
# QDRANT_URL = os.getenv("QDRANT_URL")
# genai.configure(api_key=API_KEY)

# model_llm = genai.GenerativeModel("gemini-2.0-flash")
# model_embedding = SentenceTransformer('dangvantuan/vietnamese-embedding', trust_remote_code=True, device=device)

# client = QdrantClient(
#     url=QDRANT_URL 
# )

# class ChatDataModel:

    


#     def model_gemini_chat(self, question_text, context):
#         prompt = f"""
#         Bạn là trợ lý AI về lĩnh vực Y tế, có nhiệm vụ trả lời các câu hỏi liên quan đến sức khỏe và y tế.
#         Dựa vào ngữ cảnh được cung cấp, bạn hãy trả lời các câu hỏi một cách dễ hiểu. nếu ngữ cảnh không đủ để trả lời câu hỏi, hãy trả lời rằng "Xin lỗi, tôi không có đủ thông tin để trả lời câu hỏi này"

#         Câu hỏi của người dùng: "{question_text}"
#         Ngữ cảnh bổ sung: "{context}"
#         """

#         response = model_llm.generate_content(prompt)
#         return response.text.strip()
    
#     def model_gemini_query(self, history, question_text):
#         prompt = f"""
#         Bạn là trợ lý AI. Dựa vào lịch sử hội thoại và câu hỏi hiện tại, hãy thực hiện 2 nhiệm vụ:

#         1. Nếu câu hỏi hiện tại mang được ý nghĩa đầy đủ của một câu hỏi thì không cần phải viết lại câu hỏi mới, nếu nó phụ thuộc vào lịch sử phía trước thì bạn viết lại dựa vào lịch sử cung cấp.
#         2. Phân loại câu hỏi đó vào một trong các nhóm sau:
#         - hello (câu hỏi chào hỏi, giới thiệu, v.v.)
#         - goodbye (câu hỏi tạm biệt, kết thúc hội thoại, v.v.)
#         - medical (câu hỏi về y tế, sức khỏe, bệnh tật, điều trị, v.v.)
#         - realtime (câu hỏi về y tế liên quan đến thời gian thực)
#         - other (câu hỏi không thuộc 2 nhóm trên)

#         Trả lời kết quả theo định dạng JSON như sau:
#         {{
#             "rewritten_question": "<câu hỏi đã viết lại>",
#             "category": "<hello | goodbye | medical | realtime | other>"
#         }}

#         Lịch sử hội thoại: "{history}"
#         Câu hỏi hiện tại: "{question_text}"
#         """

#         response = model_llm.generate_content(prompt)
#         return response.text.strip()
    
#     def model_embedding(self, sentences):
#         tokenizer_sent = tokenize(sentences)
#         embedding = model_embedding.encode(tokenizer_sent)
#         return embedding
    
#     def model_rag(self, embedding):
#         search_result = client.search(
#             collection_name="tamanh-hospital",
#             query_vector=embedding,
#             limit=20,
#             with_payload=True
#         )

#         if not search_result:
#             return "Không tìm thấy thông tin liên quan."


#         return search_result
    
#     def model_qa(self, history, question_text):
#         json_string = self.model_gemini_query(history, question_text)
#         cleaned_string = json_string.strip("`").strip("json\n").strip()
#         query_transfor = json.loads(cleaned_string)
#         query_transformed = query_transfor['rewritten_question']
#         # print(f"Transformed Query: {query_transformed}")
#         category = query_transfor['category']
#         if category == "hello":
#             return "Xin chào! Tôi là trợ lý AI của bạn. Có thể giúp gì cho bạn hôm nay?"
#         elif category == "goodbye":
#             return "Cảm ơn bạn đã trò chuyện! Hẹn gặp lại lần sau!"
#         elif category == "realtime":
#             return "Câu hỏi về thời gian thực không được hỗ trợ trong mô hình này."
#         elif category == "other":
#             return "xin mời bạn đặt câu hỏi khác hoặc cung cấp thêm thông tin để tôi có thể giúp đỡ tốt hơn."
#         else:
#             embedding = self.model_embedding(query_transformed)
#             search_result = self.model_rag(embedding)
#             context = "\n".join([item.payload['chunk'] for item in search_result])
#             # print(f"Context: {context}")
#             response = self.model_gemini_chat(query_transformed, context)
#             return response
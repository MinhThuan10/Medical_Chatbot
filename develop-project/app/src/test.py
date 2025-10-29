from sentence_transformers import CrossEncoder

MODEL_ID = 'itdainb/PhoRanker'
MAX_LENGTH = 256

model = CrossEncoder(MODEL_ID, max_length=MAX_LENGTH)
model.model.half()  # Optional: nếu bạn dùng GPU hỗ trợ fp16

query = "Trường UIT là gì?"
sentences = [
    "Trường Đại học Công nghệ Thông tin có tên tiếng Anh là University of Information Technology (viết tắt là UIT) là thành viên của Đại học Quốc Gia TP.HCM.",
    "Trường Đại học Kinh tế – Luật (tiếng Anh: University of Economics and Law – UEL) là trường đại học đào tạo và nghiên cứu khối ngành kinh tế, kinh doanh và luật hàng đầu Việt Nam.",
    "Quĩ uỷ thác đầu tư (tiếng Anh: Unit Investment Trusts; viết tắt: UIT) là một công ty đầu tư mua hoặc nắm giữ một danh mục đầu tư cố định"
]

# Tạo cặp [query, sentence]
tokenized_pairs = [[query, sentence] for sentence in sentences]

# Dự đoán độ liên quan
scores = model.predict(tokenized_pairs)

print(scores)

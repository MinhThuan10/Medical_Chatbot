# def test_convervation(client):

#     response = client.post("/chat_data/66", json={"question_text": "Xóa cuộc trò chuyện"})
#     assert response.status_code == 200
#     assert response.headers["content-type"].startswith("text/plain")
#     content = response.text.strip()
#     print("Response content:", content)
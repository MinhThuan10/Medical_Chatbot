# def test_convervation(client):
#     client.cookies.set("user_id", "3e242e58-939f-4553-bb4e-66c007b996ce")
#     response = client.post("/chat_data/66", json={"question_text": "Xóa cuộc trò chuyện"})
#     assert response.status_code == 200
#     assert response.headers["content-type"].startswith("text/plain")
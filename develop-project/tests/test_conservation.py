
def test_get_all_conservations(client):

    # Gọi /conservation với cookie hợp lệ
    response = client.get("/conservation")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "list_conservations" in data
    assert isinstance(data["list_conservations"], list)


def test_create_conservation(client):
    response = client.post("/conservation/new", json={"question_text": "Xin chào, tạo cuộc trò chuyện mới"})
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["message"] == "Conversation created"

def test_update_conservation(client):
    create_response = client.post("/conservation/new", json={"question_text": "Cập nhật cuộc trò chuyện"})
    conversation_id = create_response.json().get("conversation_id")

    update_response = client.put(f"/conservation/update/{conversation_id}", json={"name": "Cuộc trò chuyện đã cập nhật"})
    assert update_response.status_code == 200
    data = update_response.json()
    assert "message" in data
    assert data["message"] == "Conversation updated successfully"

def test_delete_conservation(client):
    create_response = client.post("/conservation/new", json={"question_text": "Xóa cuộc trò chuyện"})
    conversation_id = create_response.json().get("conversation_id")

    delete_response = client.delete(f"/conservation/delete/{conversation_id}")
    assert delete_response.status_code == 200
    data = delete_response.json()
    assert "message" in data
    assert data["message"] == "Conversation deleted successfully"

def test_convervation(client):
    create_response = client.post("/conservation/new", json={"question_text": "Xóa cuộc trò chuyện"})
    conversation_id = create_response.json().get("conversation_id")


    response = client.get(f"/conservation/{conversation_id}")
    assert response.status_code == 200
    data = response.json()
    assert "conservation" in data
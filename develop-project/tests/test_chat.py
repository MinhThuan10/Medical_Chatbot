def test_convervation(client):
    client.cookies.set("user_id", "3e242e58-939f-4553-bb4e-66c007b996ce")
    response = client.get(f"/chat/66")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

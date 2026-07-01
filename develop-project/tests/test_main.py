
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

# def test_read_main(client):
#     response = client.get("/")
#     assert response.status_code == 200
#     assert "text/html" in response.headers["content-type"]



from flask.testing import FlaskClient


def test_health_returns_ok(client: FlaskClient) -> None:
    response = client.get("/health", headers={"Host": "unregistered.example"})

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "service": "yapibina",
    }

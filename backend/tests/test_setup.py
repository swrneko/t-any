from httpx import AsyncClient


async def test_fresh_install_needs_setup(client: AsyncClient) -> None:
    response = await client.get("/api/setup/status")

    assert response.status_code == 200
    assert response.json() == {"needs_setup": True, "auth_mode": "builtin", "has_diarizer": False}


async def test_setup_creates_admin_and_finishes_setup(client: AsyncClient) -> None:
    response = await client.post(
        "/api/setup",
        json={"username": "admin", "password": "correct horse battery staple"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "admin"
    assert body["is_admin"] is True
    assert "password" not in body and "password_hash" not in body

    status = await client.get("/api/setup/status")
    assert status.json() == {"needs_setup": False, "auth_mode": "builtin", "has_diarizer": False}


async def test_setup_is_rejected_once_an_admin_exists(client: AsyncClient) -> None:
    await client.post(
        "/api/setup",
        json={"username": "admin", "password": "correct horse battery staple"},
    )

    second = await client.post(
        "/api/setup",
        json={"username": "intruder", "password": "hunter2hunter2"},
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "setup_already_completed"

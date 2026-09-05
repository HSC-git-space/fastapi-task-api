import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from main import app, get_db
from database import Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

async def override_get_db():
    async with TestSessionLocal() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_create_user():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/users", json={"username": "alice", "password": "secret123"})
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "alice"
        assert "id" in data


async def test_duplicate_username_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response1 = await client.post("/users", json={"username": "bob", "password": "pass123"})
        assert response1.status_code == 201

        response2 = await client.post("/users", json={"username": "bob", "password": "differentpass"})
        assert response2.status_code != 201

async def test_login_success():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/users", json={"username": "carol", "password": "mypassword"})

        response = await client.post("/login", json={"username": "carol", "password": "mypassword"})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

async def test_login_wrong_password():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/users", json={"username": "dave", "password": "correctpass"})

        response = await client.post("/login", json={"username": "dave", "password": "wrongpass"})
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Incorrect username or password"

async def test_user_cannot_access_others_task():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/users", json={"username": "eve", "password": "pass1"})
        await client.post("/users", json={"username": "frank", "password": "pass2"})

        eve_login = await client.post("/login", json={"username": "eve", "password": "pass1"})
        frank_login = await client.post("/login", json={"username": "frank", "password": "pass2"})
        eve_token = eve_login.json()["access_token"]
        frank_token = frank_login.json()["access_token"]

        eve_headers = {"Authorization": f"Bearer {eve_token}"}
        create_response = await client.post("/tasks", json={"title": "Eve's private task"}, headers=eve_headers)
        task_id = create_response.json()["id"]

        frank_headers = {"Authorization": f"Bearer {frank_token}"}
        frank_attempt = await client.get(f"/tasks/{task_id}", headers=frank_headers)
        assert frank_attempt.status_code == 403

        eve_attempt = await client.get(f"/tasks/{task_id}", headers=eve_headers)
        assert eve_attempt.status_code == 200

async def test_refresh_returns_new_access_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/users", json={"username": "grace", "password": "pass123"})
        login_response = await client.post("/login", json={"username": "grace", "password": "pass123"})
        refresh_token = login_response.json()["refresh_token"]

        refresh_response = await client.post("/refresh", json={"refresh_token": refresh_token})
        assert refresh_response.status_code == 200
        assert "access_token" in refresh_response.json()

async def test_blacklisted_refresh_token_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/users", json={"username": "heidi", "password": "pass123"})
        login_response = await client.post("/login", json={"username": "heidi", "password": "pass123"})
        refresh_token = login_response.json()["refresh_token"]

        logout_response = await client.post("/logout", json={"refresh_token": refresh_token})
        assert logout_response.status_code == 200

        refresh_response = await client.post("/refresh", json={"refresh_token": refresh_token})
        assert refresh_response.status_code == 401
        assert refresh_response.json()["error"]["message"] == "Refresh token has been revoked"

async def test_access_token_rejected_at_refresh_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/users", json={"username": "ivan", "password": "pass123"})
        login_response = await client.post("/login", json={"username": "ivan", "password": "pass123"})
        access_token = login_response.json()["access_token"]

        refresh_response = await client.post("/refresh", json={"refresh_token": access_token})
        assert refresh_response.status_code == 401
        assert refresh_response.json()["error"]["message"] == "Not a refresh token"

async def test_update_task_with_correct_version_succeeds():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/users", json={"username": "judy", "password": "pass123"})
        login_response = await client.post("/login", json={"username": "judy", "password": "pass123"})
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        create_response = await client.post("/tasks", json={"title": "Original title"}, headers=headers)
        task = create_response.json()
        assert task["version"] == 0

        update_response = await client.patch(
            f"/tasks/{task['id']}",
            json={"title": "Updated title", "version": 0},
            headers=headers,
        )
        assert update_response.status_code == 200
        updated_task = update_response.json()
        assert updated_task["title"] == "Updated title"
        assert updated_task["version"] == 1

async def test_update_task_with_stale_version_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/users", json={"username": "karl", "password": "pass123"})
        login_response = await client.post("/login", json={"username": "karl", "password": "pass123"})
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        create_response = await client.post("/tasks", json={"title": "Original title"}, headers=headers)
        task = create_response.json()

        first_update = await client.patch(
            f"/tasks/{task['id']}",
            json={"title": "First update", "version": 0},
            headers=headers,
        )
        assert first_update.status_code == 200

        stale_update = await client.patch(
            f"/tasks/{task['id']}",
            json={"title": "Stale update", "version": 0},
            headers=headers,
        )
        assert stale_update.status_code == 409
        assert stale_update.json()["error"]["message"] == "Task has been modified since you last loaded it"
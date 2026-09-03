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
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "alice"
        assert "id" in data


async def test_duplicate_username_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # create the first user
        response1 = await client.post("/users", json={"username": "bob", "password": "pass123"})
        assert response1.status_code == 200

        # try to create a second user with the same username
        response2 = await client.post("/users", json={"username": "bob", "password": "differentpass"})
        assert response2.status_code != 200

async def test_login_success():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # create a user first
        await client.post("/users", json={"username": "carol", "password": "mypassword"})

        # now log in with the correct credentials
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
        assert response.json()["detail"] == "Incorrect username or password"

async def test_user_cannot_access_others_task():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # create two users
        await client.post("/users", json={"username": "eve", "password": "pass1"})
        await client.post("/users", json={"username": "frank", "password": "pass2"})

        # log in as both, get their tokens
        eve_login = await client.post("/login", json={"username": "eve", "password": "pass1"})
        frank_login = await client.post("/login", json={"username": "frank", "password": "pass2"})
        eve_token = eve_login.json()["access_token"]
        frank_token = frank_login.json()["access_token"]

        # eve creates a task
        eve_headers = {"Authorization": f"Bearer {eve_token}"}
        create_response = await client.post("/tasks", json={"title": "Eve's private task"}, headers=eve_headers)
        task_id = create_response.json()["id"]

        # frank tries to access eve's task using his own token
        frank_headers = {"Authorization": f"Bearer {frank_token}"}
        frank_attempt = await client.get(f"/tasks/{task_id}", headers=frank_headers)
        assert frank_attempt.status_code == 403

        # eve can still access her own task
        eve_attempt = await client.get(f"/tasks/{task_id}", headers=eve_headers)
        assert eve_attempt.status_code == 200
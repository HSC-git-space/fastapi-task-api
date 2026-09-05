# fastapi-task-api

A task management API built with FastAPI, SQLAlchemy, and SQLite, used as a structured, hands-on path into real backend engineering. Started as basic CRUD and grew, one deliberately confronted gap at a time, into a project with real authentication, real concurrency control, and a real found-and-fixed security vulnerability.

Every feature here exists because a specific gap was identified first, not because it looked good on a checklist.

## Background

This project started as a simple in-memory CRUD API and was rebuilt in layers, each layer chosen to close a specific, named gap in backend fundamentals rather than to add surface-level features. The build order was: in-memory CRUD, then real persistence via SQLAlchemy, then Alembic migrations, then JWT authentication, then a full async conversion, then SQL depth (indexing, window functions, transactions), then refresh tokens and logout invalidation, then secrets management, then Docker, then a REST API design pass with optimistic concurrency control wired in.

Several of the most valuable pieces of this project were not planned features, they were bugs found while building something else, then fixed and turned into permanent regression tests. That pattern shows up repeatedly below.

## What Is Built

- Full CRUD for tasks, scoped per user, with ownership enforced server-side on every route
- JWT authentication with bcrypt password hashing
- A real authorization vulnerability found and fixed: users could originally access and modify other users' tasks by guessing task IDs. Fixed by deriving user identity server-side from the token, never trusting a client-supplied user ID, and returning 403 on any cross-user access attempt
- Refresh tokens and logout invalidation: short-lived access tokens paired with longer-lived refresh tokens carrying a unique token ID (jti) and an explicit type claim, plus a blacklist table so logout can actually revoke a still-valid, unexpired token
- Optimistic concurrency control on task updates: a version column that must be sent back on every PATCH, rejecting stale writes with 409 instead of silently overwriting another update
- SQL depth: an index diagnosed and added via EXPLAIN QUERY PLAN, two window functions verified against thousands of rows of messy test data, and transaction isolation work that reproduced a real lost-update race condition before fixing it
- Full async database layer using SQLAlchemy's async engine and aiosqlite
- A pytest suite covering authentication, authorization, refresh token lifecycle, and concurrency control, several of which were written specifically because manual testing surfaced a real bug first
- Secrets management via environment variables, with the app refusing to start if a secret key is missing rather than silently proceeding
- Docker support, verified by actually running the containerized app against a real login and refresh flow, not just confirming the image builds
- Consistent, structured error responses and correct REST status codes (201 on create, 204 on delete) across every route

## Tech Stack

| Tool | Purpose |
|------|---------|
| Python | Core language |
| FastAPI | Web framework |
| SQLAlchemy (async) | ORM and database layer |
| aiosqlite | Async SQLite driver |
| Alembic | Database migrations |
| Pydantic | Request and response validation |
| PyJWT | Token creation and verification |
| bcrypt | Password hashing |
| pytest, httpx, pytest-asyncio | Test suite |
| python-dotenv | Environment variable configuration |
| Docker | Containerized runtime |

## Project Structure

task-api/
|
|-- main.py # Routes, request/response models, exception handlers
|-- auth.py # Password hashing, token creation and verification, blacklist checks
|-- models.py # SQLAlchemy models: User, Task, BlacklistedToken
|-- database.py # Async engine and session setup
|-- alembic/
| -- versions/ # One migration per real schema change, in the order they were made |-- tests/ | -- test_main.py # Full pytest suite, async, in-memory test database
|-- Dockerfile
|-- .dockerignore
|-- requirements.txt
|-- pytest.ini
`-- .env # Real secrets, never committed


## Authentication and Token Flow

Login is the only place credentials are ever sent. It returns two tokens with very different jobs.

POST /login (credentials verified once)
|
|--> Access token (short-lived, ~30 min)
| sent on every API request
| exposed often, so it is deliberately short-lived
|
`--> Refresh token (long-lived, ~7 days)
sent only to /refresh
exposed rarely, carries a unique jti and a type claim

/refresh flow:
client sends refresh token
|
v
decode: check signature and expiry
|
v
check type claim equals "refresh"
(rejects an access token sent here by mistake)
|
v
check jti against the blacklist
(rejects a token that was already logged out)
|
v
issue a new access token


Logout decodes the refresh token and inserts its jti into the blacklist. This is the actual revocation mechanism, a JWT cannot be edited or deleted once issued, so revocation has to be tracked separately, outside the token itself.

## Optimistic Concurrency Control

Two users editing the same task at the same time creates a real risk: the second save can silently overwrite the first one's changes, with no error and no warning. This is called a lost update, and it was reproduced live in this project using two real concurrent sqlite3 connections before being fixed, not just read about.

The fix does not lock anything. Every task carries a `version` number. A client must send back the version it last read when updating. If someone else already updated the task in between, the version will not match, and the update is rejected with a 409 instead of overwriting.

Client A reads task, version = 0
Client B reads task, version = 0

Client A updates, sends version 0 -> succeeds, task is now version 1
Client B updates, sends version 0 -> rejected with 409
(someone already changed this)


## Bugs Found and Fixed Along the Way

These were not planned test cases, they were real issues found while building or testing something else, then fixed and turned into permanent regression tests.

**Cross-user task access.** Early versions of the ownership check were missing entirely, any authenticated user could view or modify any task by ID. Fixed with server-side ownership checks on every task route, now covered by a dedicated test.

**Unhandled crash on duplicate usernames.** `create_user` had no error handling around the database commit, so creating a user with a taken username caused an unhandled 500 instead of a clean error. Found while writing the pytest suite, fixed with a try/except around the integrity error, now returns a proper 400.

**Lost update race condition.** Reproduced live with two concurrent database connections before any fix existed. Fixed with the optimistic concurrency control described above.

**Silent auth bypass risk on /refresh.** Nothing initially stopped a client from sending a valid access token to the refresh endpoint instead of a real refresh token, since both are structurally valid JWTs. Fixed by stamping a `type` claim onto refresh tokens at creation and checking it explicitly on every refresh attempt.

## Setup

### Prerequisites

- Python 3.12
- pip

### Local setup

git clone https://github.com/HSC-git-space/fastapi-task-api
cd fastapi-task-api
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt


Create a `.env` file in the project root:

SECRET_KEY=your-own-random-secret-here


Generate a real one instead of typing something by hand:

python -c "import secrets; print(secrets.token_hex(32))"


Run the app:

uvicorn main:app --reload


### Running tests

pytest tests/test_main.py -v


### Docker

docker build -t task-api .
docker run --env-file .env -p 8000:8000 task-api


The `.env` file is intentionally never copied into the image. Real deployment platforms inject environment variables directly rather than shipping a secrets file inside a container, and this setup follows that same pattern locally.

## Known Limitations

- SQLite is used throughout, chosen deliberately for a learning-focused project, a production deployment of this scale would more likely use PostgreSQL
- No rate limiting, CORS configuration, or request throttling yet, deliberately deferred to a larger project with real production traffic constraints
- No caching layer or background job queue, same reasoning, these earn their place once there is a real workload that needs them
- Refresh token blacklist entries are never cleaned up or expired from the table, in a long-running production system these would need a periodic cleanup job
- Cloud deployment is not yet done, this repo currently runs locally and in Docker, real hosted deployment is the next step

## What Comes Next

- Deploy to a real hosting platform (Render or Railway), the current gap between "runs in Docker locally" and "actually deployed somewhere real"
- CI pipeline via GitHub Actions, running the full pytest suite automatically on every push
- After this repo: a larger project applying these same fundamentals under real production constraints, real concurrency, caching, and observability, rather than a second learning-scale CRUD API
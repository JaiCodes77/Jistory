# Jistory

Local-first memory for your AI chats. Import ChatGPT, Claude, or Cursor history, search it, see how conversations connect, and ask questions answered only from that history.

If your archive does not contain the answer, Jistory says so. It is not a general chatbot.

## Run it

Python **3.11–3.13** (3.12 is pinned in `backend/.python-version`). Two terminals:

```bash
# terminal 1 — API
cd backend
uv sync --group dev
cp .env.example .env          # set GEMINI_API_KEY if you want Ask
uv run uvicorn app.main:app --reload --port 8000
```

```bash
# terminal 2 — app
cd frontend
pnpm install
echo 'NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api' > .env.local
pnpm dev --hostname 127.0.0.1
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). API health: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health).

Use the same hostname for the app and API (`localhost` or `127.0.0.1`). Mixing them can look like a blank Graph page.

## What you can do

| | |
| --- | --- |
| **Import** | ChatGPT / Claude export ZIP or share link. Cursor from a local `state.vscdb` (never scans `$HOME` unless you pick a path). |
| **Browse & search** | Full threads plus `/` or `⌘K` keyword + semantic search. |
| **Graph** | Conversations as a map. Links are shared title topics or similar content, with a reason you can read. |
| **Ask** | Gemini answers from retrieved excerpts only. Type `@` to pin a chat. |

Parse stores conversations immediately. Embeddings index in the background; keyword search works as soon as parse finishes.

## Privacy

| Stays on this machine | Leaves only if you use Ask |
| --- | --- |
| Exports, conversations, search index, embeddings, API key file | Retrieved excerpts + recent Ask turns to Gemini |

Nothing is logged as conversation content. ZIP path traversal is rejected. The API never returns your Gemini key.

## Config

Copy `backend/.env.example` to `backend/.env`. Do not commit `.env`.

```text
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

You can also save the Gemini key in Settings (`backend/data/settings.json`). Environment variables win.

`EMBEDDING_PROVIDER=hash` is tests-only.

## Stack

Next.js + Tailwind + shadcn · FastAPI + SQLite/FTS5 · local FastEmbed (`bge-small-en-v1.5`) · Gemini Flash on Ask only.

## Develop

```bash
cd backend && uv run pytest && uv run ruff check app tests
cd frontend && pnpm lint && pnpm exec tsc --noEmit
```

Schema is created at startup (`create_all` plus additive indexes). `uv run alembic upgrade head` is optional and never drops `jistory.db`.

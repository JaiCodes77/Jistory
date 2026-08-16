# Jistory

Local-first AI conversation memory. Import ChatGPT exports, browse and search what you discussed, then ask questions that are answered only from your history.

## What is Jistory?

Jistory stores your AI conversations on your machine and turns them into searchable memory.

Typical questions:

- What conclusion did I reach about Grafana?
- What did I discuss about Redis over the last two months?
- Which conversation contained the FastAPI authentication solution?

Jistory is not a general-purpose chatbot. If your history does not contain the answer, it says so.

## Architecture

```text
ChatGPT ZIP
    → validate / extract (local)
    → parse into conversations + messages (SQLite)
    → FTS5 keyword index + local embeddings
    → hybrid retrieval
    → Gemini Flash (only retrieved excerpts, only on Ask)
```

Frontend and backend stay separate. Provider integrations are abstracted (`ConversationParser`, `EmbeddingProvider`, `LLMProvider`) so Claude, Gemini, or Cursor imports can be added later without rewriting retrieval.

## Tech stack

| Layer | Tech |
| --- | --- |
| Frontend | Next.js App Router, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | FastAPI, Python 3.11+, SQLAlchemy, Alembic |
| Database | SQLite (FTS5 for search, blobs for embeddings) |
| Embeddings | Local ONNX model via FastEmbed (`BAAI/bge-small-en-v1.5`) |
| Answers | Gemini Flash (configurable model name) |
| Package managers | pnpm (frontend), uv (backend) |

## Local setup

Use **Python 3.11–3.13**. Python 3.14 is not supported yet (SQLAlchemy). The backend pins 3.12 via `backend/.python-version`.

### Backend

```bash
cd backend
uv sync --group dev
cp .env.example .env
# edit .env and set GEMINI_API_KEY if you want Ask Jistory
uv run uvicorn app.main:app --reload --port 8000
```

Health check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

App: [http://localhost:3000](http://localhost:3000)

## Environment variables

Copy `backend/.env.example` to `backend/.env`. Never commit `.env`.

```text
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
DATABASE_URL=sqlite:///./data/jistory.db
MAX_IMPORT_SIZE_MB=500
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RETRIEVAL_LIMIT=8
CORS_ORIGINS=http://localhost:3000
```

`EMBEDDING_PROVIDER=hash` is tests-only. If FastEmbed is missing, indexing fails with a visible error instead of silently using hash embeddings. Keyword search still works after parse.

Frontend:

```text
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

The Gemini API key can also be saved from Settings. That writes a local `settings.json` next to the database. Environment variables take precedence. The API never returns the key.

## Importing ChatGPT history

1. In ChatGPT: **Settings → Data controls → Export data**.
2. Download the ZIP.
3. Open Jistory at [http://localhost:3000](http://localhost:3000).
4. Go to **Import**.
5. Upload the ZIP.
6. Click **Parse Conversations**.

Parse stores conversations immediately, then indexes embeddings in a background thread. Import shows **Indexing embeddings** (including the first FastEmbed model download) until status is **Ready**. Keyword search works as soon as parse finishes.

Exports are extracted under `backend/data/imports/<timestamp>/`. Parsing is idempotent: the same conversation is not duplicated if you import or parse the same export again. Existing SQLite databases get an additive unique index on `(source, external_id)` at startup; Jistory never deletes `backend/data/jistory.db` to apply schema changes.

## Asking Jistory questions

1. Import and parse at least one export.
2. Open **Ask Jistory**.
3. Ask a question about your history.

Retrieval uses SQLite FTS5 plus local embeddings, then merges results. Only those retrieved chunks (and recent Ask turns) are sent to Gemini. The backend owns source citations; clicking a source opens the conversation at the matching message.

Follow-up questions keep a bounded Ask session so “Why did I choose it?” can refer to the previous topic.

## Privacy

| Stays on this machine | Leaves the machine |
| --- | --- |
| ZIP exports, conversations, messages | Nothing, unless you use Ask Jistory |
| Full-text index and embeddings | Retrieved excerpts + recent Ask turns, sent to Gemini for an answer |
| Settings file and API key | The API key is sent only to Google as Gemini authentication |

Conversation content is not written to application logs. Imported files are not served as public static URLs. Path traversal inside ZIP archives is rejected.

## Keyboard shortcuts

- `/` focuses global search when you are not typing in an input
- `⌘K` / `Ctrl+K` opens global search
- Enter in the palette opens the Search page at `/search`

## Schema

Startup uses SQLAlchemy `create_all` plus additive `ensure_runtime_schema` (new columns and the conversation unique index). That is the source of truth for the local SQLite file.

```bash
uv run alembic upgrade head   # optional; same additive helpers, never drops the DB
```

## Development commands

```bash
# backend
cd backend
uv sync --group dev
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run ruff check app tests
uv run alembic upgrade head   # optional; startup also creates tables and additive indexes

# frontend
cd frontend
pnpm install
pnpm dev
pnpm lint
pnpm exec tsc --noEmit
```

## Project structure

```text
jistory/
├── backend/
│   ├── alembic/
│   ├── app/
│   │   ├── ask/              # RAG + Ask API
│   │   ├── conversations/    # browser API
│   │   ├── embeddings/       # local / gemini / hash providers
│   │   ├── imports/          # ZIP ingest + parsers
│   │   ├── llm/              # LLMProvider (Gemini)
│   │   ├── retrieval/        # FTS + semantic hybrid
│   │   └── user_settings/
│   └── tests/
└── frontend/
    ├── app/
    └── components/
```

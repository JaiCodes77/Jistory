# Jistory

Local-first AI conversation memory system.

## Stack

| Layer | Tech |
| --- | --- |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui |
| Backend | FastAPI, Python |
| Database | SQLite + SQLAlchemy |
| Package managers | pnpm (frontend), uv (backend) |

## Project structure

```text
jistory/
├── backend/
│   └── app/
│       ├── api/
│       ├── core/
│       ├── db/
│       ├── models/
│       ├── schemas/
│       ├── services/
│       └── utils/
└── frontend/
    ├── app/
    ├── components/
    ├── lib/
    ├── hooks/
    └── types/
```

## Getting started

### Backend

```bash
cd backend
uv sync
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

## Import & parse (ChatGPT)

1. Open [http://localhost:3000/import](http://localhost:3000/import)
2. Upload a ChatGPT export ZIP
3. Click **Parse Conversations**

```bash
# Upload
curl -X POST http://localhost:8000/api/import/chatgpt \
  -F "file=@chatgpt-export.zip"

# Parse (idempotent)
curl -X POST http://localhost:8000/api/import/<importId>/parse
```

Exports are extracted to `backend/data/imports/<timestamp>/`. Parsing normalizes conversations and messages into SQLite.

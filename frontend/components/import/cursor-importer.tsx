"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { FolderOpen, LoaderCircle } from "lucide-react"

import { ImportError, type IndexBannerState } from "@/components/import/import-status"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  getImportJob,
  getSettings,
  importCursorFile,
  importCursorFromPath,
} from "@/lib/api"
import type { ImportStatusResponse, ParseJobSuccess } from "@/types/import"

const INDEX_POLL_MS = 900

type CursorImporterProps = {
  onStatusChange?: (state: IndexBannerState | null) => void
}

export function CursorImporter({ onStatusChange }: CursorImporterProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [path, setPath] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [state, setState] = useState<"idle" | "importing" | "success" | "error">("idle")
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ParseJobSuccess | null>(null)
  const [indexStatus, setIndexStatus] = useState<ImportStatusResponse | null>(null)
  const [savedPath, setSavedPath] = useState("")

  useEffect(() => {
    void getSettings()
      .then((settings) => {
        setSavedPath(settings.cursor_import_path || "")
        setPath((current) => current || settings.cursor_import_path || "")
      })
      .catch(() => undefined)
  }, [])

  const currentStatus = indexStatus?.status || result?.status
  const indexing =
    state === "success" &&
    (currentStatus === "indexing" || currentStatus === "processing")
  const ready = currentStatus === "ready" || currentStatus === "completed"
  const keywordReady = ready || currentStatus === "parsed"
  const busy = state === "importing" || indexing

  useEffect(() => {
    if (state !== "success") {
      onStatusChange?.(null)
      return
    }
    onStatusChange?.({
      indexing,
      ready,
      keywordReady,
      indexError: indexStatus?.index_error ?? null,
      embeddingStatus: indexStatus?.embedding_status ?? null,
      embeddingDetail: indexStatus?.embedding_status_detail ?? null,
    })
  }, [state, indexing, ready, keywordReady, indexStatus, onStatusChange])

  const reset = () => {
    setFile(null)
    setState("idle")
    setError(null)
    setResult(null)
    setIndexStatus(null)
    onStatusChange?.(null)
    if (fileRef.current) fileRef.current.value = ""
  }

  const pollIndex = async (importId: string) => {
    for (let attempt = 0; attempt < 600; attempt += 1) {
      const status = await getImportJob(importId)
      setIndexStatus(status)
      if (
        status.status === "ready" ||
        status.status === "completed" ||
        status.status === "parsed" ||
        status.status === "failed"
      ) {
        return
      }
      await new Promise((resolve) => window.setTimeout(resolve, INDEX_POLL_MS))
    }
  }

  const finishImport = async (response: ParseJobSuccess) => {
    setResult(response)
    setState("success")
    if (response.importId) {
      await pollIndex(response.importId)
    }
  }

  const startPathImport = async () => {
    if (busy) return
    setState("importing")
    setError(null)
    setResult(null)
    setIndexStatus(null)
    try {
      const response = await importCursorFromPath(path)
      await finishImport(response)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not import Cursor data from that path."
      )
      setState("error")
    }
  }

  const startFileImport = async () => {
    if (!file || busy) return
    setState("importing")
    setError(null)
    setResult(null)
    setIndexStatus(null)
    try {
      const response = await importCursorFile(file)
      await finishImport(response)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not import that Cursor file."
      )
      setState("error")
    }
  }

  const canImportPath = Boolean(path.trim() || savedPath)

  return (
    <Card className="border-border bg-card shadow-none">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Cursor</CardTitle>
        <CardDescription>
          Local files only. Paste an absolute path to <span className="font-mono">state.vscdb</span>{" "}
          or a transcript folder, or choose the file. Jistory never scans your home
          directory.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-1.5">
          <Label htmlFor="cursor-path">Path on this machine</Label>
          <Input
            id="cursor-path"
            value={path}
            onChange={(event) => setPath(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void startPathImport()
            }}
            placeholder="/absolute/path/to/state.vscdb"
            disabled={busy}
            autoComplete="off"
            spellCheck={false}
          />
          {savedPath ? (
            <p className="text-[11px] text-muted-foreground">
              Settings default: <span className="font-mono">{savedPath}</span>
            </p>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              You can save a default path in Settings. Public Cursor share URLs are not
              imported.
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            disabled={!canImportPath || busy}
            onClick={() => void startPathImport()}
          >
            {state === "importing" && !file ? "Importing…" : "Import from path"}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
          >
            <FolderOpen className="size-3.5" />
            Choose file
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".vscdb,.json,.jsonl,.sqlite,.db,application/octet-stream"
            className="hidden"
            onChange={(event) => {
              const next = event.target.files?.[0] ?? null
              setFile(next)
              setError(null)
              setState("idle")
              setResult(null)
            }}
          />
          {file && (
            <Button
              type="button"
              variant="secondary"
              disabled={busy}
              onClick={() => void startFileImport()}
            >
              Import {file.name}
            </Button>
          )}
        </div>

        {state === "importing" && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <LoaderCircle className="size-3.5 animate-spin" />
            Copying the selected Cursor file and parsing locally…
          </div>
        )}

        {state === "error" && error && <ImportError kind="upload" message={error} />}

        {result && state === "success" && (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg border border-border px-3 py-3">
                <p className="text-xs text-muted-foreground">Conversations</p>
                <p className="mt-1 text-2xl font-medium tracking-tight">
                  {result.conversations.toLocaleString()}
                </p>
              </div>
              <div className="rounded-lg border border-border px-3 py-3">
                <p className="text-xs text-muted-foreground">Messages</p>
                <p className="mt-1 text-2xl font-medium tracking-tight">
                  {result.messages.toLocaleString()}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Link
                href="/"
                className="inline-flex h-8 w-fit items-center rounded-lg bg-primary px-2.5 text-sm font-medium text-primary-foreground shadow-[0_0_20px_-8px_var(--primary)] hover:bg-primary/88"
              >
                Open Dashboard
              </Link>
              <Link
                href="/ask"
                className="inline-flex h-8 w-fit items-center rounded-lg border border-border px-2.5 text-sm hover:bg-muted"
              >
                Ask Jistory
              </Link>
              <Button type="button" variant="outline" onClick={reset}>
                Import another
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

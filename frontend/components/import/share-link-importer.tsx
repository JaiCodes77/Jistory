"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Link2, LoaderCircle } from "lucide-react"

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
import { getImportJob, importShareLink } from "@/lib/api"
import type { ImportStatusResponse, ParseJobSuccess } from "@/types/import"

const INDEX_POLL_MS = 900

type ShareLinkImporterProps = {
  onStatusChange?: (state: IndexBannerState | null) => void
}

export function ShareLinkImporter({ onStatusChange }: ShareLinkImporterProps) {
  const [url, setUrl] = useState("")
  const [state, setState] = useState<"idle" | "importing" | "success" | "error">("idle")
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ParseJobSuccess | null>(null)
  const [indexStatus, setIndexStatus] = useState<ImportStatusResponse | null>(null)

  const currentStatus = indexStatus?.status || result?.status
  const indexing =
    state === "success" &&
    (currentStatus === "indexing" || currentStatus === "processing")
  const ready = currentStatus === "ready" || currentStatus === "completed"
  const keywordReady = ready || currentStatus === "parsed"

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
    setUrl("")
    setState("idle")
    setError(null)
    setResult(null)
    setIndexStatus(null)
    onStatusChange?.(null)
  }

  const startImport = async () => {
    const trimmed = url.trim()
    if (!trimmed || state === "importing") return

    setState("importing")
    setError(null)
    setResult(null)
    setIndexStatus(null)

    try {
      const response = await importShareLink(trimmed)
      setResult(response)
      setState("success")
      if (response.importId) {
        await pollIndex(response.importId)
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not import that share link."
      )
      setState("error")
    }
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

  return (
    <Card className="h-full border-border bg-card shadow-none">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Share link</CardTitle>
        <CardDescription>
          In ChatGPT or Claude, open a chat → Share → Copy link, then paste it
          here. One public snapshot becomes one local conversation.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative min-w-0 flex-1">
            <Link2 className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void startImport()
              }}
              placeholder="https://chatgpt.com/share/... or https://claude.ai/share/..."
              className="pl-8"
              disabled={state === "importing" || indexing}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <Button
            type="button"
            disabled={!url.trim() || state === "importing" || indexing}
            onClick={() => void startImport()}
          >
            {state === "importing" ? "Importing…" : "Import chat"}
          </Button>
        </div>

        {state === "importing" && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <LoaderCircle className="size-3.5 animate-spin" />
            Fetching the public share page…
          </div>
        )}

        {state === "error" && error && <ImportError kind="share" message={error} />}

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

"use client"

import { useState } from "react"
import Link from "next/link"
import { AlertCircle, CheckCircle2, Link2, LoaderCircle } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { getImportJob, importChatGPTShare } from "@/lib/api"
import type { ImportStatusResponse, ParseJobSuccess } from "@/types/import"

const INDEX_POLL_MS = 900

export function ShareLinkImporter() {
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

  const reset = () => {
    setUrl("")
    setState("idle")
    setError(null)
    setResult(null)
    setIndexStatus(null)
  }

  const startImport = async () => {
    const trimmed = url.trim()
    if (!trimmed || state === "importing") return

    setState("importing")
    setError(null)
    setResult(null)
    setIndexStatus(null)

    try {
      const response = await importChatGPTShare(trimmed)
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
    <Card className="border-border bg-card shadow-none">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Share link</CardTitle>
        <CardDescription>
          In ChatGPT, open a chat → Share → Copy link, then paste it here.
          Sharing makes that snapshot public to anyone with the link; you can
          turn sharing off in ChatGPT after importing.
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
              placeholder="https://chatgpt.com/share/..."
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

        {state === "error" && error && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <p>{error}</p>
          </div>
        )}

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

            {indexing && (
              <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-sm">
                <LoaderCircle className="mt-0.5 size-4 shrink-0 animate-spin" />
                <div>
                  <p className="font-medium">Indexing embeddings</p>
                  <p className="text-xs text-muted-foreground">
                    Keyword search is already available.
                  </p>
                </div>
              </div>
            )}

            {indexStatus?.index_error && (
              <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                <p>{indexStatus.index_error}</p>
              </div>
            )}

            {keywordReady && !indexing && (
              <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-sm">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-foreground" />
                <div>
                  <p className="font-medium">
                    {ready ? "Chat imported" : "Imported — keyword search ready"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Stored locally. Import another share link whenever you want.
                  </p>
                </div>
              </div>
            )}

            <div className="flex items-center gap-2">
              <Link
                href="/conversations"
                className="inline-flex h-8 w-fit items-center rounded-lg bg-primary px-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/80"
              >
                Open conversations
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

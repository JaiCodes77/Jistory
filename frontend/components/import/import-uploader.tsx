"use client"

import { useCallback, useRef, useState } from "react"
import Link from "next/link"
import { CheckCircle2, FileArchive, LoaderCircle, Upload } from "lucide-react"

import { ForgetButton } from "@/components/conversations/forget-button"
import { CursorImporter } from "@/components/import/cursor-importer"
import {
  ImportError,
  ImportIndexBanner,
  type IndexBannerState,
} from "@/components/import/import-status"
import { ShareLinkImporter } from "@/components/import/share-link-importer"
import { PageIntro } from "@/components/layout/page-intro"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  formatBytes,
  formatImportedAt,
  forgetImportJob,
  getImportJob,
  parseImportJob,
  reindexImportJob,
  uploadExport,
} from "@/lib/api"
import { formatImportStatus } from "@/lib/labels"
import { cn } from "@/lib/utils"
import type {
  ImportJobSuccess,
  ImportStatusResponse,
  ParseJobSuccess,
  ParseState,
  UploadState,
} from "@/types/import"

const INDEX_POLL_MS = 900

export function ImportUploader() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [zipSource, setZipSource] = useState<"chatgpt" | "claude">("chatgpt")
  const [state, setState] = useState<UploadState>("idle")
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ImportJobSuccess | null>(null)
  const [dragActive, setDragActive] = useState(false)

  const [parseState, setParseState] = useState<ParseState>("idle")
  const [parseError, setParseError] = useState<string | null>(null)
  const [parseResult, setParseResult] = useState<ParseJobSuccess | null>(null)
  const [indexStatus, setIndexStatus] = useState<ImportStatusResponse | null>(null)
  const [shareStatus, setShareStatus] = useState<IndexBannerState | null>(null)
  const [cursorStatus, setCursorStatus] = useState<IndexBannerState | null>(null)
  const [reindexing, setReindexing] = useState(false)

  const resetSelection = useCallback(() => {
    setFile(null)
    setState("idle")
    setProgress(0)
    setError(null)
    setResult(null)
    setParseState("idle")
    setParseError(null)
    setParseResult(null)
    setIndexStatus(null)
    if (inputRef.current) {
      inputRef.current.value = ""
    }
  }, [])

  const selectFile = useCallback((next: File | null) => {
    if (!next) return

    if (!next.name.toLowerCase().endsWith(".zip")) {
      setFile(null)
      setResult(null)
      setParseResult(null)
      setIndexStatus(null)
      setProgress(0)
      setState("error")
      setError(
        zipSource === "claude"
          ? "Please select a Claude export ZIP file (.zip)."
          : "Please select a ChatGPT export ZIP file (.zip)."
      )
      return
    }

    setFile(next)
    setResult(null)
    setParseResult(null)
    setIndexStatus(null)
    setParseState("idle")
    setParseError(null)
    setError(null)
    setProgress(0)
    setState("selected")
  }, [zipSource])

  const onInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const next = event.target.files?.[0] ?? null
    selectFile(next)
  }

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragActive(false)
    const next = event.dataTransfer.files?.[0] ?? null
    selectFile(next)
  }

  const pollIndex = async (importId: string) => {
    for (let attempt = 0; attempt < 600; attempt += 1) {
      const status = await getImportJob(importId)
      setIndexStatus(status)
      setResult((prev) => (prev ? { ...prev, status: status.status } : prev))
      if (
        status.status === "ready" ||
        status.status === "completed" ||
        status.status === "parsed" ||
        status.status === "failed"
      ) {
        return status
      }
      await new Promise((resolve) => window.setTimeout(resolve, INDEX_POLL_MS))
    }
    throw new Error("Indexing is taking too long. Keyword search may already work.")
  }

  const runParse = async (importId: string) => {
    setParseState("parsing")
    setParseError(null)
    setIndexStatus(null)

    try {
      const response = await parseImportJob(importId)
      setParseResult(response)
      setResult((prev) => (prev ? { ...prev, status: response.status } : prev))
      setParseState("success")
      await pollIndex(importId)
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to parse conversations."
      setParseError(message)
      setParseState("error")
    }
  }

  const startUpload = async () => {
    if (!file || state === "uploading") return

    setState("uploading")
    setProgress(0)
    setError(null)
    setResult(null)
    setParseState("idle")
    setParseError(null)
    setParseResult(null)
    setIndexStatus(null)

    try {
      const response = await uploadExport({
        file,
        source: zipSource,
        onProgress: setProgress,
      })
      setResult(response)
      setProgress(100)
      setState("success")
      await runParse(response.importId)
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Upload failed. Please try again."
      setError(message)
      setState("error")
    }
  }

  const currentStatus = indexStatus?.status || parseResult?.status || result?.status
  const indexing =
    parseState === "success" &&
    (currentStatus === "indexing" || currentStatus === "processing")
  const indexError = indexStatus?.index_error
  const ready = currentStatus === "ready" || currentStatus === "completed"
  const keywordReady = ready || currentStatus === "parsed"

  const zipBanner: IndexBannerState | null =
    parseState === "success" || indexing || Boolean(indexError)
      ? {
          indexing,
          ready,
          keywordReady,
          indexError: indexError ?? null,
          embeddingStatus: indexStatus?.embedding_status ?? null,
          embeddingDetail: indexStatus?.embedding_status_detail ?? null,
        }
      : null

  const pageBanner =
    zipBanner?.indexing || zipBanner?.indexError
      ? zipBanner
      : shareStatus?.indexing || shareStatus?.indexError
        ? shareStatus
        : cursorStatus?.indexing || cursorStatus?.indexError
          ? cursorStatus
          : zipBanner?.keywordReady
            ? zipBanner
            : shareStatus?.keywordReady
              ? shareStatus
              : cursorStatus

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <div className="flex flex-col gap-2">
        <PageIntro description="Paste a ChatGPT or Claude share link, upload an export ZIP, or import Cursor chats from a file you choose. Everything stays on this machine." />
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
          <span>1. Upload or paste</span>
          <span>2. Parse</span>
          <span>3. Keyword search ready</span>
          <span>4. Embeddings indexing</span>
        </div>
      </div>

      {pageBanner && (
        <ImportIndexBanner
          state={pageBanner}
          reindexing={reindexing}
          onReindex={
            result?.importId && pageBanner.indexError
              ? () => {
                  void (async () => {
                    if (!result?.importId) return
                    setReindexing(true)
                    try {
                      await reindexImportJob(result.importId)
                      await pollIndex(result.importId)
                    } catch (err) {
                      setParseError(
                        err instanceof Error ? err.message : "Could not reindex embeddings."
                      )
                    } finally {
                      setReindexing(false)
                    }
                  })()
                }
              : undefined
          }
        />
      )}

      <div className="grid items-stretch gap-4 lg:grid-cols-2">
        <ShareLinkImporter onStatusChange={setShareStatus} />

        <Card className="h-full border-border bg-card shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Export ZIP</CardTitle>
            <CardDescription>
              {zipSource === "claude"
                ? "Claude → Settings → Privacy → Export data. Drop the ZIP here; parse starts automatically after upload."
                : "ChatGPT → Settings → Data controls → Export data. Drop the ZIP here; parse starts automatically after upload."}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex gap-1 rounded-lg border border-border p-1">
              <Button
                type="button"
                size="sm"
                variant={zipSource === "chatgpt" ? "secondary" : "ghost"}
                disabled={state === "uploading" || parseState === "parsing" || indexing}
                onClick={() => setZipSource("chatgpt")}
              >
                ChatGPT
              </Button>
              <Button
                type="button"
                size="sm"
                variant={zipSource === "claude" ? "secondary" : "ghost"}
                disabled={state === "uploading" || parseState === "parsing" || indexing}
                onClick={() => setZipSource("claude")}
              >
                Claude
              </Button>
            </div>
            <div
              onDragEnter={(event) => {
                event.preventDefault()
                setDragActive(true)
              }}
              onDragOver={(event) => {
                event.preventDefault()
                setDragActive(true)
              }}
              onDragLeave={(event) => {
                event.preventDefault()
                setDragActive(false)
              }}
              onDrop={onDrop}
              className={cn(
                "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed px-6 py-10 text-center transition-colors",
                dragActive
                  ? "border-primary/45 bg-primary/8"
                  : "border-border bg-background/60",
                state === "uploading" && "pointer-events-none opacity-70"
              )}
            >
              <div className="flex size-10 items-center justify-center rounded-md border border-border bg-muted/40">
                <Upload className="size-4 text-muted-foreground" />
              </div>
              <div className="flex flex-col gap-1">
                <p className="text-sm font-medium">Drop your ZIP here</p>
                <p className="text-xs text-muted-foreground">
                  or choose a file from your computer
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={state === "uploading" || parseState === "parsing" || indexing}
                onClick={() => inputRef.current?.click()}
              >
                Select ZIP
              </Button>
              <input
                ref={inputRef}
                type="file"
                accept=".zip,application/zip"
                className="hidden"
                onChange={onInputChange}
              />
            </div>

            {file && (
              <div className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5">
                <div className="flex min-w-0 items-center gap-2.5">
                  <FileArchive className="size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0">
                    <p className="truncate text-sm">{file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatBytes(file.size)}
                    </p>
                  </div>
                </div>
                {state !== "uploading" && parseState !== "parsing" && !indexing && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="xs"
                    onClick={resetSelection}
                  >
                    Clear
                  </Button>
                )}
              </div>
            )}

            {state === "uploading" && (
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Uploading…</span>
                  <span>{progress}%</span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full bg-brand-gradient-x transition-[width] duration-150"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}

            {parseState === "parsing" && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <LoaderCircle className="size-3.5 animate-spin" />
                Parsing conversations… keyword search comes next.
              </div>
            )}

            {state === "error" && error && <ImportError kind="upload" message={error} />}
            {parseState === "error" && parseError && (
              <ImportError kind="parse" message={parseError} />
            )}

            <div className="flex items-center gap-2">
              <Button
                type="button"
                disabled={!file || state === "uploading" || parseState === "parsing" || indexing}
                onClick={() => {
                  if (state === "success" && parseState === "error" && result?.importId) {
                    void runParse(result.importId)
                    return
                  }
                  void startUpload()
                }}
              >
                {state === "uploading"
                  ? "Uploading…"
                  : parseState === "parsing"
                    ? "Parsing…"
                    : parseState === "error"
                      ? "Retry parse"
                      : "Upload export"}
              </Button>
              {(state === "success" || state === "error") && (
                <Button
                  type="button"
                  variant="outline"
                  disabled={parseState === "parsing" || indexing}
                  onClick={resetSelection}
                >
                  Import another
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <CursorImporter onStatusChange={setCursorStatus} />

      {result && state === "success" && (
        <Card className="border-border bg-card shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Import summary</CardTitle>
            <CardDescription>
              Stored under <span className="font-mono text-xs">{result.folder}</span>
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
              <SummaryItem label="Filename" value={result.filename ?? "—"} />
              <SummaryItem
                label="File size"
                value={formatBytes(result.fileSize)}
              />
              <SummaryItem
                label="Imported at"
                value={formatImportedAt(result.importedAt)}
              />
              <SummaryItem label="Status" value={formatImportStatus(currentStatus)} />
              <SummaryItem label="Source" value={result.source} />
              <SummaryItem label="Import ID" value={result.importId} mono />
            </dl>
            <ForgetButton
              label="Forget this import"
              confirmCopy="This permanently deletes this import and every conversation, message, and embedding that came from it."
              onConfirm={async () => {
                await forgetImportJob(result.importId)
                resetSelection()
              }}
            />
          </CardContent>
        </Card>
      )}

      {parseResult && parseState === "success" && (
        <Card className="border-border bg-card shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Imported</CardTitle>
            <CardDescription>
              Normalized and stored in SQLite. Keyword search is available while
              embeddings finish indexing.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <StatBlock
                label="Conversations"
                value={parseResult.conversations.toLocaleString()}
              />
              <StatBlock
                label="Messages"
                value={parseResult.messages.toLocaleString()}
              />
              <StatBlock label="Elapsed" value={parseResult.elapsed} />
            </div>

            {parseResult.skipped > 0 && (
              <p className="text-xs text-muted-foreground">
                Skipped {parseResult.skipped.toLocaleString()} malformed
                conversation{parseResult.skipped === 1 ? "" : "s"}.
              </p>
            )}

            {keywordReady && !indexing && (
              <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-sm">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-foreground" />
                <div>
                  <p className="font-medium">
                    {ready ? "Ready for Search and Ask" : "Ready for keyword search"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Next: open the Dashboard, then Ask and type @ to tag a chat.
                  </p>
                </div>
              </div>
            )}

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
              <Link
                href="/conversations"
                className="inline-flex h-8 w-fit items-center rounded-lg border border-border px-2.5 text-sm hover:bg-muted"
              >
                Browse conversations
              </Link>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function SummaryItem({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="rounded-lg border border-border px-3 py-2.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd
        className={cn(
          "mt-1 truncate text-sm",
          mono && "font-mono text-xs"
        )}
        title={value}
      >
        {value}
      </dd>
    </div>
  )
}

function StatBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border px-3 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-medium tracking-tight">{value}</p>
    </div>
  )
}

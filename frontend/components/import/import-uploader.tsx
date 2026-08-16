"use client"

import { useCallback, useRef, useState } from "react"
import Link from "next/link"
import {
  AlertCircle,
  CheckCircle2,
  FileArchive,
  LoaderCircle,
  Upload,
} from "lucide-react"

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
  getImportJob,
  parseImportJob,
  uploadChatGPTExport,
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
  const [state, setState] = useState<UploadState>("idle")
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ImportJobSuccess | null>(null)
  const [dragActive, setDragActive] = useState(false)

  const [parseState, setParseState] = useState<ParseState>("idle")
  const [parseError, setParseError] = useState<string | null>(null)
  const [parseResult, setParseResult] = useState<ParseJobSuccess | null>(null)
  const [indexStatus, setIndexStatus] = useState<ImportStatusResponse | null>(null)

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
      setError("Please select a ChatGPT export ZIP file (.zip).")
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
  }, [])

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
      const response = await uploadChatGPTExport({
        file,
        onProgress: setProgress,
      })
      setResult(response)
      setProgress(100)
      setState("success")
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Upload failed. Please try again."
      setError(message)
      setState("error")
    }
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

  const startParse = async () => {
    if (!result?.importId || parseState === "parsing") return

    setParseState("parsing")
    setParseError(null)
    setIndexStatus(null)

    try {
      const response = await parseImportJob(result.importId)
      setParseResult(response)
      setResult((prev) =>
        prev ? { ...prev, status: response.status } : prev
      )
      setParseState("success")
      await pollIndex(result.importId)
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to parse conversations."
      setParseError(message)
      setParseState("error")
    }
  }

  const currentStatus = indexStatus?.status || parseResult?.status || result?.status
  const indexing =
    parseState === "success" &&
    (currentStatus === "indexing" || currentStatus === "processing")
  const indexError = indexStatus?.index_error
  const ready =
    currentStatus === "ready" || currentStatus === "completed"
  const keywordReady = ready || currentStatus === "parsed"

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-6 py-10">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-medium tracking-tight">Import</h2>
        <p className="text-sm text-muted-foreground">
          Upload a ChatGPT data export ZIP, then parse conversations into
          Jistory.
        </p>
      </div>

      <Card className="border-border bg-card shadow-none">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">ChatGPT export</CardTitle>
          <CardDescription>
            Export from ChatGPT → Settings → Data controls → Export data.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
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
              "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed px-6 py-12 text-center transition-colors",
              dragActive
                ? "border-foreground/40 bg-muted/40"
                : "border-border bg-background",
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
                <span className="inline-flex items-center gap-1.5">
                  <LoaderCircle className="size-3.5 animate-spin" />
                  Uploading…
                </span>
                <span>{progress}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full bg-primary transition-[width] duration-150"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {state === "error" && error && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <p>{error}</p>
            </div>
          )}

          {state === "success" && (
            <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-sm">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-foreground" />
              <p>Import completed successfully. Export saved locally.</p>
            </div>
          )}

          <div className="flex items-center gap-2">
            <Button
              type="button"
              disabled={!file || state === "uploading" || parseState === "parsing" || indexing}
              onClick={startUpload}
            >
              {state === "uploading" ? "Uploading…" : "Upload export"}
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

            {parseState !== "success" && (
              <div className="flex flex-col gap-3 border-t border-border pt-4">
                <div className="flex flex-col gap-1">
                  <p className="text-sm font-medium">Next step</p>
                  <p className="text-xs text-muted-foreground">
                    Parse the export into normalized conversations and messages.
                    Embeddings index in the background after parse.
                  </p>
                </div>

                {parseState === "parsing" && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <LoaderCircle className="size-3.5 animate-spin" />
                    Parsing conversations…
                  </div>
                )}

                {parseState === "error" && parseError && (
                  <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
                    <AlertCircle className="mt-0.5 size-4 shrink-0" />
                    <p>{parseError}</p>
                  </div>
                )}

                <div>
                  <Button
                    type="button"
                    disabled={parseState === "parsing"}
                    onClick={startParse}
                  >
                    {parseState === "parsing"
                      ? "Parsing…"
                      : parseState === "error"
                        ? "Retry parse"
                        : "Parse Conversations"}
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {parseResult && parseState === "success" && (
        <Card className="border-border bg-card shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Imported</CardTitle>
            <CardDescription>Normalized and stored in SQLite.</CardDescription>
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

            {indexing && (
              <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-sm">
                <LoaderCircle className="mt-0.5 size-4 shrink-0 animate-spin" />
                <div>
                  <p className="font-medium">Indexing embeddings</p>
                  <p className="text-xs text-muted-foreground">
                    {indexStatus?.embedding_status === "downloading"
                      ? indexStatus.embedding_status_detail ||
                        "Downloading the local embedding model (first run)…"
                      : "Keyword search is already available. Semantic search will turn on when indexing finishes."}
                  </p>
                </div>
              </div>
            )}

            {indexError && (
              <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                <p>{indexError}</p>
              </div>
            )}

            {keywordReady && !indexing && (
              <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-sm">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-foreground" />
                <div>
                  <p className="font-medium">
                    {ready ? "Ready for Search and Ask" : "Ready for keyword search"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {ready
                      ? "Conversations are stored locally with keyword and semantic indexes."
                      : "Conversations are stored locally. Semantic indexing did not finish, but Search still works."}
                  </p>
                </div>
              </div>
            )}

            <Link
              href="/conversations"
              className="inline-flex h-8 w-fit items-center rounded-lg bg-primary px-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/80"
            >
              Browse conversations
            </Link>
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

import { AlertCircle, CheckCircle2, LoaderCircle } from "lucide-react"

import { Button } from "@/components/ui/button"
import { importNextStep } from "@/lib/labels"

export type IndexBannerState = {
  indexing: boolean
  ready: boolean
  keywordReady: boolean
  indexError: string | null
  embeddingStatus: string | null
  embeddingDetail: string | null
}

export function ImportIndexBanner({
  state,
  onReindex,
  reindexing = false,
}: {
  state: IndexBannerState
  onReindex?: () => void
  reindexing?: boolean
}) {
  if (state.indexing) {
    return (
      <div className="rounded-xl border border-primary/25 bg-primary/8 px-4 py-3">
        <div className="flex items-start gap-2">
          <LoaderCircle className="mt-0.5 size-4 shrink-0 animate-spin" />
          <div>
            <p className="text-sm font-medium">Indexing embeddings</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {state.embeddingStatus === "downloading"
                ? state.embeddingDetail ||
                  "Downloading the local embedding model (first run)…"
                : "Keyword search is already available. Semantic search turns on when this finishes — you can leave this page."}
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (state.indexError) {
    return (
      <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        <div className="flex items-start gap-2">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-medium">{state.indexError}</p>
            <p className="mt-1 text-xs text-destructive/90">
              Next: {importNextStep("index", state.indexError)}
            </p>
            {onReindex && (
              <Button
                type="button"
                variant="outline"
                size="xs"
                className="mt-2"
                disabled={reindexing}
                onClick={onReindex}
              >
                {reindexing ? "Reindexing…" : "Reindex embeddings"}
              </Button>
            )}
          </div>
        </div>
      </div>
    )
  }

  if (state.keywordReady && !state.indexing) {
    return (
      <div className="rounded-xl border border-border bg-muted/40 px-4 py-3">
        <div className="flex items-start gap-2">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="text-sm font-medium">
              {state.ready ? "Ready for Search and Ask" : "Keyword search is ready"}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {state.ready
                ? "Conversations are stored locally with keyword and semantic indexes."
                : "Conversations are stored locally. Semantic indexing did not finish, but Search still works."}
            </p>
          </div>
        </div>
      </div>
    )
  }

  return null
}

export function ImportError({
  message,
  kind,
}: {
  message: string
  kind: "upload" | "parse" | "index" | "share"
}) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <div>
        <p>{message}</p>
        <p className="mt-1 text-xs text-destructive/90">Next: {importNextStep(kind, message)}</p>
      </div>
    </div>
  )
}

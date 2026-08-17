"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import { EmptyState } from "@/components/layout/empty-state"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { conversationTitle, formatDate, getDashboard, searchMemories } from "@/lib/api"
import type { SearchHit } from "@/types/api"

const PAGE_SIZE = 20

export function SearchResults() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const queryParam = searchParams.get("q") || ""
  const [input, setInput] = useState(queryParam)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<SearchHit[]>([])
  const [total, setTotal] = useState(0)
  const [hasMemories, setHasMemories] = useState<boolean | null>(null)

  useEffect(() => {
    void getDashboard()
      .then((data) => setHasMemories(data.total_conversations > 0))
      .catch(() => setHasMemories(null))
  }, [])

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setInput(queryParam)
      setPage(1)
    }, 0)
    return () => window.clearTimeout(handle)
  }, [queryParam])

  useEffect(() => {
    const trimmed = queryParam.trim()
    const handle = window.setTimeout(async () => {
      if (trimmed.length < 2) {
        setResults([])
        setTotal(0)
        setLoading(false)
        setError(null)
        return
      }
      setLoading(true)
      setError(null)
      try {
        const response = await searchMemories(trimmed, page, PAGE_SIZE)
        setResults(response.results)
        setTotal(response.total)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Search failed.")
      } finally {
        setLoading(false)
      }
    }, 80)
    return () => window.clearTimeout(handle)
  }, [queryParam, page])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-8">
      <div>
        <h2 className="text-lg font-medium tracking-tight">Search</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Keyword and semantic search over conversations stored on this machine.
          Press / or ⌘K from anywhere.
        </p>
      </div>

      {hasMemories === false ? (
        <EmptyState
          title="Nothing to search yet"
          description="Import a conversation first. Search looks through chats stored on this machine."
        />
      ) : (
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            const next = input.trim()
            setPage(1)
            router.replace(next ? `/search?q=${encodeURIComponent(next)}` : "/search")
          }}
        >
          <Input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Search Grafana, Redis, FastAPI…"
          />
          <Button type="submit">Search</Button>
        </form>
      )}

      {loading && (
        <div className="text-sm text-muted-foreground">Searching…</div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      {!loading &&
        hasMemories !== false &&
        queryParam.trim().length < 2 &&
        !error && (
          <p className="text-sm text-muted-foreground">
            Type at least two characters. Hits open the conversation with the
            matching message highlighted.
          </p>
        )}

      {!loading && queryParam.trim().length >= 2 && total === 0 && !error && (
        <p className="text-sm text-muted-foreground">No results found.</p>
      )}

      <div className="flex flex-col gap-2">
        {results.map((hit) => (
          <Link
            key={`${hit.conversation_id}:${hit.message_id}:${hit.score}`}
            href={`/conversations/${hit.conversation_id}?message=${hit.message_id}`}
            className="rounded-xl border border-border bg-card px-4 py-3 hover:bg-muted/40"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="truncate text-sm font-medium">
                {conversationTitle(hit.conversation_title)}
              </p>
              <span className="shrink-0 text-[11px] text-muted-foreground">
                {hit.source} · {formatDate(hit.timestamp)}
              </span>
            </div>
            <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">
              {hit.snippet}
            </p>
          </Link>
        ))}
      </div>

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm">
          <p className="text-muted-foreground">{total.toLocaleString()} results</p>
          <div className="flex items-center justify-between gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
            >
              Previous
            </Button>
            <span className="text-xs text-muted-foreground">
              {page} / {pageCount}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= pageCount}
              onClick={() => setPage((value) => value + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

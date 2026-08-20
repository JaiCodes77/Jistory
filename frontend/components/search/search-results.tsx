"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import { DateRangeChips, rangeToIso, type MemoryRangeKey } from "@/components/memory/date-range-chips"
import { EmptyState } from "@/components/layout/empty-state"
import { PageIntro } from "@/components/layout/page-intro"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { conversationTitle, formatDate, getDashboard, listConversationSources, searchMemories } from "@/lib/api"
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
  const [source, setSource] = useState("")
  const [sourceOptions, setSourceOptions] = useState<string[]>(["ChatGPT", "Claude"])
  const [dateRange, setDateRange] = useState<MemoryRangeKey>("")
  const [customFrom, setCustomFrom] = useState("")
  const [customTo, setCustomTo] = useState("")

  useEffect(() => {
    void getDashboard()
      .then((data) => setHasMemories(data.total_conversations > 0))
      .catch(() => setHasMemories(null))
    void listConversationSources()
      .then((data) => setSourceOptions(data.items))
      .catch(() => undefined)
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
        const dates = rangeToIso(dateRange, customFrom, customTo)
        const response = await searchMemories(trimmed, page, PAGE_SIZE, {
          source,
          dateFrom: dates.dateFrom,
          dateTo: dates.dateTo,
        })
        setResults(response.results)
        setTotal(response.total)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Search failed.")
      } finally {
        setLoading(false)
      }
    }, 80)
    return () => window.clearTimeout(handle)
  }, [queryParam, page, source, dateRange, customFrom, customTo])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-8">
      <PageIntro description="Keyword and semantic search over conversations on this machine. Press / or ⌘K from anywhere." />

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

      {hasMemories !== false && (
        <div className="flex flex-col gap-3">
          <DateRangeChips
            range={dateRange}
            customFrom={customFrom}
            customTo={customTo}
            onRangeChange={(value) => {
              setDateRange(value)
              setPage(1)
            }}
            onCustomFromChange={(value) => {
              setCustomFrom(value)
              setPage(1)
            }}
            onCustomToChange={(value) => {
              setCustomTo(value)
              setPage(1)
            }}
          />
          <select
            value={source}
            onChange={(event) => {
              setSource(event.target.value)
              setPage(1)
            }}
            className="h-8 w-full max-w-xs rounded-lg border border-border bg-background px-2 text-sm"
            aria-label="Filter by source"
          >
            <option value="">All sources</option>
            {sourceOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
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

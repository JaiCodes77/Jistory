"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"

import { ForgetButton } from "@/components/conversations/forget-button"
import { EmptyState } from "@/components/layout/empty-state"
import { PageIntro } from "@/components/layout/page-intro"
import { ThreadFilament } from "@/components/layout/thread-filament"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { conversationTitle, forgetConversation, formatDate, listConversationSources, listConversations } from "@/lib/api"
import type { ConversationSummary } from "@/types/api"

const RANGES = [
  { value: "all", label: "All time" },
  { value: "today", label: "Today" },
  { value: "last_7_days", label: "Last 7 days" },
  { value: "last_30_days", label: "Last 30 days" },
  { value: "last_3_months", label: "Last 3 months" },
  { value: "custom", label: "Custom range" },
]

const SORTS = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
  { value: "most_messages", label: "Most messages" },
  { value: "recently_updated", label: "Recently updated" },
]

const PAGE_SIZE = 30

export function ConversationBrowser() {
  const [items, setItems] = useState<ConversationSummary[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const [debouncedSearch, setDebouncedSearch] = useState("")
  const [source, setSource] = useState("")
  const [sourceOptions, setSourceOptions] = useState<string[]>(["ChatGPT", "Claude"])
  const [range, setRange] = useState("all")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [sort, setSort] = useState("newest")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedSearch(search), 200)
    return () => window.clearTimeout(handle)
  }, [search])

  useEffect(() => {
    void listConversationSources()
      .then((data) => setSourceOptions(data.items))
      .catch(() => undefined)
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await listConversations({
        page,
        pageSize: PAGE_SIZE,
        search: debouncedSearch,
        source,
        range,
        dateFrom: range === "custom" ? dateFrom : "",
        dateTo: range === "custom" ? dateTo : "",
        sort,
      })
      setItems(response.items)
      setTotal(response.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load conversations.")
    } finally {
      setLoading(false)
    }
  }, [page, debouncedSearch, source, range, dateFrom, dateTo, sort])

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void load()
    }, 0)
    return () => window.clearTimeout(handle)
  }, [load])

  const updateFilter = <T,>(setter: (value: T) => void, value: T) => {
    setter(value)
    setPage(1)
  }

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const filtersActive =
    Boolean(debouncedSearch.trim()) || Boolean(source) || range !== "all"

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-8">
      <PageIntro description="Imported chats on this machine. Use / or ⌘K to search inside messages." />

      <div className="surface flex flex-col gap-3 rounded-lg p-3">
        <div className="grid gap-2 md:grid-cols-4">
          <Input
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setPage(1)
            }}
            placeholder="Filter by title"
          />
          <select
            value={source}
            onChange={(event) => updateFilter(setSource, event.target.value)}
            className="field-select"
          >
            <option value="">All sources</option>
            {sourceOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <select
            value={range}
            onChange={(event) => updateFilter(setRange, event.target.value)}
            className="field-select"
          >
            {RANGES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <select
            value={sort}
            onChange={(event) => updateFilter(setSort, event.target.value)}
            className="field-select"
          >
            {SORTS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        {range === "custom" && (
          <div className="grid gap-2 md:grid-cols-2">
            <Input
              type="date"
              value={dateFrom}
              onChange={(event) => updateFilter(setDateFrom, event.target.value)}
            />
            <Input
              type="date"
              value={dateTo}
              onChange={(event) => updateFilter(setDateTo, event.target.value)}
            />
          </div>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading && (
        <div className="text-sm text-muted-foreground">Loading conversations…</div>
      )}

      {!loading && total === 0 && !filtersActive && (
        <EmptyState
          title="No conversations yet"
          description="Import a ChatGPT share link or export ZIP, then browse and search from here."
        />
      )}

      {!loading && total === 0 && filtersActive && (
        <p className="text-sm text-muted-foreground">
          No conversations match these filters.
        </p>
      )}

      {!loading && items.length > 0 && (
        <div className="flex flex-col gap-2">
          {items.map((item) => (
            <div
              key={item.id}
              className="surface relative flex items-stretch overflow-hidden rounded-lg"
            >
              <ThreadFilament source={item.source} />
              <Link
                href={`/conversations/${item.id}`}
                className="min-w-0 flex-1 py-3 pr-4 pl-6 transition-colors hover:bg-muted/40"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {conversationTitle(item.title)}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {formatDate(item.updated_at || item.created_at)} ·{" "}
                      {item.message_count.toLocaleString()} messages
                    </p>
                  </div>
                  <Badge variant="outline">{item.source}</Badge>
                </div>
              </Link>
              <div className="flex items-center border-l border-border px-2">
                <ForgetButton
                  confirmCopy="This permanently deletes this conversation, its messages, and embeddings. Search and Ask will no longer use it."
                  onConfirm={async () => {
                    await forgetConversation(item.id)
                    await load()
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm">
          <p className="text-muted-foreground">
            {total.toLocaleString()} conversations
          </p>
          <div className="flex items-center gap-2">
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

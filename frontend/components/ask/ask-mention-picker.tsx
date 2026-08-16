"use client"

import { useEffect, useState } from "react"
import { LoaderCircle } from "lucide-react"

import { conversationTitle, formatDate, listConversations } from "@/lib/api"
import type { ConversationSummary } from "@/types/api"
import { cn } from "@/lib/utils"

type AskMentionPickerProps = {
  query: string
  excludeIds: string[]
  activeIndex: number
  onActiveIndexChange: (index: number) => void
  onItemsChange: (items: ConversationSummary[]) => void
  onSelect: (item: ConversationSummary) => void
}

export function AskMentionPicker({
  query,
  excludeIds,
  activeIndex,
  onActiveIndexChange,
  onItemsChange,
  onSelect,
}: AskMentionPickerProps) {
  const [items, setItems] = useState<ConversationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const excludeKey = excludeIds.join(",")

  useEffect(() => {
    const excluded = new Set(excludeKey ? excludeKey.split(",") : [])
    let cancelled = false
    const handle = window.setTimeout(() => {
      setLoading(true)
      setError(null)
      void listConversations({
        page: 1,
        pageSize: 8,
        search: query.trim(),
        sort: "recently_updated",
      })
        .then((response) => {
          if (cancelled) return
          const next = response.items.filter((item) => !excluded.has(item.id))
          setItems(next)
          onItemsChange(next)
        })
        .catch((err: unknown) => {
          if (cancelled) return
          setItems([])
          onItemsChange([])
          setError(err instanceof Error ? err.message : "Could not load conversations.")
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }, 120)
    return () => {
      cancelled = true
      window.clearTimeout(handle)
    }
  }, [query, excludeKey, onItemsChange])

  const highlight = items.length === 0 ? 0 : activeIndex % items.length

  return (
    <div
      className="absolute inset-x-0 bottom-full z-20 mb-2 overflow-hidden rounded-xl border border-border bg-card"
      role="listbox"
      aria-label="Tag a conversation"
    >
      <div className="border-b border-border px-3 py-2">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Tag a conversation
        </p>
      </div>
      <div className="max-h-64 overflow-auto p-1.5">
        {loading && (
          <div className="flex items-center gap-2 px-2 py-3 text-sm text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin" />
            Searching conversations…
          </div>
        )}
        {error && <p className="px-2 py-3 text-sm text-destructive">{error}</p>}
        {!loading && !error && items.length === 0 && (
          <p className="px-2 py-3 text-sm text-muted-foreground">
            No matching conversations.
          </p>
        )}
        {!loading &&
          items.map((item, index) => (
            <button
              key={item.id}
              type="button"
              role="option"
              aria-selected={index === highlight}
              className={cn(
                "flex w-full flex-col rounded-lg px-2.5 py-2 text-left",
                index === highlight ? "bg-muted" : "hover:bg-muted/60"
              )}
              onMouseEnter={() => onActiveIndexChange(index)}
              onMouseDown={(event) => {
                event.preventDefault()
                onSelect(item)
              }}
            >
              <span className="truncate text-sm font-medium">
                {conversationTitle(item.title)}
              </span>
              <span className="mt-0.5 text-[11px] text-muted-foreground">
                {item.source} · {formatDate(item.updated_at || item.created_at)} ·{" "}
                {item.message_count.toLocaleString()} messages
              </span>
            </button>
          ))}
      </div>
    </div>
  )
}

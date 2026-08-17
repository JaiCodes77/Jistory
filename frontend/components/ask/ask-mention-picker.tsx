"use client"

import { useEffect, useState } from "react"

import { conversationTitle, formatDate, listConversations } from "@/lib/api"
import type { ConversationSummary } from "@/types/api"
import { cn } from "@/lib/utils"

const FETCH_SIZE = 40
const VISIBLE_SIZE = 8

type AskMentionPickerProps = {
  query: string
  excludeIds: string[]
  activeIndex: number
  atMax?: boolean
  onActiveIndexChange: (index: number) => void
  onItemsChange: (items: ConversationSummary[]) => void
  onSelect: (item: ConversationSummary) => void
}

export function AskMentionPicker({
  query,
  excludeIds,
  activeIndex,
  atMax = false,
  onActiveIndexChange,
  onItemsChange,
  onSelect,
}: AskMentionPickerProps) {
  const [items, setItems] = useState<ConversationSummary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(!atMax)
  const [error, setError] = useState<string | null>(null)

  const excludeKey = excludeIds.join(",")
  const trimmedQuery = query.trim()

  useEffect(() => {
    if (atMax) {
      setItems([])
      onItemsChange([])
      setLoading(false)
      setError(null)
      return
    }

    const excluded = new Set(excludeKey ? excludeKey.split(",") : [])
    setItems((current) => current.filter((item) => !excluded.has(item.id)))

    let cancelled = false
    const handle = window.setTimeout(() => {
      setLoading(true)
      setError(null)
      void listConversations({
        page: 1,
        pageSize: FETCH_SIZE,
        search: trimmedQuery,
        sort: "recently_updated",
      })
        .then((response) => {
          if (cancelled) return
          const next = response.items
            .filter((item) => !excluded.has(item.id))
            .slice(0, VISIBLE_SIZE)
          setTotal(response.total)
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
  }, [trimmedQuery, excludeKey, atMax, onItemsChange])

  const highlight = items.length === 0 ? 0 : activeIndex % items.length

  let emptyCopy = "No matching conversations."
  if (atMax) {
    emptyCopy = "You can tag at most 8 chats. Remove a tag to add another."
  } else if (total === 0 && !trimmedQuery) {
    emptyCopy = "No conversations imported yet."
  } else if (items.length === 0 && excludeIds.length > 0 && !trimmedQuery) {
    emptyCopy = "All listed chats are already tagged. Type to find another."
  } else if (items.length === 0 && excludeIds.length > 0 && trimmedQuery) {
    emptyCopy = "No untagged chats match that name."
  } else if (trimmedQuery) {
    emptyCopy = `No conversations match “${trimmedQuery}”.`
  }

  return (
    <div
      className="absolute inset-x-0 bottom-full z-20 mb-2 overflow-hidden rounded-xl border border-border bg-card"
      role="listbox"
      aria-label="Tag a conversation"
    >
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Tag a conversation
        </p>
        <p className="text-[11px] text-muted-foreground">↑↓ Enter Esc</p>
      </div>
      <div className="max-h-64 overflow-auto p-1.5">
        {atMax && (
          <p className="px-2 py-3 text-sm text-muted-foreground">{emptyCopy}</p>
        )}
        {!atMax && loading && items.length === 0 && (
          <p className="px-2 py-3 text-sm text-muted-foreground">
            Searching conversations…
          </p>
        )}
        {!atMax && error && <p className="px-2 py-3 text-sm text-destructive">{error}</p>}
        {!atMax && !error && !loading && items.length === 0 && (
          <p className="px-2 py-3 text-sm text-muted-foreground">{emptyCopy}</p>
        )}
        {!atMax &&
          !error &&
          items.map((item, index) => (
            <button
              key={item.id}
              id={`mention-option-${item.id}`}
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

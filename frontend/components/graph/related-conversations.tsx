"use client"

import Link from "next/link"
import { useEffect, useState } from "react"

import { conversationTitle, formatDate, getRelatedConversations } from "@/lib/api"
import { formatWeight, sourceSwatchClass } from "@/lib/graph-style"
import { cn } from "@/lib/utils"
import type { RelatedConversation } from "@/types/api"
import { ThreadFilament } from "@/components/layout/thread-filament"

export function RelatedConversations({
  conversationId,
  compact = false,
}: {
  conversationId: string
  compact?: boolean
}) {
  const [items, setItems] = useState<RelatedConversation[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void getRelatedConversations(conversationId)
      .then((response) => {
        if (!cancelled) {
          setItems(response.items)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load related conversations.")
        }
      })
    return () => {
      cancelled = true
    }
  }, [conversationId])

  return (
    <section className={cn("flex flex-col gap-3", compact ? "" : "h-full min-h-0 px-4 py-5")}>
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h3 className="font-heading text-sm tracking-tight">Related conversations</h3>
          <p className="text-xs text-muted-foreground">Why these chats connect.</p>
        </div>
        <Link
          href={`/graph?focus=${encodeURIComponent(conversationId)}`}
          className="text-[11px] text-muted-foreground hover:text-foreground"
        >
          View in graph
        </Link>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {items === null && !error && (
        <p className="text-sm text-muted-foreground">Finding related chats…</p>
      )}
      {items && items.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No related conversations yet. Links appear after indexing when chats share topics or
          similar content.
        </p>
      )}
      {items && items.length > 0 && (
        <div className={cn("flex flex-col gap-2", !compact && "min-h-0 overflow-auto")}>
          {items.map((item) => (
            <Link
              key={item.id}
              href={`/conversations/${item.id}`}
              className="surface relative rounded-md px-3 py-2 pl-6 hover:bg-muted/50"
            >
              <ThreadFilament source={item.source} />
              <div className="flex items-start justify-between gap-2">
                <p className="truncate text-sm">{conversationTitle(item.title)}</p>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {formatWeight(item.weight)}
                </span>
              </div>
              <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <span className={cn("size-1.5 rounded-full", sourceSwatchClass(item.source))} />
                {item.source} · {formatDate(item.last_message_at)}
              </p>
              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{item.reason}</p>
              <span
                className="mt-2 block h-0.5 rounded-full bg-foreground/20"
                style={{ width: `${Math.max(14, Math.min(100, item.weight * 100))}%` }}
              />
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}

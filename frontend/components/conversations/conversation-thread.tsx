"use client"

import Link from "next/link"
import { useCallback, useEffect, useRef, useState } from "react"
import { useSearchParams } from "next/navigation"
import { LoaderCircle } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  conversationTitle,
  formatDate,
  formatImportedAt,
  getConversationMessages,
} from "@/lib/api"
import { formatRole } from "@/lib/labels"
import type { ConversationSummary, MessageItem } from "@/types/api"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 80
const MAX_RENDERED = 160

const ROLE_STYLES: Record<string, string> = {
  user: "border-border bg-muted/40",
  assistant: "border-border bg-card",
  system: "border-border bg-background text-muted-foreground",
  tool: "border-border bg-background text-muted-foreground",
}

function mergeMessages(current: MessageItem[], incoming: MessageItem[]): MessageItem[] {
  const byId = new Map<string, MessageItem>()
  for (const item of [...current, ...incoming]) {
    byId.set(item.id, item)
  }
  return Array.from(byId.values()).sort(
    (a, b) => a.sequence_number - b.sequence_number
  )
}

function capWindow(items: MessageItem[], anchorId?: string | null): MessageItem[] {
  if (items.length <= MAX_RENDERED) return items
  if (!anchorId) return items.slice(-MAX_RENDERED)
  const index = items.findIndex((item) => item.id === anchorId)
  if (index < 0) return items.slice(0, MAX_RENDERED)
  const half = Math.floor(MAX_RENDERED / 2)
  const start = Math.max(0, Math.min(index - half, items.length - MAX_RENDERED))
  return items.slice(start, start + MAX_RENDERED)
}

function scrollToMessage(id: string, attempts = 24) {
  const node = document.getElementById(`message-${id}`)
  if (node) {
    node.scrollIntoView({ block: "center" })
    return
  }
  if (attempts > 0) {
    window.requestAnimationFrame(() => scrollToMessage(id, attempts - 1))
  }
}

export function ConversationThread({ conversationId }: { conversationId: string }) {
  const searchParams = useSearchParams()
  const highlightId = searchParams.get("message")
  const listRef = useRef<HTMLDivElement>(null)

  const [conversation, setConversation] = useState<ConversationSummary | null>(null)
  const [messages, setMessages] = useState<MessageItem[]>([])
  const [hasBefore, setHasBefore] = useState(false)
  const [hasAfter, setHasAfter] = useState(false)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingBefore, setLoadingBefore] = useState(false)
  const [loadingAfter, setLoadingAfter] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const applyResponse = useCallback(
    (
      incoming: MessageItem[],
      append: "replace" | "before" | "after",
      flags: { has_before: boolean; has_after: boolean }
    ) => {
      setMessages((current) => {
        const merged =
          append === "replace" ? incoming : mergeMessages(current, incoming)
        const capped = capWindow(merged, highlightId)
        const droppedStart = Boolean(
          merged.length && capped.length && merged[0].id !== capped[0].id
        )
        const droppedEnd = Boolean(
          merged.length &&
            capped.length &&
            merged[merged.length - 1].id !== capped[capped.length - 1].id
        )
        setHasBefore(flags.has_before || droppedStart)
        setHasAfter(flags.has_after || droppedEnd)
        return capped
      })
    },
    [highlightId]
  )

  const loadInitial = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await getConversationMessages(
        conversationId,
        1,
        PAGE_SIZE,
        highlightId || undefined
      )
      setConversation(response.conversation)
      setTotal(response.total)
      applyResponse(response.items, "replace", {
        has_before: response.has_before,
        has_after: response.has_after,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load conversation.")
    } finally {
      setLoading(false)
    }
  }, [applyResponse, conversationId, highlightId])

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void loadInitial()
    }, 0)
    return () => window.clearTimeout(handle)
  }, [loadInitial])

  useEffect(() => {
    if (!highlightId || loading) return
    const handle = window.setTimeout(() => scrollToMessage(highlightId), 30)
    return () => window.clearTimeout(handle)
  }, [highlightId, loading, messages])

  const loadEarlier = async () => {
    if (!messages.length || loadingBefore) return
    setLoadingBefore(true)
    setError(null)
    try {
      const response = await getConversationMessages(
        conversationId,
        1,
        PAGE_SIZE,
        undefined,
        messages[0].sequence_number
      )
      setConversation(response.conversation)
      setTotal(response.total)
      applyResponse(response.items, "before", {
        has_before: response.has_before,
        has_after: hasAfter,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load earlier messages.")
    } finally {
      setLoadingBefore(false)
    }
  }

  const loadLater = async () => {
    if (!messages.length || loadingAfter) return
    setLoadingAfter(true)
    setError(null)
    try {
      const response = await getConversationMessages(
        conversationId,
        1,
        PAGE_SIZE,
        undefined,
        undefined,
        messages[messages.length - 1].sequence_number
      )
      setConversation(response.conversation)
      setTotal(response.total)
      applyResponse(response.items, "after", {
        has_before: hasBefore,
        has_after: response.has_after,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load more messages.")
    } finally {
      setLoadingAfter(false)
    }
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-6 py-6">
      <Link href="/conversations" className="mb-4 text-xs text-muted-foreground hover:text-foreground">
        ← Conversations
      </Link>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin" />
          Loading conversation…
        </div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      {conversation && (
        <div className="mb-6 border-b border-border pb-4">
          <h2 className="text-lg font-medium tracking-tight">
            {conversationTitle(conversation.title)}
          </h2>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <Badge variant="outline">{conversation.source}</Badge>
            <span>Created {formatDate(conversation.created_at)}</span>
            <span>Updated {formatImportedAt(conversation.updated_at)}</span>
            <span>{conversation.message_count.toLocaleString()} messages</span>
          </div>
        </div>
      )}

      <div ref={listRef} className="flex flex-col gap-3 pb-10">
        {hasBefore && !loading && (
          <div className="flex justify-center">
            <Button
              variant="outline"
              disabled={loadingBefore}
              onClick={() => void loadEarlier()}
            >
              {loadingBefore ? "Loading…" : "Load earlier messages"}
            </Button>
          </div>
        )}

        {messages.map((message) => (
          <article
            key={message.id}
            id={`message-${message.id}`}
            style={{ contentVisibility: "auto", containIntrinsicSize: "auto 120px" }}
            className={cn(
              "rounded-xl border px-4 py-3",
              ROLE_STYLES[message.role] ?? ROLE_STYLES.system,
              highlightId === message.id && "ring-2 ring-ring"
            )}
          >
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {formatRole(message.role)}
              </p>
              <p className="text-[11px] text-muted-foreground">
                {formatImportedAt(message.created_at)}
              </p>
            </div>
            <pre className="whitespace-pre-wrap font-sans text-sm leading-6">
              {message.content || "(no text)"}
            </pre>
          </article>
        ))}

        {hasAfter && !loading && (
          <div className="flex justify-center pt-2">
            <Button
              variant="outline"
              disabled={loadingAfter}
              onClick={() => void loadLater()}
            >
              {loadingAfter ? "Loading…" : "Load later messages"}
            </Button>
          </div>
        )}

        {!loading && messages.length > 0 && total > messages.length && (
          <p className="text-center text-[11px] text-muted-foreground">
            Showing {messages.length.toLocaleString()} of {total.toLocaleString()} messages
          </p>
        )}
      </div>
    </div>
  )
}

"use client"

import Link from "next/link"
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import { ExpandableMessage } from "@/components/conversations/expandable-message"
import { ForgetButton } from "@/components/conversations/forget-button"
import { RelatedConversations } from "@/components/graph/related-conversations"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { CopyTextButton } from "@/components/ui/copy-text-button"
import {
  conversationTitle,
  forgetConversation,
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
  user: "border-border/80 bg-muted/35",
  assistant: "border-border/80 bg-card/80 backdrop-blur-md",
  system: "border-border/80 bg-background/50 text-muted-foreground",
  tool: "border-border/80 bg-background/50 text-muted-foreground",
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
  if (index < 0) return items.slice(-MAX_RENDERED)
  const half = Math.floor(MAX_RENDERED / 2)
  const start = Math.max(0, Math.min(index - half, items.length - MAX_RENDERED))
  return items.slice(start, start + MAX_RENDERED)
}

function captureScrollAnchor(list: HTMLElement, ids: string[]) {
  const top = list.scrollTop
  for (const id of ids) {
    const node = document.getElementById(`message-${id}`)
    if (!node) continue
    if (node.offsetTop + node.offsetHeight > top) {
      return { id, offset: node.offsetTop - top }
    }
  }
  return null
}

function restoreScrollAnchor(
  list: HTMLElement,
  anchor: { id: string; offset: number } | null
) {
  if (!anchor) return
  const node = document.getElementById(`message-${anchor.id}`)
  if (!node) return
  list.scrollTop = node.offsetTop - anchor.offset
}

function scrollToMessage(id: string, attempts = 24) {
  const node = document.getElementById(`message-${id}`)
  if (node) {
    node.scrollIntoView({ block: "center", inline: "nearest" })
    return
  }
  if (attempts > 0) {
    window.requestAnimationFrame(() => scrollToMessage(id, attempts - 1))
  }
}

export function ConversationThread({ conversationId }: { conversationId: string }) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const highlightId = searchParams.get("message")
  const listRef = useRef<HTMLDivElement>(null)
  const pendingAnchor = useRef<{ id: string; offset: number } | null>(null)
  const alignedHighlight = useRef<string | null>(null)

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
      flags: { has_before: boolean; has_after: boolean },
      capAnchor?: string | null
    ) => {
      setMessages((current) => {
        const merged =
          append === "replace" ? incoming : mergeMessages(current, incoming)
        const anchor =
          capAnchor ?? (append === "replace" ? highlightId : null)
        const capped = capWindow(merged, anchor)
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
    alignedHighlight.current = null
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

  useLayoutEffect(() => {
    const anchor = pendingAnchor.current
    const node = listRef.current
    if (!anchor || !node) return
    restoreScrollAnchor(node, anchor)
    pendingAnchor.current = null
  }, [messages])

  useEffect(() => {
    if (!highlightId || loading) return
    if (alignedHighlight.current === highlightId) return
    if (!messages.some((item) => item.id === highlightId)) return
    alignedHighlight.current = highlightId
    const handle = window.setTimeout(() => scrollToMessage(highlightId), 30)
    return () => window.clearTimeout(handle)
  }, [highlightId, loading, messages])

  const loadEarlier = async () => {
    if (!messages.length || loadingBefore) return
    const list = listRef.current
    if (list) {
      pendingAnchor.current = captureScrollAnchor(
        list,
        messages.map((item) => item.id)
      )
    }
    const capAnchorId = messages[0].id
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
      applyResponse(
        response.items,
        "before",
        {
          has_before: response.has_before,
          has_after: hasAfter,
        },
        capAnchorId
      )
    } catch (err) {
      pendingAnchor.current = null
      setError(err instanceof Error ? err.message : "Could not load earlier messages.")
    } finally {
      setLoadingBefore(false)
    }
  }

  const loadLater = async () => {
    if (!messages.length || loadingAfter) return
    const list = listRef.current
    if (list) {
      pendingAnchor.current = captureScrollAnchor(
        list,
        messages.map((item) => item.id)
      )
    }
    const capAnchorId = messages[messages.length - 1].id
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
      applyResponse(
        response.items,
        "after",
        {
          has_before: hasBefore,
          has_after: response.has_after,
        },
        capAnchorId
      )
    } catch (err) {
      pendingAnchor.current = null
      setError(err instanceof Error ? err.message : "Could not load more messages.")
    } finally {
      setLoadingAfter(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden lg:flex-row">
      <div className="mx-auto flex h-full min-h-0 w-full max-w-3xl flex-1 flex-col px-6 py-6">
      <Link href="/conversations" className="mb-4 text-xs text-muted-foreground hover:text-foreground">
        ← Conversations
      </Link>

      {loading && (
        <div className="text-sm text-muted-foreground">Loading conversation…</div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      {conversation && (
        <div className="mb-4 shrink-0 border-b border-border pb-4">
          <div className="flex items-start justify-between gap-4">
            <h2 className="text-lg font-medium tracking-tight">
              {conversationTitle(conversation.title)}
            </h2>
            <ForgetButton
              confirmCopy="This permanently deletes this conversation, its messages, and embeddings. Search and Ask will no longer use it."
              onConfirm={async () => {
                await forgetConversation(conversationId)
                router.push("/conversations")
                router.refresh()
              }}
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <Badge variant="outline">{conversation.source}</Badge>
            <span>Created {formatDate(conversation.created_at)}</span>
            <span>Updated {formatImportedAt(conversation.updated_at)}</span>
            <span>{conversation.message_count.toLocaleString()} messages</span>
          </div>
          <div className="mt-4 lg:hidden">
            <RelatedConversations key={conversationId} conversationId={conversationId} compact />
          </div>
        </div>
      )}

      <div ref={listRef} className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto pb-10">
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
            style={
              highlightId === message.id
                ? undefined
                : { contentVisibility: "auto", containIntrinsicSize: "auto 120px" }
            }
            className={cn(
              "scroll-mt-6 rounded-xl border px-4 py-3",
              ROLE_STYLES[message.role] ?? ROLE_STYLES.system,
              highlightId === message.id &&
                "border-primary/40 bg-primary/8 ring-2 ring-primary/35"
            )}
          >
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {formatRole(message.role)}
                {highlightId === message.id ? " · Matched" : ""}
              </p>
              <div className="flex shrink-0 items-center gap-1.5">
                <CopyTextButton text={message.content} />
                <p className="text-[11px] text-muted-foreground">
                  {formatImportedAt(message.created_at)}
                </p>
              </div>
            </div>
            <ExpandableMessage
              content={message.content}
              defaultExpanded={highlightId === message.id}
            />
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
      <aside className="hidden min-h-0 w-80 shrink-0 overflow-auto border-l border-border/80 bg-background/50 backdrop-blur-xl lg:block">
        <RelatedConversations key={conversationId} conversationId={conversationId} />
      </aside>
    </div>
  )
}

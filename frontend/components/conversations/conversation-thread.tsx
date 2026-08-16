"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
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
import type { ConversationSummary, MessageItem } from "@/types/api"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 80

const ROLE_STYLES: Record<string, string> = {
  user: "border-border bg-muted/40",
  assistant: "border-border bg-card",
  system: "border-border bg-background text-muted-foreground",
  tool: "border-border bg-background text-muted-foreground",
}

export function ConversationThread({ conversationId }: { conversationId: string }) {
  const searchParams = useSearchParams()
  const highlightId = searchParams.get("message")
  const listRef = useRef<HTMLDivElement>(null)

  const [conversation, setConversation] = useState<ConversationSummary | null>(null)
  const [messages, setMessages] = useState<MessageItem[]>([])
  const [loadedPage, setLoadedPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadPage = useCallback(
    async (nextPage: number, around?: string, append = false) => {
      if (append) setLoadingMore(true)
      else setLoading(true)
      setError(null)
      try {
        const response = await getConversationMessages(
          conversationId,
          nextPage,
          PAGE_SIZE,
          around
        )
        setConversation(response.conversation)
        setTotal(response.total)
        setLoadedPage(response.page)
        setMessages((current) =>
          append ? [...current, ...response.items] : response.items
        )
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load conversation.")
      } finally {
        setLoading(false)
        setLoadingMore(false)
      }
    },
    [conversationId]
  )

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void loadPage(1, highlightId || undefined)
    }, 0)
    return () => window.clearTimeout(handle)
  }, [loadPage, highlightId])

  useEffect(() => {
    if (!highlightId) return
    const node = document.getElementById(`message-${highlightId}`)
    node?.scrollIntoView({ block: "center" })
  }, [highlightId, messages])

  const loadedCount = messages.length
  const hasMore = loadedCount < total
  const pagesLoaded = useMemo(
    () => Math.ceil(loadedCount / PAGE_SIZE) || loadedPage,
    [loadedCount, loadedPage]
  )

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
        {messages.map((message) => (
          <article
            key={message.id}
            id={`message-${message.id}`}
            className={cn(
              "rounded-xl border px-4 py-3",
              ROLE_STYLES[message.role] ?? ROLE_STYLES.system,
              highlightId === message.id && "ring-2 ring-ring"
            )}
          >
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {message.role}
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

        {hasMore && (
          <div className="flex justify-center pt-2">
            <Button
              variant="outline"
              disabled={loadingMore}
              onClick={() => void loadPage(pagesLoaded + 1, undefined, true)}
            >
              {loadingMore ? "Loading…" : "Load more messages"}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

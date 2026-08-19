"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { X } from "lucide-react"

import { AskMentionPicker } from "@/components/ask/ask-mention-picker"
import { AskSessionSidebar } from "@/components/ask/ask-session-sidebar"
import { AskSources } from "@/components/ask/ask-sources"
import { DateRangeChips, rangeToIso, type MemoryRangeKey } from "@/components/memory/date-range-chips"
import { EmptyState } from "@/components/layout/empty-state"
import { MessageMarkdown } from "@/components/markdown/message-markdown"
import { Button } from "@/components/ui/button"
import { CopyTextButton } from "@/components/ui/copy-text-button"
import { Textarea } from "@/components/ui/textarea"
import {
  askJistoryStream,
  conversationTitle,
  deleteAskSession,
  getAskSession,
  getConversation,
  getDashboard,
  getSettings,
  listAskSessions,
} from "@/lib/api"
import {
  getActiveMention,
  MAX_TAGGED_CONVERSATIONS,
  removeActiveMention,
} from "@/lib/mentions"
import type { AskSessionSummary, ConversationSummary, SourceReference } from "@/types/api"
import { cn } from "@/lib/utils"

type ChatItem = {
  role: "user" | "assistant"
  content: string
  sources?: SourceReference[]
  tags?: ConversationSummary[]
}

export function AskChat() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const sessionParam = searchParams.get("session")
  const tagParam = searchParams.get("tag")
  const [input, setInput] = useState("")
  const [caret, setCaret] = useState(0)
  const [items, setItems] = useState<ChatItem[]>([])
  const [tags, setTags] = useState<ConversationSummary[]>([])
  const [mentionItems, setMentionItems] = useState<ConversationSummary[]>([])
  const [mentionIndex, setMentionIndex] = useState(0)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<AskSessionSummary[]>([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMemories, setHasMemories] = useState<boolean | null>(null)
  const [apiKeyConfigured, setApiKeyConfigured] = useState<boolean | null>(null)
  const [dateRange, setDateRange] = useState<MemoryRangeKey>("")
  const [customFrom, setCustomFrom] = useState("")
  const [customTo, setCustomTo] = useState("")
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const hadSessionParam = useRef(false)

  const mention = useMemo(() => getActiveMention(input, caret), [input, caret])
  const atMaxTags = tags.length >= MAX_TAGGED_CONVERSATIONS
  const mentionOpen = mention !== null
  const excludeIds = useMemo(() => tags.map((tag) => tag.id), [tags])
  const mentionQuery = mention?.query ?? ""
  const [mentionQuerySeen, setMentionQuerySeen] = useState(mentionQuery)
  if (mentionQuery !== mentionQuerySeen) {
    setMentionQuerySeen(mentionQuery)
    setMentionIndex(0)
  }

  useEffect(() => {
    void getDashboard()
      .then((data) => setHasMemories(data.total_conversations > 0))
      .catch(() => setHasMemories(null))
    void getSettings()
      .then((data) => setApiKeyConfigured(data.api_key_configured))
      .catch(() => setApiKeyConfigured(null))
    void listAskSessions()
      .then((data) => setSessions(data.items))
      .catch(() => setSessions([]))
  }, [])

  const resetComposer = useCallback(() => {
    setItems([])
    setTags([])
    setSessionId(null)
    setError(null)
    setInput("")
    setCaret(0)
  }, [])

  useEffect(() => {
    if (!tagParam || sessionParam) return
    let cancelled = false
    void getConversation(tagParam)
      .then((conversation) => {
        if (cancelled) return
        setTags((current) =>
          current.some((tag) => tag.id === conversation.id)
            ? current
            : [...current, conversation].slice(0, MAX_TAGGED_CONVERSATIONS)
        )
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [tagParam, sessionParam])

  useEffect(() => {
    if (!sessionParam) {
      if (hadSessionParam.current) {
        resetComposer()
        hadSessionParam.current = false
      }
      return
    }
    hadSessionParam.current = true
    let cancelled = false
    void getAskSession(sessionParam)
      .then((detail) => {
        if (cancelled) return
        const nextItems: ChatItem[] = []
        for (const turn of detail.turns) {
          if (turn.role === "user") {
            nextItems.push({
              role: "user",
              content: turn.content,
              tags: detail.tagged_conversations,
            })
          } else if (turn.role === "assistant") {
            nextItems.push({
              role: "assistant",
              content: turn.content,
              sources: turn.sources,
            })
          }
        }
        setItems(nextItems)
        setTags(detail.tagged_conversations)
        setSessionId(detail.id)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : "Could not load that Ask session.")
      })
    return () => {
      cancelled = true
    }
  }, [sessionParam])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" })
  }, [items, pending])

  const syncCaret = () => {
    const node = textareaRef.current
    if (!node) return
    setCaret(node.selectionStart ?? 0)
  }

  const selectMention = useCallback(
    (conversation: ConversationSummary) => {
      if (tags.length >= MAX_TAGGED_CONVERSATIONS) return
      const currentValue = textareaRef.current?.value ?? input
      const active = getActiveMention(
        currentValue,
        textareaRef.current?.selectionStart ?? caret
      )
      const nextValue = active ? removeActiveMention(currentValue, active) : currentValue
      setTags((current) =>
        current.some((tag) => tag.id === conversation.id)
          ? current
          : [...current, conversation].slice(0, MAX_TAGGED_CONVERSATIONS)
      )
      setInput(nextValue)
      setMentionItems([])
      requestAnimationFrame(() => {
        textareaRef.current?.focus()
        const position = Math.min(nextValue.length, active?.start ?? nextValue.length)
        textareaRef.current?.setSelectionRange(position, position)
        setCaret(position)
      })
    },
    [caret, input, tags.length]
  )

  const removeTag = (id: string) => {
    setTags((current) => current.filter((tag) => tag.id !== id))
    textareaRef.current?.focus()
  }

  const submit = async () => {
    const message = input.trim()
    if (!message || pending || mentionOpen) return
    const tagged = tags
    setInput("")
    setCaret(0)
    setError(null)
    setItems((current) => [
      ...current,
      { role: "user", content: message, tags: tagged },
      { role: "assistant", content: "", sources: [] },
    ])
    setPending(true)
    try {
      await askJistoryStream(
        message,
        sessionId,
        tagged.map((tag) => tag.id),
        rangeToIso(dateRange, customFrom, customTo),
        {
          onSources: (payload) => {
            if (payload.conversation_id) setSessionId(payload.conversation_id)
            setItems((current) => {
              const next = [...current]
              const last = next[next.length - 1]
              if (last?.role === "assistant") {
                next[next.length - 1] = { ...last, sources: payload.sources }
              }
              return next
            })
          },
          onToken: (text) => {
            setItems((current) => {
              const next = [...current]
              const last = next[next.length - 1]
              if (last?.role === "assistant") {
                next[next.length - 1] = { ...last, content: `${last.content}${text}` }
              }
              return next
            })
          },
          onDone: (payload) => {
            setSessionId(payload.conversation_id)
            setItems((current) => {
              const next = [...current]
              const last = next[next.length - 1]
              if (last?.role === "assistant" && payload.answer && !last.content) {
                next[next.length - 1] = { ...last, content: payload.answer }
              }
              return next
            })
            router.replace(`/ask?session=${encodeURIComponent(payload.conversation_id)}`)
            void listAskSessions()
              .then((data) => setSessions(data.items))
              .catch(() => undefined)
          },
        }
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ask failed.")
    } finally {
      setPending(false)
    }
  }

  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (mentionOpen) {
      if (event.key === "ArrowDown") {
        event.preventDefault()
        setMentionIndex((index) =>
          mentionItems.length === 0 ? 0 : (index + 1) % mentionItems.length
        )
        return
      }
      if (event.key === "ArrowUp") {
        event.preventDefault()
        setMentionIndex((index) =>
          mentionItems.length === 0
            ? 0
            : (index - 1 + mentionItems.length) % mentionItems.length
        )
        return
      }
      if (event.key === "Home") {
        event.preventDefault()
        setMentionIndex(0)
        return
      }
      if (event.key === "End") {
        event.preventDefault()
        setMentionIndex(mentionItems.length === 0 ? 0 : mentionItems.length - 1)
        return
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault()
        const selected =
          mentionItems.length === 0
            ? undefined
            : mentionItems[mentionIndex % mentionItems.length]
        if (selected) selectMention(selected)
        return
      }
      if (event.key === "Escape") {
        event.preventDefault()
        const node = textareaRef.current
        if (node && mention) {
          const next = `${input.slice(0, mention.start)}${input.slice(mention.end)}`
          setInput(next)
          requestAnimationFrame(() => {
            node.focus()
            node.setSelectionRange(mention.start, mention.start)
            setCaret(mention.start)
          })
        }
        return
      }
    }

    if (event.key === "Backspace" && !input && tags.length > 0) {
      event.preventDefault()
      setTags((current) => current.slice(0, -1))
      return
    }

    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      void submit()
    }
  }

  const tagHelper =
    tags.length > 0
      ? `Scoped to ${tags.length}/${MAX_TAGGED_CONVERSATIONS} tagged chat${
          tags.length === 1 ? "" : "s"
        }. Tags stay after you send so follow-ups stay in these chats.`
      : `Type @ to tag up to ${MAX_TAGGED_CONVERSATIONS} chats. Tags stay after send so follow-ups stay scoped.`

  return (
    <div className="flex h-full min-h-0 flex-1 max-md:flex-col">
      <AskSessionSidebar
        sessions={sessions}
        activeId={sessionParam || sessionId}
        onNew={() => {
          resetComposer()
          router.push("/ask")
        }}
        onSelect={(id) => {
          router.push(`/ask?session=${encodeURIComponent(id)}`)
        }}
        onDelete={(id) => {
          void deleteAskSession(id)
            .then(() => {
              setSessions((current) => current.filter((session) => session.id !== id))
              if ((sessionParam || sessionId) === id) {
                resetComposer()
                router.push("/ask")
              }
            })
            .catch((err: unknown) => {
              setError(err instanceof Error ? err.message : "Could not delete that session.")
            })
        }}
      />
    <div className="mx-auto flex h-full min-h-0 w-full max-w-3xl flex-1 flex-col px-6 py-6">
      <div className="mb-6">
        <h2 className="text-lg font-medium tracking-tight">Ask Jistory</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Answers use only your imported conversations. Type @ to tag specific
          chats. Retrieved excerpts are sent to Gemini to generate a reply.
        </p>
      </div>

      {hasMemories === false && items.length === 0 ? (
        <EmptyState
          title="Jistory doesn't have any memories yet"
          description="Import a ChatGPT share link or export ZIP first, then come back and @ a chat."
        />
      ) : (
        <>
          {apiKeyConfigured === false && (
            <div className="mb-4 rounded-xl border border-border px-4 py-3 text-sm">
              <p className="font-medium">Gemini is not configured.</p>
              <p className="mt-1 text-muted-foreground">
                Add GEMINI_API_KEY in Settings or your backend .env file to generate answers.
              </p>
              <Link href="/settings" className="mt-2 inline-flex text-xs hover:underline">
                Open Settings
              </Link>
            </div>
          )}

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto pb-4">
        {items.length === 0 && hasMemories !== false && (
          <p className="text-sm text-muted-foreground">
            Ask what you discussed, learned, decided, or built. Type @ to scope the
            question to tagged conversations. Tags remain for follow-ups until you
            remove them.
          </p>
        )}
        {items.map((item, index) => (
          <div
            key={`${item.role}-${index}`}
            className={cn(
              "rounded-xl border border-border px-4 py-3",
              item.role === "user" ? "bg-muted/40" : "bg-card"
            )}
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {item.role === "user" ? "You" : "Jistory"}
              </p>
              {item.role === "assistant" && item.content ? (
                <CopyTextButton text={item.content} className="-mr-1.5" />
              ) : null}
            </div>
            {item.tags && item.tags.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {item.tags.map((tag) => (
                  <Link
                    key={tag.id}
                    href={`/conversations/${tag.id}`}
                    className="inline-flex min-w-0 max-w-[min(100%,14rem)] items-center rounded-md border border-border bg-background px-1.5 py-0.5 text-[11px] font-medium hover:bg-muted"
                    title={conversationTitle(tag.title)}
                  >
                    <span className="truncate">@{conversationTitle(tag.title)}</span>
                  </Link>
                ))}
              </div>
            )}
            {item.role === "assistant" ? (
              item.content ? (
                <MessageMarkdown content={item.content} />
              ) : pending && index === items.length - 1 ? (
                <p className="whitespace-pre-wrap text-sm leading-6">
                  Searching your history…
                </p>
              ) : null
            ) : (
              <p className="whitespace-pre-wrap text-sm leading-6">{item.content}</p>
            )}
            {item.sources && item.sources.length > 0 ? (
              <AskSources sources={item.sources} />
            ) : null}
          </div>
        ))}
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div ref={bottomRef} />
      </div>

      <form
          className="mt-auto flex flex-col gap-2 border-t border-border pt-4"
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
        >
          <div className="relative">
            {mention && (
              <AskMentionPicker
                query={mention.query}
                excludeIds={excludeIds}
                activeIndex={mentionIndex}
                atMax={atMaxTags}
                onActiveIndexChange={setMentionIndex}
                onItemsChange={setMentionItems}
                onSelect={selectMention}
              />
            )}
            <div className="rounded-lg border border-border bg-background focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
              <div className="px-3 pt-2">
                <DateRangeChips
                  range={dateRange}
                  customFrom={customFrom}
                  customTo={customTo}
                  onRangeChange={setDateRange}
                  onCustomFromChange={setCustomFrom}
                  onCustomToChange={setCustomTo}
                />
              </div>
              {tags.length > 0 && (
                <div className="flex flex-wrap items-start gap-1.5 px-3 pt-2">
                  {tags.map((tag) => (
                    <span
                      key={tag.id}
                      className="inline-flex min-w-0 max-w-[min(100%,14rem)] items-center gap-1 rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-[11px] font-medium"
                    >
                      <span className="min-w-0 truncate" title={conversationTitle(tag.title)}>
                        @{conversationTitle(tag.title)}
                      </span>
                      <button
                        type="button"
                        className="shrink-0 rounded-sm text-muted-foreground hover:text-foreground"
                        aria-label={`Remove ${conversationTitle(tag.title)}`}
                        onClick={() => removeTag(tag.id)}
                      >
                        <X className="size-3" />
                      </button>
                    </span>
                  ))}
                  <span className="self-center text-[11px] text-muted-foreground">
                    {tags.length}/{MAX_TAGGED_CONVERSATIONS}
                  </span>
                </div>
              )}
              <Textarea
                ref={textareaRef}
                value={input}
                onChange={(event) => {
                  setInput(event.target.value)
                  setCaret(event.target.selectionStart ?? event.target.value.length)
                }}
                onKeyUp={syncCaret}
                onClick={syncCaret}
                onSelect={syncCaret}
                placeholder="What did I decide about Grafana? Type @ to tag a chat"
                className="border-0 focus-visible:border-transparent focus-visible:ring-0"
                onKeyDown={onComposerKeyDown}
                aria-expanded={mentionOpen}
                aria-autocomplete="list"
              />
            </div>
          </div>
          <div className="flex items-center justify-between gap-3">
            <p className="min-w-0 text-[11px] leading-4 text-muted-foreground">{tagHelper}</p>
            <Button type="submit" disabled={pending || !input.trim() || mentionOpen}>
              Ask
            </Button>
          </div>
        </form>
        </>
      )}
    </div>
    </div>
  )
}

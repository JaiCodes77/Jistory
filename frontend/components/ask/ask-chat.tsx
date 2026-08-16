"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { LoaderCircle, X } from "lucide-react"

import { AskMentionPicker } from "@/components/ask/ask-mention-picker"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import {
  askJistory,
  conversationTitle,
  formatDate,
  getDashboard,
  getSettings,
} from "@/lib/api"
import {
  getActiveMention,
  MAX_TAGGED_CONVERSATIONS,
  removeActiveMention,
} from "@/lib/mentions"
import type { ConversationSummary, SourceReference } from "@/types/api"
import { cn } from "@/lib/utils"

type ChatItem = {
  role: "user" | "assistant"
  content: string
  sources?: SourceReference[]
  tags?: ConversationSummary[]
}

export function AskChat() {
  const [input, setInput] = useState("")
  const [caret, setCaret] = useState(0)
  const [items, setItems] = useState<ChatItem[]>([])
  const [tags, setTags] = useState<ConversationSummary[]>([])
  const [mentionItems, setMentionItems] = useState<ConversationSummary[]>([])
  const [mentionIndex, setMentionIndex] = useState(0)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMemories, setHasMemories] = useState<boolean | null>(null)
  const [apiKeyConfigured, setApiKeyConfigured] = useState<boolean | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const mention = useMemo(
    () => (tags.length >= MAX_TAGGED_CONVERSATIONS ? null : getActiveMention(input, caret)),
    [input, caret, tags.length]
  )
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
  }, [])

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
    [caret, input]
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
    setItems((current) => [...current, { role: "user", content: message, tags: tagged }])
    setPending(true)
    try {
      const response = await askJistory(
        message,
        sessionId,
        tagged.map((tag) => tag.id)
      )
      setSessionId(response.conversation_id)
      setItems((current) => [
        ...current,
        {
          role: "assistant",
          content: response.answer,
          sources: response.sources,
        },
      ])
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

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-6 py-6">
      <div className="mb-6">
        <h2 className="text-lg font-medium tracking-tight">Ask Jistory</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Answers use only your imported conversations. Type @ to tag specific
          chats. Retrieved excerpts are sent to Gemini to generate a reply.
        </p>
      </div>

      {hasMemories === false && items.length === 0 && (
        <div className="mb-6 rounded-xl border border-dashed border-border px-4 py-10 text-center">
          <p className="text-sm font-medium">Jistory doesn&apos;t have any memories yet.</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Import a conversation history first.
          </p>
          <Link
            href="/import"
            className="mt-4 inline-flex h-8 items-center rounded-lg border border-border px-2.5 text-sm hover:bg-muted"
          >
            Import conversations
          </Link>
        </div>
      )}

      {apiKeyConfigured === false && hasMemories !== false && (
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
            question to tagged conversations.
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
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {item.role === "user" ? "You" : "Jistory"}
            </p>
            {item.tags && item.tags.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {item.tags.map((tag) => (
                  <Link
                    key={tag.id}
                    href={`/conversations/${tag.id}`}
                    className="inline-flex max-w-full items-center rounded-md border border-border bg-background px-1.5 py-0.5 text-[11px] font-medium hover:bg-muted"
                  >
                    <span className="truncate">@{conversationTitle(tag.title)}</span>
                  </Link>
                ))}
              </div>
            )}
            <p className="whitespace-pre-wrap text-sm leading-6">{item.content}</p>
            {item.sources && item.sources.length > 0 && (
              <div className="mt-4 border-t border-border pt-3">
                <p className="mb-2 text-xs font-medium text-muted-foreground">Sources</p>
                <ol className="flex flex-col gap-2">
                  {item.sources.map((source, sourceIndex) => (
                    <li key={`${source.conversation_id}-${sourceIndex}`}>
                      <Link
                        href={
                          source.message_id
                            ? `/conversations/${source.conversation_id}?message=${source.message_id}`
                            : `/conversations/${source.conversation_id}`
                        }
                        className="block rounded-lg px-2 py-1.5 hover:bg-muted"
                      >
                        <p className="text-sm">
                          {sourceIndex + 1}. {conversationTitle(source.title)}
                        </p>
                        <p className="text-[11px] text-muted-foreground">
                          {source.source} · {formatDate(source.timestamp)}
                        </p>
                        {source.snippet && (
                          <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                            {source.snippet}
                          </p>
                        )}
                      </Link>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        ))}
        {pending && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin" />
            Searching your history…
          </div>
        )}
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
          {mentionOpen && (
            <AskMentionPicker
              query={mention.query}
              excludeIds={excludeIds}
              activeIndex={mentionIndex}
              onActiveIndexChange={setMentionIndex}
              onItemsChange={setMentionItems}
              onSelect={selectMention}
            />
          )}
          <div className="rounded-lg border border-border bg-background focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 px-3 pt-2">
                {tags.map((tag) => (
                  <span
                    key={tag.id}
                    className="inline-flex max-w-full items-center gap-1 rounded-md border border-border bg-muted/60 px-1.5 py-0.5 text-[11px] font-medium"
                  >
                    <span className="truncate">@{conversationTitle(tag.title)}</span>
                    <button
                      type="button"
                      className="rounded-sm text-muted-foreground hover:text-foreground"
                      aria-label={`Remove ${conversationTitle(tag.title)}`}
                      onClick={() => removeTag(tag.id)}
                    >
                      <X className="size-3" />
                    </button>
                  </span>
                ))}
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
            />
          </div>
        </div>
        <div className="flex items-center justify-between">
          <p className="text-[11px] text-muted-foreground">
            {tags.length > 0
              ? `Answers will use only the ${tags.length} tagged conversation${tags.length === 1 ? "" : "s"}.`
              : "Only retrieved excerpts leave this machine, and only when you ask."}
          </p>
          <Button type="submit" disabled={pending || !input.trim() || mentionOpen}>
            Ask
          </Button>
        </div>
      </form>
    </div>
  )
}

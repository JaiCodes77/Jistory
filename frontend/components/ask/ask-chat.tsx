"use client"

import Link from "next/link"
import { useEffect, useRef, useState } from "react"
import { LoaderCircle } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { askJistory, conversationTitle, formatDate, getDashboard, getSettings } from "@/lib/api"
import type { SourceReference } from "@/types/api"
import { cn } from "@/lib/utils"

type ChatItem = {
  role: "user" | "assistant"
  content: string
  sources?: SourceReference[]
}

export function AskChat() {
  const [input, setInput] = useState("")
  const [items, setItems] = useState<ChatItem[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMemories, setHasMemories] = useState<boolean | null>(null)
  const [apiKeyConfigured, setApiKeyConfigured] = useState<boolean | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

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

  const submit = async () => {
    const message = input.trim()
    if (!message || pending) return
    setInput("")
    setError(null)
    setItems((current) => [...current, { role: "user", content: message }])
    setPending(true)
    try {
      const response = await askJistory(message, sessionId)
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

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-6 py-6">
      <div className="mb-6">
        <h2 className="text-lg font-medium tracking-tight">Ask Jistory</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Answers use only your imported conversations. Retrieved excerpts are sent to
          Gemini to generate a reply.
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
            Ask what you discussed, learned, decided, or built.
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
        <Textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="What did I decide about Grafana?"
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault()
              void submit()
            }
          }}
        />
        <div className="flex items-center justify-between">
          <p className="text-[11px] text-muted-foreground">
            Only retrieved excerpts leave this machine, and only when you ask.
          </p>
          <Button type="submit" disabled={pending || !input.trim()}>
            Ask
          </Button>
        </div>
      </form>
    </div>
  )
}

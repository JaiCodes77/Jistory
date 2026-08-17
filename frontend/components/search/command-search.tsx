"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import { LoaderCircle, Search } from "lucide-react"

import { conversationTitle, formatDate, getDashboard, searchMemories } from "@/lib/api"
import { isEditableTarget } from "@/lib/keyboard"
import type { SearchHit } from "@/types/api"
import { cn } from "@/lib/utils"

export function CommandSearch() {
  const pathname = usePathname()
  const router = useRouter()
  const inputRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<SearchHit[]>([])
  const [hasMemories, setHasMemories] = useState<boolean | null>(null)

  const close = useCallback(() => {
    setOpen(false)
    setQuery("")
    setResults([])
    setError(null)
  }, [])
  const lastPathname = useRef(pathname)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing = isEditableTarget(event.target)

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        setOpen(true)
        return
      }

      if (event.key === "/" && !typing) {
        event.preventDefault()
        setOpen(true)
        return
      }

      if (event.key === "Escape") {
        close()
      }
    }

    const openSearch = () => setOpen(true)
    window.addEventListener("keydown", onKey)
    window.addEventListener("jistory:open-search", openSearch)
    return () => {
      window.removeEventListener("keydown", onKey)
      window.removeEventListener("jistory:open-search", openSearch)
    }
  }, [close])

  useEffect(() => {
    if (open) {
      const id = window.setTimeout(() => inputRef.current?.focus(), 10)
      if (hasMemories === null) {
        void getDashboard()
          .then((data) => setHasMemories(data.total_conversations > 0))
          .catch(() => setHasMemories(null))
      }
      return () => window.clearTimeout(id)
    }
  }, [open, hasMemories])

  useEffect(() => {
    if (lastPathname.current !== pathname) {
      lastPathname.current = pathname
      queueMicrotask(() => close())
    }
  }, [pathname, close])

  useEffect(() => {
    const trimmed = query.trim()
    if (!open || trimmed.length < 2) {
      return
    }

    const handle = window.setTimeout(async () => {
      setLoading(true)
      setError(null)
      try {
        const response = await searchMemories(trimmed, 1, 12)
        setResults(response.results)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Search failed.")
      } finally {
        setLoading(false)
      }
    }, 180)

    return () => window.clearTimeout(handle)
  }, [query, open])

  const empty = useMemo(
    () => query.trim().length >= 2 && !loading && results.length === 0 && !error,
    [query, loading, results.length, error]
  )

  if (!open) return null

  const searchHref = `/search?q=${encodeURIComponent(query.trim())}`

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-[12vh]">
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="Close search"
        onClick={close}
      />
      <div className="relative z-10 w-full max-w-xl overflow-hidden rounded-xl border border-border bg-card">
        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search className="size-4 text-muted-foreground" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && query.trim().length >= 2) {
                event.preventDefault()
                close()
                router.push(searchHref)
              }
            }}
            placeholder="Search conversations and messages"
            className="h-11 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          {loading && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
        </div>
        <div className="max-h-80 overflow-auto p-2">
          {error && (
            <p className="px-2 py-3 text-sm text-destructive">{error}</p>
          )}
          {hasMemories === false && (
            <p className="px-2 py-3 text-sm text-muted-foreground">
              Nothing to search yet.{" "}
              <Link href="/import" className="underline-offset-2 hover:underline" onClick={close}>
                Import conversations
              </Link>{" "}
              first.
            </p>
          )}
          {hasMemories !== false && query.trim().length < 2 && (
            <p className="px-2 py-3 text-sm text-muted-foreground">
              Type at least two characters. Hits open the matching message.
            </p>
          )}
          {empty && (
            <p className="px-2 py-3 text-sm text-muted-foreground">
              No results found.
            </p>
          )}
          {query.trim().length >= 2 &&
            results.map((hit) => (
            <Link
              key={`${hit.conversation_id}:${hit.message_id}`}
              href={`/conversations/${hit.conversation_id}?message=${hit.message_id}`}
              className={cn(
                "block rounded-lg px-2.5 py-2 hover:bg-muted"
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="truncate text-sm font-medium">
                  {conversationTitle(hit.conversation_title)}
                </p>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {hit.source} · {formatDate(hit.timestamp)}
                </span>
              </div>
              <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                {hit.snippet}
              </p>
            </Link>
          ))}
        </div>
        <div className="flex items-center justify-between border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
          <span>Enter opens the search page. Conversations stay on this machine.</span>
          {query.trim().length >= 2 && (
            <Link href={searchHref} className="hover:text-foreground">
              View all results
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}

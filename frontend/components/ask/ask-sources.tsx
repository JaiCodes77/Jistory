"use client"

import { useState } from "react"
import Link from "next/link"
import { ChevronDown, ChevronRight } from "lucide-react"

import { Button } from "@/components/ui/button"
import { conversationTitle, formatDate } from "@/lib/api"
import type { SourceReference } from "@/types/api"

function sourceHref(source: SourceReference): string {
  return source.message_id
    ? `/conversations/${source.conversation_id}?message=${source.message_id}`
    : `/conversations/${source.conversation_id}`
}

export function AskSources({ sources }: { sources: SourceReference[] }) {
  const [expanded, setExpanded] = useState(false)

  if (sources.length === 0) return null

  const label = `${sources.length} source${sources.length === 1 ? "" : "s"}`

  return (
    <div className="mt-4 border-t border-border pt-3">
      <div className="flex min-w-0 items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="xs"
          className="-ml-2 shrink-0 text-muted-foreground"
          aria-expanded={expanded}
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded ? (
            <ChevronDown className="size-3" />
          ) : (
            <ChevronRight className="size-3" />
          )}
          {label}
        </Button>
        {!expanded && (
          <div className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden">
            {sources.slice(0, 3).map((source, sourceIndex) => (
              <Link
                key={`${source.conversation_id}-${source.message_id ?? sourceIndex}`}
                href={sourceHref(source)}
                title={conversationTitle(source.title)}
                className="inline-flex min-w-0 max-w-[9rem] shrink-0 items-center rounded-md border border-border bg-background px-1.5 py-0.5 text-[11px] font-medium hover:bg-muted"
              >
                <span className="truncate">{conversationTitle(source.title)}</span>
              </Link>
            ))}
            {sources.length > 3 && (
              <span className="shrink-0 text-[11px] text-muted-foreground">
                +{sources.length - 3}
              </span>
            )}
          </div>
        )}
      </div>
      {expanded && (
        <ol className="mt-2 flex flex-col gap-2">
          {sources.map((source, sourceIndex) => (
            <li key={`${source.conversation_id}-${source.message_id ?? sourceIndex}`}>
              <Link
                href={sourceHref(source)}
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
      )}
    </div>
  )
}

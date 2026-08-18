"use client"

import { Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { conversationTitle, formatImportedAt } from "@/lib/api"
import type { AskSessionSummary } from "@/types/api"
import { cn } from "@/lib/utils"

export function AskSessionSidebar({
  sessions,
  activeId,
  onNew,
  onSelect,
  onDelete,
}: {
  sessions: AskSessionSummary[]
  activeId: string | null
  onNew: () => void
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}) {
  return (
    <aside className="flex h-full min-h-0 w-56 shrink-0 flex-col border-r border-border bg-card/40 max-md:h-auto max-md:max-h-32 max-md:w-full max-md:border-r-0 max-md:border-b">
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-3 max-md:py-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Sessions
        </p>
        <Button type="button" variant="outline" size="xs" onClick={onNew}>
          <Plus className="size-3" />
          New
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-2 max-md:overflow-x-auto max-md:overflow-y-hidden">
        {sessions.length === 0 ? (
          <p className="px-1 py-2 text-[11px] leading-4 text-muted-foreground">
            New questions start a session you can resume after refresh.
          </p>
        ) : (
          <ul className="flex flex-col gap-1 max-md:w-max max-md:flex-row">
            {sessions.map((session) => {
              const active = session.id === activeId
              return (
                <li key={session.id}>
                  <div
                    className={cn(
                      "flex items-start gap-1 rounded-lg px-2 py-1.5 max-md:w-44",
                      active ? "bg-muted" : "hover:bg-muted/50"
                    )}
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left"
                      onClick={() => onSelect(session.id)}
                    >
                      <p className="truncate text-xs font-medium">
                        {conversationTitle(session.title)}
                      </p>
                      <p className="mt-0.5 text-[10px] text-muted-foreground">
                        {formatImportedAt(session.updated_at)}
                      </p>
                    </button>
                    <button
                      type="button"
                      className="mt-0.5 rounded-sm p-1 text-muted-foreground hover:bg-background hover:text-foreground"
                      aria-label="Delete Ask session"
                      onClick={(event) => {
                        event.preventDefault()
                        event.stopPropagation()
                        const ok = window.confirm(
                          "Delete this Ask session? Imported conversations stay on this machine."
                        )
                        if (ok) onDelete(session.id)
                      }}
                    >
                      <Trash2 className="size-3" />
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </aside>
  )
}

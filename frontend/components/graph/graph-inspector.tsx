"use client"

import { useRouter } from "next/navigation"

import { ThreadFilament } from "@/components/layout/thread-filament"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { conversationTitle, formatDate } from "@/lib/api"
import { formatWeight, sourceSwatchClass } from "@/lib/graph-style"
import { cn } from "@/lib/utils"
import type { GraphEdge, GraphNode } from "@/types/api"

export function GraphInspector({
  node,
  edges,
  nodes,
  onSelect,
}: {
  node: GraphNode | null
  edges: GraphEdge[]
  nodes: GraphNode[]
  onSelect: (id: string) => void
}) {
  const router = useRouter()

  if (!node) {
    return (
      <aside className="hidden h-full min-h-0 w-80 shrink-0 flex-col border-l border-border bg-sidebar xl:flex">
        <div className="px-4 py-5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Inspector</p>
          <h3 className="font-heading mt-1 text-sm leading-snug">No conversation selected</h3>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
            Click a node to inspect its links. Double-click opens the thread.
          </p>
        </div>
      </aside>
    )
  }

  const topics = node.topics ?? []
  const degree = node.degree ?? 0
  const neighbors = edges
    .filter((edge) => edge.source_id === node.id || edge.target_id === node.id)
    .map((edge) => {
      const otherId = edge.source_id === node.id ? edge.target_id : edge.source_id
      const other = nodes.find((item) => item.id === otherId)
      return other ? { node: other, edge } : null
    })
    .filter((item): item is { node: GraphNode; edge: GraphEdge } => item !== null)
    .sort((a, b) => b.edge.weight - a.edge.weight)

  return (
    <aside className="flex h-full min-h-0 w-full shrink-0 flex-col border-t border-border bg-sidebar xl:w-80 xl:border-t-0 xl:border-l">
      <div className="relative border-b border-border px-4 py-4 pl-6">
        <ThreadFilament source={node.source} animate />
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Conversation</p>
        <h3 className="font-heading mt-1 text-sm leading-snug">{conversationTitle(node.title)}</h3>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className="gap-1.5">
            <span className={cn("size-2 rounded-full", sourceSwatchClass(node.source))} />
            {node.source}
          </Badge>
          <span className="text-[11px] text-muted-foreground">{formatDate(node.last_message_at)}</span>
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          {node.message_count.toLocaleString()} messages · {degree} {degree === 1 ? "link" : "links"}
        </p>
        {topics.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {topics.map((topic) => (
              <Badge key={topic} variant="outline">
                {topic}
              </Badge>
            ))}
          </div>
        )}
        {node.snippet ? (
          <p className="mt-3 line-clamp-5 text-[12px] leading-relaxed text-muted-foreground">
            {node.snippet}
          </p>
        ) : null}
        <div className="mt-3 flex gap-2">
          <Button size="sm" onClick={() => router.push(`/conversations/${node.id}`)}>
            Open
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => router.push(`/ask?tag=${encodeURIComponent(node.id)}`)}
          >
            Ask
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Linked conversations
        </p>
        {neighbors.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">No links at the current filter.</p>
        ) : (
          <div className="mt-2 flex flex-col gap-2">
            {neighbors.map(({ node: other, edge }) => (
              <button
                key={other.id}
                type="button"
                onClick={() => onSelect(other.id)}
                className="relative rounded-md border border-border bg-card py-2 pr-3 pl-6 text-left hover:bg-muted/50"
              >
                <ThreadFilament source={other.source} />
                <div className="flex items-start justify-between gap-2">
                  <p className="truncate text-sm">{conversationTitle(other.title)}</p>
                  <span className="shrink-0 text-[11px] text-muted-foreground">
                    {formatWeight(edge.weight)}
                  </span>
                </div>
                <p className="mt-0.5 text-[11px] text-muted-foreground">{other.source}</p>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{edge.reason}</p>
                <span
                  className="mt-2 block h-0.5 rounded-full bg-foreground/20"
                  style={{ width: `${Math.max(12, Math.min(100, edge.weight * 100))}%` }}
                />
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}

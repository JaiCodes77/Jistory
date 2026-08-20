"use client"

import { useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import { ForceGraphCanvas } from "@/components/graph/force-graph"
import { GraphInspector } from "@/components/graph/graph-inspector"
import { EmptyState } from "@/components/layout/empty-state"
import {
  DateRangeChips,
  rangeToIso,
  type MemoryRangeKey,
} from "@/components/memory/date-range-chips"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  conversationTitle,
  getMemoryGraph,
  listConversationSources,
  rebuildMemoryGraph,
} from "@/lib/api"
import { sourceSwatchClass } from "@/lib/graph-style"
import { cn } from "@/lib/utils"
import type { GraphNode, GraphResponse } from "@/types/api"

const WEIGHTS = [
  { value: 0, label: "All" },
  { value: 0.4, label: "Medium" },
  { value: 0.55, label: "Strong" },
] as const

export function GraphView() {
  const searchParams = useSearchParams()
  const focusParam = searchParams.get("focus")
  return <GraphBoard key={focusParam ?? "all"} focusParam={focusParam} />
}

function GraphBoard({ focusParam }: { focusParam: string | null }) {
  const router = useRouter()
  const [data, setData] = useState<GraphResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [rebuilding, setRebuilding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [source, setSource] = useState("")
  const [sourceOptions, setSourceOptions] = useState<string[]>(["ChatGPT", "Claude", "Cursor"])
  const [dateRange, setDateRange] = useState<MemoryRangeKey>("")
  const [customFrom, setCustomFrom] = useState("")
  const [customTo, setCustomTo] = useState("")
  const [minWeight, setMinWeight] = useState(0)
  const [includeIsolated, setIncludeIsolated] = useState(true)
  const [query, setQuery] = useState("")
  const [selectedId, setSelectedId] = useState<string | null>(focusParam)
  const [fitNonce, setFitNonce] = useState(0)
  const [inspectorOpen, setInspectorOpen] = useState(true)

  useEffect(() => {
    void listConversationSources()
      .then((response) => setSourceOptions(response.items))
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    const dates = rangeToIso(dateRange, customFrom, customTo)
    let cancelled = false
    void getMemoryGraph({
      source,
      dateFrom: dates.dateFrom,
      dateTo: dates.dateTo,
    })
      .then((response) => {
        if (!cancelled) {
          setData(response)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load the memory graph.")
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [source, dateRange, customFrom, customTo])

  const visible = useMemo(() => {
    if (!data) return { nodes: [] as GraphNode[], edges: [], isolated: 0 }
    const edges = data.edges.filter((edge) => edge.weight >= minWeight)
    const linked = new Set<string>()
    for (const edge of edges) {
      linked.add(edge.source_id)
      linked.add(edge.target_id)
    }
    const degree = new Map<string, number>()
    for (const edge of edges) {
      degree.set(edge.source_id, (degree.get(edge.source_id) ?? 0) + 1)
      degree.set(edge.target_id, (degree.get(edge.target_id) ?? 0) + 1)
    }
    const base = includeIsolated
      ? data.nodes
      : data.nodes.filter((node) => linked.has(node.id))
    const nodes = base.map((node) => ({
      ...node,
      degree: degree.get(node.id) ?? 0,
    }))
    return {
      nodes,
      edges,
      isolated: nodes.filter((node) => !linked.has(node.id)).length,
    }
  }, [data, includeIsolated, minWeight])

  const matchIds = useMemo(() => {
    const term = query.trim().toLowerCase()
    if (term.length < 2) return new Set<string>()
    return new Set(
      visible.nodes
        .filter((node) => {
          const haystack = [
            conversationTitle(node.title),
            node.snippet,
            ...(node.topics ?? []),
            node.source,
          ]
            .join(" ")
            .toLowerCase()
          return haystack.includes(term)
        })
        .map((node) => node.id)
    )
  }, [query, visible.nodes])

  const selected = visible.nodes.find((node) => node.id === selectedId) ?? null
  const sourcesInView = useMemo(() => {
    return Array.from(new Set(visible.nodes.map((node) => node.source))).sort()
  }, [visible.nodes])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const typing =
        target?.tagName === "INPUT" ||
        target?.tagName === "SELECT" ||
        target?.tagName === "TEXTAREA"
      if (typing) {
        if (event.key === "Escape") {
          if (query) setQuery("")
          target?.blur()
        }
        return
      }
      if (event.key === "Escape") setSelectedId(null)
      if (event.key === "f" || event.key === "F") setFitNonce((value) => value + 1)
      if (event.key === "i" || event.key === "I") setInspectorOpen((value) => !value)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [query])

  const rebuild = async () => {
    setRebuilding(true)
    setError(null)
    try {
      await rebuildMemoryGraph()
      const dates = rangeToIso(dateRange, customFrom, customTo)
      const response = await getMemoryGraph({
        source,
        dateFrom: dates.dateFrom,
        dateTo: dates.dateTo,
      })
      setData(response)
      setFitNonce((value) => value + 1)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not rebuild the graph.")
    } finally {
      setRebuilding(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
      <header className="shrink-0 border-b border-border/80 bg-background/50 px-4 py-2.5 backdrop-blur-md md:px-5">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== "Enter" || matchIds.size === 0) return
              const first = visible.nodes.find((node) => matchIds.has(node.id))
              if (first) setSelectedId(first.id)
            }}
            placeholder="Find a conversation"
            className="max-w-xs"
            aria-label="Find a conversation in the graph"
          />
          <select
            value={source}
            onChange={(event) => setSource(event.target.value)}
            className="h-8 w-[9.5rem] rounded-lg border border-border bg-background px-2 text-sm"
            aria-label="Filter by source"
          >
            <option value="">All sources</option>
            {sourceOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <div className="inline-flex rounded-lg border border-border p-0.5">
            {WEIGHTS.map((item) => (
              <Button
                key={item.label}
                type="button"
                size="xs"
                variant={minWeight === item.value ? "secondary" : "ghost"}
                onClick={() => setMinWeight(item.value)}
              >
                {item.label}
              </Button>
            ))}
          </div>
          <Button
            type="button"
            size="xs"
            variant={includeIsolated ? "secondary" : "outline"}
            aria-pressed={includeIsolated}
            onClick={() => setIncludeIsolated((value) => !value)}
          >
            Isolated
          </Button>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Button type="button" size="xs" variant="outline" onClick={() => setFitNonce((v) => v + 1)}>
              Fit
            </Button>
            <Button
              type="button"
              size="xs"
              variant="outline"
              onClick={() => setInspectorOpen((value) => !value)}
            >
              {inspectorOpen ? "Hide inspector" : "Inspector"}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="xs"
              disabled={rebuilding}
              onClick={() => void rebuild()}
            >
              {rebuilding ? "Rebuilding…" : "Rebuild"}
            </Button>
          </div>
        </div>
        <div className="mt-2">
          <DateRangeChips
            range={dateRange}
            customFrom={customFrom}
            customTo={customTo}
            onRangeChange={setDateRange}
            onCustomFromChange={setCustomFrom}
            onCustomToChange={setCustomTo}
          />
        </div>
        {data && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            {visible.nodes.length.toLocaleString()} conversations ·{" "}
            {visible.edges.length.toLocaleString()} links
            {visible.isolated > 0 ? ` · ${visible.isolated} isolated` : ""}
            {data.truncated ? " · showing the 600 most recently updated" : ""}
            {matchIds.size > 0 ? ` · ${matchIds.size} matches` : ""}
          </p>
        )}
      </header>

      {error && <p className="px-5 py-2 text-sm text-destructive">{error}</p>}

      {loading && (
        <div className="px-5 py-10 text-sm text-muted-foreground">Loading graph…</div>
      )}

      {!loading && data && data.nodes.length === 0 && (
        <div className="mx-auto w-full max-w-2xl px-6 py-16">
          <EmptyState
            title="Nothing to map yet"
            description="Import conversations first. The graph appears after indexing, with links for shared topics and similar content."
          />
        </div>
      )}

      {!loading && data && data.nodes.length > 0 && (
        <div className="flex min-h-0 flex-1 flex-col xl:flex-row">
          <div className="relative flex min-h-[52vh] min-w-0 flex-1 flex-col xl:min-h-0">
            <ForceGraphCanvas
              nodes={visible.nodes}
              edges={visible.edges}
              selectedId={selected?.id ?? null}
              matchIds={matchIds}
              fitNonce={fitNonce}
              onSelect={setSelectedId}
              onOpen={(id) => router.push(`/conversations/${id}`)}
            />
            {sourcesInView.length > 0 && (
              <div className="pointer-events-none absolute bottom-3 left-4 flex flex-wrap gap-2">
                {sourcesInView.map((name) => (
                  <LegendSwatch key={name} name={name} />
                ))}
              </div>
            )}
            <p className="pointer-events-none absolute bottom-3 right-4 hidden text-[11px] text-muted-foreground md:block">
              Scroll zoom · drag pan · click inspect · double-click open
            </p>
          </div>
          {inspectorOpen ? (
            <div className="max-h-[42vh] min-h-0 xl:max-h-none xl:h-full xl:w-80">
              <GraphInspector
                node={selected}
                edges={visible.edges}
                nodes={visible.nodes}
                onSelect={setSelectedId}
              />
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

function LegendSwatch({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-border/80 bg-card/80 px-2 py-1 text-[11px] text-muted-foreground backdrop-blur-md">
      <span className={cn("size-2 rounded-full", sourceSwatchClass(name))} />
      {name}
    </span>
  )
}

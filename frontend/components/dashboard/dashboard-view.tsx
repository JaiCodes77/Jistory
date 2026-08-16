"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { LoaderCircle } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { conversationTitle, formatDate, formatImportedAt, getDashboard } from "@/lib/api"
import { formatImportStatus } from "@/lib/labels"
import type { DashboardResponse } from "@/types/api"

export function DashboardView() {
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void getDashboard()
      .then(setData)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Could not load dashboard.")
      )
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-6 py-10 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" />
        Loading dashboard…
      </div>
    )
  }

  if (error) {
    return <p className="px-6 py-10 text-sm text-destructive">{error}</p>
  }

  if (!data || data.total_conversations === 0) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-3 px-6 py-16 text-center">
        <h2 className="text-lg font-medium tracking-tight">Welcome to Jistory</h2>
        <p className="text-sm text-muted-foreground">
          Import your ChatGPT history to build a searchable long-term memory of your
          conversations. Paste a share link or upload an export ZIP.
        </p>
        <Link
          href="/import"
          className="mx-auto mt-2 inline-flex h-8 items-center rounded-lg bg-primary px-2.5 text-sm font-medium text-primary-foreground"
        >
          Import conversations
        </Link>
      </div>
    )
  }

  const maxBucket = Math.max(1, ...data.conversations_over_time.map((item) => item.count))

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-8">
      <div>
        <h2 className="text-lg font-medium tracking-tight">Dashboard</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          A snapshot of your local conversation memory.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Conversations" value={data.total_conversations.toLocaleString()} />
        <Stat label="Messages" value={data.total_messages.toLocaleString()} />
        <Stat
          label="Sources"
          value={data.sources.map((item) => item.name).join(", ") || "—"}
        />
      </div>

      {data.latest_import && (
        <section className="rounded-xl border border-border bg-card px-4 py-3">
          <p className="text-xs text-muted-foreground">Most recent import</p>
          <p className="mt-1 text-sm">
            {data.latest_import.filename || data.latest_import.source} ·{" "}
            {formatImportedAt(data.latest_import.imported_at)}
          </p>
          <p className="text-xs text-muted-foreground">
            {formatImportStatus(data.latest_import.status)}
            {data.latest_import.conversations != null
              ? ` · ${data.latest_import.conversations.toLocaleString()} conversations`
              : ""}
          </p>
        </section>
      )}

      {data.conversations_over_time.length > 0 && (
        <section className="rounded-xl border border-border bg-card px-4 py-3">
          <p className="mb-3 text-xs text-muted-foreground">Conversations over time</p>
          <div className="flex h-24 items-end gap-px">
            {data.conversations_over_time.map((bucket) => (
              <div
                key={bucket.date}
                title={`${bucket.date}: ${bucket.count}`}
                className="flex-1 rounded-sm bg-foreground/70"
                style={{ height: `${Math.max(8, (bucket.count / maxBucket) * 100)}%` }}
              />
            ))}
          </div>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <p className="mb-2 text-xs text-muted-foreground">Recent conversations</p>
          <div className="flex flex-col gap-2">
            {data.recent_conversations.map((item) => (
              <Link
                key={item.id}
                href={`/conversations/${item.id}`}
                className="rounded-xl border border-border px-3 py-2 hover:bg-muted/40"
              >
                <p className="truncate text-sm">{conversationTitle(item.title)}</p>
                <p className="text-[11px] text-muted-foreground">
                  {item.source} · {formatDate(item.updated_at)} · {item.message_count} messages
                </p>
              </Link>
            ))}
          </div>
        </section>
        <section>
          <p className="mb-2 text-xs text-muted-foreground">Frequently discussed</p>
          {data.frequent_topics.length === 0 ? (
            <p className="text-sm text-muted-foreground">Not enough titles to extract topics yet.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {data.frequent_topics.map((topic) => (
                <Badge key={topic.term} variant="outline">
                  {topic.term} · {topic.count}
                </Badge>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-card px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-medium tracking-tight">{value}</p>
    </div>
  )
}

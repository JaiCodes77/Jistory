"use client"

import Link from "next/link"
import { useEffect, useState } from "react"

import { ForgetButton } from "@/components/conversations/forget-button"
import { EmptyState } from "@/components/layout/empty-state"
import { Badge } from "@/components/ui/badge"
import {
  conversationTitle,
  forgetImportJob,
  formatDate,
  formatDayLabel,
  formatImportedAt,
  getDashboard,
} from "@/lib/api"
import { formatImportStatus } from "@/lib/labels"
import type { DashboardResponse } from "@/types/api"

const TOPIC_MIN_COUNT = 2

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
      <div className="px-6 py-10 text-sm text-muted-foreground">Loading dashboard…</div>
    )
  }

  if (error) {
    return <p className="px-6 py-10 text-sm text-destructive">{error}</p>
  }

  if (!data || data.total_conversations === 0) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-3 px-6 py-16">
        <EmptyState
          title="Welcome to Jistory"
          description="Import a ChatGPT share link or export ZIP to build a searchable long-term memory. Then open Ask and type @ to scope a question to a chat."
        />
      </div>
    )
  }

  const topics = data.frequent_topics.filter((topic) => topic.count >= TOPIC_MIN_COUNT)
  const sourceLabel =
    data.sources.length === 0
      ? "—"
      : data.sources.map((item) => `${item.name} (${item.count})`).join(", ")

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-6 py-8">
      <div>
        <h2 className="text-lg font-medium tracking-tight">Dashboard</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          A snapshot of your local conversation memory.
        </p>
      </div>

      <section className="flex flex-col gap-3">
        <div>
          <h3 className="text-sm font-medium">Overview</h3>
          <p className="text-xs text-muted-foreground">
            Counts from conversations stored on this machine.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="Conversations" value={data.total_conversations.toLocaleString()} />
          <Stat label="Messages" value={data.total_messages.toLocaleString()} />
          <Stat label="Sources" value={sourceLabel} />
        </div>
      </section>

      {data.latest_import && (
        <section className="rounded-xl border border-border bg-card px-4 py-3">
          <h3 className="text-sm font-medium">Most recent import</h3>
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
          <div className="mt-3">
            <ForgetButton
              label="Forget this import"
              confirmCopy="This permanently deletes this import and every conversation, message, and embedding that came from it."
              onConfirm={async () => {
                await forgetImportJob(data.latest_import!.id)
                const next = await getDashboard()
                setData(next)
              }}
            />
          </div>
        </section>
      )}

      {data.conversations_over_time.length > 0 && (
        <ConversationsChart buckets={data.conversations_over_time} />
      )}

      <div className="grid gap-8 lg:grid-cols-2">
        <section className="min-w-0">
          <div className="mb-3">
            <h3 className="text-sm font-medium">Recent conversations</h3>
            <p className="text-xs text-muted-foreground">Newest activity first.</p>
          </div>
          {data.recent_conversations.length === 0 ? (
            <p className="text-sm text-muted-foreground">No recent conversations to show.</p>
          ) : (
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
          )}
        </section>
        <section className="min-w-0">
          <div className="mb-3">
            <h3 className="text-sm font-medium">Frequently discussed</h3>
            <p className="text-xs text-muted-foreground">
              Words that appear in more than one conversation title.
            </p>
          </div>
          {topics.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No repeated title words yet. With only a couple of chats this stays quiet
              on purpose — topics appear when imported titles share the same word.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {topics.map((topic) => (
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

function ConversationsChart({
  buckets,
}: {
  buckets: { date: string; count: number }[]
}) {
  const [active, setActive] = useState<string | null>(null)
  const maxBucket = Math.max(1, ...buckets.map((item) => item.count))
  const activeBucket = buckets.find((item) => item.date === active)

  return (
    <section className="overflow-visible rounded-xl border border-border bg-card px-4 py-3">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium">Conversations over time</h3>
          <p className="text-xs text-muted-foreground">One bar per day. Empty days are short ticks.</p>
        </div>
        <p className="min-h-4 text-[11px] tabular-nums text-foreground/70">
          {activeBucket
            ? `${formatDayLabel(activeBucket.date, "full")} · ${activeBucket.count} conversation${
                activeBucket.count === 1 ? "" : "s"
              }`
            : "Hover or focus a day for the count"}
        </p>
      </div>
      <div
        className="flex h-24 items-stretch gap-px overflow-visible"
        role="list"
        onMouseLeave={() => setActive(null)}
      >
        {buckets.map((bucket) => (
          <button
            key={bucket.date}
            type="button"
            role="listitem"
            aria-label={`${formatDayLabel(bucket.date, "full")}: ${bucket.count} conversation${
              bucket.count === 1 ? "" : "s"
            }`}
            aria-pressed={active === bucket.date}
            className="relative flex min-w-px flex-1 items-end rounded-sm outline-none hover:bg-foreground/5 focus-visible:bg-foreground/10"
            onMouseEnter={() => setActive(bucket.date)}
            onFocus={() => setActive(bucket.date)}
          >
            <span
              className={
                bucket.count === 0
                  ? "min-w-px w-full rounded-sm bg-foreground/20"
                  : "min-w-px w-full rounded-sm bg-foreground/80"
              }
              style={{
                height:
                  bucket.count === 0
                    ? "3px"
                    : `${Math.max(12, (bucket.count / maxBucket) * 100)}%`,
              }}
            />
          </button>
        ))}
      </div>
      <div className="mt-2 flex justify-between gap-3 overflow-visible pt-0.5 text-[11px] leading-4 text-foreground/65">
        <span className="shrink-0 whitespace-nowrap">{formatDayLabel(buckets[0]?.date)}</span>
        <span className="shrink-0 whitespace-nowrap">
          {formatDayLabel(buckets[buckets.length - 1]?.date)}
        </span>
      </div>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-card px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 truncate text-2xl font-medium tracking-tight" title={value}>
        {value}
      </p>
    </div>
  )
}

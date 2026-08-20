import Link from "next/link"

type EmptyStateProps = {
  title: string
  description: string
  actionHref?: string
  actionLabel?: string
}

export function EmptyState({
  title,
  description,
  actionHref = "/import",
  actionLabel = "Import conversations",
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border bg-card/40 px-6 py-16 text-center">
      <span className="flex size-8 items-center justify-center rounded-lg bg-foreground text-xs font-semibold text-background">
        J
      </span>
      <p className="text-sm font-medium">{title}</p>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground">{description}</p>
      <Link
        href={actionHref}
        className="inline-flex h-8 items-center rounded-lg bg-primary px-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/80"
      >
        {actionLabel}
      </Link>
    </div>
  )
}

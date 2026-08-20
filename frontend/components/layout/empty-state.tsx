import Link from "next/link"

import { BrandLogo } from "@/components/layout/brand-logo"

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
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border bg-card/40 px-6 py-16 text-center backdrop-blur-md">
      <BrandLogo size={44} alt="Jistory" />
      <p className="text-sm font-medium tracking-tight">{title}</p>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground">{description}</p>
      <Link
        href={actionHref}
        className="inline-flex h-8 items-center rounded-lg bg-primary px-2.5 text-sm font-medium text-primary-foreground shadow-[0_0_24px_-8px_var(--primary)] hover:bg-primary/90"
      >
        {actionLabel}
      </Link>
    </div>
  )
}

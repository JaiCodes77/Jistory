import Link from "next/link"

import { BrandLogo } from "@/components/layout/brand-logo"
import { buttonVariants } from "@/components/ui/button"

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
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border bg-card px-6 py-16 text-center">
      <BrandLogo size={44} alt="Jistory" />
      <p className="font-heading text-base tracking-tight">{title}</p>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground">{description}</p>
      <Link href={actionHref} className={buttonVariants()}>
        {actionLabel}
      </Link>
    </div>
  )
}

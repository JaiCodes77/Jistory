"use client"

import { usePathname } from "next/navigation"

import { getPageTitle } from "@/lib/navigation"

export function TopNav() {
  const pathname = usePathname()
  const title = getPageTitle(pathname)

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-background px-5">
      <div className="flex items-center gap-2">
        <h1 className="text-sm font-medium tracking-tight">{title}</h1>
      </div>
      <div className="flex items-center gap-2">
        <span className="rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground">
          Local
        </span>
      </div>
    </header>
  )
}

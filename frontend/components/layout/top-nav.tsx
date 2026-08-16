"use client"

import { usePathname } from "next/navigation"
import { Search } from "lucide-react"

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
        <button
          type="button"
          onClick={() => window.dispatchEvent(new Event("jistory:open-search"))}
          className="hidden items-center gap-2 rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted sm:inline-flex"
        >
          <Search className="size-3" />
          Search
          <kbd className="rounded border border-border px-1">⌘K</kbd>
        </button>
        <span className="rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground">
          Local
        </span>
      </div>
    </header>
  )
}

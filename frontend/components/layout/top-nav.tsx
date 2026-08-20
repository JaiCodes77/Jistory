"use client"

import { usePathname } from "next/navigation"
import { Menu, Search, X } from "lucide-react"

import { ThemeToggle } from "@/components/layout/theme-toggle"
import { Button } from "@/components/ui/button"
import { getPageTitle } from "@/lib/navigation"

type TopNavProps = {
  mobileNavOpen?: boolean
  onMenuClick?: () => void
}

export function TopNav({ mobileNavOpen = false, onMenuClick }: TopNavProps) {
  const pathname = usePathname()
  const title = getPageTitle(pathname)

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-background px-5">
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="md:hidden"
          onClick={onMenuClick}
          aria-label={mobileNavOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={mobileNavOpen}
          aria-controls="jistory-sidebar"
        >
          {mobileNavOpen ? <X /> : <Menu />}
        </Button>
        <h1 className="text-sm font-medium tracking-tight">{title}</h1>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => window.dispatchEvent(new Event("jistory:open-search"))}
          className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <Search className="size-3" />
          Search
          <kbd className="rounded border border-border px-1">⌘K</kbd>
        </button>
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-2 py-1 text-[11px] text-muted-foreground">
          <span className="size-1.5 rounded-full bg-foreground/70" />
          Local
        </span>
        <ThemeToggle />
      </div>
    </header>
  )
}

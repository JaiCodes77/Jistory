"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

import { ScrollArea } from "@/components/ui/scroll-area"
import { mainNav } from "@/lib/navigation"
import { cn } from "@/lib/utils"

type SidebarProps = {
  mobileOpen?: boolean
  onNavigate?: () => void
}

export function Sidebar({ mobileOpen = false, onNavigate }: SidebarProps) {
  const pathname = usePathname()

  return (
    <aside
      id="jistory-sidebar"
      className={cn(
        "flex h-full w-56 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground",
        "max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-50",
        !mobileOpen && "max-md:hidden"
      )}
    >
      <Link
        href="/"
        onClick={onNavigate}
        className="flex h-12 items-center gap-2.5 px-4 hover:bg-sidebar-accent/50"
      >
        <span className="flex size-6 items-center justify-center rounded-md bg-foreground text-[11px] font-semibold text-background">
          J
        </span>
        <span className="text-sm font-medium tracking-tight">Jistory</span>
      </Link>

      <ScrollArea className="flex-1 px-2 py-2">
        <nav className="flex flex-col gap-0.5">
          {mainNav.map((item) => {
            const Icon = item.icon
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname === item.href || pathname.startsWith(`${item.href}/`)

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                className={cn(
                  "relative flex h-8 items-center gap-2 rounded-md px-2 text-[13px] transition-colors",
                  isActive
                    ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground"
                )}
                aria-current={isActive ? "page" : undefined}
              >
                {isActive ? (
                  <span className="absolute inset-y-1.5 left-0 w-px rounded-full bg-foreground" />
                ) : null}
                <Icon className="size-4 shrink-0 opacity-70" />
                <span className="truncate">{item.title}</span>
                {item.href === "/search" && (
                  <kbd className="ml-auto rounded border border-border px-1 text-[10px] font-normal text-muted-foreground">
                    ⌘K
                  </kbd>
                )}
              </Link>
            )
          })}
        </nav>
      </ScrollArea>

      <div className="border-t border-sidebar-border px-4 py-3">
        <p className="text-[11px] text-muted-foreground">Stays on this machine</p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          <kbd className="rounded border border-border px-1">/</kbd>
          {" or "}
          <kbd className="rounded border border-border px-1">⌘K</kbd>
          {" to search"}
        </p>
      </div>
    </aside>
  )
}

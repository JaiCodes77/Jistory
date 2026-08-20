"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

import { BrandLogo } from "@/components/layout/brand-logo"
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
        "flex h-full w-56 shrink-0 flex-col border-r border-sidebar-border bg-sidebar/90 text-sidebar-foreground backdrop-blur-xl",
        "max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-50",
        !mobileOpen && "max-md:hidden"
      )}
    >
      <Link
        href="/"
        onClick={onNavigate}
        className="flex h-14 items-center gap-2.5 px-3.5 hover:bg-sidebar-accent/40"
      >
        <BrandLogo size={32} />
        <span className="text-[13px] font-medium tracking-[0.04em]">Jistory</span>
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
                  "relative flex h-8 items-center gap-2 rounded-lg px-2 text-[13px] transition-colors",
                  isActive
                    ? "bg-primary/12 font-medium text-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground"
                )}
                aria-current={isActive ? "page" : undefined}
              >
                {isActive ? (
                  <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-brand-gradient" />
                ) : null}
                <Icon className="size-4 shrink-0 opacity-70" />
                <span className="truncate">{item.title}</span>
                {item.href === "/search" && (
                  <kbd className="ml-auto rounded-md border border-border/80 px-1 font-mono text-[10px] font-normal text-muted-foreground">
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
          <kbd className="rounded-md border border-border/80 px-1 font-mono">/</kbd>
          {" or "}
          <kbd className="rounded-md border border-border/80 px-1 font-mono">⌘K</kbd>
          {" to search"}
        </p>
      </div>
    </aside>
  )
}

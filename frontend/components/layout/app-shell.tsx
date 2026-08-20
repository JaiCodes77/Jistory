"use client"

import { useEffect, useState } from "react"
import { usePathname } from "next/navigation"

import { Sidebar } from "@/components/layout/sidebar"
import { TopNav } from "@/components/layout/top-nav"
import { cn } from "@/lib/utils"

type AppShellProps = {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname()
  const fillViewport = pathname.startsWith("/graph")
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  useEffect(() => {
    const media = window.matchMedia("(min-width: 768px)")
    const onChange = (event: MediaQueryListEvent) => {
      if (event.matches) {
        setMobileNavOpen(false)
      }
    }
    media.addEventListener("change", onChange)
    return () => media.removeEventListener("change", onChange)
  }, [])

  useEffect(() => {
    if (!mobileNavOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileNavOpen(false)
    }
    window.addEventListener("keydown", onKeyDown)
    const previous = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      window.removeEventListener("keydown", onKeyDown)
      document.body.style.overflow = previous
    }
  }, [mobileNavOpen])

  return (
    <div className="relative flex h-screen overflow-hidden bg-background text-foreground">
      <Sidebar
        mobileOpen={mobileNavOpen}
        onNavigate={() => setMobileNavOpen(false)}
      />
      {mobileNavOpen ? (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-background/70 md:hidden"
          aria-label="Close navigation"
          onClick={() => setMobileNavOpen(false)}
        />
      ) : null}
      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
        <TopNav
          mobileNavOpen={mobileNavOpen}
          onMenuClick={() => setMobileNavOpen((open) => !open)}
        />
        <main
          className={cn(
            "flex min-h-0 flex-1 flex-col",
            fillViewport ? "overflow-hidden" : "overflow-auto"
          )}
        >
          {children}
        </main>
      </div>
    </div>
  )
}

"use client"

import { useSyncExternalStore } from "react"
import { Moon, Sun } from "lucide-react"

import { Button } from "@/components/ui/button"
import { applyTheme, getStoredTheme, subscribeTheme, type Theme } from "@/lib/theme"

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeTheme, getStoredTheme, () => "dark")

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark"
    applyTheme(next)
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      onClick={toggle}
      aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
    >
      {theme === "dark" ? <Sun /> : <Moon />}
    </Button>
  )
}

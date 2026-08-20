import {
  LayoutDashboard,
  MessageSquareText,
  Network,
  Search,
  Settings,
  Sparkles,
  Upload,
} from "lucide-react"

import type { NavItem } from "@/types/navigation"

export const mainNav: NavItem[] = [
  {
    title: "Dashboard",
    href: "/",
    icon: LayoutDashboard,
  },
  {
    title: "Import",
    href: "/import",
    icon: Upload,
  },
  {
    title: "Conversations",
    href: "/conversations",
    icon: MessageSquareText,
  },
  {
    title: "Graph",
    href: "/graph",
    icon: Network,
  },
  {
    title: "Search",
    href: "/search",
    icon: Search,
  },
  {
    title: "Ask Jistory",
    href: "/ask",
    icon: Sparkles,
  },
  {
    title: "Settings",
    href: "/settings",
    icon: Settings,
  },
]

export function getPageTitle(pathname: string): string {
  if (pathname.startsWith("/search")) return "Search"
  if (pathname.startsWith("/graph")) return "Graph"
  if (pathname.startsWith("/conversations/") && pathname !== "/conversations") {
    return "Conversation"
  }

  const exact = mainNav.find((item) => item.href === pathname)
  if (exact) return exact.title

  const nested = mainNav.find(
    (item) => item.href !== "/" && pathname.startsWith(item.href)
  )
  return nested?.title ?? "Jistory"
}

import { AppShell } from "@/components/layout/app-shell"
import { CommandSearch } from "@/components/search/command-search"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <AppShell>
      <CommandSearch />
      {children}
    </AppShell>
  )
}

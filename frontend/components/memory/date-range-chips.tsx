"use client"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

export const MEMORY_RANGES = [
  { value: "", label: "All time" },
  { value: "last_7_days", label: "Last 7 days" },
  { value: "last_30_days", label: "Last 30 days" },
  { value: "last_90_days", label: "Last 90 days" },
  { value: "custom", label: "Custom" },
] as const

export type MemoryRangeKey = (typeof MEMORY_RANGES)[number]["value"]

export function rangeToIso(
  key: MemoryRangeKey,
  customFrom: string,
  customTo: string
): { dateFrom?: string; dateTo?: string } {
  if (!key) return {}
  if (key === "custom") {
    return {
      dateFrom: customFrom ? `${customFrom}T00:00:00.000Z` : undefined,
      dateTo: customTo ? `${customTo}T23:59:59.999Z` : undefined,
    }
  }
  const days = key === "last_7_days" ? 7 : key === "last_30_days" ? 30 : 90
  const to = new Date()
  const from = new Date(to.getTime() - days * 24 * 60 * 60 * 1000)
  return { dateFrom: from.toISOString(), dateTo: to.toISOString() }
}

export function DateRangeChips({
  range,
  customFrom,
  customTo,
  onRangeChange,
  onCustomFromChange,
  onCustomToChange,
}: {
  range: MemoryRangeKey
  customFrom: string
  customTo: string
  onRangeChange: (value: MemoryRangeKey) => void
  onCustomFromChange: (value: string) => void
  onCustomToChange: (value: string) => void
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        {MEMORY_RANGES.map((item) => (
          <Button
            key={item.value || "all"}
            type="button"
            size="xs"
            variant={range === item.value ? "secondary" : "outline"}
            className={cn(range === item.value && "border-border")}
            onClick={() => onRangeChange(item.value)}
          >
            {item.label}
          </Button>
        ))}
      </div>
      {range === "custom" && (
        <div className="grid gap-2 sm:grid-cols-2">
          <Input
            type="date"
            value={customFrom}
            onChange={(event) => onCustomFromChange(event.target.value)}
            aria-label="From date"
          />
          <Input
            type="date"
            value={customTo}
            onChange={(event) => onCustomToChange(event.target.value)}
            aria-label="To date"
          />
        </div>
      )}
    </div>
  )
}

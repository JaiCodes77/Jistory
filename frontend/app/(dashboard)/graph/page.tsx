import { Suspense } from "react"

import { GraphView } from "@/components/graph/graph-view"

export default function GraphPage() {
  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
      <Suspense
        fallback={
          <div className="px-6 py-10 text-sm text-muted-foreground">Loading graph…</div>
        }
      >
        <GraphView />
      </Suspense>
    </div>
  )
}

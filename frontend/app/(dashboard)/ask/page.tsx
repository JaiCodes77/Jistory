import { Suspense } from "react"

import { AskChat } from "@/components/ask/ask-chat"

export default function AskPage() {
  return (
    <Suspense
      fallback={
        <div className="px-6 py-10 text-sm text-muted-foreground">Loading Ask…</div>
      }
    >
      <AskChat />
    </Suspense>
  )
}

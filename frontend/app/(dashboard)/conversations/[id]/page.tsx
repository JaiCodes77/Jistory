import { Suspense } from "react"

import { ConversationThread } from "@/components/conversations/conversation-thread"

export default async function ConversationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  return (
    <Suspense
      fallback={
        <div className="px-6 py-10 text-sm text-muted-foreground">
          Loading conversation…
        </div>
      }
    >
      <ConversationThread conversationId={id} />
    </Suspense>
  )
}

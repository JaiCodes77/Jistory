"use client"

import { useState } from "react"

import { MessageMarkdown } from "@/components/markdown/message-markdown"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const LONG_CHAR_THRESHOLD = 1200
const LONG_LINE_THRESHOLD = 28

function isLongContent(content: string): boolean {
  if (content.length > LONG_CHAR_THRESHOLD) return true
  return content.split("\n").length > LONG_LINE_THRESHOLD
}

export function ExpandableMessage({
  content,
  defaultExpanded = false,
}: {
  content: string
  defaultExpanded?: boolean
}) {
  const long = isLongContent(content)
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [forced, setForced] = useState(defaultExpanded)
  if (defaultExpanded !== forced) {
    setForced(defaultExpanded)
    if (defaultExpanded) setExpanded(true)
  }
  const collapsed = long && !expanded

  return (
    <div>
      <div
        className={cn(
          collapsed &&
            "max-h-[18rem] overflow-hidden [mask-image:linear-gradient(to_bottom,black_calc(100%-3.5rem),transparent)] [-webkit-mask-image:linear-gradient(to_bottom,black_calc(100%-3.5rem),transparent)]"
        )}
      >
        {content ? (
          <MessageMarkdown content={content} />
        ) : (
          <p className="text-sm leading-6">(no text)</p>
        )}
      </div>
      {long && (
        <Button
          type="button"
          variant="ghost"
          size="xs"
          className="mt-2 text-muted-foreground"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Show less" : "Show more"}
        </Button>
      )}
    </div>
  )
}

"use client"

import { useState } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function ForgetButton({
  label = "Forget",
  confirmCopy,
  pendingLabel = "Forgetting…",
  disabled = false,
  className,
  onConfirm,
}: {
  label?: string
  confirmCopy: string
  pendingLabel?: string
  disabled?: boolean
  className?: string
  onConfirm: () => Promise<void> | void
}) {
  const [confirming, setConfirming] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (confirming) {
    return (
      <div className={cn("flex max-w-md flex-col gap-2", className)}>
        <p className="text-xs leading-5 text-muted-foreground">{confirmCopy}</p>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="destructive"
            size="xs"
            disabled={pending || disabled}
            onClick={() => {
              setPending(true)
              setError(null)
              void Promise.resolve(onConfirm())
                .catch((err: unknown) => {
                  setError(err instanceof Error ? err.message : "Could not forget this.")
                  setPending(false)
                })
                .then(() => {
                  setPending(false)
                })
            }}
          >
            {pending ? pendingLabel : "Forget permanently"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            disabled={pending}
            onClick={() => {
              setConfirming(false)
              setError(null)
            }}
          >
            Cancel
          </Button>
        </div>
      </div>
    )
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="xs"
      disabled={disabled}
      className={cn("text-muted-foreground", className)}
      onClick={(event) => {
        event.preventDefault()
        event.stopPropagation()
        setConfirming(true)
      }}
    >
      {label}
    </Button>
  )
}

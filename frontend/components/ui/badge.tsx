import * as React from "react"

import { cn } from "@/lib/utils"

function Badge({
  className,
  variant = "default",
  ...props
}: React.ComponentProps<"span"> & { variant?: "default" | "outline" | "muted" }) {
  return (
    <span
      data-slot="badge"
      className={cn(
        "inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-medium",
        variant === "default" && "border-transparent bg-muted text-foreground",
        variant === "outline" && "border-border text-muted-foreground",
        variant === "muted" && "border-transparent bg-muted/60 text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

export { Badge }

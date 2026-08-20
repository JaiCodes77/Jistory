import { filamentClass } from "@/lib/graph-style"
import { cn } from "@/lib/utils"

type ThreadFilamentProps = {
  source?: string
  className?: string
  animate?: boolean
}

export function ThreadFilament({
  source,
  className,
  animate = false,
}: ThreadFilamentProps) {
  const tone = filamentClass(source)

  return (
    <span
      aria-hidden
      className={cn(
        "pointer-events-none absolute top-2 bottom-2 left-0 w-3",
        className
      )}
    >
      <span className={cn("absolute top-0 left-[5px] size-1.5 rounded-full", tone)} />
      <span
        className={cn(
          "absolute top-1.5 bottom-0 left-[7px] w-px origin-top",
          tone,
          animate && "filament-draw"
        )}
      />
    </span>
  )
}

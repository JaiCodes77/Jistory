import { cn } from "@/lib/utils"

type BrandLogoProps = {
  size?: number
  className?: string
  alt?: string
}

export function BrandLogo({ size = 28, className, alt = "" }: BrandLogoProps) {
  return (
    <span
      className={cn(
        "relative inline-flex shrink-0 overflow-hidden rounded-full bg-[#0e1418] ring-1 ring-border",
        className
      )}
      style={{ width: size, height: size }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/logo.png"
        alt={alt}
        width={size}
        height={size}
        className="size-full object-cover"
        aria-hidden={alt ? undefined : true}
      />
    </span>
  )
}

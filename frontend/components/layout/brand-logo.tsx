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
        "relative inline-flex shrink-0 overflow-hidden rounded-full bg-[#0b0e14] shadow-[0_0_18px_-6px_color-mix(in_oklch,var(--brand-cyan)_70%,var(--brand-gold))]",
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

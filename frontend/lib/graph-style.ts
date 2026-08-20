export const SOURCE_HUES: Record<string, number> = {
  ChatGPT: 205,
  Claude: 48,
  Cursor: 172,
}

export const SOURCE_SWATCH: Record<string, string> = {
  ChatGPT: "bg-[hsl(205_58%_40%)] dark:bg-[hsl(198_62%_68%)]",
  Claude: "bg-[hsl(48_62%_40%)] dark:bg-[hsl(42_72%_62%)]",
  Cursor: "bg-[hsl(172_48%_36%)] dark:bg-[hsl(172_52%_62%)]",
}

export function sourceHue(source: string): number {
  return SOURCE_HUES[source] ?? Math.abs(hashString(source)) % 360
}

export function sourceFill(source: string, dark: boolean): string {
  const hue = sourceHue(source)
  return dark ? `hsl(${hue} 54% 64%)` : `hsl(${hue} 52% 40%)`
}

export function sourceRing(source: string, dark: boolean): string {
  const hue = sourceHue(source)
  return dark ? `hsl(${hue} 46% 78%)` : `hsl(${hue} 50% 32%)`
}

export function sourceSwatchClass(source: string): string {
  return SOURCE_SWATCH[source] ?? "bg-foreground/70"
}

export function nodeRadius(messageCount: number, degree = 0): number {
  return 6 + Math.min(7, Math.log2(Math.max(messageCount, 1))) + Math.min(3, degree * 0.35)
}

export function formatWeight(weight: number): string {
  return `${Math.round(Math.max(0, Math.min(1, weight)) * 100)}%`
}

export function hashString(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) | 0
  }
  return hash
}

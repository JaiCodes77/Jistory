export const SOURCE_HUES: Record<string, number> = {
  ChatGPT: 176,
  Claude: 42,
  Cursor: 24,
}

export const SOURCE_SWATCH: Record<string, string> = {
  ChatGPT: "bg-brand-cyan",
  Claude: "bg-brand-gold",
  Cursor: "bg-brand-orange",
}

const SOURCE_FILL_DARK: Record<string, string> = {
  ChatGPT: "#2BB8B0",
  Claude: "#E0B14A",
  Cursor: "#E07A3D",
}

const SOURCE_FILL_LIGHT: Record<string, string> = {
  ChatGPT: "#1A8A86",
  Claude: "#A87A1A",
  Cursor: "#C45E28",
}

export function filamentClass(source?: string): string {
  if (!source) return "bg-primary"
  return SOURCE_SWATCH[source] ?? "bg-primary"
}

export function sourceHue(source: string): number {
  return SOURCE_HUES[source] ?? Math.abs(hashString(source)) % 360
}

export function sourceFill(source: string, dark: boolean): string {
  const named = dark ? SOURCE_FILL_DARK[source] : SOURCE_FILL_LIGHT[source]
  if (named) return named
  const hue = sourceHue(source)
  return dark ? `hsl(${hue} 42% 62%)` : `hsl(${hue} 48% 38%)`
}

export function sourceRing(source: string, dark: boolean): string {
  return sourceFill(source, dark)
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

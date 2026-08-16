export const MAX_TAGGED_CONVERSATIONS = 8

export type MentionQuery = {
  start: number
  end: number
  query: string
}

export function getActiveMention(
  value: string,
  caret: number
): MentionQuery | null {
  if (caret < 0 || caret > value.length) return null
  const before = value.slice(0, caret)
  const at = before.lastIndexOf("@")
  if (at < 0) return null
  if (at > 0 && !/\s/.test(before.charAt(at - 1))) return null
  const query = before.slice(at + 1)
  if (query.includes("\n") || query.length > 80) return null
  return { start: at, end: caret, query }
}

export function removeActiveMention(value: string, mention: MentionQuery): string {
  const left = value.slice(0, mention.start)
  const right = value.slice(mention.end)
  if (!left) return right.replace(/^\s+/, "")
  if (!right) return left.replace(/\s+$/, "")
  const leftPart = left.endsWith(" ") ? left : `${left} `
  return `${leftPart}${right.replace(/^\s+/, "")}`
}

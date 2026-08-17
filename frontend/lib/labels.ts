export function formatImportStatus(status: string | null | undefined): string {
  switch (status) {
    case "uploaded":
      return "Uploaded"
    case "processing":
      return "Parsing"
    case "parsed":
      return "Parsed — keyword search ready"
    case "indexing":
      return "Indexing embeddings"
    case "ready":
    case "completed":
      return "Ready"
    case "failed":
      return "Failed"
    case "pending":
      return "Pending"
    default:
      return status ? status.replaceAll("_", " ") : "—"
  }
}

export function formatRole(role: string | null | undefined): string {
  switch (role) {
    case "user":
      return "You"
    case "assistant":
      return "Assistant"
    case "system":
      return "System"
    case "tool":
      return "Tool"
    default:
      return role || "Message"
  }
}

export function formatEmbeddingStatus(status: string | null | undefined): string {
  switch (status) {
    case "downloading":
      return "Downloading embedding model"
    case "ready":
      return "Embedding model ready"
    case "unavailable":
      return "Embeddings unavailable"
    case "hash":
      return "Test embeddings"
    default:
      return "Embedding model idle"
  }
}

export function importNextStep(
  kind: "upload" | "parse" | "index" | "share",
  message?: string | null
): string {
  const text = (message || "").toLowerCase()
  if (text.includes("unavailable") || text.includes("port 8000")) {
    return "Start the Jistory backend, then retry."
  }
  if (kind === "share") {
    return "Paste a public chatgpt.com/share/… or claude.ai/share/… link, or upload an export ZIP instead."
  }
  if (kind === "upload") {
    return "Choose a ChatGPT or Claude export .zip, then try again."
  }
  if (kind === "parse") {
    return "The file is already saved locally. Retry parse to continue."
  }
  return "Keyword search may already work. Open Conversations, or retry parse to re-index embeddings."
}

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

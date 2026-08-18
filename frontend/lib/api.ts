import type {
  AskSessionDetail,
  AskSessionSummary,
  ConversationFilters,
  ConversationListResponse,
  ConversationSummary,
  DashboardResponse,
  MessageListResponse,
  SearchResponse,
  SourceReference,
  UserSettings,
} from "@/types/api"
import type {
  ImportJobError,
  ImportJobSuccess,
  ImportStatusResponse,
  ParseJobSuccess,
} from "@/types/import"

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api"

export function getApiUrl(path: string = ""): string {
  const normalized = path.startsWith("/") ? path : `/${path}`
  return `${API_BASE_URL}${normalized === "/" ? "" : normalized}`
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B"
  const units = ["B", "KB", "MB", "GB"]
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1
  )
  const value = bytes / 1024 ** index
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

export function formatImportedAt(value: string | null | undefined): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date)
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—"
  const date = parseDateValue(value)
  if (!date) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date)
}

export function formatDayLabel(
  value: string | null | undefined,
  style: "short" | "full" = "short"
): string {
  if (!value) return "—"
  const date = parseDateValue(value)
  if (!date) return value
  return new Intl.DateTimeFormat(
    undefined,
    style === "full"
      ? { month: "short", day: "numeric", year: "numeric" }
      : { month: "short", day: "numeric" }
  ).format(date)
}

function parseDateValue(value: string): Date | null {
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  const date = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function conversationTitle(title: string | null | undefined): string {
  const trimmed = title?.trim()
  return trimmed ? trimmed : "Untitled conversation"
}

type UploadExportOptions = {
  file: File
  source?: "chatgpt" | "claude"
  onProgress?: (percent: number) => void
  signal?: AbortSignal
}

export function uploadChatGPTExport(
  options: Omit<UploadExportOptions, "source">
): Promise<ImportJobSuccess> {
  return uploadExport({ ...options, source: "chatgpt" })
}

export function uploadExport({
  file,
  source = "chatgpt",
  onProgress,
  signal,
}: UploadExportOptions): Promise<ImportJobSuccess> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const formData = new FormData()
    formData.append("file", file)
    const path = source === "claude" ? "/import/claude" : "/import/chatgpt"

    xhr.open("POST", getApiUrl(path))

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      const percent = Math.round((event.loaded / event.total) * 100)
      onProgress?.(percent)
    }

    xhr.onload = () => {
      let payload: unknown
      try {
        payload = JSON.parse(xhr.responseText)
      } catch {
        reject(
          new Error(
            xhr.status === 0
              ? "Server unavailable. Is the Jistory backend running?"
              : "Received an invalid response from the server."
          )
        )
        return
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as ImportJobSuccess)
        return
      }

      const errorPayload = payload as ImportJobError
      reject(
        new Error(
          errorPayload?.error ||
            mapStatusToMessage(xhr.status) ||
            "Upload failed."
        )
      )
    }

    xhr.onerror = () => {
      reject(
        new Error(
          "Server unavailable. Check that the backend is running on port 8000."
        )
      )
    }

    xhr.onabort = () => {
      reject(new Error("Upload was cancelled."))
    }

    if (signal) {
      if (signal.aborted) {
        xhr.abort()
        return
      }
      signal.addEventListener("abort", () => xhr.abort(), { once: true })
    }

    xhr.send(formData)
  })
}

export async function parseImportJob(importId: string): Promise<ParseJobSuccess> {
  return apiFetch<ParseJobSuccess>(`/import/${importId}/parse`, { method: "POST" })
}

export function detectShareSource(url: string): "chatgpt" | "claude" {
  const text = url.trim().toLowerCase()
  if (text.includes("claude.ai")) return "claude"
  return "chatgpt"
}

export async function importChatGPTShare(url: string): Promise<ParseJobSuccess> {
  return importShareLink(url)
}

export async function importShareLink(url: string): Promise<ParseJobSuccess> {
  const path =
    detectShareSource(url) === "claude"
      ? "/import/claude/share"
      : "/import/chatgpt/share"
  return apiFetch<ParseJobSuccess>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  })
}

export async function importCursorFromPath(path?: string): Promise<ParseJobSuccess> {
  return apiFetch<ParseJobSuccess>("/import/cursor", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: path?.trim() ? path.trim() : null }),
  })
}

export async function importCursorFile(file: File): Promise<ParseJobSuccess> {
  const formData = new FormData()
  formData.append("file", file)
  return apiFetch<ParseJobSuccess>("/import/cursor/upload", {
    method: "POST",
    body: formData,
  })
}

export async function getImportJob(importId: string): Promise<ImportStatusResponse> {
  return apiFetch<ImportStatusResponse>(`/import/${importId}`)
}

export async function listConversationSources(): Promise<{
  items: string[]
  available: string[]
}> {
  return apiFetch<{ items: string[]; available: string[] }>("/conversations/sources")
}

export async function listConversations(
  filters: Partial<ConversationFilters>
): Promise<ConversationListResponse> {
  const params = new URLSearchParams()
  params.set("page", String(filters.page ?? 1))
  params.set("page_size", String(filters.pageSize ?? 30))
  if (filters.search) params.set("search", filters.search)
  if (filters.source) params.set("source", filters.source)
  if (filters.range && filters.range !== "all") params.set("range", filters.range)
  if (filters.dateFrom) params.set("date_from", filters.dateFrom)
  if (filters.dateTo) params.set("date_to", filters.dateTo)
  if (filters.sort) params.set("sort", filters.sort)
  return apiFetch<ConversationListResponse>(`/conversations?${params.toString()}`)
}

export async function getConversation(
  id: string
): Promise<ConversationSummary> {
  return apiFetch<ConversationSummary>(`/conversations/${id}`)
}

export async function forgetConversation(id: string): Promise<void> {
  await apiFetch(`/conversations/${id}`, { method: "DELETE" })
}

export async function forgetImportJob(importId: string): Promise<void> {
  await apiFetch(`/import/${importId}`, { method: "DELETE" })
}

export async function reindexImportJob(importId: string): Promise<ImportStatusResponse> {
  return apiFetch<ImportStatusResponse>(`/import/${importId}/reindex`, {
    method: "POST",
  })
}

export async function getConversationMessages(
  id: string,
  page = 1,
  pageSize = 80,
  around?: string,
  before?: number,
  after?: number
): Promise<MessageListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (around) params.set("around", around)
  if (before != null) params.set("before", String(before))
  if (after != null) params.set("after", String(after))
  return apiFetch<MessageListResponse>(
    `/conversations/${id}/messages?${params.toString()}`
  )
}

export async function searchMemories(
  query: string,
  page = 1,
  pageSize = 20,
  options?: {
    source?: string
    dateFrom?: string
    dateTo?: string
  }
): Promise<SearchResponse> {
  const params = new URLSearchParams({
    q: query,
    page: String(page),
    page_size: String(pageSize),
    mode: "hybrid",
  })
  if (options?.source) params.set("source", options.source)
  if (options?.dateFrom) params.set("date_from", options.dateFrom)
  if (options?.dateTo) params.set("date_to", options.dateTo)
  return apiFetch<SearchResponse>(`/search?${params.toString()}`)
}

export async function askJistoryStream(
  message: string,
  conversationId: string | null | undefined,
  taggedConversationIds: string[] | undefined,
  dateRange: { dateFrom?: string; dateTo?: string } | undefined,
  handlers: {
    onSources: (payload: {
      sources: SourceReference[]
      retrieved: number
      conversation_id: string
    }) => void
    onToken: (text: string) => void
    onDone: (payload: {
      conversation_id: string
      retrieved: number
      answer: string
    }) => void
  }
): Promise<void> {
  let response: Response
  try {
    response = await fetch(getApiUrl("/ask/stream"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: conversationId || null,
        tagged_conversation_ids: taggedConversationIds ?? [],
        date_from: dateRange?.dateFrom || null,
        date_to: dateRange?.dateTo || null,
      }),
    })
  } catch {
    throw new Error(
      "Server unavailable. Check that the backend is running on port 8000."
    )
  }

  if (!response.ok) {
    let payload: unknown
    try {
      payload = await response.json()
    } catch {
      throw new Error("Received an invalid response from the server.")
    }
    const errorPayload = payload as ImportJobError
    throw new Error(
      errorPayload?.error ||
        mapStatusToMessage(response.status) ||
        "Request failed."
    )
  }

  if (!response.body) {
    throw new Error("Received an invalid response from the server.")
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split("\n\n")
    buffer = parts.pop() ?? ""
    for (const part of parts) {
      const line = part
        .split("\n")
        .find((item) => item.startsWith("data: "))
      if (!line) continue
      const event = JSON.parse(line.slice(6)) as {
        type: string
        text?: string
        sources?: SourceReference[]
        retrieved?: number
        conversation_id?: string
        answer?: string
        error?: string
        code?: string
      }
      if (event.type === "sources") {
        handlers.onSources({
          sources: event.sources ?? [],
          retrieved: event.retrieved ?? 0,
          conversation_id: event.conversation_id || "",
        })
      } else if (event.type === "token" && event.text) {
        handlers.onToken(event.text)
      } else if (event.type === "done") {
        handlers.onDone({
          conversation_id: event.conversation_id || "",
          retrieved: event.retrieved ?? 0,
          answer: event.answer || "",
        })
      } else if (event.type === "error") {
        throw new Error(event.error || mapStatusToMessage(400) || "Ask failed.")
      }
    }
  }
}

export async function listAskSessions(): Promise<{ items: AskSessionSummary[] }> {
  return apiFetch<{ items: AskSessionSummary[] }>("/ask/sessions")
}

export async function getAskSession(id: string): Promise<AskSessionDetail> {
  return apiFetch<AskSessionDetail>(`/ask/sessions/${id}`)
}

export async function deleteAskSession(id: string): Promise<void> {
  await apiFetch(`/ask/sessions/${id}`, { method: "DELETE" })
}

export async function getDashboard(): Promise<DashboardResponse> {
  return apiFetch<DashboardResponse>("/dashboard")
}

export async function getSettings(): Promise<UserSettings> {
  return apiFetch<UserSettings>("/settings")
}

export async function updateSettings(
  payload: Partial<{
    gemini_model: string
    gemini_api_key: string
    retrieval_limit: number
    embedding_provider: string
    cursor_import_path: string
  }>
): Promise<UserSettings> {
  return apiFetch<UserSettings>("/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(getApiUrl(path), init)
  } catch {
    throw new Error(
      "Server unavailable. Check that the backend is running on port 8000."
    )
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new Error("Received an invalid response from the server.")
  }

  if (!response.ok) {
    const errorPayload = payload as ImportJobError
    throw new Error(
      errorPayload?.error ||
        mapStatusToMessage(response.status) ||
        "Request failed."
    )
  }

  return payload as T
}

function mapStatusToMessage(status: number): string | null {
  switch (status) {
    case 413:
      return "File is too large for import."
    case 400:
      return "That request could not be completed."
    case 404:
      return "The requested item was not found."
    case 429:
      return "Gemini is rate-limited. Please wait and try again."
    case 502:
      return "Jistory could not reach Gemini. Check Settings."
    case 504:
      return "Gemini timed out. Please try again."
    case 503:
      return "Server unavailable. Please try again."
    default:
      return null
  }
}

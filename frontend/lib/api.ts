import type {
  AskResponse,
  ConversationFilters,
  ConversationListResponse,
  ConversationSummary,
  DashboardResponse,
  MessageListResponse,
  SearchResponse,
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
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date)
}

export function conversationTitle(title: string | null | undefined): string {
  const trimmed = title?.trim()
  return trimmed ? trimmed : "Untitled conversation"
}

type UploadChatGPTOptions = {
  file: File
  onProgress?: (percent: number) => void
  signal?: AbortSignal
}

export function uploadChatGPTExport({
  file,
  onProgress,
  signal,
}: UploadChatGPTOptions): Promise<ImportJobSuccess> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const formData = new FormData()
    formData.append("file", file)

    xhr.open("POST", getApiUrl("/import/chatgpt"))

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

export async function getImportJob(importId: string): Promise<ImportStatusResponse> {
  return apiFetch<ImportStatusResponse>(`/import/${importId}`)
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
  pageSize = 20
): Promise<SearchResponse> {
  const params = new URLSearchParams({
    q: query,
    page: String(page),
    page_size: String(pageSize),
    mode: "hybrid",
  })
  return apiFetch<SearchResponse>(`/search?${params.toString()}`)
}

export async function askJistory(
  message: string,
  conversationId?: string | null
): Promise<AskResponse> {
  return apiFetch<AskResponse>("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId || null,
    }),
  })
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

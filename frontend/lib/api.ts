import type {
  ImportJobError,
  ImportJobSuccess,
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
  let response: Response
  try {
    response = await fetch(getApiUrl(`/import/${importId}/parse`), {
      method: "POST",
    })
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
        "Failed to parse import."
    )
  }

  return payload as ParseJobSuccess
}

function mapStatusToMessage(status: number): string | null {
  switch (status) {
    case 413:
      return "File is too large for import."
    case 400:
      return "Invalid ChatGPT export ZIP."
    case 404:
      return "Import job was not found."
    case 503:
      return "Server unavailable. Please try again."
    default:
      return null
  }
}

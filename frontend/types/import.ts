export type ImportJobSuccess = {
  success: true
  importId: string
  source: string
  folder: string
  status: string
  filename: string | null
  fileSize: number
  importedAt: string | null
  notes: string | null
}

export type ImportJobError = {
  success: false
  error: string
  code: string
}

export type ImportJobResult = ImportJobSuccess | ImportJobError

export type ParseJobSuccess = {
  success: true
  importId: string
  conversations: number
  messages: number
  skipped: number
  elapsed: string
  elapsed_ms?: number
  status: string
  chunks_indexed?: number | null
  index_error?: string | null
}

export type ImportStatusResponse = ImportJobSuccess & {
  conversations?: number | null
  messages?: number | null
  skipped?: number | null
  chunks_indexed?: number | null
  index_error?: string | null
  embedding_status?: string | null
  embedding_status_detail?: string | null
}

export type UploadState =
  | "idle"
  | "selected"
  | "uploading"
  | "success"
  | "error"

export type ParseState = "idle" | "parsing" | "success" | "error"

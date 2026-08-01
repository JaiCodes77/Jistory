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
  status: string
}

export type UploadState =
  | "idle"
  | "selected"
  | "uploading"
  | "success"
  | "error"

export type ParseState = "idle" | "parsing" | "success" | "error"

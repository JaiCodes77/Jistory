export type ConversationSummary = {
  id: string
  title: string | null
  source: string
  created_at: string | null
  updated_at: string | null
  message_count: number
  first_message_at: string | null
  last_message_at: string | null
}

export type ConversationListResponse = {
  items: ConversationSummary[]
  page: number
  page_size: number
  total: number
}

export type MessageItem = {
  id: string
  role: string
  content: string
  created_at: string | null
  sequence_number: number
  parent_message_id: string | null
}

export type MessageListResponse = {
  items: MessageItem[]
  page: number
  page_size: number
  total: number
  conversation: ConversationSummary
  has_before: boolean
  has_after: boolean
}

export type SearchHit = {
  conversation_id: string
  message_id: string
  conversation_title: string | null
  snippet: string
  source: string
  timestamp: string | null
  score: number
  match_type: string
}

export type SearchResponse = {
  results: SearchHit[]
  page: number
  page_size: number
  total: number
  query: string
}

export type SourceReference = {
  conversation_id: string
  message_id: string | null
  title: string | null
  source: string
  timestamp: string | null
  snippet: string
}

export type AskResponse = {
  answer: string
  sources: SourceReference[]
  conversation_id: string
  retrieved: number
}

export type DashboardResponse = {
  total_conversations: number
  total_messages: number
  sources: { name: string; count: number }[]
  latest_import: {
    id: string
    source: string
    filename: string | null
    imported_at: string | null
    status: string
    conversations: number | null
  } | null
  conversations_over_time: { date: string; count: number }[]
  recent_conversations: {
    id: string
    title: string | null
    source: string
    updated_at: string | null
    message_count: number
  }[]
  frequent_topics: { term: string; count: number }[]
}

export type UserSettings = {
  llm_provider: string
  gemini_model: string
  api_key_configured: boolean
  embedding_provider: string
  embedding_model: string
  retrieval_limit: number
  stored_locally: boolean
  sent_to_gemini_on_ask: boolean
  embedding_status: string
  embedding_status_detail: string
}

export type ConversationFilters = {
  page: number
  pageSize: number
  search: string
  source: string
  range: string
  dateFrom: string
  dateTo: string
  sort: string
}

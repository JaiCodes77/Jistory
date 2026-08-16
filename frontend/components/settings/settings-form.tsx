"use client"

import { useEffect, useState } from "react"
import { LoaderCircle } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { getSettings, updateSettings } from "@/lib/api"
import type { UserSettings } from "@/types/api"

export function SettingsForm() {
  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [model, setModel] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [retrievalLimit, setRetrievalLimit] = useState("8")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    void getSettings()
      .then((data) => {
        setSettings(data)
        setModel(data.gemini_model)
        setRetrievalLimit(String(data.retrieval_limit))
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Could not load settings.")
      )
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const payload: Parameters<typeof updateSettings>[0] = {
        gemini_model: model.trim(),
        retrieval_limit: Number(retrievalLimit) || 8,
      }
      if (apiKey.trim()) payload.gemini_api_key = apiKey.trim()
      const next = await updateSettings(payload)
      setSettings(next)
      setApiKey("")
      setSaved(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save settings.")
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-6 py-10 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" />
        Loading settings…
      </div>
    )
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-8 px-6 py-8">
      <div>
        <h2 className="text-lg font-medium tracking-tight">Settings</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Secrets stay on this machine. They are never returned by the API.
        </p>
      </div>

      <section className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4">
        <div>
          <h3 className="text-sm font-medium">AI</h3>
          <p className="text-xs text-muted-foreground">
            Gemini Flash is used only to generate Ask Jistory answers from retrieved
            excerpts.
          </p>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="provider">Provider</Label>
          <Input id="provider" value="Gemini" disabled />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="model">Model</Label>
          <Input
            id="model"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder="gemini-2.5-flash"
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="api-key">API key</Label>
          <Input
            id="api-key"
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder={
              settings?.api_key_configured ? "••••••••  (configured)" : "GEMINI_API_KEY"
            }
            autoComplete="off"
          />
          <p className="text-[11px] text-muted-foreground">
            Prefer environment variables. A key saved here is stored in a local
            settings file next to the database, not in git.
          </p>
        </div>
      </section>

      <section className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4">
        <div>
          <h3 className="text-sm font-medium">Search</h3>
          <p className="text-xs text-muted-foreground">
            Number of retrieved chunks sent to Gemini with each question.
          </p>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="chunks">Retrieved chunks</Label>
          <Input
            id="chunks"
            type="number"
            min={1}
            max={32}
            value={retrievalLimit}
            onChange={(event) => setRetrievalLimit(event.target.value)}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Embedding provider: {settings?.embedding_provider} ({settings?.embedding_model}).
          Conversation text is embedded locally by default.
        </p>
      </section>

      <section className="rounded-xl border border-border bg-card p-4 text-sm">
        <h3 className="text-sm font-medium">Privacy</h3>
        <ul className="mt-2 flex flex-col gap-1 text-muted-foreground">
          <li>Stored locally: imports, conversations, search index, embeddings.</li>
          <li>
            Sent to Gemini: only the retrieved excerpts for an Ask Jistory question,
            plus recent Ask turns.
          </li>
        </ul>
      </section>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {saved && <p className="text-sm text-muted-foreground">Settings saved.</p>}

      <div>
        <Button onClick={() => void save()} disabled={saving}>
          {saving ? "Saving…" : "Save settings"}
        </Button>
      </div>
    </div>
  )
}

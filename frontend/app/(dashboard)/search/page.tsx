import { Suspense } from "react"

import { SearchResults } from "@/components/search/search-results"

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="px-6 py-10 text-sm text-muted-foreground">Loading search…</div>
      }
    >
      <SearchResults />
    </Suspense>
  )
}

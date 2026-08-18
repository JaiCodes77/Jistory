"use client"

import type { Components } from "react-markdown"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { cn } from "@/lib/utils"

const markdownComponents: Components = {
  h1: ({ children }) => (
    <h1 className="mt-4 mb-2 text-base font-semibold tracking-tight first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mt-4 mb-2 text-[15px] font-semibold tracking-tight first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-3 mb-1.5 text-sm font-semibold tracking-tight first:mt-0">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="mt-3 mb-1 text-sm font-medium first:mt-0">{children}</h4>
  ),
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => (
    <ul className="my-2 list-disc space-y-1 pl-5 first:mt-0 last:mb-0">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2 list-decimal space-y-1 pl-5 first:mt-0 last:mb-0">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-6 [&>p]:my-1">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-border pl-3 text-muted-foreground">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-border" />,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="underline underline-offset-2 hover:text-foreground"
    >
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[28rem] border-collapse text-left text-[13px]">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted/50">{children}</thead>,
  th: ({ children }) => (
    <th className="border-b border-border px-3 py-1.5 font-medium">{children}</th>
  ),
  td: ({ children }) => (
    <td className="border-b border-border px-3 py-1.5 align-top last:border-b-0">{children}</td>
  ),
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-lg border border-border bg-muted/40 p-3 font-mono text-[12px] leading-5">
      {children}
    </pre>
  ),
  code: ({ className, children, ...props }) => {
    const inline = !className
    if (inline) {
      return (
        <code
          className="rounded-md border border-border bg-muted/60 px-1 py-px font-mono text-[12px]"
          {...props}
        >
          {children}
        </code>
      )
    }
    return (
      <code className={cn("font-mono", className)} {...props}>
        {children}
      </code>
    )
  },
}

export function MessageMarkdown({
  content,
  className,
}: {
  content: string
  className?: string
}) {
  if (!content) return null

  return (
    <div className={cn("jistory-markdown text-sm leading-6 break-words", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  )
}

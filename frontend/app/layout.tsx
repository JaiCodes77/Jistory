import type { Metadata } from "next"
import { Atkinson_Hyperlegible, IBM_Plex_Mono, Literata } from "next/font/google"
import Script from "next/script"

import { THEME_INIT_SCRIPT } from "@/lib/theme"

import "./globals.css"

const atkinson = Atkinson_Hyperlegible({
  variable: "--font-atkinson",
  subsets: ["latin"],
  weight: ["400", "700"],
})

const literata = Literata({
  variable: "--font-literata",
  subsets: ["latin"],
})

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
})

export const metadata: Metadata = {
  title: "Jistory",
  description: "Local-first AI conversation memory",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      className={`${atkinson.variable} ${literata.variable} ${plexMono.variable} dark h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full bg-background font-sans text-foreground">
        <Script
          id="jistory-theme"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }}
        />
        {children}
      </body>
    </html>
  )
}

"use client"

import { useEffect, useRef, useState } from "react"

import { conversationTitle, formatDate } from "@/lib/api"
import { formatWeight, nodeRadius, sourceFill, sourceRing } from "@/lib/graph-style"
import type { GraphEdge, GraphNode } from "@/types/api"

type SimNode = GraphNode & { x: number; y: number; vx: number; vy: number }

type HoverState = {
  node: GraphNode
  other?: GraphNode
  edge?: GraphEdge
  x: number
  y: number
  wrapW: number
  wrapH: number
}

export function ForceGraphCanvas({
  nodes,
  edges,
  selectedId,
  matchIds,
  fitNonce = 0,
  onSelect,
  onOpen,
}: {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedId: string | null
  matchIds: Set<string>
  fitNonce?: number
  onSelect: (id: string | null) => void
  onOpen: (id: string) => void
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const simRef = useRef<SimNode[]>([])
  const transformRef = useRef({ x: 0, y: 0, k: 1 })
  const selectedRef = useRef(selectedId)
  const matchRef = useRef(matchIds)
  const dragRef = useRef<{
    mode: "pan" | "node" | null
    id?: string
    lastX: number
    lastY: number
    moved: boolean
  }>({ mode: null, lastX: 0, lastY: 0, moved: false })
  const hoverIdRef = useRef<string | null>(null)
  const hoverEdgeRef = useRef<GraphEdge | null>(null)
  const lastClickRef = useRef<{ id: string; at: number } | null>(null)
  const [hover, setHover] = useState<HoverState | null>(null)
  const [cursor, setCursor] = useState("grab")

  useEffect(() => {
    selectedRef.current = selectedId
  }, [selectedId])

  useEffect(() => {
    matchRef.current = matchIds
  }, [matchIds])

  useEffect(() => {
    const previous = new Map(simRef.current.map((node) => [node.id, node]))
    const groups = new Map<string, GraphNode[]>()
    for (const node of nodes) {
      const list = groups.get(node.source) ?? []
      list.push(node)
      groups.set(node.source, list)
    }
    const sources = Array.from(groups.keys())
    const next: SimNode[] = []
    sources.forEach((source, sourceIndex) => {
      const members = groups.get(source) ?? []
      const wedge = (2 * Math.PI * sourceIndex) / Math.max(sources.length, 1)
      members.forEach((node, index) => {
        const existing = previous.get(node.id)
        if (existing) {
          next.push({
            ...node,
            x: existing.x,
            y: existing.y,
            vx: existing.vx,
            vy: existing.vy,
          })
          return
        }
        const spread = (index - (members.length - 1) / 2) * 0.22
        const radius = 40 + 16 * Math.sqrt(nodes.length)
        next.push({
          ...node,
          x: Math.cos(wedge + spread) * radius,
          y: Math.sin(wedge + spread) * radius,
          vx: 0,
          vy: 0,
        })
      })
    })
    const previousIds = simRef.current.map((node) => node.id).join("\0")
    const nextIds = next.map((node) => node.id).join("\0")
    simRef.current = next
    if (previousIds !== nextIds) {
      const wrap = wrapRef.current
      window.requestAnimationFrame(() => {
        fitTransform(simRef.current, wrap, transformRef.current)
      })
    }
  }, [nodes])

  useEffect(() => {
    if (!fitNonce) return
    fitTransform(simRef.current, wrapRef.current, transformRef.current)
  }, [fitNonce])

  useEffect(() => {
    if (!selectedId) return
    const node = simRef.current.find((item) => item.id === selectedId)
    const wrap = wrapRef.current
    if (!node || !wrap) return
    const rect = wrap.getBoundingClientRect()
    const t = transformRef.current
    const sx = rect.width / 2 + t.x + node.x * t.k
    const sy = rect.height / 2 + t.y + node.y * t.k
    const pad = 72
    if (sx < pad || sy < pad || sx > rect.width - pad || sy > rect.height - pad) {
      t.x = -node.x * t.k
      t.y = -node.y * t.k
    }
  }, [selectedId])

  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    let frame = 0
    let running = true
    let ticks = 0

    const resize = () => {
      const rect = wrap.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      canvas.width = Math.max(1, Math.floor(rect.width * dpr))
      canvas.height = Math.max(1, Math.floor(rect.height * dpr))
      canvas.style.width = `${rect.width}px`
      canvas.style.height = `${rect.height}px`
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(wrap)

    const tick = () => {
      if (!running) return
      const sim = simRef.current
      const rect = wrap.getBoundingClientRect()
      const dragging = dragRef.current.mode === "node"
      if (dragging || ticks < 220) {
        stepSimulation(sim, edges, dragRef.current.id)
        ticks += 1
      }
      drawGraph(ctx, sim, edges, {
        width: rect.width,
        height: rect.height,
        dpr: window.devicePixelRatio || 1,
        transform: transformRef.current,
        hoverId: hoverIdRef.current,
        hoverEdge: hoverEdgeRef.current,
        selectedId: selectedRef.current,
        matchIds: matchRef.current,
        dragId: dragRef.current.id,
      })
      frame = window.requestAnimationFrame(tick)
    }
    frame = window.requestAnimationFrame(tick)

    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const rect = wrap.getBoundingClientRect()
      const t = transformRef.current
      const scale = event.deltaY < 0 ? 1.08 : 0.92
      const nextK = Math.min(4, Math.max(0.22, t.k * scale))
      const sx = event.clientX - rect.left
      const sy = event.clientY - rect.top
      const wx = (sx - rect.width / 2 - t.x) / t.k
      const wy = (sy - rect.height / 2 - t.y) / t.k
      t.k = nextK
      t.x = sx - rect.width / 2 - wx * nextK
      t.y = sy - rect.height / 2 - wy * nextK
    }
    canvas.addEventListener("wheel", onWheel, { passive: false })

    return () => {
      running = false
      window.cancelAnimationFrame(frame)
      observer.disconnect()
      canvas.removeEventListener("wheel", onWheel)
    }
  }, [edges, nodes])

  const toWorld = (clientX: number, clientY: number) => {
    const rect = wrapRef.current?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    const t = transformRef.current
    return {
      x: (clientX - rect.left - rect.width / 2 - t.x) / t.k,
      y: (clientY - rect.top - rect.height / 2 - t.y) / t.k,
    }
  }

  const hitNode = (clientX: number, clientY: number) => {
    const world = toWorld(clientX, clientY)
    const k = transformRef.current.k
    let best: SimNode | null = null
    let bestDist = 22 / k
    for (const node of simRef.current) {
      const dist = Math.hypot(node.x - world.x, node.y - world.y)
      const radius = nodeRadius(node.message_count, node.degree) + 6 / k
      if (dist <= radius && dist < bestDist) {
        best = node
        bestDist = dist
      }
    }
    return best
  }

  const hitEdge = (clientX: number, clientY: number) => {
    const world = toWorld(clientX, clientY)
    const k = transformRef.current.k
    const byId = new Map(simRef.current.map((node) => [node.id, node]))
    let best: GraphEdge | null = null
    let bestDist = 8 / k
    for (const edge of edges) {
      const a = byId.get(edge.source_id)
      const b = byId.get(edge.target_id)
      if (!a || !b) continue
      const dist = pointToSegment(world.x, world.y, a.x, a.y, b.x, b.y)
      if (dist < bestDist) {
        best = edge
        bestDist = dist
      }
    }
    return best
  }

  return (
    <div ref={wrapRef} className="relative min-h-0 flex-1 overflow-hidden bg-background">
      <canvas
        ref={canvasRef}
        className="absolute inset-0 size-full touch-none select-none"
        style={{ cursor }}
        aria-label="Memory graph"
        onPointerDown={(event) => {
          const node = hitNode(event.clientX, event.clientY)
          dragRef.current = {
            mode: node ? "node" : "pan",
            id: node?.id,
            lastX: event.clientX,
            lastY: event.clientY,
            moved: false,
          }
          setCursor("grabbing")
          event.currentTarget.setPointerCapture(event.pointerId)
        }}
        onPointerMove={(event) => {
          const drag = dragRef.current
          const dx = event.clientX - drag.lastX
          const dy = event.clientY - drag.lastY
          if (Math.hypot(dx, dy) > 3) drag.moved = true
          if (drag.mode === "pan") {
            transformRef.current.x += dx
            transformRef.current.y += dy
            drag.lastX = event.clientX
            drag.lastY = event.clientY
          } else if (drag.mode === "node" && drag.id) {
            const world = toWorld(event.clientX, event.clientY)
            const node = simRef.current.find((item) => item.id === drag.id)
            if (node) {
              node.x = world.x
              node.y = world.y
              node.vx = 0
              node.vy = 0
            }
            drag.lastX = event.clientX
            drag.lastY = event.clientY
          }

          const hovered = hitNode(event.clientX, event.clientY)
          const edge = hovered ? null : hitEdge(event.clientX, event.clientY)
          hoverIdRef.current = hovered?.id ?? null
          hoverEdgeRef.current = edge
          setCursor(hovered ? "pointer" : drag.mode ? "grabbing" : "grab")
          const box = wrapRef.current?.getBoundingClientRect()
          if (hovered || edge) {
            const a = edge
              ? simRef.current.find((item) => item.id === edge.source_id)
              : hovered
            const b = edge
              ? simRef.current.find((item) => item.id === edge.target_id)
              : undefined
            if (a) {
              const next: HoverState = {
                node: hovered ?? a,
                other: hovered ? undefined : b,
                edge: edge ?? undefined,
                x: event.clientX - (box?.left ?? 0),
                y: event.clientY - (box?.top ?? 0),
                wrapW: box?.width ?? 320,
                wrapH: box?.height ?? 200,
              }
              setHover((prev) => {
                if (
                  prev &&
                  prev.node.id === next.node.id &&
                  prev.other?.id === next.other?.id &&
                  prev.edge === next.edge &&
                  Math.abs(prev.x - next.x) < 6 &&
                  Math.abs(prev.y - next.y) < 6
                ) {
                  return prev
                }
                return next
              })
            }
          } else {
            setHover(null)
          }
        }}
        onPointerUp={(event) => {
          const drag = dragRef.current
          if (!drag.moved) {
            if (drag.mode === "node" && drag.id) {
              const now = Date.now()
              const last = lastClickRef.current
              if (last && last.id === drag.id && now - last.at < 320) {
                onOpen(drag.id)
                lastClickRef.current = null
              } else {
                onSelect(drag.id)
                lastClickRef.current = { id: drag.id, at: now }
              }
            } else {
              onSelect(null)
            }
          }
          dragRef.current = { mode: null, lastX: 0, lastY: 0, moved: false }
          setCursor("grab")
          event.currentTarget.releasePointerCapture(event.pointerId)
        }}
        onPointerLeave={() => {
          hoverIdRef.current = null
          hoverEdgeRef.current = null
          setHover(null)
          setCursor("grab")
        }}
      />
      {hover && (
        <div
          className="pointer-events-none absolute z-10 w-72 rounded-lg border border-border bg-card px-3 py-2"
          style={{
            left: Math.max(8, Math.min(hover.x + 14, hover.wrapW - 300)),
            top: Math.max(8, Math.min(hover.y + 14, hover.wrapH - 132)),
          }}
        >
          {hover.edge && hover.other ? (
            <>
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Link</p>
              <p className="mt-1 line-clamp-2 text-sm font-medium leading-snug">
                {conversationTitle(hover.node.title)}
                <span className="font-normal text-muted-foreground"> · </span>
                {conversationTitle(hover.other.title)}
              </p>
              <p className="mt-1 text-[11px] text-foreground/80">{hover.edge.reason}</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                Strength {formatWeight(hover.edge.weight)}
              </p>
            </>
          ) : (
            <>
              <p className="truncate text-sm font-medium">{conversationTitle(hover.node.title)}</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {hover.node.source} · {formatDate(hover.node.last_message_at)} ·{" "}
                {hover.node.message_count} messages
                {hover.node.degree ? ` · ${hover.node.degree} links` : ""}
              </p>
              {hover.node.snippet ? (
                <p className="mt-1 line-clamp-3 text-[11px] text-muted-foreground">
                  {hover.node.snippet}
                </p>
              ) : null}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function fitTransform(
  nodes: SimNode[],
  wrap: HTMLDivElement | null,
  transform: { x: number; y: number; k: number }
) {
  if (!wrap || nodes.length === 0) return
  const rect = wrap.getBoundingClientRect()
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const node of nodes) {
    minX = Math.min(minX, node.x)
    maxX = Math.max(maxX, node.x)
    minY = Math.min(minY, node.y)
    maxY = Math.max(maxY, node.y)
  }
  const width = Math.max(80, maxX - minX)
  const height = Math.max(80, maxY - minY)
  const k = Math.min(rect.width / (width + 96), rect.height / (height + 96), 2.4)
  transform.k = Math.max(0.25, k)
  transform.x = -((minX + maxX) / 2) * transform.k
  transform.y = -((minY + maxY) / 2) * transform.k
}

function pointToSegment(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number
): number {
  const dx = x2 - x1
  const dy = y2 - y1
  const length = dx * dx + dy * dy || 1
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / length))
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
}

function stepSimulation(nodes: SimNode[], edges: GraphEdge[], pinnedId?: string) {
  const n = nodes.length
  if (n === 0) return
  const byId = new Map(nodes.map((node) => [node.id, node]))

  for (let i = 0; i < n; i += 1) {
    for (let j = i + 1; j < n; j += 1) {
      const a = nodes[i]
      const b = nodes[j]
      let dx = a.x - b.x
      let dy = a.y - b.y
      const dist = Math.hypot(dx, dy) || 0.01
      const minDist =
        nodeRadius(a.message_count, a.degree) + nodeRadius(b.message_count, b.degree) + 18
      const force = 900 / (dist * dist) + (dist < minDist ? (minDist - dist) * 0.08 : 0)
      dx = (dx / dist) * force
      dy = (dy / dist) * force
      a.vx += dx
      a.vy += dy
      b.vx -= dx
      b.vy -= dy
      if (a.source === b.source) {
        a.vx += (b.x - a.x) * 0.0008
        a.vy += (b.y - a.y) * 0.0008
        b.vx += (a.x - b.x) * 0.0008
        b.vy += (a.y - b.y) * 0.0008
      }
    }
  }

  for (const edge of edges) {
    const a = byId.get(edge.source_id)
    const b = byId.get(edge.target_id)
    if (!a || !b) continue
    const dx = b.x - a.x
    const dy = b.y - a.y
    const dist = Math.hypot(dx, dy) || 0.01
    const rest = 64 + 56 * (1 - edge.weight)
    const spring = (dist - rest) * 0.02
    a.vx += (dx / dist) * spring
    a.vy += (dy / dist) * spring
    b.vx -= (dx / dist) * spring
    b.vy -= (dy / dist) * spring
  }

  for (const node of nodes) {
    if (node.id === pinnedId) {
      node.vx = 0
      node.vy = 0
      continue
    }
    node.vx += -node.x * 0.005
    node.vy += -node.y * 0.005
    node.vx *= 0.84
    node.vy *= 0.84
    const speed = Math.hypot(node.vx, node.vy)
    if (speed > 9) {
      node.vx = (node.vx / speed) * 9
      node.vy = (node.vy / speed) * 9
    }
    node.x += node.vx
    node.y += node.vy
  }
}

function neighborhood(selectedId: string | null, edges: GraphEdge[]): Set<string> {
  const ids = new Set<string>()
  if (!selectedId) return ids
  ids.add(selectedId)
  for (const edge of edges) {
    if (edge.source_id === selectedId) ids.add(edge.target_id)
    if (edge.target_id === selectedId) ids.add(edge.source_id)
  }
  return ids
}

function drawGraph(
  ctx: CanvasRenderingContext2D,
  nodes: SimNode[],
  edges: GraphEdge[],
  opts: {
    width: number
    height: number
    dpr: number
    transform: { x: number; y: number; k: number }
    hoverId: string | null
    hoverEdge: GraphEdge | null
    selectedId: string | null
    matchIds: Set<string>
    dragId?: string
  }
) {
  const { width, height, dpr, transform, hoverId, hoverEdge, selectedId, matchIds, dragId } = opts
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)

  const dark = document.documentElement.classList.contains("dark")
  drawPaper(ctx, width, height, dark)

  const muted = dark ? "rgba(212,212,216,0.92)" : "rgba(63,63,70,0.92)"
  const labelBg = dark ? "rgba(24,24,27,0.86)" : "rgba(255,255,255,0.92)"
  const dimEdge = dark ? "rgba(250,250,250,0.07)" : "rgba(24,24,27,0.07)"
  const liveEdge = dark ? "rgba(250,250,250,0.4)" : "rgba(24,24,27,0.3)"
  const focus = neighborhood(selectedId, edges)
  const hasFocus = focus.size > 0

  ctx.save()
  ctx.translate(width / 2 + transform.x, height / 2 + transform.y)
  ctx.scale(transform.k, transform.k)

  const byId = new Map(nodes.map((node) => [node.id, node]))
  for (const edge of edges) {
    const a = byId.get(edge.source_id)
    const b = byId.get(edge.target_id)
    if (!a || !b) continue
    const active = !hasFocus || (focus.has(edge.source_id) && focus.has(edge.target_id))
    const hovered =
      hoverEdge === edge ||
      Boolean(hoverId && (edge.source_id === hoverId || edge.target_id === hoverId))
    ctx.strokeStyle = active ? liveEdge : dimEdge
    ctx.globalAlpha = hovered ? 1 : 0.5 + edge.weight * 0.5
    ctx.lineWidth = ((hovered ? 2.6 : 1.05) + edge.weight) / transform.k
    ctx.beginPath()
    ctx.moveTo(a.x, a.y)
    ctx.lineTo(b.x, b.y)
    ctx.stroke()
  }
  ctx.globalAlpha = 1

  for (const node of nodes) {
    const radius = nodeRadius(node.message_count, node.degree)
    const inFocus = !hasFocus || focus.has(node.id)
    const active = node.id === hoverId || node.id === selectedId || node.id === dragId
    const matched = matchIds.has(node.id)
    ctx.globalAlpha = inFocus ? 1 : 0.14
    if (node.id === selectedId) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, radius + 11 / transform.k, 0, Math.PI * 2)
      ctx.fillStyle = sourceFill(node.source, dark)
      ctx.globalAlpha = inFocus ? 0.18 : 0.06
      ctx.fill()
      ctx.globalAlpha = inFocus ? 1 : 0.14
    }
    if (active || matched) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, radius + 5 / transform.k, 0, Math.PI * 2)
      ctx.strokeStyle = matched && !active ? liveEdge : sourceRing(node.source, dark)
      ctx.lineWidth = (node.id === selectedId ? 2.4 : 1.8) / transform.k
      ctx.stroke()
    }
    ctx.beginPath()
    ctx.arc(node.x, node.y, radius, 0, Math.PI * 2)
    ctx.fillStyle = sourceFill(node.source, dark)
    ctx.fill()
    ctx.lineWidth = 1 / transform.k
    ctx.strokeStyle = dark ? "rgba(9,9,11,0.55)" : "rgba(255,255,255,0.8)"
    ctx.stroke()
  }

  ctx.textAlign = "center"
  ctx.textBaseline = "top"
  ctx.font = `${11 / transform.k}px ui-sans-serif, system-ui, sans-serif`
  const showAll = nodes.length <= 40
  for (const node of nodes) {
    const show =
      node.id === hoverId ||
      node.id === selectedId ||
      focus.has(node.id) ||
      matchIds.has(node.id) ||
      showAll
    if (!show) continue
    const title = conversationTitle(node.title)
    const label = title.length > 32 ? `${title.slice(0, 31)}…` : title
    const y = node.y + nodeRadius(node.message_count, node.degree) + 5 / transform.k
    const textWidth = ctx.measureText(label).width
    ctx.globalAlpha = 1
    ctx.fillStyle = labelBg
    const pad = 3 / transform.k
    ctx.fillRect(node.x - textWidth / 2 - pad, y - pad, textWidth + pad * 2, 14 / transform.k)
    ctx.fillStyle = muted
    ctx.fillText(label, node.x, y)
  }
  ctx.globalAlpha = 1
  ctx.restore()
}

function drawPaper(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  dark: boolean
) {
  const gap = 22
  ctx.fillStyle = dark ? "rgba(250,250,250,0.035)" : "rgba(24,24,27,0.045)"
  for (let x = 12; x < width; x += gap) {
    for (let y = 12; y < height; y += gap) {
      ctx.beginPath()
      ctx.arc(x, y, 0.65, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}

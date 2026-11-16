import { useEffect, useRef } from 'react'
import { typeColor } from '../lib/data'

/**
 * The hero's compile field: a steady flow from materials (left) through evidence particles and a
 * knowledge network to the files of the generated repository (right).
 *
 * It is a schematic. Proportions follow the build (source kinds, object types, the share of
 * conflict links, the real artifact list); positions and individual links are not the real graph.
 */

export type FieldRow = { label: string; group: 'doc' | 'skill' | 'tool'; status?: string }
export type ZoneLabel = { step: string; title: string; value: string; sub: string }

type Props = {
  kinds: { pdf: number; table: number; text: number; other: number }
  objectsByType: Record<string, number>
  conflictShare: number
  rows: FieldRow[]
  zones: [ZoneLabel, ZoneLabel, ZoneLabel, ZoneLabel]
  stages: [string, string, string]
  groupTitles: { doc: string; skill: string; tool: string }
  reduce: boolean
  ariaLabel: string
}

const MINT = '#4fe3a4'
const AMBER = '#efb75a'
const SKY = '#74a9f7'
const ROSE = '#ef7a7a'
const INK = '#e9efe9'
const KIND_COLOR: Record<string, string> = { pdf: '#8fd3b6', table: AMBER, text: SKY, other: '#8d9a92' }
const GROUP_COLOR: Record<string, string> = { doc: MINT, skill: AMBER, tool: SKY }
const STATUS_COLOR: Record<string, string> = { verified: MINT, tested: AMBER, failed: ROSE, blocked: ROSE }

// Zone boundaries as fractions of the width; the DOM labels use the same numbers.
const X_SPLIT = 0.23
const X_EXTRACT = 0.43
const X_REPO = 0.745

function rng(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function rgba(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

const sprites = new Map<string, HTMLCanvasElement>()
function sprite(color: string) {
  let c = sprites.get(color)
  if (c) return c
  c = document.createElement('canvas')
  c.width = c.height = 64
  const g = c.getContext('2d')!
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32)
  grad.addColorStop(0, rgba(color, 0.95))
  grad.addColorStop(0.22, rgba(color, 0.4))
  grad.addColorStop(1, rgba(color, 0))
  g.fillStyle = grad
  g.fillRect(0, 0, 64, 64)
  sprites.set(color, c)
  return c
}

type Doc = { x: number; y: number; v: number; kind: string; lane: number }
type Particle = { x: number; y: number; px: number; py: number; vx: number; vy: number; target: number; speed: number; color: string; phase: number }
type Node = { bx: number; by: number; x: number; y: number; energy: number; phase: number; color: string }
type Link = { a: number; b: number; conflict: boolean }
type Packet = { x0: number; y0: number; x1: number; y1: number; t: number; dur: number; row: number; color: string }
type RowL = FieldRow & { y: number; glow: number; color: string; dot: string; text: string; header?: string }
type Flash = { x: number; y: number; a: number; color: string }

export default function CompileField({ kinds, objectsByType, conflictShare, rows, zones, stages, groupTitles, reduce, ariaLabel }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rowsKey = JSON.stringify(rows)
  const typesKey = JSON.stringify(objectsByType)
  const kindsKey = JSON.stringify(kinds)
  const titlesKey = JSON.stringify(groupTitles)

  useEffect(() => {
    const wrap = wrapRef.current
    const canvas = canvasRef.current
    if (!wrap || !canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const rand = rng(20261115)
    let W = 0
    let H = 0
    let compact = false
    let scale = 1
    let xSplit = 0
    let xExtract = 0
    let xRepo = 0
    let rowX = 0
    let docs: Doc[] = []
    let parts: Particle[] = []
    let nodes: Node[] = []
    let links: Link[] = []
    let packets: Packet[] = []
    let rowsL: RowL[] = []
    let flashes: Flash[] = []
    let lanes: number[] = []
    let spawnAcc = 0
    let packetAcc = 0
    let rowCursor = 0
    let time = 0

    const kindPool: string[] = []
    const totalKinds = kinds.pdf + kinds.table + kinds.text + kinds.other || 1
    for (const k of ['pdf', 'table', 'text', 'other'] as const) {
      const n = Math.round((kinds[k] / totalKinds) * 40)
      for (let i = 0; i < Math.max(kinds[k] > 0 ? 1 : 0, n); i++) kindPool.push(k)
    }

    function layout() {
      const r = wrap!.getBoundingClientRect()
      W = Math.max(280, r.width)
      H = Math.max(200, r.height)
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      canvas!.width = Math.round(W * dpr)
      canvas!.height = Math.round(H * dpr)
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
      compact = W < 720
      scale = Math.max(0.5, Math.min(1.25, W / 1200))
      xSplit = W * X_SPLIT
      xExtract = W * X_EXTRACT
      xRepo = W * X_REPO
      rowX = xRepo + (compact ? 10 : 30)

      const laneCount = compact ? 4 : 6
      const laneTop = compact ? 0.26 : 0.3
      lanes = Array.from({ length: laneCount }, (_, i) => H * (laneTop + ((0.84 - laneTop) * i) / (laneCount - 1)))

      // knowledge network: stable pseudo-random points in an ellipse, typed in the build's proportions
      const lr = rng(7)
      const n = compact ? 24 : 58
      const cx = (xExtract + xRepo) / 2
      const cy = H * (compact ? 0.56 : 0.6)
      const rx = (xRepo - xExtract) / 2 - (compact ? 14 : 40)
      const ry = H * (compact ? 0.3 : 0.28)
      const minD = Math.sqrt((Math.PI * rx * ry) / n) * 0.74
      nodes = []
      let guard = 0
      while (nodes.length < n && guard++ < 8000) {
        const a = lr() * Math.PI * 2
        const rr = Math.sqrt(lr())
        const x = cx + Math.cos(a) * rx * rr
        const y = cy + Math.sin(a) * ry * rr
        if (nodes.every((q) => (q.bx - x) ** 2 + (q.by - y) ** 2 > minD * minD))
          nodes.push({ bx: x, by: y, x, y, energy: 0, phase: lr() * 6.283, color: MINT })
      }
      const types = Object.entries(objectsByType).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
      const total = types.reduce((s, [, v]) => s + v, 0) || 1
      const quota = types.map(([t, v]) => [t, Math.max(1, Math.round((v / total) * nodes.length))] as [string, number])
      let qi = 0
      for (const node of nodes) {
        while (qi < quota.length - 1 && quota[qi][1] <= 0) qi++
        node.color = typeColor[quota[qi][0]] ?? MINT
        quota[qi][1]--
      }
      // interleave the types so that colours are mixed across the field
      for (let i = nodes.length - 1; i > 0; i--) {
        const j = Math.floor(lr() * (i + 1))
        const c = nodes[i].color
        nodes[i].color = nodes[j].color
        nodes[j].color = c
      }
      const seen = new Set<string>()
      links = []
      nodes.forEach((p, i) => {
        const near = nodes
          .map((q, j) => ({ j, d: (q.bx - p.bx) ** 2 + (q.by - p.by) ** 2 }))
          .filter((o) => o.j !== i)
          .sort((a, b) => a.d - b.d)
          .slice(0, 2)
        for (const { j } of near) {
          const key = i < j ? `${i}-${j}` : `${j}-${i}`
          if (!seen.has(key)) {
            seen.add(key)
            links.push({ a: i, b: j, conflict: false })
          }
        }
      })
      const every = conflictShare > 0 ? Math.max(4, Math.round(1 / conflictShare)) : 0
      if (every) links.forEach((l, i) => (l.conflict = i % every === every - 1))

      // repository rows
      const groups: FieldRow['group'][] = ['doc', 'skill', 'tool']
      const ordered = groups.flatMap((g) => rows.filter((r0) => r0.group === g))
      const headers = groups.filter((g) => ordered.some((r0) => r0.group === g)).length
      const top = compact ? Math.max(H * 0.2, 58) : Math.max(H * 0.25, 92)
      const bottom = H * 0.93
      const stepY = (bottom - top) / Math.max(1, ordered.length + headers)
      const font = compact ? 9 : 10.5
      ctx!.font = `${font}px "Plex Mono", ui-monospace, monospace`
      const maxText = W - (rowX + 13) - (compact ? 4 : 10)
      let y = top
      let last = ''
      rowsL = ordered.map((r0) => {
        let header: string | undefined
        if (r0.group !== last) {
          header = groupTitles[r0.group]
          last = r0.group
          y += stepY
        }
        let text = r0.label
        if (maxText < 34) text = ''
        else if (ctx!.measureText(text).width > maxText) {
          while (text.length > 3 && ctx!.measureText(text + '…').width > maxText) text = text.slice(0, -1)
          text += '…'
        }
        const row: RowL = {
          ...r0,
          y,
          glow: 0,
          color: GROUP_COLOR[r0.group],
          dot: r0.group === 'tool' ? STATUS_COLOR[r0.status ?? ''] ?? SKY : GROUP_COLOR[r0.group],
          text,
          header,
        }
        y += stepY
        return row
      })
      docs = []
      parts = []
      packets = []
      flashes = []
    }

    function step(dt: number) {
      time += dt
      // materials
      spawnAcc += dt * (compact ? 1.1 : 2.1)
      while (spawnAcc >= 1) {
        spawnAcc -= 1
        const free = lanes.map((_, i) => i).filter((i) => !docs.some((d) => d.lane === i && d.x < 26))
        if (!free.length) break
        const lane = free[Math.floor(rand() * free.length)]
        docs.push({ x: -22, y: lanes[lane] + (rand() - 0.5) * 6, v: (44 + rand() * 24) * scale, kind: kindPool[Math.floor(rand() * kindPool.length)], lane })
      }
      for (let i = docs.length - 1; i >= 0; i--) {
        const d = docs[i]
        d.x += d.v * dt
        if (d.x >= xSplit - 6) {
          docs.splice(i, 1)
          flashes.push({ x: xSplit, y: d.y, a: 1, color: KIND_COLOR[d.kind] })
          const count = compact ? 7 : 16
          for (let k = 0; k < count && parts.length < 900; k++) {
            const y = d.y + (rand() - 0.5) * 26
            // part of the evidence yields no knowledge object: it fades at the extraction line
            const target = rand() < 0.66 ? Math.floor(rand() * nodes.length) : -1
            parts.push({
              x: xSplit + rand() * 5, y, px: xSplit, py: y,
              vx: (60 + rand() * 60) * scale, vy: (rand() - 0.5) * 46,
              target, speed: (92 + rand() * 70) * scale, color: '#cfe6da', phase: rand() * 6.283,
            })
          }
        }
      }
      // evidence
      for (let i = parts.length - 1; i >= 0; i--) {
        const p = parts[i]
        p.px = p.x
        p.py = p.y
        if (p.target < 0) {
          p.vy += Math.sin(time * 2.2 + p.phase) * 26 * dt
          p.vy *= 1 - 1.2 * dt
          p.x += p.vx * dt
          p.y += p.vy * dt
          if (p.x >= xExtract) parts.splice(i, 1)
          continue
        }
        const n = nodes[p.target]
        const dx = n.x - p.x
        const dy = n.y - p.y
        const d = Math.hypot(dx, dy) || 1
        const past = p.x > xExtract - 10
        if (past) p.color = n.color
        const k = Math.min(1, dt * (past ? 3.4 : 0.7))
        p.vx += ((dx / d) * p.speed - p.vx) * k
        p.vy += ((dy / d) * p.speed - p.vy) * k + Math.sin(time * 3 + p.phase) * 30 * dt
        p.x += p.vx * dt
        p.y += p.vy * dt
        if (d < 7) {
          n.energy = Math.min(1.6, n.energy + 0.32)
          parts.splice(i, 1)
        }
      }
      // knowledge
      for (const n of nodes) {
        n.energy *= Math.exp(-dt * 0.85)
        n.x = n.bx + Math.sin(time * 0.5 + n.phase) * 3.2
        n.y = n.by + Math.cos(time * 0.42 + n.phase * 1.3) * 3.2
      }
      // compile: knowledge is written into the repository's files
      packetAcc += dt
      const interval = compact ? 0.55 : 0.34
      while (packetAcc >= interval && rowsL.length) {
        packetAcc -= interval
        const hot = nodes.filter((n) => n.energy > 0.3)
        if (!hot.length) break
        const n = hot[Math.floor(rand() * hot.length)]
        rowCursor = (rowCursor + 5) % rowsL.length
        const row = rowsL[rowCursor]
        n.energy *= 0.8
        packets.push({ x0: n.x, y0: n.y, x1: rowX - 6, y1: row.y, t: 0, dur: 0.85 + rand() * 0.5, row: rowCursor, color: row.color })
      }
      for (let i = packets.length - 1; i >= 0; i--) {
        const p = packets[i]
        p.t += dt / p.dur
        if (p.t >= 1) {
          rowsL[p.row].glow = 1
          packets.splice(i, 1)
        }
      }
      for (const r of rowsL) r.glow *= Math.exp(-dt * 0.9)
      for (let i = flashes.length - 1; i >= 0; i--) {
        flashes[i].a -= dt * 2.4
        if (flashes[i].a <= 0) flashes.splice(i, 1)
      }
    }

    function bez(p: Packet, t: number): [number, number] {
      const mx = p.x0 + (p.x1 - p.x0) * 0.55
      const u = 1 - t
      const x = u * u * u * p.x0 + 3 * u * u * t * mx + 3 * u * t * t * mx + t * t * t * p.x1
      const y = u * u * u * p.y0 + 3 * u * u * t * p.y0 + 3 * u * t * t * p.y1 + t * t * t * p.y1
      return [x, y]
    }

    function draw() {
      const c = ctx!
      c.clearRect(0, 0, W, H)
      c.globalCompositeOperation = 'source-over'

      // stage lines
      for (const x of [xSplit, xExtract, xRepo]) {
        const g = c.createLinearGradient(0, H * 0.12, 0, H * 0.97)
        g.addColorStop(0, rgba(MINT, 0))
        g.addColorStop(0.2, rgba(MINT, 0.3))
        g.addColorStop(0.8, rgba(MINT, 0.3))
        g.addColorStop(1, rgba(MINT, 0))
        c.strokeStyle = g
        c.lineWidth = 1
        c.beginPath()
        c.moveTo(Math.round(x) + 0.5, H * 0.12)
        c.lineTo(Math.round(x) + 0.5, H * 0.97)
        c.stroke()
      }

      // links
      for (const l of links) {
        const a = nodes[l.a]
        const b = nodes[l.b]
        const e = Math.min(1, (a.energy + b.energy) / 2)
        if (l.conflict) {
          c.setLineDash([3, 3])
          c.strokeStyle = rgba(ROSE, 0.35 + 0.45 * (0.5 + 0.5 * Math.sin(time * 2.4 + l.a)))
          c.lineWidth = 1
        } else {
          c.setLineDash([])
          c.strokeStyle = rgba(INK, 0.07 + 0.3 * e)
          c.lineWidth = 0.7
        }
        c.beginPath()
        c.moveTo(a.x, a.y)
        c.lineTo(b.x, b.y)
        c.stroke()
      }
      c.setLineDash([])

      // materials
      for (const d of docs) {
        const fade = Math.min(1, (d.x + 22) / 60) * Math.min(1, Math.max(0.15, (xSplit - d.x) / 26))
        const col = KIND_COLOR[d.kind]
        const w = compact ? 13 : 17
        const h = compact ? 17 : 22
        const x = d.x - w / 2
        const y = d.y - h / 2
        c.fillStyle = rgba(col, 0.1 * fade)
        c.strokeStyle = rgba(col, 0.8 * fade)
        c.lineWidth = 1
        c.beginPath()
        c.moveTo(x, y)
        c.lineTo(x + w - 5, y)
        c.lineTo(x + w, y + 5)
        c.lineTo(x + w, y + h)
        c.lineTo(x, y + h)
        c.closePath()
        c.fill()
        c.stroke()
        c.strokeStyle = rgba(col, 0.45 * fade)
        c.beginPath()
        for (let i = 0; i < 3; i++) {
          const ly = y + 8 + i * (compact ? 3 : 4)
          c.moveTo(x + 3, ly)
          c.lineTo(x + w - (i === 2 ? 7 : 3), ly)
        }
        c.stroke()
      }

      c.globalCompositeOperation = 'lighter'
      for (const f of flashes) {
        const s = 26 + (1 - f.a) * 26
        c.globalAlpha = f.a * 0.8
        c.drawImage(sprite(f.color), f.x - s / 2, f.y - s / 2, s, s)
      }
      c.globalAlpha = 1

      // evidence
      c.lineWidth = 1.5
      for (const p of parts) {
        let a = 0.9
        if (p.target < 0) a = 0.7 * Math.max(0, Math.min(1, (xExtract - p.x) / ((xExtract - xSplit) * 0.6)))
        c.strokeStyle = rgba(p.color, a)
        c.beginPath()
        c.moveTo(p.px - p.vx * 0.035, p.py - p.vy * 0.035)
        c.lineTo(p.x, p.y)
        c.stroke()
      }

      // compile packets
      for (const p of packets) {
        c.strokeStyle = rgba(p.color, 0.5)
        c.lineWidth = 1.2
        c.beginPath()
        const t0 = Math.max(0, p.t - 0.16)
        let [x, y] = bez(p, t0)
        c.moveTo(x, y)
        for (let k = 1; k <= 6; k++) {
          ;[x, y] = bez(p, t0 + ((p.t - t0) * k) / 6)
          c.lineTo(x, y)
        }
        c.stroke()
        c.globalAlpha = 0.9
        c.drawImage(sprite(p.color), x - 7, y - 7, 14, 14)
        c.globalAlpha = 1
      }

      // knowledge nodes
      for (const n of nodes) {
        const e = Math.min(1, n.energy)
        const s = 16 + e * 30
        c.globalAlpha = 0.3 + 0.7 * e
        c.drawImage(sprite(n.color), n.x - s / 2, n.y - s / 2, s, s)
      }
      c.globalAlpha = 1
      c.globalCompositeOperation = 'source-over'
      for (const n of nodes) {
        c.fillStyle = rgba(n.color, 0.75 + 0.25 * Math.min(1, n.energy))
        c.beginPath()
        c.arc(n.x, n.y, 1.7 + Math.min(1, n.energy) * 1.5, 0, 6.283)
        c.fill()
      }

      // repository
      const font = compact ? 9 : 10.5
      for (const r of rowsL) {
        if (r.header) {
          c.font = `${compact ? 8 : 9}px "Plex Mono", ui-monospace, monospace`
          c.fillStyle = rgba(r.color, 0.75)
          c.fillText(r.header, rowX - 2, r.y - (rowsL.length > 1 ? (rowsL[1].y - rowsL[0].y) * 0.78 : 12))
        }
        if (r.glow > 0.03) {
          c.globalCompositeOperation = 'lighter'
          c.globalAlpha = r.glow * 0.9
          c.drawImage(sprite(r.dot), rowX + 3 - 11, r.y - 11, 22, 22)
          const g = c.createLinearGradient(rowX, 0, W, 0)
          g.addColorStop(0, rgba(r.color, 0.16 * r.glow))
          g.addColorStop(1, rgba(r.color, 0))
          c.globalAlpha = 1
          c.fillStyle = g
          c.fillRect(rowX - 4, r.y - 7, W - rowX, 14)
          c.globalCompositeOperation = 'source-over'
        }
        c.fillStyle = rgba(r.dot, 0.55 + 0.45 * r.glow)
        c.beginPath()
        c.arc(rowX + 3, r.y, 2.4, 0, 6.283)
        c.fill()
        if (r.text) {
          c.font = `${font}px "Plex Mono", ui-monospace, monospace`
          c.fillStyle = rgba(INK, 0.5 + 0.5 * r.glow)
          c.fillText(r.text, rowX + 13, r.y + 3.5)
        }
      }
    }

    function warm(seconds: number) {
      for (let i = 0; i < seconds * 30; i++) step(1 / 30)
    }

    let raf = 0
    let last = 0
    let visible = true
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame)
      if (!visible || document.hidden) {
        last = now
        return
      }
      const dt = Math.min(0.05, (now - last) / 1000 || 0.016)
      last = now
      step(dt)
      draw()
    }

    layout()
    warm(9)
    draw()
    if (!reduce) raf = requestAnimationFrame(frame)

    const ro = new ResizeObserver(() => {
      layout()
      warm(9)
      draw()
    })
    ro.observe(wrap)
    const io = new IntersectionObserver((entries) => {
      visible = entries.some((e) => e.isIntersecting)
    })
    io.observe(wrap)
    // The mono font may arrive after the first layout; re-measure the row labels once it has.
    document.fonts?.ready.then(() => {
      layout()
      warm(9)
      draw()
    }).catch(() => {})

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      io.disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rowsKey, typesKey, kindsKey, titlesKey, conflictShare, reduce])

  const cols = `${X_SPLIT * 100}% ${(X_EXTRACT - X_SPLIT) * 100}% ${(X_REPO - X_EXTRACT) * 100}% ${(1 - X_REPO) * 100}%`
  return (
    <div className="relative h-[300px] sm:h-[340px] lg:h-[min(410px,45vh)] lg:min-h-[290px]" role="img" aria-label={ariaLabel}>
      <div
        ref={wrapRef}
        className="absolute inset-0 [mask-image:linear-gradient(to_right,transparent,black_7%,black_100%)]"
      >
        <canvas ref={canvasRef} className="block h-full w-full" />
      </div>
      <div className="pointer-events-none absolute inset-x-0 top-0 grid" style={{ gridTemplateColumns: cols }}>
        {zones.map((z, i) => (
          <div key={z.step} className={`min-w-0 ${i === 0 ? 'pl-5 md:pl-[max(2rem,calc((100vw-1240px)/2+2rem))]' : 'pl-3 md:pl-7'} pr-2`}>
            <div className="mono text-[9.5px] md:text-[10.5px] tracking-[0.18em] text-mint/80 uppercase truncate">
              {z.step} <span className="text-mute">· {z.title}</span>
            </div>
            <div className="display tabular text-[1.15rem] md:text-[1.9rem] leading-none text-ink mt-1.5 md:mt-2">{z.value}</div>
            <div className="hidden md:block mono text-[10px] text-faint mt-1.5 truncate">{z.sub}</div>
          </div>
        ))}
      </div>
      {[X_SPLIT, X_EXTRACT, X_REPO].map((x, i) => (
        <div
          key={x}
          className="pointer-events-none absolute bottom-0 -translate-x-1/2 mono text-[9px] md:text-[10px] tracking-[0.14em] uppercase text-mint/75 bg-void/80 px-1.5 py-0.5 whitespace-nowrap"
          style={{ left: `${x * 100}%` }}
        >
          {stages[i]}
        </div>
      ))}
    </div>
  )
}

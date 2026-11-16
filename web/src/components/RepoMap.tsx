import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useReducedMotion } from 'motion/react'
import { useT } from '../lib/i18n'
import type { Artifact, ChainObject, Meta } from '../lib/data'
import { AMBER, MINT, SKY, displayTitle, pictogram, skillLinks, skillSteps, statusColor } from './artifactGlyph'

/**
 * The repository as a wiring diagram: which documents each skill reads and which tool it calls.
 * Nodes and links are the artifacts and their recorded dependencies; nothing is drawn by hand.
 */

const C = {
  kicker: { zh: '仓库接线图', en: 'How the repository is wired' },
  title: { zh: 'Agent 读知识，照 Skill 做，调工具算', en: 'An agent reads the knowledge, follows a skill, calls a tool' },
  hint: { zh: '悬停任意一块，看它连着什么 · 点击查看出处', en: 'Hover a block to see what it connects to · click for its provenance' },
  docs: { zh: '知识文档', en: 'Knowledge' },
  docsSub: { zh: 'Agent 先读', en: 'read first' },
  skills: { zh: 'Skills', en: 'Skills' },
  skillsSub: { zh: 'Agent 照着做', en: 'followed step by step' },
  tools: { zh: '工具', en: 'Tools' },
  toolsSub: { zh: 'Agent 调用', en: 'called for the numbers' },
  steps: { zh: '步', en: 'steps' },
  reads: { zh: '读', en: 'reads' },
  calls: { zh: '调用', en: 'calls' },
}

const W = 1200
const TOP = 74
const NODE_H = 46
const COL = { doc: { x: 24, w: 316 }, skill: { x: 442, w: 316 }, tool: { x: 860, w: 316 } }

function column(n: number, span: number): number[] {
  const gap = Math.min(span / Math.max(n, 1), 112)
  const start = TOP + (span - gap * n) / 2
  return Array.from({ length: n }, (_, i) => start + i * gap + (gap - NODE_H) / 2)
}

function Node({ x, y, w, color, on, dim, dimTo, icon, title, note, href, enter, leave, mono = false }: {
  x: number; y: number; w: number; color: string; on: boolean; dim: boolean; dimTo: number; icon: ReactNode; title: string; note: string; href: string; enter: () => void; leave: () => void; mono?: boolean
}) {
  return (
    <a href={href} onMouseEnter={enter} onMouseLeave={leave} onFocus={enter} onBlur={leave} aria-label={title}>
      <g opacity={dim ? dimTo : 1} style={{ transition: 'opacity .35s' }}>
        <rect x={x} y={y} width={w} height={NODE_H} rx={7} fill="#0c1310" stroke={color} strokeOpacity={on ? 1 : 0.42} strokeWidth={on ? 1.6 : 1} style={on ? { filter: `drop-shadow(0 0 9px ${color}99)` } : undefined} />
        <foreignObject x={x} y={y} width={w} height={NODE_H}>
          <div className="flex h-full items-center gap-2.5 pl-2 pr-3">
            <span className="flex h-[32px] w-[32px] shrink-0 items-center justify-center rounded-[6px] border" style={{ color, borderColor: `${color}55`, background: '#0a100d' }}>{icon}</span>
            <span className={`min-w-0 flex-1 truncate text-ink ${mono ? 'mono text-[10.5px]' : 'text-[12.5px]'}`}>{title}</span>
            <span className="mono text-[9.5px] text-mute shrink-0">{note}</span>
          </div>
        </foreignObject>
      </g>
    </a>
  )
}

export default function RepoMap({ meta, artifacts, chains }: { meta: Meta; artifacts: Artifact[]; chains: Record<string, ChainObject[]> }) {
  const t = useT()
  const reduce = useReducedMotion() ?? false
  const [hover, setHover] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  const m = useMemo(() => {
    const byId = new Map(artifacts.map((a) => [a.id, a]))
    const docs = artifacts.filter((a) => a.kind === 'knowledge_doc')
    const skills = artifacts.filter((a) => a.kind === 'skill')
    const tools = artifacts.filter((a) => a.kind === 'tool')
    const span = Math.max(docs.length, skills.length, tools.length) * 60
    const y = new Map<string, number>()
    column(docs.length, span).forEach((v, i) => y.set(docs[i].id, v))
    column(skills.length, span).forEach((v, i) => y.set(skills[i].id, v))
    column(tools.length, span).forEach((v, i) => y.set(tools[i].id, v))
    const edges = skills.flatMap((s) => {
      const l = skillLinks(s, byId)
      return [
        ...l.docs.filter((d) => y.has(d.id)).map((d) => ({ from: d.id, to: s.id, kind: 'read' as const, color: MINT })),
        ...l.tools.filter((x) => y.has(x.id)).map((x) => ({ from: s.id, to: x.id, kind: 'call' as const, color: statusColor(x.tool?.status) })),
      ]
    })
    return { docs, skills, tools, span, y, edges, taskTitle: new Map(meta.tasks.map((x) => [x.id, x.title])) }
  }, [artifacts, meta])

  // at rest, walk through the skills so the wiring is never a static tangle
  useEffect(() => {
    if (reduce || hover || m.skills.length === 0) return
    const id = setInterval(() => setTick((x) => x + 1), 2600)
    return () => clearInterval(id)
  }, [reduce, hover, m.skills.length])

  const hot = hover ?? (reduce ? null : m.skills[tick % Math.max(m.skills.length, 1)]?.id ?? null)
  const linked = useMemo(() => {
    if (!hot) return null
    const set = new Set<string>([hot])
    for (const e of m.edges) {
      if (e.from === hot) set.add(e.to)
      if (e.to === hot) set.add(e.from)
    }
    return set
  }, [hot, m.edges])
  // a pointer on a block isolates it; the idle walk-through only lowers the rest
  const dimTo = hover ? 0.24 : 0.6
  const H = TOP + m.span + 18
  const heads = [
    { c: COL.doc, label: t(C.docs), sub: t(C.docsSub), n: m.docs.length, color: MINT },
    { c: COL.skill, label: t(C.skills), sub: t(C.skillsSub), n: m.skills.length, color: AMBER },
    { c: COL.tool, label: t(C.tools), sub: t(C.toolsSub), n: m.tools.length, color: SKY },
  ]

  return (
    <div className="mx-auto hidden lg:block max-w-[1240px] px-5 md:px-8 pt-16">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-2">
        <div>
          <div className="mono text-[11px] tracking-[0.22em] uppercase text-mint/80">{t(C.kicker)}</div>
          <h2 className="display text-[1.9rem] md:text-[2.2rem] leading-[1.12] mt-3">{t(C.title)}</h2>
        </div>
        <div className="mono text-[10.5px] text-faint">{t(C.hint)}</div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-6 block w-full h-auto" role="img" aria-label={t(C.title)}>
        {heads.map((h) => (
          <g key={h.label}>
            <text x={h.c.x} y={30} fill={h.color} fontSize="24" fontFamily="var(--font-serif)">{h.n}</text>
            <text x={h.c.x + 18 + String(h.n).length * 13} y={24} fill="#e9efe9" fontSize="13.5" fontWeight="600" fontFamily="var(--font-sans)">{h.label}</text>
            <text x={h.c.x + h.c.w} y={24} fill="#8d9a92" fontSize="10.5" textAnchor="end" fontFamily="var(--font-mono)">{h.sub}</text>
            <line x1={h.c.x} y1={42} x2={h.c.x + h.c.w} y2={42} stroke={h.color} strokeOpacity="0.7" strokeWidth="1.4" />
          </g>
        ))}
        <text x={(COL.doc.x + COL.doc.w + COL.skill.x) / 2} y={62} fill={MINT} fontSize="10" textAnchor="middle" fontFamily="var(--font-mono)">{t(C.reads)} →</text>
        <text x={(COL.skill.x + COL.skill.w + COL.tool.x) / 2} y={62} fill={SKY} fontSize="10" textAnchor="middle" fontFamily="var(--font-mono)">{t(C.calls)} →</text>

        {/* links */}
        {m.edges.map((e) => {
          const from = e.kind === 'read' ? COL.doc : COL.skill
          const to = e.kind === 'read' ? COL.skill : COL.tool
          const x1 = from.x + from.w
          const x2 = to.x
          const y1 = m.y.get(e.from)! + NODE_H / 2
          const y2 = m.y.get(e.to)! + NODE_H / 2
          const on = e.from === hot || e.to === hot
          const mid = (x1 + x2) / 2
          return (
            <path
              key={`${e.from}>${e.to}`}
              d={`M${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`}
              fill="none"
              stroke={e.color}
              strokeWidth={on ? 2 : 1}
              strokeOpacity={on ? 0.95 : linked ? (hover ? 0.08 : 0.2) : 0.3}
              className={on && !reduce ? 'flow-line' : ''}
              style={{ transition: 'stroke-opacity .25s' }}
            />
          )
        })}

        {/* nodes */}
        {m.docs.map((a) => (
          <Node key={a.id} x={COL.doc.x} y={m.y.get(a.id)!} w={COL.doc.w} color={MINT} on={hot === a.id || (!!linked && linked.has(a.id))} dim={!!linked && !linked.has(a.id)} dimTo={dimTo} icon={pictogram(a, 22)} title={a.title} note={String((chains[a.id] ?? []).length)} href={`#/artifact/${encodeURIComponent(a.id)}`} enter={() => setHover(a.id)} leave={() => setHover(null)} />
        ))}
        {m.skills.map((a) => (
          <Node key={a.id} x={COL.skill.x} y={m.y.get(a.id)!} w={COL.skill.w} color={AMBER} on={hot === a.id || (!!linked && linked.has(a.id))} dim={!!linked && !linked.has(a.id)} dimTo={dimTo} icon={pictogram(a, 22)} title={displayTitle(a, m.taskTitle)} note={`${skillSteps(a.body).length} ${t(C.steps)}`} href={`#/artifact/${encodeURIComponent(a.id)}`} enter={() => setHover(a.id)} leave={() => setHover(null)} />
        ))}
        {m.tools.map((a) => {
          const col = statusColor(a.tool?.status)
          return <Node key={a.id} x={COL.tool.x} y={m.y.get(a.id)!} w={COL.tool.w} color={col} on={hot === a.id || (!!linked && linked.has(a.id))} dim={!!linked && !linked.has(a.id)} dimTo={dimTo} icon={pictogram(a, 22)} title={displayTitle(a, m.taskTitle)} note="ƒ(x)" mono href={`#/artifact/${encodeURIComponent(a.id)}`} enter={() => setHover(a.id)} leave={() => setHover(null)} />
        })}
      </svg>
    </div>
  )
}

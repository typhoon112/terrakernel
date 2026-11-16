import type { ReactNode } from 'react'
import { Balance, Boundary, Chain, CoalPlant, Factory, Matrix, Mine, Molecule, Pylon, Standards } from './ClimateIcons'
import type { Artifact, ChainObject, SourceRow } from '../lib/data'

/**
 * How an artifact is drawn on the results page: its pictogram, its display title, and the mix of
 * material formats behind it. The pictogram is picked from words in the artifact's own title, path
 * and tool name; everything else is read from the bundle.
 */

export const MINT = '#4fe3a4'
export const AMBER = '#efb75a'
export const SKY = '#74a9f7'
export const VIOLET = '#b39dfa'
export const ROSE = '#ef7a7a'

const RULES: [RegExp, (size: number) => ReactNode][] = [
  [/plant|电厂/, (s) => <CoalPlant size={s} />],
  [/grid|scope ?2|electricity|电网|电力/, (s) => <Pylon size={s} />],
  [/scope ?3|value.?chain|价值链/, (s) => <Chain size={s} />],
  [/ipcc|inventory|清单/, (s) => <Molecule size={s} />],
  [/mrio|provincial|省际/, (s) => <Matrix size={s} />],
  [/standard|disclosure|披露|标准/, (s) => <Standards size={s} />],
  [/boundary|口径/, (s) => <Boundary size={s} />],
  [/average|平均/, (s) => <Mine size={s} />],
  [/benchmark|基准|responsibility|责任/, (s) => <Balance size={s} />],
]

export function pictogram(a: Artifact, size = 38): ReactNode {
  const own = `${a.title} ${a.path ?? ''} ${a.tool?.name ?? ''}`.toLowerCase()
  for (const [re, icon] of RULES) if (re.test(own)) return icon(size)
  const about = a.description.toLowerCase()
  for (const [re, icon] of RULES) if (re.test(about)) return icon(size)
  return <Factory size={size} />
}

/** Title as people read it: the task title for a skill, the function name for a tool. */
export function displayTitle(a: Artifact, taskTitle: Map<string, string>): string {
  if (a.kind === 'skill') return taskTitle.get(a.id.split(':')[1]) || (a.body?.match(/^#\s+(.+)$/m)?.[1] ?? '').trim() || a.title
  if (a.kind === 'tool') return a.tool?.name ?? a.title
  return a.title
}

/** The numbered steps of a skill's procedure, as written in its SKILL.md. */
export function skillSteps(body?: string): string[] {
  if (!body) return []
  const proc = body.split(/^##\s+Procedure\s*$/m)[1]?.split(/^##\s+/m)[0] ?? ''
  return proc.split(/^(?=\d+\.\s)/m).filter((b) => /^\d+\.\s/.test(b))
}

/** The artifacts a skill reads and calls, resolved from its dependencies. */
export function skillLinks(a: Artifact, byId: Map<string, Artifact>) {
  const pick = (prefix: string) => a.depends_on.filter((d) => d.startsWith(prefix)).map((d) => byId.get(d)).filter((x): x is Artifact => Boolean(x))
  return { docs: pick('doc:'), tools: pick('tool:') }
}

export const statusColor = (status?: string) => (status === 'verified' ? MINT : status === 'tested' ? AMBER : ROSE)

const FORMATS: { tag: string; ext: RegExp; color: string }[] = [
  { tag: 'PDF', ext: /\.pdf$/i, color: MINT },
  { tag: 'DOCX', ext: /\.(docx?|md|txt)$/i, color: VIOLET },
  { tag: 'HTML', ext: /\.html?$/i, color: SKY },
  { tag: 'XLS', ext: /\.(xlsx?|xlsm|csv|tsv|parquet|nc)$/i, color: AMBER },
]

export function formatOf(path: string): { tag: string; color: string } {
  return FORMATS.find((f) => f.ext.test(path)) ?? { tag: (path.split('.').pop() ?? '').toUpperCase().slice(0, 4), color: '#8d9a92' }
}

export type Backing = {
  objects: number
  evidence: number
  sources: number
  types: Record<string, number>
  /** material formats behind the artifact, largest first */
  formats: { tag: string; color: string; n: number }[]
}

/** What stands behind an artifact: knowledge objects, evidence, and the files that evidence is in. */
export function backing(chain: ChainObject[] | undefined, sourcePath: Map<string, string>): Backing {
  const ev = new Set<string>()
  const src = new Set<string>()
  const types: Record<string, number> = {}
  for (const o of chain ?? []) {
    types[o.t] = (types[o.t] ?? 0) + 1
    for (const e of o.evidence) {
      ev.add(e.id)
      src.add(e.source)
    }
  }
  const by = new Map<string, { tag: string; color: string; n: number }>()
  for (const s of src) {
    const f = formatOf(sourcePath.get(s) ?? '')
    by.set(f.tag, { ...f, n: (by.get(f.tag)?.n ?? 0) + 1 })
  }
  return { objects: (chain ?? []).length, evidence: ev.size, sources: src.size, types, formats: [...by.values()].sort((a, b) => b.n - a.n) }
}

export const sourcePaths = (sources: SourceRow[]) => new Map(sources.map((s) => [s.id, s.path]))

/** One small file mark per source file, coloured by format: the material mix at a glance. */
export function SourceStrip({ formats, max = 14 }: { formats: Backing['formats']; max?: number }) {
  const total = formats.reduce((n, f) => n + f.n, 0)
  const marks: string[] = []
  for (const f of formats) for (let i = 0; i < f.n && marks.length < max; i++) marks.push(f.color)
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <span className="flex items-end gap-[3px]" aria-hidden>
        {marks.map((c, i) => (
          <svg key={i} width="9" height="12" viewBox="0 0 9 12">
            <path d="M0.5 0.5h5l3 3v8h-8z" fill={`${c}33`} stroke={c} strokeWidth="1" />
          </svg>
        ))}
        {total > marks.length && <span className="mono text-[9px] text-faint ml-0.5">+{total - marks.length}</span>}
      </span>
      <span className="flex gap-2.5 mono text-[9.5px]">
        {formats.map((f) => (
          <span key={f.tag} style={{ color: f.color }}>
            {f.tag} <span className="tabular text-ink/85">{f.n}</span>
          </span>
        ))}
      </span>
    </div>
  )
}

/** The mark for the skill layer: steps taken in order. */
export function StepsIcon({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden>
      <circle cx="9" cy="36" r="5" />
      <circle cx="24" cy="24" r="5" />
      <circle cx="39" cy="12" r="5" fill="currentColor" fillOpacity="0.25" />
      <path d="M13 33l7-5.5M28 21l7-5.5" />
    </svg>
  )
}

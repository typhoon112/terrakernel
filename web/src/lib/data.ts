import { useEffect, useState } from 'react'

/** Data bundle written by `terrakernel export-web`; see public/data/. */

export type Counts = {
  sources: number
  evidence: number
  objects: number
  objects_by_type: Record<string, number>
  objects_by_basis: Record<string, number>
  objects_by_status: Record<string, number>
  relations: number
  relations_by_type: Record<string, number>
  gaps: number
  gaps_open: number
  gaps_resolved: number
  artifacts: number
  artifacts_by_kind: Record<string, number>
  tools: number
  tools_by_status: Record<string, number>
}

export type Meta = {
  bundle_version: number
  name: string
  goal: string
  model: string
  extract_model: string | null
  tasks: { id: string; title: string; prompt: string; acceptance: string[] }[]
  built_at: string
  stages: Record<string, { seconds: number | null; model_calls: number | null; cost: number | null }>
  cost_total: { model_calls: number; cost_usd_estimate: number }
  validation: { summary: Record<string, number>; checks: Record<string, Record<string, number>> }
  counts: Counts
}

export type SourceRow = {
  id: string
  path: string
  kind: string
  size: number
  title: string
  evidence: number
  objects: number
  in_artifacts: number
}

export type CatalogObject = {
  id: string
  t: string
  n: string
  s: string
  b: string
  st: string
  src: string[]
  ev: number
  loc: { source: string; page: number | null; section: string } | null
}

export type ToolCase = { id: string; quote?: string; evidence?: string; expected?: number; inputs?: Record<string, unknown> }

export type ToolInfo = {
  name: string
  status: string
  strategy: string
  description: string
  inputs: { name: string; kind: string; description: string; unit: string | null }[]
  output_description: string
  output_unit: string | null
  knowledge: string | null
  test_file: string | null
  tests: { passed: number; failed: number } | null
  reference_cases: number | null
  problems: string[]
  cases: ToolCase[]
}

export type Artifact = {
  id: string
  kind: string
  path: string | null
  status: string
  depends_on: string[]
  title: string
  description: string
  objects: string[]
  tool?: ToolInfo
  body?: string
}

export type EvidenceItem = {
  id: string
  kind: string
  role: string
  quote: string
  loc: string
  source: string
  page: number | null
  crop?: string
}

export type ChainObject = {
  id: string
  t: string
  n: string
  s: string
  b: string
  st: string
  evidence: EvidenceItem[]
  attrs: Record<string, unknown>
}

export type ReplayItem = {
  /** ISO timestamp from the build log */
  t: string
  /** index of the run (attempt) of the stage that produced this result */
  a: number
  msg: string
  source?: string
  evidence?: number
  objects?: number
  gaps?: number
  tool?: string
  status?: string
}

export type StageAttempt = {
  n: number
  start: string
  end: string
  seconds: number
  /** done | failed | interrupted */
  status: string
  /** results of this run that the finished build kept */
  kept_items: number
  used: boolean
  warnings: number
  model_calls: number | null
  error: string | null
}

export type StageRun = {
  stage: string
  zh: string
  en: string
  /** start / end / seconds / model_calls describe the last successful run of the stage */
  start: string
  end: string
  seconds: number
  model_calls: number
  warnings: number
  summary: string
  /** every run of the stage, including failed and interrupted ones */
  attempts: StageAttempt[]
  /** ingest and extract: the kept result of every source (possibly from an earlier run) */
  items: ReplayItem[]
}

export type Replay = {
  t0: string
  t1: string
  /** seconds between the first and the last event of the log, failures and pauses included */
  wall_seconds: number
  stages: StageRun[]
  relate_batches: { t: string; msg: string }[]
  relate_totals: { t: string; msg: string }[]
  notes: string[]
}

export type Graph = {
  nodes: { id: string; kind: string; label: string; type: string; w?: number; used?: number; basis?: string; status?: string }[]
  edges: { s: string; t: string; k: string; n?: number }[]
  relations: { s: string; t: string; k: string; note: string }[]
}

export type Exhibit = {
  id: string
  kind: string
  source: string
  path: string
  loc: string
  page: number | null
  text: string
  /** tables only: rows of cells as recorded */
  rows?: string[][]
}

export type LibrarySource = {
  id: string
  path: string
  kind: string
  title: string
  evidence: number
  objects: number
  in_artifacts: number
  by_type: Record<string, number>
  top: { id: string; t: string; n: string }[]
  figures: { src: string; page: number | null; caption: string }[]
}

const cache = new Map<string, unknown>()

async function getJSON<T>(file: string): Promise<T> {
  if (cache.has(file)) return cache.get(file) as T
  const res = await fetch(`data/${file}`)
  if (!res.ok) throw new Error(`export-web bundle: ${file} not found (${res.status})`)
  const data = (await res.json()) as T
  cache.set(file, data)
  return data
}

let metaPromise: Promise<Meta> | null = null
export const loadMeta = () => (metaPromise ??= getJSON<Meta>('meta.json'))
export const loadSources = () => getJSON<SourceRow[]>('sources.json')
export const loadArtifacts = () => getJSON<{ artifacts: Artifact[]; plan_summary: string; issues: string[] }>('artifacts.json')
export const loadChains = () => getJSON<Record<string, ChainObject[]>>('chains.json')
export const loadReplay = () => getJSON<Replay>('replay.json')
export const loadGraph = () => getJSON<Graph>('graph.json')
export const loadCatalog = () => getJSONLine<CatalogObject>('catalog.jsonl')
export const loadExhibits = () => getJSON<Record<string, Exhibit>>('exhibits.json')
export const loadLibrary = () => getJSON<LibrarySource[]>('library.json')

/** Parse a number as printed in a source table ("1,219", "−42", "-"), or null. */
export function cellNumber(cell: string | undefined): number | null {
  if (cell == null) return null
  const t = cell.replace(/[,\s]/g, '').replace(/[−–—]/g, '-')
  if (!/^-?\d+(\.\d+)?$/.test(t)) return null
  return Number(t)
}

async function getJSONLine<T>(file: string): Promise<T[]> {
  if (cache.has(file)) return cache.get(file) as T[]
  const res = await fetch(`data/${file}`)
  if (!res.ok) throw new Error(`export-web bundle: ${file} not found (${res.status})`)
  const text = await res.text()
  const rows = text.split('\n').filter(Boolean).map((l) => JSON.parse(l) as T)
  cache.set(file, rows)
  return rows
}

export function useAsync<T>(load: () => Promise<T>, deps: unknown[] = []): { data: T | null; error: string | null } {
  const [state, setState] = useState<{ data: T | null; error: string | null }>({ data: null, error: null })
  useEffect(() => {
    let alive = true
    load()
      .then((d) => alive && setState({ data: d, error: null }))
      .catch((e) => alive && setState({ data: null, error: String(e?.message ?? e) }))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return state
}

export const fmt = (n: number | null | undefined) =>
  n == null ? '–' : n >= 10000 ? n.toLocaleString('en-US') : String(n)

export const fmtCompact = (n: number) =>
  n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e4 ? `${(n / 1e3).toFixed(1)}k` : n.toLocaleString('en-US')

export const duration = (s: number) => (s >= 90 ? `${Math.round(s / 60)} min` : `${Math.round(s)} s`)

export const typeColor: Record<string, string> = {
  concept: '#4fe3a4',
  claim: '#74a9f7',
  method: '#b39dfa',
  constraint: '#efb75a',
  dataset: '#5fd6d6',
  capability: '#f28fbf',
  source: '#6f7f76',
}

export const kindLabel: Record<string, { zh: string; en: string }> = {
  concept: { zh: '概念', en: 'Concept' },
  claim: { zh: '论断', en: 'Claim' },
  method: { zh: '方法', en: 'Method' },
  constraint: { zh: '约束', en: 'Constraint' },
  dataset: { zh: '数据', en: 'Dataset' },
  capability: { zh: '能力', en: 'Capability' },
}

export const basisLabel: Record<string, { zh: string; en: string }> = {
  stated: { zh: '资料陈述', en: 'Stated' },
  inferred: { zh: '模型推导', en: 'Inferred' },
  measured: { zh: '工具实测', en: 'Measured' },
  human_confirmed: { zh: '人工确认', en: 'Human-confirmed' },
}

export const statusLabel: Record<string, { zh: string; en: string }> = {
  verified: { zh: '已验证', en: 'Verified' },
  tested: { zh: '仅性质测试', en: 'Property-tested' },
  failed: { zh: '未开放', en: 'Withheld' },
  generated: { zh: '已生成', en: 'Generated' },
  blocked: { zh: '受阻', en: 'Blocked' },
}

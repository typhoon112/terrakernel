import { useMemo } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import {
  fmt,
  kindLabel,
  loadArtifacts,
  loadChains,
  loadMeta,
  statusLabel,
  typeColor,
  useAsync,
  type Artifact,
  type ChainObject,
  type Meta,
} from '../lib/data'
import { ErrorBox, Panel, SectionHead, Skeleton, Tag } from '../components/ui'
import { Link } from '../lib/router'
import { useLang, useT } from '../lib/i18n'

/* ------------------------------------------------------------------ copy */

type Bi<T = string> = { zh: T; en: T }
type Tr = <T>(x: Bi<T>) => T

const C = {
  kicker: { zh: 'WHAT WAS BUILT · 生成结果', en: 'WHAT WAS BUILT · THE GENERATED REPOSITORY' },
  title: { zh: '三十四个文件，分为三层', en: 'Thirty-four files, in three layers' },
  intro: {
    zh: '这次构建从一个研究仓库编译出 34 个产物：知识文档记录公式与边界，skill 把方法写成可执行的流程，工具把它们变成能跑的 Python 函数。下面的每一个数字、路径和引文都直接来自构建数据包。',
    en: 'One build compiled 34 artifacts: knowledge documents record formulas and boundaries, skills turn the method into an executable procedure, and tools make it runnable Python. Every number, path and quote below comes from the build bundle.',
  },
  artifactsByKind: { zh: '产物类型', en: 'Artifacts by kind' },
  validation: { zh: '一致性校验', en: 'Consistency checks' },
  validationNote: {
    zh: '校验在构建时对每个对象与证据链执行；warn 是记录在案、不阻断产物的待确认项。',
    en: 'Checks run at build time over every object and evidence chain; warnings are recorded, non-blocking open items.',
  },
  pass: { zh: '通过', en: 'pass' },
  fail: { zh: '失败', en: 'fail' },
  warn: { zh: '警告', en: 'warn' },
  support: { zh: '支撑文件', en: 'Support files' },
  supportNote: {
    zh: '除三层主体外，仓库还包含运行时、配置、测试、入口文件与适配器——没有它们，文档与工具无法被自动调用。',
    en: 'Besides the three layers the repository ships a runtime, configs, tests, entry files and adapters — without them nothing is callable by an agent.',
  },
  knowledge: { zh: '知识层', en: 'Knowledge layer' },
  knowledgeWhat: {
    zh: '把资料中的公式、边界、数据与限制抽成带证据的知识对象，再编成可读文档。每条结论都能回到原文的页与段落。',
    en: 'Formulas, boundaries, data and limits extracted from the materials as evidence-backed objects, compiled into readable documents. Every statement leads back to a page and paragraph.',
  },
  skills: { zh: 'Skill 层', en: 'Skill layer' },
  skillsWhat: {
    zh: '把方法写成 agent 可执行的流程：何时使用、按什么顺序、依赖哪些工具。skill 本身不产生数字，它组织调用。',
    en: 'The method written as a procedure an agent can execute: when to use it, in what order, and which tools it depends on. A skill produces no numbers; it organises the calls.',
  },
  tools: { zh: '工具层', en: 'Tool layer' },
  toolsWhat: {
    zh: '从公式生成的 Python 函数。只有能从原文同时取到输入与期望输出的算例才会进入测试；取不到的，工具就停在候选状态。',
    en: 'Python functions generated from formulas. Only cases whose inputs and expected outputs both exist in the materials become tests; where they do not, the tool stops at candidate status.',
  },
  objects: { zh: '知识对象', en: 'objects' },
  evidence: { zh: '证据单元', en: 'evidence units' },
  sources: { zh: '份资料', en: 'sources' },
  path: { zh: '路径', en: 'Path' },
  open: { zh: '打开产物', en: 'Open artifact' },
  task: { zh: '对应任务', en: 'Task' },
  toolsDep: { zh: '依赖工具', en: 'Tools used' },
  docsDep: { zh: '依据文档', en: 'Grounded in' },
  knowledgeDoc: { zh: '计算说明', en: 'Computation doc' },
  cases: { zh: '原文算例', en: 'Reference cases' },
  noCases: { zh: '无可引用的算例', en: 'No case quotable from the materials' },
  expected: { zh: '期望值', en: 'expected' },
  tests: { zh: '测试', en: 'Tests' },
  noTests: { zh: '未运行测试', en: 'No tests run' },
  problems: { zh: '记录的问题', en: 'Recorded problems' },
  withheld: { zh: '未开放', en: 'Withheld' },
  withheldNote: {
    zh: '这个工具保留为失败状态，原因逐条写在下面：原文只给了公式和区间，没有给出任何一组完整输入。我们不补假设，也不给结果。',
    en: 'This tool is kept in a failed state and the reasons are quoted below: the materials give a formula and ranges, never one complete set of inputs. We add no assumptions and return no result.',
  },
  docKind: { zh: '文档', en: 'Document' },
  compKind: { zh: '计算', en: 'Computation' },
  bandCount: { zh: '个产物', en: 'artifacts' },
  objectsSpan: { zh: '个知识对象', en: 'knowledge objects' },
  evidenceSpan: { zh: '个证据单元', en: 'evidence units' },
  evidenceOverlap: {
    zh: '证据数为层内去重合计',
    en: 'evidence counted once across the band',
  },
  skipNote: {
    zh: '该产物在构建时被跳过，正文为空。',
    en: 'Skipped during the build; the body is empty.',
  },
  statusLabel: { zh: '状态', en: 'Status' },
  bundle: { zh: '数据包', en: 'Bundle' },
  jumpHint: { zh: '点击任意卡片进入产物详情', en: 'Open any card for the artifact detail' },
}

const KIND_ORDER = [
  'knowledge_doc',
  'computation_doc',
  'skill',
  'tool',
  'config',
  'runtime',
  'test',
  'entry',
  'adapter',
  'source',
]

const KIND_ZH: Record<string, { zh: string; en: string }> = {
  knowledge_doc: { zh: '知识文档', en: 'Knowledge doc' },
  computation_doc: { zh: '计算文档', en: 'Computation doc' },
  skill: { zh: 'Skill', en: 'Skill' },
  tool: { zh: '工具', en: 'Tool' },
  config: { zh: '配置', en: 'Config' },
  runtime: { zh: '运行时', en: 'Runtime' },
  test: { zh: '测试', en: 'Test' },
  entry: { zh: '入口文件', en: 'Entry' },
  adapter: { zh: '适配器', en: 'Adapter' },
  source: { zh: '原始资料', en: 'Materials' },
}

const SUPPORT_KINDS = ['runtime', 'config', 'test', 'entry', 'adapter', 'source']

const STATUS_COLOR: Record<string, 'mint' | 'amber' | 'rose' | 'sky' | 'violet' | 'mute'> = {
  verified: 'mint',
  tested: 'amber',
  failed: 'rose',
  blocked: 'rose',
  generated: 'sky',
  candidate: 'mute',
  skipped: 'mute',
}

/* --------------------------------------------------------------- helpful */

/** Bundle records a few case quotes as UTF-8 bytes decoded as latin-1; repair only when that round-trip is valid. */
function repairText(s: string): string {
  if (!/[ÃÂåæçèéð]/.test(s)) return s
  const bytes = new Uint8Array(s.length)
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i)
    if (c > 0xff) return s
    bytes[i] = c
  }
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    return s
  }
}

function firstHeading(body: string | undefined): string {
  if (!body) return ''
  const line = body.split('\n').find((l) => l.startsWith('# '))
  return line ? line.replace(/^#\s*/, '').trim() : ''
}

function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max - 1).trimEnd()}…` : s
}

const num = fmt

type ArtStats = { ev: number; sources: number; types: Record<string, number> }

function buildStats(chains: Record<string, ChainObject[]> | null): Record<string, ArtStats> {
  const out: Record<string, ArtStats> = {}
  if (!chains) return out
  for (const [id, objs] of Object.entries(chains)) {
    const ev = new Set<string>()
    const src = new Set<string>()
    const types: Record<string, number> = {}
    for (const o of objs) {
      types[o.t] = (types[o.t] ?? 0) + 1
      for (const e of o.evidence ?? []) {
        if (e?.id) ev.add(e.id)
        if (e?.source) src.add(e.source)
      }
    }
    out[id] = { ev: ev.size, sources: src.size, types }
  }
  return out
}

function bandTotals(ids: string[], chains: Record<string, ChainObject[]> | null, stats: Record<string, ArtStats>) {
  const ev = new Set<string>()
  const src = new Set<string>()
  let objects = 0
  for (const id of ids) {
    objects += stats[id] ? Object.values(stats[id].types).reduce((a, b) => a + b, 0) : 0
    for (const o of chains?.[id] ?? []) {
      for (const e of o.evidence ?? []) {
        if (e?.id) ev.add(e.id)
        if (e?.source) src.add(e.source)
      }
    }
  }
  return { objects, ev: ev.size, sources: src.size }
}

/* --------------------------------------------------------------- pieces */

function TypePills({ types }: { types: Record<string, number> }) {
  const t = useT() as Tr
  const entries = Object.entries(types)
    .filter(([k]) => k !== 'source')
    .sort((a, b) => b[1] - a[1])
  if (!entries.length) return null
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([k, n]) => {
        const color = typeColor[k] ?? '#8d9a92'
        const label = kindLabel[k]
        return (
          <span
            key={k}
            className="inline-flex items-center gap-1.5 border rounded-full px-2 py-0.5 mono text-[10.5px] tabular"
            style={{ color, borderColor: `${color}44`, background: `${color}0d` }}
          >
            {label ? t(label) : k}
            <span className="opacity-60">{n}</span>
          </span>
        )
      })}
    </div>
  )
}

function Metric({ n, label, accent }: { n: string; label: string; accent?: string }) {
  return (
    <div className="min-w-0">
      <div className="display tabular text-[22px] leading-none" style={accent ? { color: accent } : undefined}>
        {n}
      </div>
      <div className="mt-1 text-[11px] text-faint leading-tight">{label}</div>
    </div>
  )
}

function BandHeader({
  index,
  name,
  what,
  accent,
  artifacts,
  objects,
  evidence,
  sources,
  note,
}: {
  index: string
  name: Bi
  what: Bi
  accent: string
  artifacts: number
  objects: number
  evidence: number
  sources: number
  note?: Bi
}) {
  const t = useT() as Tr
  return (
    <div className="grid md:grid-cols-[minmax(0,1fr)_auto] gap-x-10 gap-y-6 items-end pb-6 mb-8 hairline">
      <div className="flex items-start gap-5">
        <div
          className="display tabular text-[64px] md:text-[84px] leading-[0.8] shrink-0 select-none"
          style={{ color: accent, opacity: 0.24 }}
          aria-hidden
        >
          {index}
        </div>
        <div className="min-w-0">
          <h2 className="display text-[28px] md:text-[34px] leading-tight text-ink">{t(name)}</h2>
          <p className="mt-3 text-[13.5px] leading-relaxed text-mute max-w-xl">{t(what)}</p>
          {note && <p className="mt-2 text-[11.5px] text-faint leading-relaxed max-w-xl">{t(note)}</p>}
        </div>
      </div>
      <div className="flex items-end gap-7 md:gap-8 md:justify-end flex-wrap">
        <Metric n={num(artifacts)} label={t(C.bandCount)} />
        <Metric n={num(objects)} label={t(C.objectsSpan)} accent={accent} />
        <Metric n={num(evidence)} label={t(C.evidenceSpan)} />
        <Metric n={num(sources)} label={t(C.sources)} />
      </div>
    </div>
  )
}

function DocCard({ a, stats }: { a: Artifact; stats: ArtStats | undefined }) {
  const t = useT() as Tr
  const { lang } = useLang()
  const title = a.title || firstHeading(a.body) || a.id
  const kindText = a.kind === 'knowledge_doc' ? t(C.docKind) : t(C.compKind)
  const empty = !a.body
  return (
    <Link to={`/artifact/${encodeURIComponent(a.id)}`} className="block h-full group">
      <Panel className="p-5 h-full flex flex-col clip-corner">
        <div className="flex items-center gap-2 mb-3">
          <span className="mono text-[10px] tracking-[0.18em] uppercase text-faint">{kindText}</span>
          <span className="flex-1" />
          <Tag color={STATUS_COLOR[a.status] ?? 'mute'}>{statusLabel[a.status]?.[lang] ?? a.status}</Tag>
        </div>
        <h3 className="display text-[19px] leading-snug text-ink group-hover:text-mint transition-colors">{title}</h3>
        {a.description ? (
          <p className="mt-2 text-[12.5px] leading-relaxed text-mute line-clamp-3">{a.description}</p>
        ) : (
          <p className="mt-2 text-[12.5px] leading-relaxed text-faint">{empty ? t(C.skipNote) : ''}</p>
        )}
        <div className="mono text-[10.5px] text-faint mt-3 break-all">{a.path ?? a.id}</div>
        <div className="mt-auto pt-4">
          {stats && Object.keys(stats.types).length > 0 && <TypePills types={stats.types} />}
          <div className="hairline mt-3 pt-3 flex items-center gap-6">
            <Metric n={num(stats ? Object.values(stats.types).reduce((x, y) => x + y, 0) : a.objects.length)} label={t(C.objects)} />
            <Metric n={num(stats?.ev ?? null)} label={t(C.evidence)} />
            <Metric n={num(stats?.sources ?? null)} label={t(C.sources)} />
          </div>
        </div>
      </Panel>
    </Link>
  )
}

function SkillCard({
  a,
  stats,
  meta,
}: {
  a: Artifact
  stats: ArtStats | undefined
  meta: Meta | null
}) {
  const t = useT() as Tr
  const { lang } = useLang()
  const name = a.id.replace(/^skill:/, '')
  const title = firstHeading(a.body) || a.title || name
  const task = meta?.tasks.find((x) => x.id === name)
  const toolDeps = a.depends_on.filter((d) => d.startsWith('tool:'))
  const docDeps = a.depends_on.filter((d) => d.startsWith('doc:'))
  return (
    <Link to={`/artifact/${encodeURIComponent(a.id)}`} className="block h-full group">
      <Panel className="p-5 h-full flex flex-col clip-corner">
        <div className="flex items-center gap-2 mb-3">
          <span className="mono text-[10px] tracking-[0.18em] uppercase text-faint">SKILL</span>
          <span className="flex-1" />
          <Tag color={STATUS_COLOR[a.status] ?? 'mute'}>{statusLabel[a.status]?.[lang] ?? a.status}</Tag>
        </div>
        <div className="mono text-[12px] text-violet/90 truncate">{name}</div>
        <h3 className="display text-[18px] leading-snug text-ink mt-1.5 group-hover:text-mint transition-colors">{title}</h3>
        {task && (
          <div className="mt-2 text-[12px] text-mute leading-relaxed">
            <span className="text-faint">{t(C.task)} </span>
            {task.title}
          </div>
        )}
        <div className="mono text-[10.5px] text-faint mt-2 break-all">{a.path ?? ''}</div>

        <div className="mt-3 space-y-2">
          <div>
            <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-faint mb-1">{t(C.toolsDep)}</div>
            <div className="flex flex-wrap gap-1">
              {toolDeps.length ? (
                toolDeps.map((d) => (
                  <span key={d} className="mono text-[10px] text-amber/90 border border-amber/25 rounded-full px-1.5 py-0.5">
                    {d.replace(/^tool:/, '')}
                  </span>
                ))
              ) : (
                <span className="text-[11px] text-faint">—</span>
              )}
            </div>
          </div>
          {docDeps.length > 0 && (
            <div>
              <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-faint mb-1">{t(C.docsDep)}</div>
              <div className="text-[10.5px] text-mute/90 leading-relaxed">
                {docDeps.map((d) => d.replace(/^doc:/, '').split('/').pop()).join(' · ')}
              </div>
            </div>
          )}
        </div>

        <div className="mt-auto pt-4">
          <div className="hairline pt-3 flex items-center gap-6">
            <Metric n={num(stats ? Object.values(stats.types).reduce((x, y) => x + y, 0) : a.objects.length)} label={t(C.objects)} />
            <Metric n={num(stats?.ev ?? null)} label={t(C.evidence)} accent="#b39dfa" />
            <Metric n={num(stats?.sources ?? null)} label={t(C.sources)} />
          </div>
        </div>
      </Panel>
    </Link>
  )
}

function ToolCard({ a, stats }: { a: Artifact; stats: ArtStats | undefined }) {
  const t = useT() as Tr
  const { lang } = useLang()
  const tool = a.tool
  if (!tool) return null
  const withheld = tool.status === 'failed'
  const accent = withheld ? '#ef7a7a' : tool.status === 'verified' ? '#4fe3a4' : '#efb75a'
  const tests = tool.tests
  return (
    <Panel className={`p-6 h-full flex flex-col ${withheld ? 'border-rose/30' : ''}`} hover={false}>
      <Link to={`/artifact/${encodeURIComponent(a.id)}`} className="group block">
        <div className="flex items-center gap-2 mb-3">
          <span className="mono text-[10px] tracking-[0.18em] uppercase text-faint">TOOL</span>
          <span className="flex-1" />
          <Tag color={withheld ? 'rose' : tool.status === 'verified' ? 'mint' : 'amber'}>
            {withheld ? t(C.withheld) : statusLabel[tool.status]?.[lang] ?? tool.status}
          </Tag>
        </div>
        <h3 className="mono text-[15px] leading-snug text-ink group-hover:text-mint transition-colors break-all">
          {tool.name}
        </h3>
        <p className="mt-2 text-[12.5px] leading-relaxed text-mute">{tool.description}</p>
      </Link>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
        <div className="min-w-0">
          <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-faint mb-1">{t(C.knowledgeDoc)}</div>
          <div className="mono text-[10.5px] text-mute break-all leading-relaxed">{tool.knowledge ?? '—'}</div>
        </div>
        <div className="min-w-0">
          <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-faint mb-1">{t(C.tests)}</div>
          {tests ? (
            <div className="mono text-[11px] tabular">
              <span className="text-mint">{tests.passed} pass</span>
              <span className="text-faint"> / </span>
              <span className={tests.failed ? 'text-rose' : 'text-faint'}>{tests.failed} fail</span>
            </div>
          ) : (
            <div className="text-[11px] text-faint">{t(C.noTests)}</div>
          )}
        </div>
        <div className="min-w-0">
          <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-faint mb-1">{t(C.objects)}</div>
          <div className="display tabular text-[20px] leading-none text-ink">
            {num(stats ? Object.values(stats.types).reduce((x, y) => x + y, 0) : a.objects.length)}
          </div>
        </div>
        <div className="min-w-0">
          <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-faint mb-1">{t(C.sources)}</div>
          <div className="display tabular text-[20px] leading-none" style={{ color: accent }}>
            {num(stats?.sources ?? null)}
          </div>
        </div>
      </div>

      {stats && Object.keys(stats.types).length > 0 && (
        <div className="mt-4">
          <TypePills types={stats.types} />
        </div>
      )}

      <div className="mt-5">
        <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-faint mb-2">{t(C.cases)}</div>
        {tool.cases.length ? (
          <ul className="space-y-2.5">
            {tool.cases.map((c) => (
              <li key={c.id} className="border-l border-line-2 pl-3">
                <div className="mono text-[11px] leading-relaxed text-ink/85">
                  “{truncate(repairText(c.quote ?? ''), 120)}”
                </div>
                <div className="mono text-[9.5px] text-faint mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5">
                  <span className="text-mint/70">{c.evidence ?? '—'}</span>
                  {c.expected != null && (
                    <span>
                      {t(C.expected)} <span className="tabular">{c.expected}</span>
                    </span>
                  )}
                  <span>{c.id}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-[11.5px] text-faint italic">{t(C.noCases)}</div>
        )}
      </div>

      {tool.problems.length > 0 && (
        <div className={`mt-auto pt-5 ${withheld ? '' : ''}`}>
          {withheld && (
            <p className="text-[11.5px] leading-relaxed text-rose/75 mb-2 max-w-prose">{t(C.withheldNote)}</p>
          )}
          <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-faint mb-1.5">{t(C.problems)}</div>
          <ul className="space-y-1.5">
            {tool.problems.slice(0, withheld ? 4 : 2).map((p, i) => (
              <li key={i} className="flex gap-2 text-[11px] leading-relaxed text-mute">
                <span className={withheld ? 'text-rose/70' : 'text-amber/70'} aria-hidden>
                  —
                </span>
                <span>{repairText(p)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  )
}

/* --------------------------------------------------------------- page */

export default function Layers() {
  const t = useT() as Tr
  const { lang } = useLang()
  const reduce = useReducedMotion()

  const metaQ = useAsync(loadMeta)
  const artQ = useAsync(loadArtifacts)
  const chainsQ = useAsync(loadChains)

  const meta = metaQ.data
  const artifacts = artQ.data?.artifacts ?? null
  const chains = chainsQ.data ?? null
  const error = metaQ.error ?? artQ.error ?? chainsQ.error

  const stats = useMemo(() => buildStats(chains), [chains])

  const byKind = useMemo(() => {
    const map: Record<string, Artifact[]> = {}
    for (const a of artifacts ?? []) (map[a.kind] ??= []).push(a)
    return map
  }, [artifacts])

  const docs = useMemo(
    () => [...(byKind.knowledge_doc ?? []), ...(byKind.computation_doc ?? [])],
    [byKind],
  )
  const skills = byKind.skill ?? []
  const tools = byKind.tool ?? []

  const docTotals = useMemo(() => bandTotals(docs.map((d) => d.id), chains, stats), [docs, chains, stats])
  const skillTotals = useMemo(() => bandTotals(skills.map((d) => d.id), chains, stats), [skills, chains, stats])
  const toolTotals = useMemo(() => bandTotals(tools.map((d) => d.id), chains, stats), [tools, chains, stats])

  const support = useMemo(
    () =>
      (artifacts ?? [])
        .filter((a) => SUPPORT_KINDS.includes(a.kind))
        .sort((a, b) => SUPPORT_KINDS.indexOf(a.kind) - SUPPORT_KINDS.indexOf(b.kind)),
    [artifacts],
  )

  const kindCounts = useMemo(() => {
    const src = meta?.counts.artifacts_by_kind ?? {}
    return KIND_ORDER.filter((k) => (src[k] ?? 0) > 0).map((k) => [k, src[k]] as const)
  }, [meta])

  const motionProps = (delay = 0) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 16 },
          whileInView: { opacity: 1, y: 0 },
          viewport: { once: true, margin: '-60px' },
          transition: { duration: 0.6, delay, ease: [0.2, 0.7, 0.2, 1] as [number, number, number, number] },
        }

  if (error)
    return (
      <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16">
        <ErrorBox msg={error} />
      </div>
    )
  if (!artifacts || !meta)
    return (
      <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16">
        <Skeleton />
      </div>
    )

  const v = meta.validation.summary
  const passN = v.pass ?? 0
  const warnN = v.warn ?? 0
  const failN = v.fail ?? 0

  return (
    <div className="bg-void">
      {/* ------------------------------------------------------- hero */}
      <section className="relative border-b border-line overflow-hidden">
        <div className="absolute inset-0 bg-radial opacity-70" aria-hidden />
        <div
          className="absolute inset-0 bg-grid opacity-40 [mask-image:radial-gradient(ellipse_at_60%_0%,black_20%,transparent_70%)]"
          aria-hidden
        />
        <div className="relative mx-auto max-w-[1240px] px-5 md:px-8 pt-14 md:pt-20 pb-10 md:pb-14">
          <motion.div {...motionProps(0)}>
            <SectionHead kicker={t(C.kicker)} title={t(C.title)} intro={t(C.intro)} />
          </motion.div>

          <motion.div {...motionProps(0.08)} className="mt-10 md:mt-12 grid gap-px bg-line grid-cols-1 md:grid-cols-[1.35fr_1fr]">
            {/* artifacts by kind */}
            <div className="bg-panel p-5 md:p-6">
              <div className="flex items-baseline justify-between gap-4 mb-4">
                <div className="mono text-[10px] tracking-[0.2em] uppercase text-mint/80">{t(C.artifactsByKind)}</div>
                <div className="mono text-[10px] text-faint">
                  {t(C.bundle)} v{meta.bundle_version}
                </div>
              </div>
              <ul className="grid grid-cols-2 sm:grid-cols-3 gap-x-5 gap-y-2.5">
                {kindCounts.map(([k, n]) => (
                  <li key={k} className="flex items-baseline justify-between gap-2 border-b border-line pb-1.5">
                    <span className="text-[12px] text-mute truncate">{t(KIND_ZH[k] ?? { zh: k, en: k })}</span>
                    <span className="mono text-[12px] tabular text-ink">{n}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* validation */}
            <div className="bg-panel p-5 md:p-6 flex flex-col">
              <div className="mono text-[10px] tracking-[0.2em] uppercase text-mint/80 mb-4">{t(C.validation)}</div>
              <div className="flex items-end gap-6">
                <Metric n={num(passN)} label={t(C.pass)} accent="#4fe3a4" />
                <Metric n={num(failN)} label={t(C.fail)} accent={failN ? '#ef7a7a' : undefined} />
                <Metric n={num(warnN)} label={t(C.warn)} accent="#efb75a" />
                {meta.counts.gaps != null && (
                  <Metric n={num(meta.counts.gaps_open)} label={lang === 'zh' ? '待补项' : 'open gaps'} />
                )}
              </div>
              <p className="mt-4 text-[11.5px] leading-relaxed text-faint">{t(C.validationNote)}</p>
            </div>
          </motion.div>

          {/* support files */}
          <motion.div {...motionProps(0.14)} className="mt-6">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-3">
              <div className="mono text-[10px] tracking-[0.2em] uppercase text-mute">{t(C.support)}</div>
              <div className="text-[11.5px] text-faint max-w-2xl leading-relaxed">{t(C.supportNote)}</div>
            </div>
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              {support.map((a) => (
                <Link key={a.id} to={`/artifact/${encodeURIComponent(a.id)}`} className="group inline-flex items-baseline gap-2">
                  <span
                    className="mono text-[9px] uppercase tracking-wider px-1.5 py-0.5 border rounded-sm"
                    style={{ color: '#8d9a92', borderColor: 'rgba(214,234,223,0.18)' }}
                  >
                    {t(KIND_ZH[a.kind] ?? { zh: a.kind, en: a.kind })}
                  </span>
                  <span className="mono text-[11px] text-mute group-hover:text-mint transition-colors break-all">
                    {a.path ?? a.id}
                  </span>
                </Link>
              ))}
            </div>
          </motion.div>
        </div>
      </section>

      {/* ------------------------------------------------ knowledge */}
      <section id="layer-knowledge" className="border-b border-line">
        <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-14 md:py-20">
          <motion.div {...motionProps(0)}>
            <BandHeader
              index="01"
              name={C.knowledge}
              what={C.knowledgeWhat}
              accent="#4fe3a4"
              artifacts={docs.length}
              objects={docTotals.objects}
              evidence={docTotals.ev}
              sources={docTotals.sources}
              note={C.evidenceOverlap}
            />
          </motion.div>
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {docs.map((a, i) => (
              <motion.div key={a.id} {...motionProps(Math.min(i, 6) * 0.04)}>
                <DocCard a={a} stats={stats[a.id]} />
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* --------------------------------------------------- skills */}
      <section id="layer-skills" className="border-b border-line bg-deep/40">
        <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-14 md:py-20">
          <motion.div {...motionProps(0)}>
            <BandHeader
              index="02"
              name={C.skills}
              what={C.skillsWhat}
              accent="#b39dfa"
              artifacts={skills.length}
              objects={skillTotals.objects}
              evidence={skillTotals.ev}
              sources={skillTotals.sources}
            />
          </motion.div>
          <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4">
            {skills.map((a, i) => (
              <motion.div key={a.id} {...motionProps(Math.min(i, 6) * 0.05)}>
                <SkillCard a={a} stats={stats[a.id]} meta={meta} />
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------- tools */}
      <section id="layer-tools">
        <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-14 md:py-20">
          <motion.div {...motionProps(0)}>
            <BandHeader
              index="03"
              name={C.tools}
              what={C.toolsWhat}
              accent="#efb75a"
              artifacts={tools.length}
              objects={toolTotals.objects}
              evidence={toolTotals.ev}
              sources={toolTotals.sources}
            />
          </motion.div>
          <div className="grid md:grid-cols-2 gap-4">
            {tools.map((a, i) => (
              <motion.div key={a.id} {...motionProps(Math.min(i, 6) * 0.05)} className="h-full">
                <ToolCard a={a} stats={stats[a.id]} />
              </motion.div>
            ))}
          </div>

          <p className="mt-8 text-[11.5px] text-faint mono">{t(C.jumpHint)}</p>
        </div>
      </section>
    </div>
  )
}

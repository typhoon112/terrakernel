import { useMemo, type ReactNode } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { useT } from '../lib/i18n'
import { kindLabel, typeColor } from '../lib/data'
import type { Artifact, ChainObject, EvidenceItem, Meta, SourceRow, ToolInfo } from '../lib/data'
import { AMBER, MINT, SKY, SourceStrip, StepsIcon, backing, displayTitle, formatOf, pictogram, skillLinks, skillSteps, sourcePaths, statusColor, type Backing } from './artifactGlyph'
import { Document } from './ClimateIcons'

/**
 * The repository drawn block by block: every knowledge document, skill and tool is a small
 * diagram of what it is. Titles, steps, inputs, numbers and page excerpts are read from the
 * generated artifacts and their evidence; only the choice of pictogram is made on the page.
 */

const C = {
  knowledge: { zh: '知识层', en: 'Knowledge' },
  knowledgeSub: { zh: '方法、定义与边界，每一条都能回到原文', en: 'Methods, definitions and boundaries, each traced to the source text' },
  skills: { zh: 'Skill 层', en: 'Skills' },
  skillsSub: { zh: 'Agent 照着执行的研究流程', en: 'Research procedures an agent follows' },
  tools: { zh: '工具层', en: 'Tools' },
  toolsSub: { zh: '由资料中的公式生成，用资料中的算例检验', en: 'Generated from formulas in the materials, checked on their worked examples' },
  objects: { zh: '条知识', en: 'objects' },
  evidence: { zh: '条证据', en: 'evidence' },
  read: { zh: '读', en: 'Read' },
  do: { zh: '做', en: 'Do' },
  call: { zh: '调用', en: 'Call' },
  steps: { zh: '步', en: 'steps' },
  noTool: { zh: '不调用工具', en: 'Calls no tool' },
  verified: { zh: '原文算例已通过', en: 'Passes the worked example' },
  tested: { zh: '仅性质测试', en: 'Property-tested only' },
  withheld: { zh: '未开放', en: 'Withheld' },
  tests: { zh: '测试', en: 'tests' },
  example: { zh: '图中数值为原文算例', en: 'Values shown are the worked example in the source' },
  noExample: { zh: '原文给出公式，未给出算例数值', en: 'The source gives the formula but no worked numbers' },
  computation: { zh: '计算说明', en: 'Computation notes' },
  page: { zh: '第 {n} 页', en: 'p. {n}' },
}

const fileName = (p: string) => p.split('/').pop() ?? p
const num = (v: unknown) => (typeof v === 'number' ? v.toLocaleString('en-US', { maximumFractionDigits: 6 }) : String(v))
/** Lets a snake_case name wrap at its underscores instead of mid-word. */
const breakable = (name: string) => name.split('_').flatMap((part, i) => (i ? [<wbr key={i} />, `_${part}`] : [part]))
const showValue = (v: unknown) => (Array.isArray(v) ? (v.length ? v.map(num).join(' · ') : '∅') : num(v))

/** First evidence of an artifact that has a page excerpt, tables first. */
function excerptOf(chain: ChainObject[] | undefined, prefer?: string): EvidenceItem | null {
  const all = (chain ?? []).flatMap((o) => o.evidence)
  return all.find((e) => e.id === prefer && e.crop) ?? all.find((e) => e.crop && e.kind === 'table') ?? all.find((e) => e.crop) ?? null
}

/* ------------------------------------------------------------------ parts */

/** A page excerpt from the material, shown as the document it came from. */
function Excerpt({ ev, path, height = 96 }: { ev: EvidenceItem; path: string; height?: number }) {
  const t = useT()
  const f = formatOf(path)
  return (
    <div className="relative overflow-hidden rounded-[5px] border border-line-2 bg-deep" style={{ height }}>
      <img src={`data/${ev.crop}`} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover object-top" style={{ filter: 'invert(0.9) hue-rotate(180deg) saturate(0.85)' }} />
      <div className="absolute inset-x-0 bottom-0 h-11 bg-gradient-to-t from-deep via-deep/85 to-transparent" />
      <div className="absolute inset-x-2.5 bottom-1.5 flex items-center gap-1.5 mono text-[9px]">
        <span style={{ color: f.color }}>{f.tag}</span>
        <span className="truncate text-mute">{fileName(path)}</span>
        {ev.page != null && <span className="ml-auto shrink-0 text-ink/85">{t(C.page).replace('{n}', String(ev.page))}</span>}
      </div>
    </div>
  )
}

/** A sentence quoted from the material, drawn as a highlighted line in a document. */
function QuoteLine({ ev, path }: { ev: EvidenceItem; path: string }) {
  const f = formatOf(path)
  return (
    <div className="rounded-[5px] border border-line-2 bg-deep px-3 py-2.5">
      <div className="space-y-[5px]" aria-hidden>
        <div className="h-[2px] w-3/4 rounded bg-ink/15" />
        <div className="h-[2px] w-11/12 rounded bg-ink/15" />
      </div>
      <div className="my-2 border-l-2 pl-2 text-[11.5px] leading-snug text-ink/90" style={{ borderColor: AMBER, background: 'linear-gradient(90deg, rgba(239,183,90,0.14), transparent)' }}>{ev.quote}</div>
      <div className="flex items-center gap-1.5 mono text-[9px]">
        <span style={{ color: f.color }}>{f.tag}</span>
        <span className="truncate text-mute">{fileName(path)}</span>
      </div>
    </div>
  )
}

/** Composition ring: the mix of knowledge types inside a document. */
function Ring({ types, size = 76, children }: { types: Record<string, number>; size?: number; children: ReactNode }) {
  const entries = Object.entries(types).sort((a, b) => b[1] - a[1])
  const total = entries.reduce((s, [, v]) => s + v, 0) || 1
  const r = size / 2 - 5
  const circ = 2 * Math.PI * r
  let acc = 0
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="absolute inset-0 -rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(214,234,223,0.08)" strokeWidth="4" />
        {entries.map(([k, v]) => {
          const len = (v / total) * circ
          const el = <circle key={k} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={typeColor[k] ?? MINT} strokeWidth="4" strokeDasharray={`${Math.max(0, len - 2)} ${circ}`} strokeDashoffset={-acc} />
          acc += len
          return el
        })}
      </svg>
      <div className="absolute inset-0 flex items-center justify-center text-ink/90">{children}</div>
    </div>
  )
}

function Card({ a, color, delay, children, reduce }: { a: Artifact; color: string; delay: number; children: ReactNode; reduce: boolean }) {
  return (
    <motion.a
      href={`#/artifact/${encodeURIComponent(a.id)}`}
      initial={reduce ? false : { opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.5, ease: [0.2, 0.7, 0.2, 1], delay }}
      className="group relative flex min-w-0 flex-col rounded-[8px] border bg-[linear-gradient(180deg,#101a15,#0a110e)] p-5 transition-shadow hover:shadow-[0_0_34px_-12px_var(--glow)]"
      style={{ borderColor: `${color}55`, ['--glow' as string]: color }}
    >
      {children}
    </motion.a>
  )
}

function Foot({ b }: { b: Backing }) {
  const t = useT()
  return (
    <div className="mt-auto pt-4">
      <SourceStrip formats={b.formats} />
      <div className="mt-2 flex items-center gap-4 mono text-[10px] text-faint">
        <span><span className="tabular text-ink/90">{b.objects}</span> {t(C.objects)}</span>
        <span><span className="tabular text-ink/90">{b.evidence}</span> {t(C.evidence)}</span>
        <span className="ml-auto text-transparent transition-colors group-hover:text-mint">→</span>
      </div>
    </div>
  )
}

/** The steps of a skill as a track; steps that call a tool are filled. */
function StepTrack({ steps, toolNames, color }: { steps: string[]; toolNames: string[]; color: string }) {
  const n = Math.max(steps.length, 1)
  const per = 20
  return (
    <svg width={n * per} height={30} viewBox={`0 0 ${n * per} 30`} className="max-w-full" aria-hidden>
      <path d={`M10 18 H${n * per - 10}`} stroke={AMBER} strokeOpacity="0.45" strokeWidth="1.2" />
      {steps.map((s, i) => {
        const calls = toolNames.some((x) => s.includes(x))
        return (
          <g key={i}>
            <circle cx={10 + i * per} cy={18} r={7.5} fill={calls ? color : '#0c1310'} stroke={calls ? color : AMBER} strokeWidth="1.1" />
            <text x={10 + i * per} y={21} textAnchor="middle" fontSize="8.5" fontFamily="var(--font-mono)" fill={calls ? '#07100c' : AMBER}>{i + 1}</text>
            {calls && <text x={10 + i * per} y={7} textAnchor="middle" fontSize="8.5" fontFamily="var(--font-mono)" fill={color}>ƒ</text>}
          </g>
        )
      })}
    </svg>
  )
}

/** inputs → ƒ(x) → output, with the worked example's values on the wires when the source has one. */
function ToolDiagram({ tool, color, reduce }: { tool: ToolInfo; color: string; reduce: boolean }) {
  const cs = tool.cases[0]
  const inputs = tool.inputs.slice(0, 5)
  const rowH = 44
  const H = Math.max(inputs.length * rowH, 96)
  const top = (H - inputs.length * rowH) / 2
  const cy = H / 2
  const wire = (d: string) => (
    <>
      <path d={d} fill="none" stroke={color} strokeOpacity="0.5" strokeWidth="1.2" />
      {!reduce && <path d={d} fill="none" stroke={color} strokeWidth="1.8" className="flow-right" />}
    </>
  )
  return (
    <svg viewBox={`0 0 380 ${H}`} className="block h-auto w-full" role="img" aria-label={tool.description}>
      {inputs.map((inp, i) => {
        const y = top + i * rowH + 3
        const v = cs?.inputs?.[inp.name]
        const my = y + (rowH - 6) / 2
        return (
          <g key={inp.name}>
            <rect x={0.5} y={y} width={200} height={rowH - 6} rx={5} fill="#0a100d" stroke="rgba(214,234,223,0.2)" />
            <foreignObject x={0} y={y} width={201} height={rowH - 6}>
              <div className="flex h-full flex-col justify-center px-2.5">
                <div className="truncate mono text-[9.5px] leading-tight text-ink/85">{inp.name}</div>
                {v !== undefined && <div className="truncate mono text-[10.5px] leading-tight mt-0.5" style={{ color: AMBER }}>{showValue(v)}</div>}
              </div>
            </foreignObject>
            {wire(`M201 ${my} C 218 ${my}, 212 ${cy}, 228 ${cy}`)}
          </g>
        )
      })}
      <circle cx={252} cy={cy} r={24} fill="#0a100d" stroke={color} strokeWidth="1.4" style={{ filter: `drop-shadow(0 0 8px ${color}88)` }} />
      <text x={252} y={cy + 4.5} textAnchor="middle" fontSize="13" fontFamily="var(--font-mono)" fill={color}>ƒ(x)</text>
      {wire(`M276 ${cy} H291`)}
      <rect x={291.5} y={cy - 27} width={88} height={54} rx={6} fill="#0a100d" stroke={color} strokeOpacity="0.8" />
      <foreignObject x={291} y={cy - 27} width={89} height={54}>
        <div className="flex h-full flex-col items-center justify-center px-1.5 text-center">
          {cs?.expected != null && <div className="display tabular text-[21px] leading-none" style={{ color }}>{num(cs.expected)}</div>}
          {tool.output_unit ? (
            <div className="mono text-[9.5px] leading-tight mt-1 max-w-full truncate" style={{ color: cs?.expected != null ? '#8d9a92' : color }}>{tool.output_unit}</div>
          ) : cs?.expected == null ? (
            <div className="mono text-[11px]" style={{ color }}>—</div>
          ) : null}
        </div>
      </foreignObject>
    </svg>
  )
}

/* ------------------------------------------------------------------ main */

export default function LayersVisual({ meta, artifacts, chains, sources }: { meta: Meta; artifacts: Artifact[]; chains: Record<string, ChainObject[]>; sources: SourceRow[] }) {
  const t = useT()
  const reduce = useReducedMotion() ?? false
  const by = useMemo(() => {
    const k = (kind: string) => artifacts.filter((a) => a.kind === kind)
    return { docs: k('knowledge_doc'), comps: k('computation_doc'), skills: k('skill'), tools: k('tool') }
  }, [artifacts])
  const byId = useMemo(() => new Map(artifacts.map((a) => [a.id, a])), [artifacts])
  const taskTitle = useMemo(() => new Map(meta.tasks.map((x) => [x.id, x.title])), [meta])
  const paths = useMemo(() => sourcePaths(sources), [sources])
  const pathOf = (ev: EvidenceItem) => paths.get(ev.source) ?? ev.source

  return (
    <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16 md:py-20 space-y-20">
      {/* ---------------------------------------------------- knowledge */}
      <section>
        <Head n="01" title={t(C.knowledge)} sub={t(C.knowledgeSub)} count={by.docs.length + by.comps.length} color={MINT} icon={<Document size={28} />} />
        <div className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {by.docs.map((a, i) => {
            const b = backing(chains[a.id], paths)
            const ex = excerptOf(chains[a.id])
            return (
              <Card key={a.id} a={a} color={MINT} delay={(i % 4) * 0.05} reduce={reduce}>
                <div className="flex items-center gap-4">
                  <Ring types={b.types}>{pictogram(a, 34)}</Ring>
                  <div className="display min-w-0 text-[1.08rem] leading-snug text-ink transition-colors group-hover:text-mint">{a.title}</div>
                </div>
                <div className="mt-3.5 flex flex-wrap gap-x-3 gap-y-1">
                  {Object.entries(b.types).sort((x, y) => y[1] - x[1]).slice(0, 4).map(([k, v]) => (
                    <span key={k} className="inline-flex items-center gap-1.5 text-[10.5px]" style={{ color: typeColor[k] }}>
                      <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: typeColor[k] }} />
                      {kindLabel[k] ? t(kindLabel[k]) : k} <span className="mono tabular text-ink/80">{v}</span>
                    </span>
                  ))}
                </div>
                {ex && <div className="mt-4"><Excerpt ev={ex} path={pathOf(ex)} /></div>}
                <Foot b={b} />
              </Card>
            )
          })}
        </div>
        {by.comps.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="mono mr-1 self-center text-[10px] uppercase tracking-[0.16em] text-faint">{t(C.computation)}</span>
            {by.comps.map((a) => (
              <a key={a.id} href={`#/artifact/${encodeURIComponent(a.id)}`} className="mono rounded-full border border-line-2 px-3 py-1 text-[11px] text-mute transition-colors hover:border-mint/40 hover:text-mint">
                ƒ {a.title}
              </a>
            ))}
          </div>
        )}
      </section>

      {/* ------------------------------------------------------- skills */}
      <section>
        <Head n="02" title={t(C.skills)} sub={t(C.skillsSub)} count={by.skills.length} color={AMBER} icon={<StepsIcon />} />
        <div className="mt-7 grid gap-4 md:grid-cols-2">
          {by.skills.map((a, i) => {
            const steps = skillSteps(a.body)
            const b = backing(chains[a.id], paths)
            const { docs, tools } = skillLinks(a, byId)
            const toolNames = tools.map((x) => x.tool?.name ?? '').filter(Boolean)
            const toolColor = tools[0] ? statusColor(tools[0].tool?.status) : SKY
            return (
              <Card key={a.id} a={a} color={AMBER} delay={(i % 2) * 0.06} reduce={reduce}>
                <div className="flex items-center gap-3.5">
                  <span className="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-[9px] border" style={{ color: AMBER, borderColor: `${AMBER}66`, background: '#0c1310', boxShadow: `0 0 22px -10px ${AMBER}` }}>{pictogram(a, 32)}</span>
                  <div className="min-w-0">
                    <div className="display text-[1.2rem] leading-snug text-ink transition-colors group-hover:text-amber">{displayTitle(a, taskTitle)}</div>
                    <div className="mono mt-0.5 truncate text-[10px] text-faint">{a.id.split(':')[1]}</div>
                  </div>
                </div>
                {/* read → do → call */}
                <div className="mt-5 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_16px_auto_16px_minmax(0,1fr)] sm:items-stretch sm:gap-0">
                  <Lane label={t(C.read)} color={MINT}>
                    {docs.slice(0, 3).map((d) => (
                      <div key={d.id} className="flex items-center gap-1.5 text-[11px] leading-tight text-ink/85">
                        <span className="shrink-0 text-mint">{pictogram(d, 16)}</span>
                        <span className="truncate">{d.title}</span>
                      </div>
                    ))}
                  </Lane>
                  <Arrow />
                  <Lane label={`${t(C.do)} · ${steps.length} ${t(C.steps)}`} color={AMBER}>
                    <StepTrack steps={steps} toolNames={toolNames} color={toolColor} />
                  </Lane>
                  <Arrow />
                  <Lane label={t(C.call)} color={SKY}>
                    {tools.length > 0 ? (
                      tools.slice(0, 2).map((x) => {
                        const col = statusColor(x.tool?.status)
                        return (
                          <div key={x.id} className="flex items-center gap-2">
                            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border mono text-[10px]" style={{ borderColor: col, color: col }}>ƒ</span>
                            <span className="mono min-w-0 text-[9.5px] leading-tight text-ink/85">{breakable(x.tool?.name ?? '')}</span>
                          </div>
                        )
                      })
                    ) : (
                      <div className="flex items-center gap-2 text-faint">
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-dashed border-line-2 mono text-[10px]">ƒ</span>
                        <span className="text-[10.5px] leading-tight">{t(C.noTool)}</span>
                      </div>
                    )}
                  </Lane>
                </div>
                <Foot b={b} />
              </Card>
            )
          })}
        </div>
      </section>

      {/* -------------------------------------------------------- tools */}
      <section>
        <Head n="03" title={t(C.tools)} sub={t(C.toolsSub)} count={by.tools.length} color={SKY} icon={<span className="mono text-[17px]">ƒ(x)</span>} />
        <div className="mt-7 grid gap-4 lg:grid-cols-3">
          {by.tools.map((a, i) => {
            const tool = a.tool!
            const b = backing(chains[a.id], paths)
            const col = statusColor(tool.status)
            const cs = tool.cases[0]
            const all = (chains[a.id] ?? []).flatMap((o) => o.evidence)
            const caseEv = cs ? all.find((e) => e.id === cs.evidence) : undefined
            const ex = excerptOf(chains[a.id], cs?.evidence)
            const shown = caseEv?.crop ? caseEv : !caseEv ? ex : null
            return (
              <Card key={a.id} a={a} color={col} delay={i * 0.06} reduce={reduce}>
                <div className="flex items-center gap-3.5">
                  <span className="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-[9px] border" style={{ color: col, borderColor: `${col}66`, background: '#0c1310', boxShadow: `0 0 22px -10px ${col}` }}>{pictogram(a, 32)}</span>
                  <div className="min-w-0">
                    <div className="mono text-[12.5px] leading-snug text-ink transition-colors group-hover:text-mint">{breakable(tool.name)}</div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px]">
                      <span className="inline-flex items-center gap-1.5" style={{ color: col }}>
                        <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: col, boxShadow: `0 0 8px ${col}` }} />
                        {tool.status === 'verified' ? t(C.verified) : tool.status === 'tested' ? t(C.tested) : t(C.withheld)}
                      </span>
                      {tool.tests && (
                        <span className="mono inline-flex items-center gap-1 text-mute">
                          {Array.from({ length: tool.tests.passed }).map((_, j) => <span key={`p${j}`} className="inline-block h-1.5 w-1.5 rounded-[1px] bg-mint" />)}
                          {Array.from({ length: tool.tests.failed }).map((_, j) => <span key={`f${j}`} className="inline-block h-1.5 w-1.5 rounded-[1px] bg-rose" />)}
                          <span className="ml-1 tabular">{tool.tests.passed}/{tool.tests.passed + tool.tests.failed} {t(C.tests)}</span>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="mt-5"><ToolDiagram tool={tool} color={col} reduce={reduce} /></div>
                <div className="mono mt-2 text-[9.5px] text-faint">{cs ? t(C.example) : t(C.noExample)}</div>
                <div className="mt-3">
                  {shown ? <Excerpt ev={shown} path={pathOf(shown)} height={112} /> : caseEv ? <QuoteLine ev={{ ...caseEv, quote: cs?.quote || caseEv.quote }} path={pathOf(caseEv)} /> : null}
                </div>
                <Foot b={b} />
              </Card>
            )
          })}
        </div>
      </section>
    </div>
  )
}

function Head({ n, title, sub, count, color, icon }: { n: string; title: string; sub: string; count: number; color: string; icon: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
      <span className="flex h-14 w-14 items-center justify-center rounded-[10px] border" style={{ color, borderColor: `${color}77`, background: 'linear-gradient(180deg,#12241c,#0a120e)', boxShadow: `0 0 30px -12px ${color}` }}>{icon}</span>
      <div>
        <div className="mono text-[10.5px] uppercase tracking-[0.22em]" style={{ color }}>{n}</div>
        <h2 className="display mt-1 text-[1.9rem] leading-none md:text-[2.2rem]">{title}</h2>
        <div className="mt-2 text-[13px] text-mute">{sub}</div>
      </div>
      <div className="display tabular ml-auto text-[3.4rem] leading-none" style={{ color }}>{count}</div>
    </div>
  )
}

function Lane({ label, color, children }: { label: string; color: string; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-[6px] border border-line-2 bg-void/50 px-2.5 py-2">
      <div className="mono mb-1.5 text-[9px] uppercase tracking-[0.16em]" style={{ color }}>{label}</div>
      <div className="space-y-1.5">{children}</div>
    </div>
  )
}

function Arrow() {
  return (
    <div className="hidden items-center justify-center text-mint/70 sm:flex" aria-hidden>
      <svg width="14" height="10" viewBox="0 0 14 10"><path d="M0 5h11M8 1.5 12 5 8 8.5" fill="none" stroke="currentColor" strokeWidth="1.3" /></svg>
    </div>
  )
}

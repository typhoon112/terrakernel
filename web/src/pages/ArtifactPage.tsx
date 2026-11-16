import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { ErrorBox, Skeleton } from '../components/ui'
import { Link } from '../lib/router'
import { useT } from '../lib/i18n'
import { basisLabel, kindLabel, loadArtifacts, loadChains, loadSources, statusLabel, typeColor, useAsync } from '../lib/data'
import type { Artifact, ChainObject, EvidenceItem, SourceRow } from '../lib/data'

/* ------------------------------------------------------------------ copy */

const C = {
  back: { zh: '生成结果', en: 'What was built' },
  notFound: { zh: '没有找到这个产物', en: 'This artifact was not found' },
  notFoundSub: { zh: '它可能已不在这次构建的数据包里。', en: 'It may not be part of this build.' },
  toLayers: { zh: '回到生成结果', en: 'Back to what was built' },
  kind_tool: { zh: '工具', en: 'Tool' },
  kind_skill: { zh: 'Skill', en: 'Skill' },
  kind_knowledge_doc: { zh: '知识文档', en: 'Knowledge document' },
  kind_computation_doc: { zh: '计算说明', en: 'Computation note' },
  kind_other: { zh: '支撑文件', en: 'Support file' },
  objects: { zh: '条结构化知识', en: 'knowledge objects' },
  evidence: { zh: '条原文证据', en: 'evidence units' },
  sources: { zh: '份原始资料', en: 'source files' },
  crops: { zh: '张原文页面截图', en: 'page images' },
  ex_verified: {
    zh: '已验证：用资料原文里的算例测过，输入和期望值都摘自原文。',
    en: 'Verified: tested against worked examples whose inputs and expected values are quoted from the materials.',
  },
  ex_tested: {
    zh: '仅性质测试：资料里找不到可独立核对的完整算例，只做了性质检查，结果需要人工复核。',
    en: 'Property-tested only: no complete, independently checkable example was found in the materials; review results by hand.',
  },
  ex_failed: {
    zh: '未开放：无法用资料验证，所以没有提供给 Agent 使用。',
    en: 'Withheld: it could not be verified against the materials, so it is not exposed to agents.',
  },
  ex_blocked: {
    zh: '受阻：它依赖的某个工具未能通过验证。',
    en: 'Blocked: a tool it depends on did not pass verification.',
  },
  contract: { zh: '工具的输入与输出', en: 'Inputs and output' },
  in_name: { zh: '参数', en: 'Parameter' },
  in_kind: { zh: '类型', en: 'Kind' },
  in_unit: { zh: '单位', en: 'Unit' },
  in_desc: { zh: '含义', en: 'Meaning' },
  output: { zh: '输出', en: 'Output' },
  tests: { zh: '测试', en: 'Tests' },
  passed: { zh: '通过', en: 'passed' },
  failedN: { zh: '失败', en: 'failed' },
  cases: { zh: '摘自原文的算例', en: 'Worked examples quoted from the materials' },
  casesSub: {
    zh: '测试的期望值来自这些原文，不是由工具自己算出来的。',
    en: 'The expected values of the tests come from these passages, not from the tool itself.',
  },
  expected: { zh: '期望值', en: 'expected' },
  noCases: { zh: '没有被采纳的原文算例。', en: 'No worked example from the materials was accepted.' },
  problems: { zh: '被拒绝的算例与原因', en: 'Examples that were rejected, and why' },
  problemsSub: {
    zh: '构建时逐条记录：原文缺少输入或期望值的算例不会被用来测试。',
    en: 'Recorded during the build: an example whose inputs or expected value are missing from the text is not used as a test.',
  },
  chain: { zh: '出处链', en: 'Provenance chain' },
  chainSub: {
    zh: '从左到右：原始资料 → 原文证据 → 结构化知识 → 这个产物。点任意一项，高亮它的上下游。',
    en: 'Left to right: source file → evidence in the text → structured knowledge → this artifact. Select any item to highlight what it comes from and what it feeds.',
  },
  colSource: { zh: '原始资料', en: 'Source files' },
  colEvidence: { zh: '原文证据', en: 'Evidence' },
  colObject: { zh: '结构化知识', en: 'Structured knowledge' },
  colArtifact: { zh: '产物', en: 'Artifact' },
  filter: { zh: '按名称筛选知识…', en: 'Filter knowledge by name…' },
  clear: { zh: '取消选择', en: 'Clear selection' },
  showAll: { zh: '显示全部 {n} 条', en: 'Show all {n}' },
  showLess: { zh: '收起', en: 'Show fewer' },
  evShown: { zh: '已选项的证据', en: 'Evidence of the selection' },
  evHint: { zh: '选择左侧的资料或右侧的知识，查看对应的原文。', en: 'Select a source or a knowledge object to see the passages.' },
  evMore: { zh: '另有 {n} 条，选择具体的知识可查看。', en: '{n} more; select a knowledge object to see them.' },
  detail: { zh: '详情', en: 'Detail' },
  close: { zh: '关闭', en: 'Close' },
  summary: { zh: '摘要', en: 'Summary' },
  attrs: { zh: '记录的属性', en: 'Recorded attributes' },
  basis_stated: { zh: '资料里明确写了。', en: 'The materials say so explicitly.' },
  basis_inferred: { zh: '由模型从资料推导，并附推导说明。', en: 'Derived by the model from the materials, with its reasoning.' },
  basis_measured: { zh: '由确定性的工具计算得到。', en: 'Computed by a deterministic tool.' },
  basis_human_confirmed: { zh: '由人回答确认。', en: 'Answered by a person.' },
  needsReview: { zh: '待复核', en: 'needs review' },
  quoteFrom: { zh: '原文', en: 'Source text' },
  noEvidence: { zh: '这条知识由关联阶段从其他知识归并而来，没有直接挂接的原文。', en: 'This object was formed by reconcile from other objects and has no passage linked directly.' },
  cropCaption: { zh: '原文页面截图，方框为这条证据的位置', en: 'Page image; the box marks this evidence' },
  role_defines: { zh: '定义', en: 'defines' },
  role_supports: { zh: '支持', en: 'supports' },
  role_implements: { zh: '实现', en: 'implements' },
  body: { zh: '查看生成的内容', en: 'View the generated content' },
  bodyHide: { zh: '收起生成的内容', en: 'Hide the generated content' },
  depends: { zh: '依赖', en: 'Depends on' },
  support: {
    zh: '这是按规划生成的支撑文件，不直接引用知识对象。',
    en: 'This is a support file generated from the plan; it does not reference knowledge objects directly.',
  },
  note: {
    zh: '这里显示的是与本产物的知识对象直接挂接的原文证据。构建出的仓库保留了每份资料的全文。',
    en: 'Shown here is the evidence linked to this artifact’s knowledge objects. The built repository keeps the full text of every source.',
  },
  from: { zh: '来自', en: 'from' },
  usedBy: { zh: '条证据', en: 'evidence' },
}

const MINT = '#4fe3a4'
const AMBER = '#efb75a'
const ROSE = '#ef7a7a'
const SKY = '#74a9f7'
const GROUP_LIMIT = 6
const statusColor = (s: string) => (s === 'verified' ? MINT : s === 'tested' ? AMBER : s === 'failed' || s === 'blocked' ? ROSE : SKY)
const fileName = (p: string) => p.split('/').pop() ?? p

/* ------------------------------------------------------------- data model */

type Sel = { kind: 'source' | 'evidence' | 'object'; id: string } | null

type Model = {
  objects: ChainObject[]
  evById: Map<string, EvidenceItem>
  evObjects: Map<string, Set<string>>
  objEvidence: Map<string, string[]>
  srcEvidence: Map<string, string[]>
  srcList: { id: string; n: number }[]
  srcObjects: Map<string, Set<string>>
  crops: number
}

function buildModel(chain: ChainObject[]): Model {
  const evById = new Map<string, EvidenceItem>()
  const evObjects = new Map<string, Set<string>>()
  const objEvidence = new Map<string, string[]>()
  const srcEvidence = new Map<string, string[]>()
  const srcObjects = new Map<string, Set<string>>()
  for (const o of chain) {
    const ids: string[] = []
    for (const e of o.evidence) {
      if (!evById.has(e.id)) {
        evById.set(e.id, e)
        srcEvidence.set(e.source, [...(srcEvidence.get(e.source) ?? []), e.id])
      }
      if (!ids.includes(e.id)) ids.push(e.id)
      if (!evObjects.has(e.id)) evObjects.set(e.id, new Set())
      evObjects.get(e.id)!.add(o.id)
      if (!srcObjects.has(e.source)) srcObjects.set(e.source, new Set())
      srcObjects.get(e.source)!.add(o.id)
    }
    objEvidence.set(o.id, ids)
  }
  const srcList = [...srcEvidence.entries()].map(([id, ev]) => ({ id, n: ev.length })).sort((a, b) => b.n - a.n)
  let crops = 0
  for (const e of evById.values()) if (e.crop) crops++
  return { objects: chain, evById, evObjects, objEvidence, srcEvidence, srcList, srcObjects, crops }
}

/** What is lit for a selection: the selected item with everything upstream and downstream of it. */
function related(m: Model, sel: Sel) {
  const src = new Set<string>()
  const ev = new Set<string>()
  const obj = new Set<string>()
  if (!sel) return { src, ev, obj }
  if (sel.kind === 'object') {
    obj.add(sel.id)
    for (const e of m.objEvidence.get(sel.id) ?? []) {
      ev.add(e)
      src.add(m.evById.get(e)!.source)
    }
  } else if (sel.kind === 'evidence') {
    ev.add(sel.id)
    const e = m.evById.get(sel.id)
    if (e) src.add(e.source)
    for (const o of m.evObjects.get(sel.id) ?? []) obj.add(o)
  } else {
    src.add(sel.id)
    for (const e of m.srcEvidence.get(sel.id) ?? []) {
      ev.add(e)
      for (const o of m.evObjects.get(e) ?? []) obj.add(o)
    }
  }
  return { src, ev, obj }
}

/* ------------------------------------------------------------ connectors */

type Path = { d: string; hot: boolean; w: number }

function useConnectors(
  wrap: React.RefObject<HTMLDivElement | null>,
  links: { from: string; to: string; hot: boolean; w?: number }[],
  deps: unknown[],
) {
  const [paths, setPaths] = useState<Path[]>([])
  const [size, setSize] = useState({ w: 0, h: 0 })
  const linksRef = useRef(links)
  linksRef.current = links

  const measure = () => {
    const el = wrap.current
    if (!el) return
    const box = el.getBoundingClientRect()
    const out: Path[] = []
    const visible = (r: DOMRect, scroller: Element | null) => {
      if (!scroller) return true
      const s = scroller.getBoundingClientRect()
      return r.bottom > s.top + 2 && r.top < s.bottom - 2
    }
    for (const l of linksRef.current) {
      const a = el.querySelector<HTMLElement>(`[data-node="${CSS.escape(l.from)}"]`)
      const b = el.querySelector<HTMLElement>(`[data-node="${CSS.escape(l.to)}"]`)
      if (!a || !b) continue
      const ra = a.getBoundingClientRect()
      const rb = b.getBoundingClientRect()
      if (!visible(ra, a.closest('[data-scroll]')) || !visible(rb, b.closest('[data-scroll]'))) continue
      const x1 = ra.right - box.left
      const y1 = ra.top + ra.height / 2 - box.top
      const x2 = rb.left - box.left
      const y2 = rb.top + rb.height / 2 - box.top
      const mx = (x1 + x2) / 2
      out.push({ d: `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`, hot: l.hot, w: l.w ?? 1 })
    }
    setSize({ w: box.width, h: box.height })
    setPaths(out)
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(measure, deps)
  useEffect(() => {
    const el = wrap.current
    if (!el) return
    let raf = 0
    const on = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(measure)
    }
    const ro = new ResizeObserver(on)
    ro.observe(el)
    const scrollers = el.querySelectorAll('[data-scroll]')
    scrollers.forEach((s) => s.addEventListener('scroll', on, { passive: true }))
    window.addEventListener('resize', on)
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      scrollers.forEach((s) => s.removeEventListener('scroll', on))
      window.removeEventListener('resize', on)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return { paths, size }
}

/* ------------------------------------------------------------ small parts */

function TypeDot({ type }: { type: string }) {
  return <span className="inline-block h-1.5 w-1.5 rounded-full shrink-0" style={{ backgroundColor: typeColor[type] ?? '#8d9a92' }} />
}

function Quote({ e, src, onZoom, compact = false }: { e: EvidenceItem; src?: SourceRow; onZoom: (url: string, alt: string) => void; compact?: boolean }) {
  const t = useT()
  const role = e.role === 'defines' ? t(C.role_defines) : e.role === 'implements' ? t(C.role_implements) : t(C.role_supports)
  const alt = `${src ? fileName(src.path) : e.source} ${e.loc}`
  return (
    <figure className="min-w-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 mono text-[10px] text-faint">
        <span className="text-mint/80 uppercase tracking-[0.14em]">{role}</span>
        <span className="text-mute break-all">{src ? fileName(src.path) : e.source}</span>
      </div>
      <blockquote
        className={`mt-2 border-l-2 border-mint/60 pl-4 font-serif text-ink/95 ${compact ? 'text-[14px] leading-[1.75]' : 'text-[15.5px] leading-[1.85]'}`}
      >
        {e.quote}
      </blockquote>
      <figcaption className="mt-2 mono text-[10px] text-faint break-words">{e.loc || e.id}</figcaption>
      {e.crop && (
        <button
          type="button"
          onClick={() => onZoom(`data/${e.crop}`, alt)}
          className="mt-3 block w-full text-left group"
          aria-label={t(C.cropCaption)}
        >
          <img
            src={`data/${e.crop}`}
            alt={alt}
            loading="lazy"
            className="w-full max-h-[300px] object-contain object-left-top bg-white rounded-sm border border-line-2 group-hover:border-mint/50 transition-colors"
          />
          <span className="mt-1.5 block mono text-[10px] text-faint">{t(C.cropCaption)}</span>
        </button>
      )}
    </figure>
  )
}

/* ------------------------------------------------------------------ page */

export default function ArtifactPage({ id }: { id: string }) {
  const t = useT()
  const reduce = useReducedMotion() ?? false
  const { data, error } = useAsync(() => Promise.all([loadArtifacts(), loadChains(), loadSources()]), [])
  const [sel, setSel] = useState<Sel>(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [showBody, setShowBody] = useState(false)
  const [zoom, setZoom] = useState<{ url: string; alt: string } | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setSel(null)
    setQuery('')
    setOpen({})
    setShowBody(false)
  }, [id])
  useEffect(() => {
    if (!zoom) return
    const on = (e: KeyboardEvent) => e.key === 'Escape' && setZoom(null)
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [zoom])

  const artifact: Artifact | undefined = data?.[0].artifacts.find((a) => a.id === id)
  const chain = useMemo(() => (data ? data[1][id] ?? [] : []), [data, id])
  const m = useMemo(() => buildModel(chain), [chain])
  const srcById = useMemo(() => new Map((data?.[2] ?? []).map((s) => [s.id, s])), [data])
  const rel = useMemo(() => related(m, sel), [m, sel])
  // A large artifact opens with its main source selected, so the chain is lit from the start.
  useEffect(() => {
    if (m.evById.size > 8 && m.srcList[0]) setSel({ kind: 'source', id: m.srcList[0].id })
  }, [m])

  const q = query.trim().toLowerCase()
  const groups = useMemo(() => {
    const by = new Map<string, ChainObject[]>()
    for (const o of m.objects) {
      if (q && !`${o.n} ${o.s}`.toLowerCase().includes(q)) continue
      by.set(o.t, [...(by.get(o.t) ?? []), o])
    }
    return [...by.entries()].sort((a, b) => b[1].length - a[1].length)
  }, [m, q])

  // objects rendered in the knowledge column: a few per type, plus everything related to the selection
  const shownObjects = useMemo(() => {
    const out: { type: string; total: number; items: ChainObject[] }[] = []
    for (const [type, items] of groups) {
      const first = open[type] ? items : items.slice(0, GROUP_LIMIT)
      const extra = open[type] ? [] : items.slice(GROUP_LIMIT).filter((o) => rel.obj.has(o.id))
      out.push({ type, total: items.length, items: [...first, ...extra] })
    }
    return out
  }, [groups, open, rel])

  // evidence column: the passages of the selection; nothing selected -> those of a small artifact
  const small = m.evById.size <= 8
  const evShown = useMemo(() => {
    const ids = sel ? [...rel.ev] : small ? [...m.evById.keys()] : []
    return ids.slice(0, 12).map((i) => m.evById.get(i)!).filter(Boolean)
  }, [sel, rel, small, m])
  const evHidden = (sel ? rel.ev.size : small ? m.evById.size : 0) - evShown.length

  const links = useMemo(() => {
    const out: { from: string; to: string; hot: boolean; w?: number }[] = []
    const shownIds = new Set(shownObjects.flatMap((g) => g.items.map((o) => o.id)))
    const evIds = new Set(evShown.map((e) => e.id))
    for (const e of evShown) {
      out.push({ from: `s:${e.source}`, to: `e:${e.id}`, hot: !!sel })
      for (const o of m.evObjects.get(e.id) ?? []) if (shownIds.has(o) && (!sel || rel.obj.has(o))) out.push({ from: `e:${e.id}`, to: `o:${o}`, hot: !!sel })
    }
    for (const g of shownObjects) {
      for (const o of g.items) {
        const hot = !!sel && rel.obj.has(o.id)
        if (out.length < 150 || hot) out.push({ from: `o:${o.id}`, to: 'artifact', hot })
        if (sel && hot && !(m.objEvidence.get(o.id) ?? []).some((e) => evIds.has(e))) {
          const first = (m.objEvidence.get(o.id) ?? [])[0]
          if (first) out.push({ from: `s:${m.evById.get(first)!.source}`, to: `o:${o.id}`, hot: true })
        }
      }
    }
    return out
  }, [shownObjects, evShown, sel, rel, m])

  const { paths, size } = useConnectors(wrapRef, links, [links, showBody])

  if (error) return <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16"><ErrorBox msg={error} /></div>
  if (!data) return <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16"><Skeleton /></div>
  if (!artifact)
    return (
      <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-20">
        <div className="panel rounded-sm p-8 max-w-xl">
          <div className="mono text-[11px] text-rose break-all">{id}</div>
          <h1 className="display text-2xl mt-3">{t(C.notFound)}</h1>
          <p className="text-sm text-mute mt-2">{t(C.notFoundSub)}</p>
          <Link to="/layers" className="inline-block mt-6 text-mint text-sm">← {t(C.toLayers)}</Link>
        </div>
      </div>
    )

  const tool = artifact.tool
  const status = tool?.status ?? artifact.status
  const kindCopy = (C as Record<string, { zh: string; en: string }>)[`kind_${artifact.kind}`] ?? C.kind_other
  const title = tool?.name ?? (artifact.kind === 'skill' ? artifact.id.split(':')[1] : artifact.title || artifact.id)
  const explain = status === 'verified' ? C.ex_verified : status === 'tested' ? C.ex_tested : status === 'failed' ? C.ex_failed : status === 'blocked' ? C.ex_blocked : null
  const typeCounts = [...m.objects.reduce((acc, o) => acc.set(o.t, (acc.get(o.t) ?? 0) + 1), new Map<string, number>())].sort((a, b) => b[1] - a[1])
  const selObject = sel?.kind === 'object' ? m.objects.find((o) => o.id === sel.id) : null
  const pick = (next: NonNullable<Sel>) => setSel((cur) => (cur && cur.kind === next.kind && cur.id === next.id ? null : next))
  const dim = (on: boolean) => (sel && !on ? 'opacity-30' : 'opacity-100')
  const statusText = statusLabel[status] ? t(statusLabel[status]) : status

  return (
    <div className="pb-10">
      {/* header */}
      <section className="mx-auto max-w-[1240px] px-5 md:px-8 pt-10 md:pt-12">
        <Link to="/layers" className="mono text-[11px] text-mute hover:text-mint transition-colors">← {t(C.back)}</Link>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <span className="mono text-[11px] tracking-[0.2em] uppercase text-mint/80">{t(kindCopy)}</span>
          <span className="inline-flex items-center gap-1.5 border rounded-full px-2.5 py-0.5 text-[11px]" style={{ color: statusColor(status), borderColor: `${statusColor(status)}55` }}>
            <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: statusColor(status) }} />
            {statusText}
          </span>
        </div>
        <h1 className={`mt-3 text-[1.9rem] md:text-[2.5rem] leading-[1.12] break-words ${tool || artifact.kind === 'skill' ? 'mono tracking-tight' : 'display'}`}>{title}</h1>
        {artifact.path && <div className="mono text-[11.5px] text-faint mt-3 break-all">{artifact.path}</div>}
        {(tool?.description || artifact.description) && (
          <p className="mt-4 text-[14.5px] leading-relaxed text-mute max-w-[760px]">{tool?.description || artifact.description}</p>
        )}
        {explain && (
          <p className="mt-4 text-[13px] leading-relaxed max-w-[760px] border-l-2 pl-3" style={{ borderColor: statusColor(status), color: '#c9d3cc' }}>
            {t(explain)}
          </p>
        )}
        {m.objects.length > 0 && (
          <div className="mt-8 hairline pt-6 flex flex-wrap items-end gap-x-10 gap-y-5">
            {[
              [m.objects.length, t(C.objects)],
              [m.evById.size, t(C.evidence)],
              [m.srcList.length, t(C.sources)],
              [m.crops, t(C.crops)],
            ].map(([n, label]) => (
              <div key={label as string}>
                <div className="display tabular text-[2rem] leading-none">{n}</div>
                <div className="mono text-[10.5px] text-mute mt-2">{label}</div>
              </div>
            ))}
            <div className="flex flex-wrap gap-2 ml-auto">
              {typeCounts.map(([type, n]) => (
                <span key={type} className="inline-flex items-center gap-1.5 border border-line-2 rounded-full px-2.5 py-0.5 text-[11px]" style={{ color: typeColor[type] }}>
                  {kindLabel[type] ? t(kindLabel[type]) : type} <span className="tabular text-mute">{n}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* tool contract */}
      {tool && (
        <section className="mx-auto max-w-[1240px] px-5 md:px-8 mt-10 grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-6">
          <div className="panel rounded-sm p-5 md:p-6 min-w-0">
            <div className="mono text-[10.5px] tracking-[0.2em] uppercase text-mint/80">{t(C.contract)}</div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-[12.5px] min-w-[420px]">
                <thead>
                  <tr className="text-left mono text-[10px] text-faint">
                    <th className="font-normal pb-2 pr-3">{t(C.in_name)}</th>
                    <th className="font-normal pb-2 pr-3">{t(C.in_kind)}</th>
                    <th className="font-normal pb-2 pr-3">{t(C.in_unit)}</th>
                    <th className="font-normal pb-2">{t(C.in_desc)}</th>
                  </tr>
                </thead>
                <tbody>
                  {tool.inputs.map((i) => (
                    <tr key={i.name} className="border-t border-line align-top">
                      <td className="py-2 pr-3 mono text-[11.5px] text-ink">{i.name}</td>
                      <td className="py-2 pr-3 mono text-[11px] text-mute">{i.kind}</td>
                      <td className="py-2 pr-3 mono text-[11px] text-amber">{i.unit ?? '—'}</td>
                      <td className="py-2 text-mute">{i.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="hairline mt-3 pt-3 flex flex-wrap gap-x-8 gap-y-2 text-[12.5px]">
              <div>
                <span className="mono text-[10px] text-faint mr-2">{t(C.output)}</span>
                <span className="text-mute">{tool.output_description}</span>{' '}
                {tool.output_unit && <span className="mono text-[11px] text-amber">{tool.output_unit}</span>}
              </div>
              {tool.tests && (
                <div className="mono text-[11px]">
                  <span className="text-faint mr-2">{t(C.tests)}</span>
                  <span className="text-mint">{tool.tests.passed} {t(C.passed)}</span>
                  <span className="text-faint"> / </span>
                  <span className={tool.tests.failed ? 'text-rose' : 'text-mute'}>{tool.tests.failed} {t(C.failedN)}</span>
                </div>
              )}
            </div>
          </div>
          <div className="panel rounded-sm p-5 md:p-6 min-w-0">
            <div className="mono text-[10.5px] tracking-[0.2em] uppercase text-mint/80">{t(C.cases)}</div>
            <p className="mt-2 text-[12px] text-faint leading-relaxed">{t(C.casesSub)}</p>
            {tool.cases.length === 0 && <div className="mt-4 text-[13px] text-mute italic">{t(C.noCases)}</div>}
            {tool.cases.map((cs) => (
              <div key={cs.id} className="mt-4">
                <blockquote className="border-l-2 border-mint/60 pl-4 font-serif text-[15px] leading-[1.8] text-ink/95">{cs.quote}</blockquote>
                {cs.inputs && Object.keys(cs.inputs).length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {Object.entries(cs.inputs).map(([k, v]) => (
                      <span key={k} className="mono text-[10.5px] border border-line-2 rounded-sm px-2 py-0.5 text-mute">
                        {k} <span className="text-ink tabular">{Array.isArray(v) ? `[${v.join(', ')}]` : String(v)}</span>
                      </span>
                    ))}
                  </div>
                )}
                <div className="mt-2 mono text-[10px] text-faint flex flex-wrap gap-x-4">
                  <span>{t(C.expected)} <span className="text-mint tabular">{cs.expected}</span></span>
                  <span className="break-all">{cs.evidence}</span>
                  <span>{cs.id}</span>
                </div>
              </div>
            ))}
            {tool.problems.length > 0 && (
              <div className="hairline mt-5 pt-4">
                <div className="mono text-[10.5px] tracking-[0.16em] uppercase" style={{ color: status === 'verified' ? AMBER : ROSE }}>{t(C.problems)}</div>
                <p className="mt-1.5 text-[12px] text-faint leading-relaxed">{t(C.problemsSub)}</p>
                <ul className="mt-3 space-y-2.5">
                  {tool.problems.map((pr, i) => (
                    <li key={i} className="text-[12.5px] leading-relaxed text-mute pl-3 border-l border-line-2 break-words">{pr}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}

      {/* the chain */}
      {m.objects.length > 0 ? (
        <section className="mx-auto max-w-[1240px] px-5 md:px-8 mt-12">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="mono text-[11px] tracking-[0.22em] uppercase text-mint/80">{t(C.chain)}</div>
              <p className="mt-2 text-[13.5px] text-mute max-w-[760px] leading-relaxed">{t(C.chainSub)}</p>
            </div>
            <div className="flex items-center gap-3">
              {m.objects.length > GROUP_LIMIT && (
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t(C.filter)}
                  className="bg-transparent border border-line-2 rounded-sm px-3 py-1.5 text-[12.5px] text-ink placeholder:text-faint w-[220px] focus:outline-none focus:border-mint/50"
                />
              )}
              {sel && (
                <button onClick={() => setSel(null)} className="mono text-[11px] text-mute hover:text-ink border border-line-2 rounded-sm px-2.5 py-1.5">
                  {t(C.clear)}
                </button>
              )}
            </div>
          </div>

          <div ref={wrapRef} className="relative mt-5 panel rounded-sm">
            <svg className="hidden lg:block absolute inset-0 pointer-events-none z-0" width={size.w} height={size.h} aria-hidden>
              {paths.filter((p) => !p.hot).map((p, i) => (
                <path key={`c${i}`} d={p.d} fill="none" stroke="rgba(214,234,223,0.11)" strokeWidth={p.w} />
              ))}
              {paths.filter((p) => p.hot).map((p, i) => (
                <path key={`h${i}`} d={p.d} fill="none" stroke={MINT} strokeWidth={1.4} className={reduce ? '' : 'flow-line'} opacity={0.9} />
              ))}
            </svg>
            <div className="relative z-10 grid lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.3fr)_minmax(0,1.05fr)_minmax(0,0.5fr)] lg:gap-x-12 divide-y lg:divide-y-0 divide-line">
              {/* sources */}
              <div className="p-4 md:p-5 min-w-0">
                <ColHead n="01" title={t(C.colSource)} count={m.srcList.length} />
                <div data-scroll className="mt-3 space-y-1.5 lg:max-h-[560px] lg:overflow-y-auto lg:pr-1">
                  {m.srcList.map(({ id: sid, n }) => {
                    const s = srcById.get(sid)
                    const on = rel.src.has(sid)
                    return (
                      <button
                        key={sid}
                        data-node={`s:${sid}`}
                        onClick={() => pick({ kind: 'source', id: sid })}
                        title={s?.path}
                        className={`w-full text-left px-2.5 py-2 rounded-sm border transition-all ${on ? 'border-mint/60 bg-mint/[0.07]' : 'border-line hover:border-line-2'} ${dim(on)}`}
                      >
                        <div className="text-[12px] leading-snug text-ink/90 break-words line-clamp-2">{s ? fileName(s.path) : sid}</div>
                        <div className="mono text-[10px] text-faint mt-1 flex justify-between gap-2">
                          <span>{s?.kind}</span>
                          <span className="tabular">{n} {t(C.usedBy)}</span>
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* evidence */}
              <div className="p-4 md:p-5 min-w-0">
                <ColHead n="02" title={t(C.colEvidence)} count={m.evById.size} />
                <div data-scroll className="mt-3 space-y-5 lg:max-h-[560px] lg:overflow-y-auto lg:pr-1">
                  {evShown.length === 0 && <div className="text-[12.5px] text-faint leading-relaxed py-6">{t(C.evHint)}</div>}
                  {evShown.map((e) => (
                    <div key={e.id} data-node={`e:${e.id}`} className="bg-[#0a0f0d] border border-line rounded-sm p-3.5">
                      <Quote e={e} src={srcById.get(e.source)} onZoom={(url, alt) => setZoom({ url, alt })} compact />
                    </div>
                  ))}
                  {evHidden > 0 && <div className="mono text-[10.5px] text-faint">{t(C.evMore).replace('{n}', String(evHidden))}</div>}
                </div>
              </div>

              {/* knowledge objects */}
              <div className="p-4 md:p-5 min-w-0">
                <ColHead n="03" title={t(C.colObject)} count={m.objects.length} />
                <div data-scroll className="mt-3 space-y-4 lg:max-h-[560px] lg:overflow-y-auto lg:pr-1">
                  {shownObjects.map((g) => (
                    <div key={g.type}>
                      <div className="flex items-center gap-2 mono text-[10px] tracking-[0.14em] uppercase" style={{ color: typeColor[g.type] }}>
                        <TypeDot type={g.type} />
                        {kindLabel[g.type] ? t(kindLabel[g.type]) : g.type}
                        <span className="text-faint tabular">{g.total}</span>
                      </div>
                      <div className="mt-1.5 space-y-1">
                        {g.items.map((o) => {
                          const on = rel.obj.has(o.id)
                          return (
                            <button
                              key={o.id}
                              data-node={`o:${o.id}`}
                              onClick={() => pick({ kind: 'object', id: o.id })}
                              className={`w-full text-left px-2.5 py-1.5 rounded-sm border text-[12px] leading-snug transition-all ${on ? 'border-mint/60 bg-mint/[0.07] text-ink' : 'border-line hover:border-line-2 text-ink/85'} ${dim(on)}`}
                            >
                              <span className="line-clamp-2 break-words">{o.n}</span>
                            </button>
                          )
                        })}
                      </div>
                      {g.total > GROUP_LIMIT && (
                        <button onClick={() => setOpen((x) => ({ ...x, [g.type]: !x[g.type] }))} className="mt-1.5 mono text-[10px] text-mute hover:text-mint">
                          {open[g.type] ? t(C.showLess) : t(C.showAll).replace('{n}', String(g.total))}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* artifact */}
              <div className="p-4 md:p-5 min-w-0 lg:flex lg:flex-col">
                <ColHead n="04" title={t(C.colArtifact)} />
                <div className="lg:flex-1 lg:flex lg:items-center mt-3">
                  <div data-node="artifact" className="w-full border rounded-sm px-3 py-3 glow-mint" style={{ borderColor: `${statusColor(status)}88` }}>
                    <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-faint">{t(kindCopy)}</div>
                    <div className="mono text-[11.5px] text-ink mt-1 break-words leading-snug">{title}</div>
                    <div className="mono text-[10px] mt-2" style={{ color: statusColor(status) }}>{statusText}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* detail of the selected object */}
          {selObject && (
            <motion.div
              key={selObject.id}
              initial={reduce ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: [0.2, 0.7, 0.2, 1] }}
              className="mt-6 panel rounded-sm p-5 md:p-7"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mono text-[10.5px]">
                    <span className="inline-flex items-center gap-1.5" style={{ color: typeColor[selObject.t] }}>
                      <TypeDot type={selObject.t} />
                      {kindLabel[selObject.t] ? t(kindLabel[selObject.t]) : selObject.t}
                    </span>
                    <span className="text-mute">· {basisLabel[selObject.b] ? t(basisLabel[selObject.b]) : selObject.b}</span>
                    {selObject.st === 'needs_review' && <span className="text-amber">· {t(C.needsReview)}</span>}
                  </div>
                  <h2 className="display text-[1.5rem] leading-snug mt-2 break-words">{selObject.n}</h2>
                  <div className="mono text-[10px] text-faint mt-1.5 break-all">{selObject.id}</div>
                </div>
                <button onClick={() => setSel(null)} className="mono text-[11px] text-mute hover:text-ink shrink-0">{t(C.close)} ✕</button>
              </div>
              <div className="mt-5 grid lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] gap-x-10 gap-y-6">
                <div className="min-w-0">
                  <div className="mono text-[10px] tracking-[0.16em] uppercase text-faint">{t(C.summary)}</div>
                  <p className="mt-2 text-[13.5px] leading-relaxed text-ink/90">{selObject.s}</p>
                  <p className="mt-3 text-[12px] text-faint leading-relaxed">
                    {t((C as Record<string, { zh: string; en: string }>)[`basis_${selObject.b}`] ?? C.basis_stated)}
                  </p>
                  {Object.keys(selObject.attrs).length > 0 && (
                    <>
                      <div className="mono text-[10px] tracking-[0.16em] uppercase text-faint mt-5">{t(C.attrs)}</div>
                      <dl className="mt-2 text-[12.5px]">
                        {Object.entries(selObject.attrs).map(([k, v]) => (
                          <div key={k} className="grid grid-cols-[110px_minmax(0,1fr)] gap-3 py-1.5 border-t border-line">
                            <dt className="mono text-[10.5px] text-mute break-words">{k}</dt>
                            <dd className="text-ink/85 break-words leading-relaxed">{Array.isArray(v) ? v.join(' · ') : String(v)}</dd>
                          </div>
                        ))}
                      </dl>
                    </>
                  )}
                </div>
                <div className="min-w-0 space-y-7">
                  <div className="mono text-[10px] tracking-[0.16em] uppercase text-faint">{t(C.quoteFrom)}</div>
                  {selObject.evidence.length === 0 && <p className="text-[12.5px] text-mute leading-relaxed">{t(C.noEvidence)}</p>}
                  {selObject.evidence.map((e, i) => (
                    <Quote key={`${e.id}-${i}`} e={e} src={srcById.get(e.source)} onZoom={(url, alt) => setZoom({ url, alt })} />
                  ))}
                </div>
              </div>
            </motion.div>
          )}
          <p className="mt-4 text-[12px] text-faint leading-relaxed max-w-[820px]">{t(C.note)}</p>
        </section>
      ) : (
        <section className="mx-auto max-w-[1240px] px-5 md:px-8 mt-10">
          <div className="panel rounded-sm p-6 max-w-2xl">
            <p className="text-[13.5px] text-mute leading-relaxed">{t(C.support)}</p>
            {artifact.depends_on.length > 0 && (
              <div className="mt-4">
                <div className="mono text-[10px] tracking-[0.16em] uppercase text-faint">{t(C.depends)}</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {artifact.depends_on.map((d) => (
                    <Link key={d} to={`/artifact/${encodeURIComponent(d)}`} className="mono text-[11px] border border-line-2 rounded-sm px-2 py-1 text-mute hover:text-mint hover:border-mint/40">
                      {d}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* dependencies + body */}
      {(artifact.body || (m.objects.length > 0 && artifact.depends_on.length > 0)) && (
        <section className="mx-auto max-w-[1240px] px-5 md:px-8 mt-10">
          {m.objects.length > 0 && artifact.depends_on.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="mono text-[10px] tracking-[0.16em] uppercase text-faint mr-1">{t(C.depends)}</span>
              {artifact.depends_on.map((d) => (
                <Link key={d} to={`/artifact/${encodeURIComponent(d)}`} className="mono text-[11px] border border-line-2 rounded-sm px-2 py-1 text-mute hover:text-mint hover:border-mint/40 break-all">
                  {d}
                </Link>
              ))}
            </div>
          )}
          {artifact.body && (
            <div className="mt-5">
              <button onClick={() => setShowBody((x) => !x)} className="mono text-[11.5px] text-mint hover:text-[#69ecb4]">
                {showBody ? '−' : '+'} {showBody ? t(C.bodyHide) : t(C.body)} <span className="text-faint">{artifact.path}</span>
              </button>
              {showBody && (
                <pre className="mt-3 panel rounded-sm p-4 md:p-5 mono text-[11.5px] leading-[1.7] text-ink/85 whitespace-pre-wrap break-words max-h-[520px] overflow-y-auto">{artifact.body}</pre>
              )}
            </div>
          )}
        </section>
      )}

      {/* lightbox */}
      {zoom && (
        <div className="fixed inset-0 z-[70] bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 md:p-10" role="dialog" aria-modal="true" onClick={() => setZoom(null)}>
          <img src={zoom.url} alt={zoom.alt} className="max-h-full max-w-full bg-white rounded-sm" />
          <button className="absolute top-4 right-5 mono text-[12px] text-ink/80 hover:text-ink" onClick={() => setZoom(null)}>{t(C.close)} ✕</button>
        </div>
      )}
    </div>
  )
}

function ColHead({ n, title, count }: { n: string; title: string; count?: number }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <div className="mono text-[10.5px] tracking-[0.18em] uppercase text-mint/80">
        {n} <span className="text-mute">· {title}</span>
      </div>
      {count != null && <div className="mono text-[10.5px] text-faint tabular">{count}</div>}
    </div>
  )
}

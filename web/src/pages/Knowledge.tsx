import { useEffect, useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { ErrorBox, Skeleton } from '../components/ui'
import { Link } from '../lib/router'
import { useT } from '../lib/i18n'
import { basisLabel, kindLabel, loadCatalog, loadGraph, loadMeta, loadSources, typeColor, useAsync } from '../lib/data'
import type { CatalogObject } from '../lib/data'

const C = {
  kicker: { zh: '知识目录', en: 'Knowledge catalog' },
  title: { zh: '从 177 份资料里抽取出的结构化知识', en: 'Structured knowledge extracted from 177 materials' },
  loading: { zh: '正在读取知识目录…', en: 'Loading the knowledge catalog…' },
  byType: { zh: '按类型', en: 'By type' },
  byBasis: { zh: '按来源', en: 'By basis' },
  relations: { zh: '知识之间的关系', en: 'Relations between objects' },
  conflictNote: { zh: '冲突的定义并排保留，不合并成一个答案', en: 'Conflicting definitions are kept side by side, never merged' },
  questions: { zh: '待确认问题', en: 'Open questions' },
  open: { zh: '仍开放', en: 'open' },
  resolved: { zh: '已解决', en: 'resolved' },
  search: { zh: '搜索名称、摘要或 ID…', en: 'Search name, summary or id…' },
  usedOnly: { zh: '只看进入最终产物的', en: 'Only those used by artifacts' },
  review: { zh: '待复核', en: 'Needs review' },
  all: { zh: '全部', en: 'All' },
  of: { zh: '共', en: 'of' },
  page: { zh: '第 {a} / {b} 页', en: 'Page {a} / {b}' },
  prev: { zh: '上一页', en: 'Prev' },
  next: { zh: '下一页', en: 'Next' },
  none: { zh: '没有匹配的知识。', en: 'No matching objects.' },
  evidence: { zh: '条证据', en: 'evidence' },
  usedBy: { zh: '用于这些产物', en: 'Used by' },
  unused: { zh: '未进入最终产物；保留在完整目录中，供检索与复核。', en: 'Not used by any artifact; kept in the full catalog for search and review.' },
  location: { zh: '首次出现', en: 'First location' },
  sources: { zh: '来源资料', en: 'Source files' },
  related: { zh: '相关关系', en: 'Relations' },
  close: { zh: '关闭', en: 'Close' },
  note: {
    zh: '目录是完整的抽取记录；文档、Skill 和工具只引用其中进入规划的部分。',
    en: 'The catalog is the full extraction record; documents, skills and tools reference the part selected by the plan.',
  },
  typeHelp: {
    concept: { zh: '有定义的术语', en: 'a defined term' },
    claim: { zh: '资料做出的陈述', en: 'a statement made by a source' },
    method: { zh: '公式或步骤', en: 'a formula or procedure' },
    constraint: { zh: '必须满足的规则', en: 'a rule that must hold' },
    dataset: { zh: '被描述的数据', en: 'a described data resource' },
    capability: { zh: '已有代码或工具', en: 'existing code or a tool' },
  } as Record<string, { zh: string; en: string }>,
}

const PAGE = 40
const ROSE = '#ef7a7a'
const num = (n: number) => n.toLocaleString('en-US')
const fileName = (p: string) => p.split('/').pop() ?? p

export default function Knowledge() {
  const t = useT()
  const reduce = useReducedMotion() ?? false
  const { data, error } = useAsync(() => Promise.all([loadMeta(), loadCatalog(), loadGraph(), loadSources()]), [])
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const [types, setTypes] = useState<Set<string>>(new Set())
  const [usedOnly, setUsedOnly] = useState(false)
  const [review, setReview] = useState(false)
  const [page, setPage] = useState(0)
  const [sel, setSel] = useState<CatalogObject | null>(null)

  useEffect(() => {
    const id = setTimeout(() => setQuery(input.trim().toLowerCase()), 180)
    return () => clearTimeout(id)
  }, [input])
  useEffect(() => setPage(0), [query, types, usedOnly, review])

  const catalog = data?.[1] ?? []
  const hay = useMemo(() => catalog.map((o) => `${o.n}\n${o.s}\n${o.id}`.toLowerCase()), [catalog])
  const used = useMemo(() => {
    const by = new Map<string, string[]>()
    for (const e of data?.[2].edges ?? []) if (e.k === 'in') by.set(e.s, [...(by.get(e.s) ?? []), e.t])
    return by
  }, [data])
  const srcById = useMemo(() => new Map((data?.[3] ?? []).map((s) => [s.id, s])), [data])

  const hits = useMemo(() => {
    const out: number[] = []
    for (let i = 0; i < catalog.length; i++) {
      const o = catalog[i]
      if (types.size && !types.has(o.t)) continue
      if (usedOnly && !used.has(o.id)) continue
      if (review && o.st !== 'needs_review') continue
      if (query && !hay[i].includes(query)) continue
      out.push(i)
    }
    return out
  }, [catalog, hay, query, types, usedOnly, review, used])

  if (error) return <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16"><ErrorBox msg={error} /></div>
  if (!data) return <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16"><Skeleton label={t(C.loading)} /></div>

  const [meta, , graph] = data
  const c = meta.counts
  const typeRows = Object.entries(c.objects_by_type).sort((a, b) => b[1] - a[1])
  const basisRows = Object.entries(c.objects_by_basis).sort((a, b) => b[1] - a[1])
  const relRows = Object.entries(c.relations_by_type).sort((a, b) => b[1] - a[1])
  const relMax = relRows[0]?.[1] ?? 1
  const pages = Math.max(1, Math.ceil(hits.length / PAGE))
  const rows = hits.slice(page * PAGE, page * PAGE + PAGE).map((i) => catalog[i])
  const toggleType = (k: string) =>
    setTypes((cur) => {
      const n = new Set(cur)
      if (n.has(k)) n.delete(k)
      else n.add(k)
      return n
    })
  const selRelations = sel ? graph.relations.filter((r) => r.s === sel.id || r.t === sel.id) : []

  return (
    <div className="pb-10">
      <section className="mx-auto max-w-[1240px] px-5 md:px-8 pt-12 md:pt-14">
        <div className="mono text-[11px] tracking-[0.22em] text-mint/80 uppercase">{t(C.kicker)}</div>
        <div className="mt-4 flex flex-wrap items-end gap-x-8 gap-y-3">
          <div className="display tabular text-[4rem] md:text-[5.5rem] leading-[0.9] text-ink text-glow">{num(c.objects)}</div>
          <h1 className="display text-[1.3rem] md:text-[1.6rem] leading-snug text-mute max-w-[18em] pb-1">{t(C.title)}</h1>
        </div>

        {/* type distribution */}
        <div className="mt-9">
          <div className="flex h-12 gap-[3px]">
            {typeRows.map(([k, n], i) => (
              <motion.button
                key={k}
                onClick={() => toggleType(k)}
                initial={reduce ? false : { scaleX: 0 }}
                animate={{ scaleX: 1 }}
                transition={{ duration: 0.7, ease: [0.2, 0.7, 0.2, 1], delay: i * 0.06 }}
                style={{ flexGrow: Math.max(n / c.objects, 0.014), backgroundColor: typeColor[k], transformOrigin: 'left', opacity: types.size && !types.has(k) ? 0.25 : 0.92 }}
                className="h-full rounded-[2px] hover:brightness-110 transition-[filter,opacity]"
                aria-label={`${k} ${n}`}
              />
            ))}
          </div>
          <div className="mt-4 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-x-6 gap-y-4">
            {typeRows.map(([k, n]) => (
              <button key={k} onClick={() => toggleType(k)} className={`text-left transition-opacity ${types.size && !types.has(k) ? 'opacity-40' : ''}`}>
                <div className="flex items-center gap-2">
                  <span className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ backgroundColor: typeColor[k] }} />
                  <span className="text-[13px] text-ink">{kindLabel[k] ? t(kindLabel[k]) : k}</span>
                </div>
                <div className="display tabular text-[1.5rem] leading-none mt-1.5" style={{ color: typeColor[k] }}>{num(n)}</div>
                <div className="text-[11px] text-faint mt-1">{C.typeHelp[k] ? t(C.typeHelp[k]) : ''}</div>
              </button>
            ))}
          </div>
        </div>

        {/* relations / basis / questions */}
        <div className="mt-10 grid lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-6">
          <div className="panel rounded-sm p-5 md:p-6">
            <div className="flex items-baseline justify-between gap-3">
              <div className="mono text-[10.5px] tracking-[0.2em] uppercase text-mint/80">{t(C.relations)}</div>
              <div className="display tabular text-[1.5rem] leading-none">{num(c.relations)}</div>
            </div>
            <div className="mt-4 space-y-2">
              {relRows.map(([k, n], i) => {
                const conflict = k === 'conflicts_with'
                return (
                  <div key={k} className="grid grid-cols-[132px_minmax(0,1fr)_52px] items-center gap-3">
                    <span className="mono text-[11px]" style={{ color: conflict ? ROSE : '#8d9a92' }}>{k}</span>
                    <div className="h-2.5 bg-white/[0.05] rounded-[1px] overflow-hidden">
                      <motion.div
                        initial={reduce ? false : { width: 0 }}
                        whileInView={{ width: `${(n / relMax) * 100}%` }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.7, ease: [0.2, 0.7, 0.2, 1], delay: i * 0.04 }}
                        className="h-full rounded-[1px]"
                        style={{ backgroundColor: conflict ? ROSE : '#4fe3a4', opacity: conflict ? 1 : 0.55, width: reduce ? `${(n / relMax) * 100}%` : undefined }}
                      />
                    </div>
                    <span className="mono text-[11px] tabular text-right" style={{ color: conflict ? ROSE : '#e9efe9' }}>{num(n)}</span>
                  </div>
                )
              })}
            </div>
            <div className="mt-4 text-[12px] text-rose/90">{num(c.relations_by_type.conflicts_with ?? 0)} · {t(C.conflictNote)}</div>
          </div>
          <div className="grid gap-6">
            <div className="panel rounded-sm p-5 md:p-6">
              <div className="mono text-[10.5px] tracking-[0.2em] uppercase text-mint/80">{t(C.byBasis)}</div>
              <div className="mt-4 flex h-3 gap-[2px]">
                {basisRows.map(([k, n], i) => (
                  <div key={k} className="h-full rounded-[1px]" style={{ flexGrow: Math.max(n / c.objects, 0.01), backgroundColor: ['#4fe3a4', '#74a9f7', '#efb75a', '#b39dfa'][i % 4] }} />
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2">
                {basisRows.map(([k, n], i) => (
                  <div key={k}>
                    <div className="display tabular text-[1.25rem] leading-none" style={{ color: ['#4fe3a4', '#74a9f7', '#efb75a', '#b39dfa'][i % 4] }}>{num(n)}</div>
                    <div className="text-[11.5px] text-mute mt-1">{basisLabel[k] ? t(basisLabel[k]) : k}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="panel rounded-sm p-5 md:p-6">
              <div className="mono text-[10.5px] tracking-[0.2em] uppercase text-amber/90">{t(C.questions)}</div>
              <div className="mt-3 flex items-baseline gap-8">
                <div>
                  <span className="display tabular text-[1.9rem] leading-none text-amber">{num(c.gaps_open)}</span>
                  <span className="text-[11.5px] text-mute ml-2">{t(C.open)}</span>
                </div>
                <div>
                  <span className="display tabular text-[1.9rem] leading-none text-mint">{num(c.gaps_resolved)}</span>
                  <span className="text-[11.5px] text-mute ml-2">{t(C.resolved)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* explorer */}
      <section className="mx-auto max-w-[1240px] px-5 md:px-8 mt-12">
        <div className="sticky top-16 z-20 -mx-5 md:-mx-8 px-5 md:px-8 py-3 bg-void/90 backdrop-blur-md border-y border-line">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t(C.search)}
              className="bg-transparent border border-line-2 rounded-sm px-3 py-2 text-[13px] text-ink placeholder:text-faint w-full sm:w-[300px] focus:outline-none focus:border-mint/50"
            />
            <div className="flex flex-wrap gap-1.5">
              {typeRows.map(([k]) => (
                <button
                  key={k}
                  onClick={() => toggleType(k)}
                  className={`text-[11.5px] px-2.5 py-1 rounded-full border transition-colors ${types.has(k) ? 'bg-white/[0.06]' : 'border-line-2 text-mute hover:text-ink'}`}
                  style={types.has(k) ? { borderColor: typeColor[k], color: typeColor[k] } : undefined}
                >
                  {kindLabel[k] ? t(kindLabel[k]) : k}
                </button>
              ))}
            </div>
            <button onClick={() => setUsedOnly((x) => !x)} className={`text-[11.5px] px-2.5 py-1 rounded-full border transition-colors ${usedOnly ? 'border-mint text-mint bg-mint/[0.07]' : 'border-line-2 text-mute hover:text-ink'}`}>
              {t(C.usedOnly)} · {used.size}
            </button>
            <button onClick={() => setReview((x) => !x)} className={`text-[11.5px] px-2.5 py-1 rounded-full border transition-colors ${review ? 'border-amber text-amber bg-amber/[0.07]' : 'border-line-2 text-mute hover:text-ink'}`}>
              {t(C.review)}
            </button>
            <span className="ml-auto mono text-[11px] text-mute tabular">
              <span className="text-ink">{num(hits.length)}</span> / {num(catalog.length)}
            </span>
          </div>
        </div>

        <div className="mt-2">
          {rows.length === 0 && <div className="py-14 text-sm text-faint">{t(C.none)}</div>}
          {rows.map((o) => (
            <button
              key={o.id}
              onClick={() => setSel(o)}
              className="w-full text-left grid grid-cols-[72px_minmax(0,1fr)] md:grid-cols-[84px_minmax(0,1fr)_minmax(0,260px)_64px] gap-x-4 gap-y-1 items-baseline py-3 border-b border-line hover:bg-white/[0.025] transition-colors px-1"
            >
              <span className="mono text-[10.5px]" style={{ color: typeColor[o.t] }}>
                {kindLabel[o.t] ? t(kindLabel[o.t]) : o.t}
              </span>
              <span className="min-w-0">
                <span className="text-[13.5px] text-ink">{o.n}</span>
                {used.has(o.id) && <span className="ml-2 inline-block h-1.5 w-1.5 rounded-full bg-mint align-middle" />}
                {o.st === 'needs_review' && <span className="ml-2 mono text-[9.5px] text-amber">{t(C.review)}</span>}
                <span className="block text-[12px] text-mute truncate mt-0.5">{o.s}</span>
              </span>
              <span className="hidden md:block mono text-[10.5px] text-faint truncate">
                {o.loc ? `${fileName(srcById.get(o.loc.source)?.path ?? o.loc.source)}${o.loc.page ? ` · p.${o.loc.page}` : ''}` : ''}
              </span>
              <span className="hidden md:block mono text-[10.5px] text-faint tabular text-right">{o.ev} {t(C.evidence)}</span>
            </button>
          ))}
        </div>
        <div className="mt-5 flex items-center gap-3 mono text-[11px] text-mute">
          <button disabled={page === 0} onClick={() => setPage((p) => p - 1)} className="border border-line-2 rounded-sm px-3 py-1.5 disabled:opacity-30 hover:text-ink">← {t(C.prev)}</button>
          <span className="tabular">{t(C.page).replace('{a}', String(page + 1)).replace('{b}', String(pages))}</span>
          <button disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)} className="border border-line-2 rounded-sm px-3 py-1.5 disabled:opacity-30 hover:text-ink">{t(C.next)} →</button>
          <span className="ml-auto text-faint hidden sm:block">{t(C.note)}</span>
        </div>
      </section>

      {/* drawer */}
      {sel && (
        <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSel(null)} />
          <motion.aside
            initial={reduce ? false : { x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.35, ease: [0.2, 0.7, 0.2, 1] }}
            className="absolute right-0 top-0 bottom-0 w-full sm:w-[480px] bg-deep border-l border-line-2 overflow-y-auto p-6 md:p-7"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="mono text-[10.5px]" style={{ color: typeColor[sel.t] }}>
                {kindLabel[sel.t] ? t(kindLabel[sel.t]) : sel.t} <span className="text-mute">· {basisLabel[sel.b] ? t(basisLabel[sel.b]) : sel.b}</span>
                {sel.st === 'needs_review' && <span className="text-amber"> · {t(C.review)}</span>}
              </div>
              <button onClick={() => setSel(null)} className="mono text-[11px] text-mute hover:text-ink">{t(C.close)} ✕</button>
            </div>
            <h2 className="display text-[1.45rem] leading-snug mt-3 break-words">{sel.n}</h2>
            <div className="mono text-[10px] text-faint mt-2 break-all select-all">{sel.id}</div>
            <p className="mt-5 text-[13.5px] leading-relaxed text-ink/90">{sel.s}</p>

            <div className="hairline mt-6 pt-4">
              <div className="mono text-[10px] tracking-[0.16em] uppercase text-faint">{t(C.usedBy)}</div>
              {used.has(sel.id) ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {[...new Set(used.get(sel.id))].map((a) => (
                    <Link key={a} to={`/artifact/${encodeURIComponent(a)}`} className="mono text-[11px] border border-mint/30 text-mint rounded-sm px-2 py-1 hover:bg-mint/[0.08] break-all">
                      {a}
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-[12.5px] text-mute leading-relaxed">{t(C.unused)}</p>
              )}
            </div>
            {sel.loc && (
              <div className="hairline mt-5 pt-4">
                <div className="mono text-[10px] tracking-[0.16em] uppercase text-faint">{t(C.location)}</div>
                <div className="mt-2 text-[12.5px] text-ink/90 break-words">{srcById.get(sel.loc.source)?.path ?? sel.loc.source}</div>
                <div className="mono text-[10.5px] text-mute mt-1 break-words">
                  {sel.loc.page ? `p.${sel.loc.page} ` : ''}{sel.loc.section}
                </div>
              </div>
            )}
            {sel.src.length > 1 && (
              <div className="hairline mt-5 pt-4">
                <div className="mono text-[10px] tracking-[0.16em] uppercase text-faint">{t(C.sources)}</div>
                <ul className="mt-2 space-y-1">
                  {sel.src.map((s) => (
                    <li key={s} className="text-[12px] text-mute break-words">{fileName(srcById.get(s)?.path ?? s)}</li>
                  ))}
                </ul>
              </div>
            )}
            {selRelations.length > 0 && (
              <div className="hairline mt-5 pt-4">
                <div className="mono text-[10px] tracking-[0.16em] uppercase text-faint">{t(C.related)}</div>
                <ul className="mt-2 space-y-3">
                  {selRelations.map((r, i) => (
                    <li key={i} className="text-[12px] leading-relaxed">
                      <span className="mono text-[10.5px]" style={{ color: r.k === 'conflicts_with' ? ROSE : '#4fe3a4' }}>{r.k}</span>
                      <span className="mono text-[10px] text-faint break-all block">{r.s === sel.id ? r.t : r.s}</span>
                      <span className="text-mute">{r.note}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </motion.aside>
        </div>
      )}
    </div>
  )
}

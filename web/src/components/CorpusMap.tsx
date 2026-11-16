import { useMemo, useState } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'motion/react'
import { useT } from '../lib/i18n'
import { kindLabel, typeColor } from '../lib/data'
import type { LibrarySource } from '../lib/data'

/**
 * The corpus as a map: one tile per source file, grouped by the folder it came in, sized by the
 * knowledge extracted from it. Selecting a tile shows what TerraKernel took from that file and
 * figures cropped from its pages.
 */

const C = {
  kicker: { zh: '资料库', en: 'The corpus' },
  title: { zh: '{n} 份资料，每一份都被读过', en: '{n} materials, every one of them read' },
  lead: {
    zh: '每个方块是一份资料，面积代表从中抽取的知识量。点开看它贡献了什么。',
    en: 'Each tile is one material; its area is the knowledge extracted from it. Select one to see what it contributed.',
  },
  files: { zh: '份', en: 'files' },
  objects: { zh: '条知识', en: 'objects' },
  evidence: { zh: '条证据', en: 'evidence units' },
  inRepo: { zh: '已进入生成的仓库', en: 'used by the generated repository' },
  legendUsed: { zh: '已进入生成的仓库', en: 'Used by the generated repository' },
  legendKept: { zh: '已抽取，保留在知识目录', en: 'Extracted, kept in the catalog' },
  top: { zh: '抽取出的知识（节选）', en: 'Knowledge extracted (sample)' },
  figures: { zh: '原文中的图', en: 'Figures from the document' },
  page: { zh: '第 {n} 页', en: 'p. {n}' },
  pick: { zh: '选择一份资料', en: 'Select a material' },
  all: { zh: '全部', en: 'All' },
  share: { zh: '知识量占比', en: 'share of extracted knowledge' },
}

const MINT = '#4fe3a4'
const fileName = (p: string) => p.split('/').pop() ?? p
const ext = (p: string) => (p.split('.').pop() ?? '').toUpperCase()
const num = (n: number) => n.toLocaleString('en-US')

/** Group key: the top folder, or the second level when the top folder holds sub-collections. */
function groupOf(s: LibrarySource, deep: Set<string>): string {
  const parts = s.path.split('/')
  return parts.length > 2 && deep.has(parts[0]) ? `${parts[0]} / ${parts[1]}` : parts[0]
}

export default function CorpusMap({ sources }: { sources: LibrarySource[] }) {
  const t = useT()
  const reduce = useReducedMotion() ?? false
  const [selId, setSelId] = useState<string | null>(null)
  const [zoom, setZoom] = useState<string | null>(null)

  const groups = useMemo(() => {
    // a top folder is "deep" when most of its files sit in sub-folders
    const nested = new Map<string, number>()
    const total = new Map<string, number>()
    for (const s of sources) {
      const parts = s.path.split('/')
      total.set(parts[0], (total.get(parts[0]) ?? 0) + 1)
      if (parts.length > 2) nested.set(parts[0], (nested.get(parts[0]) ?? 0) + 1)
    }
    const deep = new Set([...total.keys()].filter((k) => (nested.get(k) ?? 0) / total.get(k)! > 0.6))
    const by = new Map<string, LibrarySource[]>()
    for (const s of sources) {
      const g = groupOf(s, deep)
      by.set(g, [...(by.get(g) ?? []), s])
    }
    return [...by.entries()]
      .map(([name, items]) => ({ name, items: items.sort((a, b) => b.objects - a.objects), objects: items.reduce((n, s) => n + s.objects, 0), used: items.filter((s) => s.in_artifacts > 0).length }))
      .sort((a, b) => b.objects - a.objects)
  }, [sources])

  const totalObjects = sources.reduce((n, s) => n + s.objects, 0) || 1
  const maxObjects = Math.max(...sources.map((s) => s.objects), 1)
  const usedCount = sources.filter((s) => s.in_artifacts > 0).length
  const sel = sources.find((s) => s.id === selId) ?? groups[0]?.items[0] ?? null
  const size = (n: number) => 14 + Math.sqrt(n / maxObjects) * 62

  return (
    <div>
      <div className="mono text-[11px] tracking-[0.22em] text-mint/80 uppercase">{t(C.kicker)}</div>
      <h2 className="display text-[1.7rem] md:text-[2.2rem] leading-[1.12] mt-3">{t(C.title).replace('{n}', String(sources.length))}</h2>
      <p className="mt-3 text-[14px] text-mute max-w-[640px]">{t(C.lead)}</p>
      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 mono text-[10.5px] text-mute">
        <span className="inline-flex items-center gap-2"><span className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ backgroundColor: MINT }} />{t(C.legendUsed)} · {usedCount}</span>
        <span className="inline-flex items-center gap-2"><span className="inline-block h-2.5 w-2.5 rounded-[2px] border border-mint/50 bg-mint/15" />{t(C.legendKept)} · {sources.length - usedCount}</span>
      </div>

      <div className="mt-6 grid lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)] gap-6">
        <div className="panel rounded-sm p-4 md:p-5 space-y-5">
          {groups.map((g) => (
            <div key={g.name}>
              <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                <span className="text-[12.5px] text-ink/90">{g.name}</span>
                <span className="mono text-[10px] text-faint tabular">
                  {g.items.length} {t(C.files)} · {num(g.objects)} {t(C.objects)} · {Math.round((g.objects / totalObjects) * 100)}%
                </span>
              </div>
              <div className="mt-2 flex flex-wrap items-end gap-[3px]">
                {g.items.map((s) => {
                  const d = size(s.objects)
                  const used = s.in_artifacts > 0
                  const on = sel?.id === s.id
                  return (
                    <button
                      key={s.id}
                      onClick={() => setSelId(s.id)}
                      title={`${fileName(s.path)} · ${num(s.objects)}`}
                      aria-label={fileName(s.path)}
                      className="rounded-[2px] transition-all hover:brightness-125"
                      style={{
                        width: d,
                        height: d,
                        backgroundColor: used ? MINT : 'rgba(79,227,164,0.14)',
                        border: used ? '1px solid transparent' : '1px solid rgba(79,227,164,0.42)',
                        opacity: used ? 0.92 : 1,
                        outline: on ? '2px solid #efb75a' : 'none',
                        outlineOffset: 2,
                        boxShadow: on ? '0 0 18px rgba(239,183,90,0.5)' : 'none',
                      }}
                    />
                  )
                })}
              </div>
            </div>
          ))}
        </div>

        <AnimatePresence mode="wait">
          {sel && (
            <motion.div
              key={sel.id}
              initial={reduce ? false : { opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reduce ? undefined : { opacity: 0 }}
              transition={{ duration: 0.3, ease: [0.2, 0.7, 0.2, 1] }}
              className="panel rounded-sm p-5 md:p-6 min-w-0"
            >
              <div className="flex items-center gap-2 mono text-[10px]">
                <span className="border border-line-2 rounded-sm px-1.5 py-0.5 text-amber">{ext(sel.path)}</span>
                {sel.in_artifacts > 0 && <span className="text-mint">{t(C.inRepo)}</span>}
              </div>
              <div className="mt-2.5 text-[15px] leading-snug text-ink break-words">{fileName(sel.path)}</div>
              <div className="mt-4 flex gap-8">
                <div>
                  <div className="display tabular text-[1.9rem] leading-none text-mint">{num(sel.objects)}</div>
                  <div className="mono text-[10px] text-mute mt-1.5">{t(C.objects)}</div>
                </div>
                <div>
                  <div className="display tabular text-[1.9rem] leading-none">{num(sel.evidence)}</div>
                  <div className="mono text-[10px] text-mute mt-1.5">{t(C.evidence)}</div>
                </div>
              </div>
              {sel.objects > 0 && (
                <>
                  <div className="mt-4 flex h-2.5 gap-[2px]">
                    {Object.entries(sel.by_type).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
                      <div key={k} className="h-full rounded-[1px]" style={{ flexGrow: n, backgroundColor: typeColor[k] }} title={`${k} ${n}`} />
                    ))}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 mono text-[10px] text-mute">
                    {Object.entries(sel.by_type).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
                      <span key={k} style={{ color: typeColor[k] }}>{kindLabel[k] ? t(kindLabel[k]) : k} {n}</span>
                    ))}
                  </div>
                </>
              )}
              {sel.top.length > 0 && (
                <div className="hairline mt-4 pt-3">
                  <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-faint">{t(C.top)}</div>
                  <ul className="mt-2 space-y-1.5">
                    {sel.top.slice(0, 5).map((o) => (
                      <li key={o.id} className="flex items-baseline gap-2 text-[12px] leading-snug text-ink/85">
                        <span className="inline-block h-1.5 w-1.5 rounded-full shrink-0 translate-y-[-1px]" style={{ backgroundColor: typeColor[o.t] }} />
                        <span className="break-words min-w-0">{o.n}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {sel.figures.length > 0 && (
                <div className="hairline mt-4 pt-3">
                  <div className="mono text-[9.5px] tracking-[0.16em] uppercase text-faint">{t(C.figures)}</div>
                  <div className="mt-2 grid grid-cols-3 gap-1.5">
                    {sel.figures.slice(0, 6).map((f) => (
                      <button key={f.src} onClick={() => setZoom(`data/${f.src}`)} className="group relative aspect-[4/3] bg-white rounded-[2px] overflow-hidden border border-line-2 hover:border-mint/60 transition-colors">
                        <img src={`data/${f.src}`} alt={f.caption || fileName(sel.path)} loading="lazy" className="absolute inset-0 h-full w-full object-cover" />
                        {f.page && <span className="absolute bottom-0 right-0 mono text-[9px] bg-black/70 text-ink px-1">{t(C.page).replace('{n}', String(f.page))}</span>}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {zoom && (
        <div className="fixed inset-0 z-[70] bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 md:p-10" role="dialog" aria-modal="true" onClick={() => setZoom(null)}>
          <img src={zoom} alt="" className="max-h-full max-w-full bg-white rounded-sm" />
        </div>
      )}
    </div>
  )
}

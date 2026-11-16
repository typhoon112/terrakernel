import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { ErrorBox, Skeleton } from '../components/ui'
import { Link } from '../lib/router'
import { useLang, useT } from '../lib/i18n'
import { loadArtifacts, loadMeta, loadReplay, loadSources, useAsync } from '../lib/data'
import type { Artifact, Meta, Replay, SourceRow } from '../lib/data'

/* ------------------------------------------------------------------ copy */

const C = {
  kicker: { zh: '构建回放', en: 'Build replay' },
  title: { zh: '一次真实构建，从 177 份资料到一个仓库', en: 'One real build, from 177 materials to a repository' },
  intro: {
    zh: '下面播放的是构建日志里记录的事件：每份资料何时解析完、抽取出多少条知识，最后生成了哪些文件。',
    en: 'What plays below is the event log of the build: when each material was parsed, how much knowledge it yielded, and which files were finally written.',
  },
  honesty: {
    zh: '时间戳来自构建日志，回放按阶段压缩。关联阶段的日志只记录了每批的数量，没有记录每条关系出现的先后，所以这里只显示批次计数。',
    en: 'Timestamps come from the build log; the replay compresses them stage by stage. For reconcile the log records batch sizes only, not the order of individual relations, so only batch counts are shown.',
  },
  play: { zh: '播放', en: 'Play' },
  pause: { zh: '暂停', en: 'Pause' },
  restart: { zh: '重新播放', en: 'Restart' },
  speed: { zh: '速度', en: 'Speed' },
  clock: { zh: '构建时间', en: 'Build time' },
  materials: { zh: '资料', en: 'Materials' },
  parsed: { zh: '已解析', en: 'parsed' },
  extracted: { zh: '已抽取', en: 'extracted' },
  knowledge: { zh: '知识', en: 'Knowledge' },
  repository: { zh: '仓库', en: 'Repository' },
  evidence: { zh: '证据单元', en: 'Evidence units' },
  objects: { zh: '抽取出的知识对象', en: 'Knowledge objects extracted' },
  gaps: { zh: '记录的待确认问题', en: 'Open questions recorded' },
  relating: { zh: '跨资料关联', en: 'Relating across materials' },
  batch: { zh: '批', en: 'batches' },
  waiting: { zh: '等待前面的阶段', en: 'Waiting for earlier stages' },
  planning: { zh: '正在规划仓库…', en: 'Planning the repository…' },
  docs: { zh: '知识文档', en: 'Knowledge docs' },
  skills: { zh: 'Skills', en: 'Skills' },
  tools: { zh: '工具', en: 'Tools' },
  verdict: { zh: '仓库检查', en: 'Repository checks' },
  pass: { zh: '通过', en: 'pass' },
  warn: { zh: '提醒', en: 'warn' },
  fail: { zh: '失败', en: 'fail' },
  log: { zh: '构建日志', en: 'Build log' },
  logEmpty: { zh: '按播放开始。', en: 'Press play to start.' },
  done: { zh: '构建完成', en: 'Build complete' },
  doneSub: {
    zh: '仓库里最终保留的数量（关联阶段会合并同义概念并新增上位概念，所以与抽取阶段的累计数不同）。',
    en: 'What the finished repository holds (reconcile merges synonyms and adds umbrella concepts, so these differ from the running totals of extraction).',
  },
  seeLayers: { zh: '看看生成了什么', en: 'See what was built' },
  relations: { zh: '关系', en: 'Relations' },
  artifacts: { zh: '产物', en: 'Artifacts' },
  calls: { zh: '次模型调用', en: 'model calls' },
  status_verified: { zh: '已验证', en: 'verified' },
  status_tested: { zh: '仅性质测试', en: 'property-tested' },
  status_failed: { zh: '未开放', en: 'withheld' },
  status_blocked: { zh: '受阻', en: 'blocked' },
}

/* ---------------------------------------------------------------- timeline */

const MINT = '#4fe3a4'
const AMBER = '#efb75a'
const SKY = '#74a9f7'
const ROSE = '#ef7a7a'
const VIOLET = '#b39dfa'
const KIND_COLOR: Record<string, string> = { pdf: MINT, table: AMBER, text: SKY }
const BASE_SECONDS = 84 // length of the replay at 1×

const ms = (iso: string) => Date.parse(iso)
const clock = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`
const num = (n: number) => Math.round(n).toLocaleString('en-US')

type Ev = {
  u: number
  stage: string
  time: string
  msg: string
  kind: 'item' | 'batch' | 'end'
  source?: string
  evidence?: number
  objects?: number
  gaps?: number
  tool?: string
  status?: string
}

type Segment = {
  stage: string
  label: { zh: string; en: string }
  seconds: number
  calls: number
  u0: number
  u1: number
  /** build-seconds elapsed before this segment */
  b0: number
}

type Timeline = {
  segs: Segment[]
  events: Ev[]
  cumEvidence: number[]
  cumObjects: number[]
  cumGaps: number[]
  cumBatches: number[]
  totalBuild: number
  batchTotal: number
}

function buildTimeline(replay: Replay): Timeline {
  // One segment per stage. A stage that ran more than once is played as one continuous run:
  // the kept runs are laid end to end, and their seconds and model calls are added up.
  const stages = replay.stages.map((st) => ({ st, runs: st.attempts.filter((a) => a.used) })).filter((x) => x.runs.length > 0)
  const secs = stages.map(({ runs }) => runs.reduce((n, a) => n + a.seconds, 0))
  const weights = secs.map((x) => Math.sqrt(Math.max(4, x)) + 3)
  const total = weights.reduce((n, w) => n + w, 0) || 1
  const segs: Segment[] = []
  const events: Ev[] = []
  let u = 0
  let b = 0
  stages.forEach(({ st, runs }, i) => {
    const w = weights[i] / total
    const calls = runs.reduce((n, a) => n + (a.model_calls ?? 0), 0)
    const seg: Segment = { stage: st.stage, label: { zh: st.zh, en: st.en }, seconds: secs[i], calls, u0: u, u1: u + w, b0: b }
    segs.push(seg)
    let done = 0
    for (const a of runs) {
      const r0 = seg.u0 + (w * done) / Math.max(1, secs[i])
      const r1 = seg.u0 + (w * (done + a.seconds)) / Math.max(1, secs[i])
      const t0 = ms(a.start)
      const span = Math.max(1, ms(a.end) - t0)
      const at = (iso: string) => r0 + (r1 - r0) * Math.min(0.985, Math.max(0, (ms(iso) - t0) / span))
      for (const it of st.items) {
        if (it.a !== a.n) continue
        events.push({
          u: at(it.t), stage: st.stage, time: it.t, kind: 'item', msg: it.msg, source: it.source,
          evidence: it.evidence, objects: it.objects, gaps: it.gaps, tool: it.tool, status: it.status,
        })
      }
      if (st.stage === 'reconcile' && a.n === runs[runs.length - 1].n)
        for (const bt of replay.relate_batches) events.push({ u: at(bt.t), stage: st.stage, time: bt.t, kind: 'batch', msg: bt.msg })
      done += a.seconds
    }
    events.push({ u: seg.u1 - 1e-6, stage: st.stage, time: runs[runs.length - 1].end, kind: 'end', msg: `${st.stage} · ${clock(secs[i])}` })
    u += w
    b += secs[i]
  })
  events.sort((x, y) => x.u - y.u)

  const cumEvidence: number[] = []
  const cumObjects: number[] = []
  const cumGaps: number[] = []
  const cumBatches: number[] = []
  let e = 0
  let o = 0
  let g = 0
  let bn = 0
  for (const ev of events) {
    if (ev.kind === 'item') {
      e += ev.evidence ?? 0
      o += ev.objects ?? 0
      g += ev.gaps ?? 0
    }
    if (ev.kind === 'batch') bn++
    cumEvidence.push(e)
    cumObjects.push(o)
    cumGaps.push(g)
    cumBatches.push(bn)
  }
  return { segs, events, cumEvidence, cumObjects, cumGaps, cumBatches, totalBuild: b, batchTotal: bn }
}

/** index of the last event with u <= p, or -1 */
function cursorAt(events: Ev[], p: number) {
  let lo = 0
  let hi = events.length - 1
  let ans = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (events[mid].u <= p) {
      ans = mid
      lo = mid + 1
    } else hi = mid - 1
  }
  return ans
}

/* --------------------------------------------------------------- hooks */

function usePlayback(reduce: boolean) {
  const [p, setP] = useState(reduce ? 1 : 0)
  const [playing, setPlaying] = useState(!reduce)
  const [speed, setSpeed] = useState(1)
  const pRef = useRef(p)
  const speedRef = useRef(speed)
  speedRef.current = speed

  useEffect(() => {
    if (!playing) return
    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000)
      last = now
      pRef.current = Math.min(1, pRef.current + (dt * speedRef.current) / BASE_SECONDS)
      setP(pRef.current)
      if (pRef.current >= 1) {
        setPlaying(false)
        return
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing])

  const seek = useCallback((v: number) => {
    pRef.current = Math.min(1, Math.max(0, v))
    setP(pRef.current)
  }, [])
  const toggle = useCallback(() => {
    if (pRef.current >= 1) {
      pRef.current = 0
      setP(0)
      setPlaying(true)
    } else setPlaying((x) => !x)
  }, [])
  const restart = useCallback(() => {
    pRef.current = 0
    setP(0)
    setPlaying(true)
  }, [])
  return { p, playing, speed, setSpeed, seek, toggle, restart }
}

/* ------------------------------------------------------------ components */

const Cell = memo(function Cell({ state, color, title }: { state: 0 | 1 | 2; color: string; title: string }) {
  return (
    <div
      title={title}
      className="aspect-square rounded-[2px] transition-[background-color,box-shadow,opacity] duration-500"
      style={{
        backgroundColor: state === 0 ? 'rgba(214,234,223,0.06)' : color,
        opacity: state === 1 ? 0.34 : 1,
        boxShadow: state === 2 ? `0 0 8px ${color}99` : 'none',
      }}
    />
  )
})

function Counter({ value, label, color, big = false }: { value: number; label: string; color?: string; big?: boolean }) {
  return (
    <div className="min-w-0">
      <div className={`display tabular leading-none ${big ? 'text-[2.4rem] md:text-[3.1rem]' : 'text-[1.5rem] md:text-[1.9rem]'}`} style={{ color: color ?? '#e9efe9' }}>
        {num(value)}
      </div>
      <div className="mono text-[10.5px] tracking-wide text-mute mt-2 leading-snug">{label}</div>
    </div>
  )
}

/** Decorative density field: the number of dots follows the object count; positions mean nothing. */
function Density({ fraction, pulse, color }: { fraction: number; pulse: number; color: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const pts = useMemo(() => {
    let a = 1234567
    const r = () => {
      a = (a + 0x6d2b79f5) | 0
      let t = Math.imul(a ^ (a >>> 15), 1 | a)
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296
    }
    return Array.from({ length: 900 }, () => {
      const ang = r() * Math.PI * 2
      const rad = Math.sqrt(r())
      return { x: 0.5 + Math.cos(ang) * rad * 0.48, y: 0.5 + Math.sin(ang) * rad * 0.44, s: 0.6 + r() * 1.2, c: r() }
    })
  }, [])
  useEffect(() => {
    const c = ref.current
    if (!c) return
    const ctx = c.getContext('2d')
    if (!ctx) return
    const rect = c.getBoundingClientRect()
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    c.width = Math.round(rect.width * dpr)
    c.height = Math.round(rect.height * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, rect.width, rect.height)
    const n = Math.round(pts.length * Math.min(1, fraction))
    const palette = [MINT, SKY, VIOLET, AMBER]
    for (let i = 0; i < n; i++) {
      const q = pts[i]
      ctx.fillStyle = pulse > 0 && q.c < pulse ? color : palette[Math.floor(q.c * palette.length)]
      ctx.globalAlpha = 0.28 + q.c * 0.5
      ctx.beginPath()
      ctx.arc(q.x * rect.width, q.y * rect.height, q.s, 0, 6.283)
      ctx.fill()
    }
    ctx.globalAlpha = 1
  }, [fraction, pulse, color, pts])
  return <canvas ref={ref} className="h-full w-full" aria-hidden />
}

function RestartIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden>
      <path d="M2.2 6a3.8 3.8 0 1 0 1.2-2.8" />
      <path d="M1.6 1.6v2h2" />
    </svg>
  )
}

/* ------------------------------------------------------------------ page */

export default function ReplayPage() {
  const t = useT()
  const { lang } = useLang()
  const reduce = useReducedMotion() ?? false
  const { data, error } = useAsync(() => Promise.all([loadReplay(), loadMeta(), loadSources(), loadArtifacts()]), [])
  const pb = usePlayback(reduce)

  const tl = useMemo(() => (data ? buildTimeline(data[0]) : null), [data])
  const sources: SourceRow[] = data?.[2] ?? []
  const order = useMemo(() => {
    if (!data) return [] as string[]
    const ing = data[0].stages.find((s) => s.stage === 'ingest')
    const seen = new Set<string>()
    const out: string[] = []
    for (const it of ing?.items ?? []) if (it.source && !seen.has(it.source)) { seen.add(it.source); out.push(it.source) }
    for (const s of data[2]) if (!seen.has(s.id)) out.push(s.id)
    return out
  }, [data])
  const srcById = useMemo(() => new Map(sources.map((s) => [s.id, s])), [sources])

  // u at which each source was parsed / extracted
  const marks = useMemo(() => {
    const ing = new Map<string, number>()
    const ext = new Map<string, number>()
    for (const ev of tl?.events ?? []) {
      if (ev.kind !== 'item' || !ev.source) continue
      if (ev.stage === 'ingest') ing.set(ev.source, ev.u)
      if (ev.stage === 'extract') ext.set(ev.source, ev.u)
    }
    return { ing, ext }
  }, [tl])

  if (error) return <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16"><ErrorBox msg={error} /></div>
  if (!data || !tl) return <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16"><Skeleton /></div>

  const [replay, meta, , bundle] = data as [Replay, Meta, SourceRow[], { artifacts: Artifact[] }]
  const p = pb.p
  const cur = cursorAt(tl.events, p)
  const seg = tl.segs.find((s) => p >= s.u0 && p < s.u1) ?? tl.segs[tl.segs.length - 1]
  const segFrac = Math.min(1, Math.max(0, (p - seg.u0) / Math.max(1e-9, seg.u1 - seg.u0)))
  const buildSec = p >= 1 ? tl.totalBuild : seg.b0 + seg.seconds * segFrac
  const stageIdx = (name: string) => tl.segs.findIndex((s) => s.stage === name)
  const reached = (name: string) => { const i = stageIdx(name); return i >= 0 && p >= tl.segs[i].u0 }
  const finished = (name: string) => {
    const xs = tl.segs.filter((s) => s.stage === name)
    return xs.length > 0 && p >= xs[xs.length - 1].u1 - 1e-6
  }
  const evidence = cur < 0 ? 0 : tl.cumEvidence[cur]
  const objects = cur < 0 ? 0 : tl.cumObjects[cur]
  const gaps = cur < 0 ? 0 : tl.cumGaps[cur]
  const batches = cur < 0 ? 0 : tl.cumBatches[cur]
  const lastBatch = (() => { for (let i = cur; i >= 0; i--) if (tl.events[i].kind === 'batch') return tl.events[i]; return null })()
  const relateTotal = replay.relate_totals[0]?.msg ?? ''
  const ended = p >= 1
  const c = meta.counts

  const parsedN = order.reduce((n, id) => n + ((marks.ing.get(id) ?? 2) <= p ? 1 : 0), 0)
  const extractedN = order.reduce((n, id) => n + ((marks.ext.get(id) ?? 2) <= p ? 1 : 0), 0)

  const arts = bundle.artifacts
  const docs = arts.filter((a) => a.kind === 'knowledge_doc')
  const skills = arts.filter((a) => a.kind === 'skill')
  const tools = arts.filter((a) => a.kind === 'tool')
  const compileEvents = tl.events.filter((e) => e.stage === 'compile' && e.kind === 'item')
  const shownAt = (match: (msg: string) => boolean) => {
    const e = compileEvents.find((x) => match(x.msg))
    return e ? e.u <= p : finished('compile')
  }
  const planLine = tl.events.find((e) => e.stage === 'plan' && e.kind === 'item')?.msg ?? ''
  const verdictLine = tl.events.find((e) => e.stage === 'validate' && e.kind === 'item')?.msg ?? ''
  const v = meta.validation.summary

  const log = [] as Ev[]
  for (let i = cur; i >= 0 && log.length < 60; i--) if (tl.events[i].kind !== 'batch' || log.length < 3 || i % 6 === 0) log.push(tl.events[i])

  const stageColor: Record<string, string> = { ingest: '#8d9a92', extract: MINT, reconcile: VIOLET, plan: SKY, compile: AMBER, validate: MINT }

  return (
    <div className="pb-8">
      {/* header */}
      <section className="mx-auto max-w-[1240px] px-5 md:px-8 pt-12 md:pt-14">
        <div className="mono text-[11px] tracking-[0.22em] text-mint/80 uppercase">{t(C.kicker)}</div>
        <h1 className="display text-[2rem] md:text-[2.7rem] leading-[1.1] mt-4 max-w-[20em]">{t(C.title)}</h1>
        <p className="mt-4 text-[14.5px] leading-relaxed text-mute max-w-[720px]">{t(C.intro)}</p>
      </section>

      {/* transport */}
      <section className="sticky top-16 z-30 mt-8 border-y border-line bg-void/90 backdrop-blur-md">
        <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-3">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <button
              onClick={pb.toggle}
              className="inline-flex items-center gap-2 bg-mint text-void text-[13px] font-medium pl-3 pr-4 py-1.5 rounded-sm hover:bg-[#69ecb4] transition-colors"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
                {pb.playing ? <path d="M2.5 1.5h2.5v9H2.5zM7 1.5h2.5v9H7z" fill="currentColor" /> : <path d="M2.5 1.2 10.5 6l-8 4.8z" fill="currentColor" />}
              </svg>
              {pb.playing ? t(C.pause) : t(C.play)}
            </button>
            <button onClick={pb.restart} className="inline-flex items-center gap-1.5 mono text-[11px] text-mute hover:text-ink transition-colors">
              <RestartIcon />
              {t(C.restart)}
            </button>
            <div className="flex items-center gap-1 mono text-[11px] text-mute">
              <span className="mr-1">{t(C.speed)}</span>
              {[1, 2, 4].map((s) => (
                <button
                  key={s}
                  onClick={() => pb.setSpeed(s)}
                  className={`px-2 py-0.5 rounded-sm border transition-colors ${pb.speed === s ? 'border-mint/50 text-mint' : 'border-line-2 hover:text-ink'}`}
                >
                  {s}×
                </button>
              ))}
            </div>
            <div className="ml-auto mono text-[11px] text-mute tabular">
              {t(C.clock)} <span className="text-ink">{clock(buildSec)}</span> / {clock(tl.totalBuild)}
            </div>
          </div>
          {/* stage timeline */}
          <div className="relative mt-3">
            <div className="flex gap-[3px]">
              {tl.segs.map((s, i) => {
                const active = s === seg && !ended
                const past = p >= s.u1 - 1e-6
                return (
                  <button
                    key={s.stage}
                    onClick={() => pb.seek(s.u0 + 1e-6)}
                    style={{ flexGrow: s.u1 - s.u0, flexBasis: 0 }}
                    className="group relative min-w-0 text-left"
                    aria-label={t(s.label)}
                  >
                    <div className="h-1.5 rounded-[1px] overflow-hidden bg-white/[0.07]">
                      <div
                        className="h-full"
                        style={{
                          width: `${past ? 100 : active ? segFrac * 100 : 0}%`,
                          backgroundColor: stageColor[s.stage],
                        }}
                      />
                    </div>
                    <div className={`mt-1.5 mono text-[10px] truncate transition-colors ${active ? 'text-ink' : 'text-faint group-hover:text-mute'}`}>
                      <span style={{ color: active || past ? stageColor[s.stage] : undefined }}>{String(i + 1).padStart(2, '0')}</span>{' '}
                      {t(s.label)}
                    </div>
                    <div className="mono text-[9.5px] text-faint truncate hidden md:block">
                      {clock(s.seconds)}{s.calls ? ` · ${s.calls} ${t(C.calls)}` : ''}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      </section>

      {/* main stage */}
      <section className="mx-auto max-w-[1240px] px-5 md:px-8 mt-6">
        <div className="panel rounded-sm grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1.25fr)_minmax(0,1fr)] divide-y lg:divide-y-0 lg:divide-x divide-line">
          {/* materials */}
          <div className="p-5 md:p-6 min-w-0">
            <div className="flex items-baseline justify-between gap-3">
              <div className="mono text-[10.5px] tracking-[0.2em] uppercase text-mint/80">01 · {t(C.materials)}</div>
              <div className="mono text-[10.5px] text-mute tabular">
                {parsedN}/{order.length} {t(C.parsed)} · {extractedN} {t(C.extracted)}
              </div>
            </div>
            <div className="mt-4 grid gap-[3px]" style={{ gridTemplateColumns: 'repeat(15, minmax(0, 1fr))' }}>
              {order.map((id) => {
                const s = srcById.get(id)
                const state: 0 | 1 | 2 = (marks.ext.get(id) ?? 2) <= p ? 2 : (marks.ing.get(id) ?? 2) <= p ? 1 : 0
                return (
                  <Cell
                    key={id}
                    state={state}
                    color={KIND_COLOR[s?.kind ?? ''] ?? '#8d9a92'}
                    title={s ? `${s.path}\n${num(s.evidence)} evidence · ${num(s.objects)} objects` : id}
                  />
                )
              })}
            </div>
            <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 mono text-[10px] text-faint">
              {Object.entries(KIND_COLOR).map(([k, col]) => {
                const n = sources.filter((s) => s.kind === k).length
                return n ? (
                  <span key={k} className="inline-flex items-center gap-1.5">
                    <span className="inline-block h-2 w-2 rounded-[1px]" style={{ backgroundColor: col }} />
                    {k} {n}
                  </span>
                ) : null
              })}
            </div>
            <div className="mt-5 hairline pt-4 min-h-[3.2rem]">
              <CurrentSource events={tl.events} cur={cur} srcById={srcById} idle={t(C.logEmpty)} />
            </div>
          </div>

          {/* knowledge */}
          <div className="p-5 md:p-6 flex flex-col min-w-0">
            <div className="mono text-[10.5px] tracking-[0.2em] uppercase text-mint/80">02 · {t(C.knowledge)}</div>
            <div className="mt-5 grid grid-cols-2 gap-x-6 gap-y-6">
              <div className="col-span-2">
                <Counter big value={evidence} label={t(C.evidence)} />
              </div>
              <Counter value={objects} label={t(C.objects)} color={MINT} />
              <Counter value={gaps} label={t(C.gaps)} color={AMBER} />
            </div>
            <div className="relative mt-5 flex-1 min-h-[150px]">
              <Density fraction={objects / Math.max(1, tl.cumObjects[tl.cumObjects.length - 1])} pulse={reached('reconcile') && !finished('reconcile') ? (batches % 5) / 12 + 0.05 : 0} color={VIOLET} />
            </div>
            <div className="hairline pt-4 mt-2 min-h-[4.2rem]">
              {reached('reconcile') ? (
                <div>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="mono text-[10.5px] tracking-wide" style={{ color: VIOLET }}>{t(C.relating)}</span>
                    <span className="mono text-[10.5px] text-mute tabular">{batches}/{tl.batchTotal} {t(C.batch)}</span>
                  </div>
                  <div className="mt-2 h-1 bg-white/[0.07] rounded-[1px] overflow-hidden">
                    <div className="h-full" style={{ width: `${(batches / Math.max(1, tl.batchTotal)) * 100}%`, backgroundColor: VIOLET }} />
                  </div>
                  <div className="mono text-[10.5px] text-mute mt-2 truncate">
                    {finished('reconcile') ? relateTotal : lastBatch?.msg ?? ''}
                  </div>
                </div>
              ) : (
                <div className="mono text-[10.5px] text-faint">{t(C.relating)} — {t(C.waiting)}</div>
              )}
            </div>
          </div>

          {/* repository */}
          <div className="p-5 md:p-6 min-w-0">
            <div className="mono text-[10.5px] tracking-[0.2em] uppercase text-mint/80">03 · {t(C.repository)}</div>
            <div className="mt-4 mono text-[10.5px] min-h-[1.2rem] break-words" style={{ color: SKY }}>
              {finished('plan') ? planLine : reached('plan') ? t(C.planning) : <span className="text-faint">{t(C.waiting)}</span>}
            </div>
            <RepoGroup title={t(C.docs)} color={MINT}>
              {docs.map((d) => (
                <RepoRow key={d.id} on={shownAt((m) => !!d.path && m.startsWith(d.path))} label={(d.path ?? d.id).split('/').pop() ?? d.id} color={MINT} />
              ))}
            </RepoGroup>
            <RepoGroup title={t(C.skills)} color={AMBER}>
              {skills.map((s) => {
                const name = s.id.split(':')[1]
                return <RepoRow key={s.id} on={shownAt((m) => m.startsWith(`skill ${name}:`))} label={name} color={s.status === 'blocked' ? ROSE : AMBER} tag={s.status === 'blocked' ? t(C.status_blocked) : undefined} />
              })}
            </RepoGroup>
            <RepoGroup title={t(C.tools)} color={SKY}>
              {tools.map((tool) => {
                const name = tool.tool?.name ?? tool.id.split(':')[1]
                const ev = compileEvents.find((e) => e.tool === name)
                const status = ev?.status ?? tool.tool?.status
                const tag = status === 'verified' ? t(C.status_verified) : status === 'tested' ? t(C.status_tested) : status === 'failed' ? t(C.status_failed) : undefined
                return <RepoRow key={tool.id} on={ev ? ev.u <= p : finished('compile')} label={name} color={status === 'verified' ? MINT : status === 'tested' ? AMBER : ROSE} tag={tag} />
              })}
            </RepoGroup>
            <div className="mt-5 hairline pt-4 min-h-[4.6rem]">
              {finished('validate') ? (
                <motion.div initial={reduce ? false : { opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.45, ease: [0.2, 0.7, 0.2, 1] }}>
                  <div className="mono text-[10.5px] tracking-wide text-mint">{t(C.verdict)}</div>
                  <div className="mt-2 flex items-baseline gap-5">
                    <span><span className="display tabular text-[1.7rem] text-mint">{v.pass ?? 0}</span> <span className="mono text-[10.5px] text-mute">{t(C.pass)}</span></span>
                    <span><span className="display tabular text-[1.7rem] text-ink">{v.fail ?? 0}</span> <span className="mono text-[10.5px] text-mute">{t(C.fail)}</span></span>
                    <span><span className="display tabular text-[1.7rem] text-amber">{v.warn ?? 0}</span> <span className="mono text-[10.5px] text-mute">{t(C.warn)}</span></span>
                  </div>
                  <div className="mono text-[10px] text-faint mt-1 truncate">{verdictLine}</div>
                </motion.div>
              ) : (
                <div className="mono text-[10.5px] text-faint">{t(C.verdict)} — {t(C.waiting)}</div>
              )}
            </div>
          </div>
        </div>
        <p className="mt-3 text-[12px] leading-relaxed text-faint max-w-[900px]">
          {t(C.honesty)}
        </p>
      </section>

      {/* end state */}
      {ended && (
        <motion.section
          initial={reduce ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.2, 0.7, 0.2, 1] }}
          className="mx-auto max-w-[1240px] px-5 md:px-8 mt-8"
        >
          <div className="panel glow-mint rounded-sm p-6 md:p-8">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="mono text-[10.5px] tracking-[0.2em] uppercase text-mint">{t(C.done)}</div>
                <p className="mt-2 text-[12.5px] text-mute max-w-[620px] leading-relaxed">{t(C.doneSub)}</p>
              </div>
              <div className="flex gap-3">
                <button onClick={pb.restart} className="inline-flex items-center gap-2 border border-line-2 text-ink text-[13px] px-4 py-2 rounded-sm hover:border-mint/40 hover:text-mint transition-colors"><RestartIcon />{t(C.restart)}</button>
                <Link to="/layers" className="bg-mint text-void text-[13px] font-medium px-4 py-2 rounded-sm hover:bg-[#69ecb4] transition-colors">{t(C.seeLayers)} →</Link>
              </div>
            </div>
            <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-6 gap-y-6">
              <Counter value={c.sources} label={t(C.materials)} color={MINT} />
              <Counter value={c.evidence} label={t(C.evidence)} />
              <Counter value={c.objects} label={lang === 'zh' ? '知识对象' : 'Knowledge objects'} />
              <Counter value={c.relations} label={t(C.relations)} />
              <Counter value={c.gaps_open} label={lang === 'zh' ? '仍待确认的问题' : 'Questions still open'} color={AMBER} />
              <Counter value={c.artifacts} label={t(C.artifacts)} />
            </div>
          </div>
        </motion.section>
      )}

      {/* log + attempts */}
      <section className="mx-auto max-w-[1240px] px-5 md:px-8 mt-8">
        <div className="panel rounded-sm p-5 md:p-6 min-w-0">
          <div className="mono text-[10.5px] tracking-[0.2em] uppercase text-mint/80">{t(C.log)}</div>
          <div className="mt-4 h-[300px] overflow-y-auto pr-2">
            {log.length === 0 && <div className="mono text-[11px] text-faint">{t(C.logEmpty)}</div>}
            {log.map((e, i) => (
              <div key={`${e.u}-${i}`} className="flex gap-3 mono text-[11px] leading-[1.75]">
                <span className="text-faint tabular shrink-0">{e.time.slice(11, 19)}</span>
                <span className="shrink-0 w-[68px]" style={{ color: stageColor[e.stage] }}>{e.stage}</span>
                <span className={`min-w-0 break-words ${i === 0 ? 'text-ink' : 'text-mute'}`}>{e.msg}</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}

function CurrentSource({ events, cur, srcById, idle }: { events: Ev[]; cur: number; srcById: Map<string, SourceRow>; idle: string }) {
  let ev: Ev | null = null
  for (let i = cur; i >= 0; i--) if (events[i].kind === 'item' && events[i].source) { ev = events[i]; break }
  if (!ev) return <div className="mono text-[10.5px] text-faint">{idle}</div>
  const s = srcById.get(ev.source!)
  return (
    <div className="min-w-0">
      <div className="mono text-[10.5px] text-ink truncate" title={s?.path}>{s?.path.split('/').pop() ?? ev.source}</div>
      <div className="mono text-[10.5px] text-mute mt-1 tabular">
        {ev.stage === 'ingest' ? `→ ${num(ev.evidence ?? 0)} evidence units` : `→ ${num(ev.objects ?? 0)} objects · ${num(ev.gaps ?? 0)} gaps`}
      </div>
    </div>
  )
}

function RepoGroup({ title, color, children }: { title: string; color: string; children: React.ReactNode }) {
  return (
    <div className="mt-4">
      <div className="mono text-[9.5px] tracking-[0.18em] uppercase" style={{ color }}>{title}</div>
      <div className="mt-1.5 space-y-[5px]">{children}</div>
    </div>
  )
}

function RepoRow({ on, label, color, tag }: { on: boolean; label: string; color: string; tag?: string }) {
  return (
    <div className={`flex items-center gap-2 mono text-[11px] transition-all duration-500 ${on ? 'opacity-100 translate-x-0' : 'opacity-[0.16] -translate-x-1'}`}>
      <span
        className="inline-block h-1.5 w-1.5 rounded-full shrink-0"
        style={on ? { backgroundColor: color, boxShadow: `0 0 6px ${color}` } : { backgroundColor: 'rgba(255,255,255,0.2)' }}
      />
      <span className="truncate text-ink/90">{label}</span>
      {on && tag && <span className="ml-auto shrink-0 text-[9.5px]" style={{ color }}>{tag}</span>}
    </div>
  )
}

import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { loadMeta, loadReplay, loadSources, useAsync, type Meta, type Replay, type SourceRow } from '../lib/data'
import { ErrorBox, Panel, SectionHead, Skeleton, Stat, Tag } from '../components/ui'
import { useT } from '../lib/i18n'

/* ------------------------------------------------------------------ copy */

type Bi<T = string> = { zh: T; en: T }
type Tr = <T>(x: Bi<T>) => T

const num = (n: number | null | undefined) => (n == null ? '–' : n.toLocaleString('en-US'))

const C = {
  kicker: { zh: 'TERRAKERNEL · 构建工作流', en: 'TERRAKERNEL · BUILD WORKFLOW' },
  title: { zh: '一条只能引用资料、不能编造的流水线', en: 'A pipeline that quotes the materials and invents nothing' },
  intro: {
    zh: '从 177 份研究材料出发，六个阶段生成一个带工具、测试与 skill 的研究仓库。图中每一个数字都来自这次真实构建的日志，不是示意值。',
    en: 'Starting from 177 research documents, six stages produce a research repository with tools, tests and skills. Every number below comes from the log of this real build, not from a mock-up.',
  },
  statFiles: { zh: '份研究资料', en: 'research files' },
  statEvidence: { zh: '个可定位证据单元', en: 'evidence units' },
  statObjects: { zh: '个知识对象', en: 'knowledge objects' },
  statRelations: { zh: '条跨资料关系', en: 'cross-source relations' },
  statArtifacts: { zh: '个编译产物', en: 'compiled artifacts' },
  statCalls: { zh: '次模型调用', en: 'model calls' },
  graphKicker: { zh: 'PIPELINE', en: 'PIPELINE' },
  graphTitle: { zh: '一次构建的六个阶段', en: 'Six stages of one build' },
  graphHint: {
    zh: '点击任一阶段查看它的数字与日志；窄屏为纵向布局，可拖动平移。',
    en: 'Click a stage for its numbers and log lines. On narrow screens the chain is vertical and can be panned.',
  },
  chipHint: { zh: '选择阶段', en: 'Pick a stage' },
  detail: { zh: '阶段详情', en: 'Stage detail' },
  what: { zh: '它做什么', en: 'What it does' },
  numbers: { zh: '真实数字', en: 'Real numbers' },
  events: { zh: '构建日志 · 原样摘录', en: 'Build log · quoted as recorded' },
  replayLine: { zh: '回放', en: 'Replay' },
  calls: { zh: '模型调用', en: 'model calls' },
  warns: { zh: '警告', en: 'warnings' },
  guaranteedKicker: { zh: 'GUARANTEES', en: 'GUARANTEES' },
  guaranteedTitle: { zh: '流水线强制执行的规则', en: 'Rules the pipeline enforces' },
  guaranteedIntro: {
    zh: '这些不是设计口号：每一条都能在本次构建中找到对应的数字与产物，点击可跳到发生它的阶段。',
    en: 'These are not slogans: each one has a number and an artifact behind it in this build. Click one to jump to the stage where it happened.',
  },
  built: { zh: '构建于', en: 'Built' },
  bundle: { zh: '数据包版本', en: 'bundle' },
  inputLabel: { zh: '资料', en: 'Materials' },
  outputLabel: { zh: '生成的仓库', en: 'Generated repository' },
  stageCount: { zh: '6 个阶段', en: '6 stages' },
  workbooks: { zh: '工作簿', en: 'workbooks' },
  callUnit: { zh: '次调用', en: 'calls' },
}

const STAGES: { key: string; zh: string; en: string; accent: string; short: Bi; what: Bi }[] = [
  {
    key: 'ingest',
    zh: '资料导入',
    en: 'Ingest',
    accent: '#74a9f7',
    short: {
      zh: 'PDF、工作簿、网页与专著，全部转成可定位证据',
      en: 'PDFs, workbooks, a web page and a book, all turned into locatable evidence',
    },
    what: {
      zh: '逐份读取材料，把每一页、每一节切成证据单元，并记下来源路径与页码。此阶段不做判断，也不调用模型。',
      en: 'Reads every file and cuts pages and sections into evidence units, recording source path and page. No judgement and no model calls at this stage.',
    },
  },
  {
    key: 'extract',
    zh: '知识抽取',
    en: 'Extract',
    accent: '#4fe3a4',
    short: {
      zh: '每条陈述必须逐字引用证据，否则被拒绝；说不清的记为待补项',
      en: 'Each statement must quote its evidence verbatim or it is rejected; what is unclear becomes a recorded gap',
    },
    what: {
      zh: '每份资料被切成证据单元，抽取出的每条陈述必须逐字引用原文证据，由代码逐条校验，引不出原文的陈述被拒绝。资料没说的内容记为待补项，不用常识补全。',
      en: 'Every source is chunked into evidence units; each extracted statement must quote its evidence verbatim and is checked by code. Statements without a verbatim quote are rejected. What the materials do not say is recorded as an open gap instead of being filled from common sense.',
    },
  },
  {
    key: 'reconcile',
    zh: '跨资料关联',
    en: 'Reconcile',
    accent: '#b39dfa',
    short: {
      zh: '把跨资料的同义概念接起来，矛盾并排保留，缺口逐条记录',
      en: 'Links synonymous concepts across sources, keeps contradictions side by side, records gaps',
    },
    what: {
      zh: '按批次把不同资料里的同一概念接起来（same_as、possibly_same_as、variant_of），把分散的条目归到伞形概念下。互相矛盾的表述不被合并成一条“正确答案”，而是并排保留；无法确认的缺口逐条记录。',
      en: 'In batches, links the same concept across sources (same_as, possibly_same_as, variant_of) and groups scattered entries under umbrella concepts. Contradictory statements are not merged into one “correct answer” but kept side by side; unresolved gaps are recorded one by one.',
    },
  },
  {
    key: 'plan',
    zh: '仓库规划',
    en: 'Plan',
    accent: '#efb75a',
    short: {
      zh: '决定写哪些文档、计算说明、工具与 skill，各自覆盖哪些对象',
      en: 'Decides which docs, computation notes, tools and skills to write, and which objects each covers',
    },
    what: {
      zh: '把知识库整理成仓库蓝图：哪些主题值得写成知识文档、哪些公式值得写成计算说明、哪些方法可以变成可执行工具、哪些流程值得做成 skill，以及每个产物的依赖与覆盖范围。',
      en: 'Turns the knowledge base into a repository blueprint: which topics deserve a knowledge doc, which formulas a computation note, which methods an executable tool, which workflows a skill — plus each artifact’s dependencies and coverage.',
    },
  },
  {
    key: 'compile',
    zh: '生成产物',
    en: 'Compile',
    accent: '#5fd6d6',
    short: {
      zh: '写出文档、工具、测试与 skill；工具用资料里的算例核对',
      en: 'Writes docs, tools, tests and skills; tools are checked against worked examples',
    },
    what: {
      zh: '按蓝图写出知识文档、计算说明、工具、测试、skill 与仓库入口。每个工具都用资料原文中的算例核对期望值；对不上、或资料中没有可核对算例的，降低状态或直接撤回，不留在仓库里冒充可用。',
      en: 'Writes knowledge docs, computation notes, tools, tests, skills and repository entries from the blueprint. Every tool is checked against worked examples quoted from the materials; tools that fail, or that have no checkable example, are demoted or withdrawn rather than shipped as if usable.',
    },
  },
  {
    key: 'validate',
    zh: '检查',
    en: 'Validate',
    accent: '#4fe3a4',
    short: {
      zh: '对生成的仓库跑静态与运行时检查：引文、链接、工具输出、覆盖',
      en: 'Static and runtime checks on the generated repository: quotes, links, tool output, coverage',
    },
    what: {
      zh: '在生成结果上再跑一遍自动检查：每条引文能否定位、文档链接是否成立、工具是否能运行、文档是否引用了它声称覆盖的对象。通过、警告与失败分开计数。',
      en: 'Runs another automated pass over the generated repository: can every quote be located, do document links resolve, do the tools run, does each doc cite the objects it claims to cover. Passes, warnings and failures are counted separately.',
    },
  },
]

const GUARANTEES: { rule: Bi; evidence: Bi; stage: string; accent: 'mint' | 'amber' | 'sky' | 'violet' }[] = [
  {
    rule: { zh: '每条陈述都引用证据，并由代码逐条校验。', en: 'Every statement cites evidence, and code checks each one.' },
    evidence: { zh: '15,375 条引文校验通过，160 条被拒绝', en: '15,375 quote checks passed, 160 rejected' },
    stage: 'extract',
    accent: 'mint',
  },
  {
    rule: { zh: '冲突并排保留，不被合并成一条“正确答案”。', en: 'Conflicts are kept side by side, never merged into one “correct answer”.' },
    evidence: { zh: '316 组冲突关系原样保留', en: '316 conflicts_with relations kept' },
    stage: 'reconcile',
    accent: 'violet',
  },
  {
    rule: { zh: '缺口如实记录，不用默认值填平。', en: 'Gaps are recorded, not filled with defaults.' },
    evidence: { zh: '4,780 个待补项，4,651 个仍未解决', en: '4,780 gaps recorded, 4,651 still open' },
    stage: 'extract',
    accent: 'amber',
  },
  {
    rule: { zh: '工具必须用资料中的算例验证，验证不过就降级或撤回。', en: 'Tools must be verified against worked examples in the materials; those that fail are demoted or withdrawn.' },
    evidence: { zh: '4 个工具：1 已验证，2 仅性质测试，1 撤回', en: '4 tools: 1 verified, 2 property-tested, 1 withheld' },
    stage: 'compile',
    accent: 'sky',
  },
]

/* --------------------------------------------------------------- helpers */

function useWide(min = 760) {
  const [wide, setWide] = useState(() => (typeof window === 'undefined' ? true : window.innerWidth >= min))
  useEffect(() => {
    const mq = window.matchMedia(`(min-width: ${min}px)`)
    const on = () => setWide(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [min])
  return wide
}

function pick3<T>(rows: T[]): T[] {
  if (rows.length <= 3) return rows
  return [rows[0], rows[Math.floor(rows.length / 2)], rows[rows.length - 1]]
}

type StageData = {
  idx: string
  zh: string
  en: string
  accent: string
  meta: string
  short: Bi
  active: boolean
  inPos: Position | null
  outPos: Position | null
}

type MaterialsData = { title: string; total: string; rows: string[]; outPos: Position | null }
type OutputData = { title: string; rows: { path: string; note: string }[]; inPos: Position | null }

/* ----------------------------------------------------------------- nodes */

function Dot({ pos, type, id }: { pos: Position; type: 'source' | 'target'; id?: string }) {
  return (
    <Handle
      id={id}
      type={type}
      position={pos}
      className="!h-1.5 !w-1.5 !border-0 !bg-mint/70"
      style={{ pointerEvents: 'none' }}
    />
  )
}

function StageNode({ data }: NodeProps) {
  const d = data as unknown as StageData
  const t = useT()
  return (
    <div
      className={`panel rounded-sm px-4 py-3.5 w-full transition-colors ${d.active ? 'glow-mint' : ''}`}
      style={d.active ? { borderColor: 'rgba(79,227,164,0.45)' } : undefined}
    >
      {d.inPos && <Dot type="target" pos={d.inPos} />}
      {d.outPos && <Dot type="source" pos={d.outPos} />}
      <div className="flex items-center justify-between gap-2">
        <span className="mono text-[10px] tracking-[0.22em]" style={{ color: d.accent }}>
          {d.idx}
        </span>
        {d.active && <span className="mono text-[9px] tracking-widest text-mint">ACTIVE</span>}
      </div>
      <div className="display text-[17px] leading-tight text-ink mt-1.5">{t({ zh: d.zh, en: d.en })}</div>
      <div className="mono tabular text-[10px] text-mute mt-1.5">{d.meta}</div>
      <div className="text-[10.5px] leading-snug text-faint mt-2">{t(d.short)}</div>
    </div>
  )
}

function MaterialsNode({ data }: NodeProps) {
  const d = data as unknown as MaterialsData
  return (
    <div className="panel rounded-sm px-4 py-3.5 w-full" style={{ borderColor: 'rgba(116,169,247,0.28)' }}>
      {d.outPos && <Dot type="source" pos={d.outPos} />}
      <div className="mono text-[9.5px] tracking-[0.22em] text-sky/80">INPUT</div>
      <div className="display text-[18px] text-ink mt-1">{d.title}</div>
      <div className="display tabular text-[28px] leading-none text-ink mt-1.5">{d.total}</div>
      <div className="mt-2.5 space-y-1">
        {d.rows.map((r) => (
          <div key={r} className="mono text-[10px] text-mute tabular">
            {r}
          </div>
        ))}
      </div>
    </div>
  )
}

function OutputNode({ data }: NodeProps) {
  const d = data as unknown as OutputData
  return (
    <div className="panel rounded-sm px-4 py-3.5 w-full" style={{ borderColor: 'rgba(79,227,164,0.3)' }}>
      {d.inPos && <Dot type="target" pos={d.inPos} />}
      <div className="mono text-[9.5px] tracking-[0.22em] text-mint/80">OUTPUT</div>
      <div className="display text-[18px] text-ink mt-1">{d.title}</div>
      <div className="mt-2.5 space-y-1.5">
        {d.rows.map((r) => (
          <div key={r.path} className="flex items-baseline justify-between gap-2">
            <span className="mono text-[10px] text-ink/85 truncate">{r.path}</span>
            <span className="mono text-[9px] text-faint tabular shrink-0">{r.note}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const nodeTypes = { stage: StageNode, materials: MaterialsNode, output: OutputNode }

const rfStyles = `
.rf-wrap .react-flow__controls { box-shadow: none; border: 1px solid rgba(214,234,223,0.14); border-radius: 2px; overflow: hidden; }
.rf-wrap .react-flow__controls-button { background: #0e1512; border-bottom: 1px solid rgba(214,234,223,0.09); color: #8d9a92; width: 26px; height: 26px; }
.rf-wrap .react-flow__controls-button:hover { background: #121a16; }
.rf-wrap .react-flow__controls-button svg { fill: #8d9a92; max-width: 11px; max-height: 11px; }
.rf-wrap .react-flow__attribution { background: transparent; color: #38443e; font-size: 9px; }
.rf-wrap .react-flow__attribution a { color: #38443e; }
.rf-wrap .react-flow__node { cursor: pointer; }
.rf-wrap .react-flow__handle { pointer-events: none; }
.rf-wrap .react-flow__edge-path { stroke-linecap: round; }
@media (prefers-reduced-motion: reduce) {
  .rf-wrap .flow-line { animation: none; stroke-dasharray: none; }
}
`

/* ------------------------------------------------------------------ page */

export default function Workflow() {
  const t = useT() as Tr
  const wide = useWide()
  const reduce = useReducedMotion()
  const [sel, setSel] = useState('extract')

  const metaQ = useAsync(loadMeta)
  const sourcesQ = useAsync(loadSources)
  const replayQ = useAsync(loadReplay)
  const meta = metaQ.data
  const sources = sourcesQ.data as SourceRow[] | null
  const replay = replayQ.data as Replay | null
  const error = metaQ.error ?? sourcesQ.error ?? replayQ.error

  const kinds = useMemo(() => {
    const k = { pdf: 0, table: 0, docx: 0, html: 0, other: 0 }
    for (const s of sources ?? []) {
      const p = s.path.toLowerCase()
      if (s.kind === 'pdf') k.pdf++
      else if (s.kind === 'table') k.table++
      else if (p.endsWith('.docx')) k.docx++
      else if (p.endsWith('.html')) k.html++
      else k.other++
    }
    return k
  }, [sources])

  const select = useCallback((key: string) => {
    setSel(key)
    window.setTimeout(() => {
      document.getElementById('stage-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 60)
  }, [])

  const stage = STAGES.find((s) => s.key === sel) ?? STAGES[0]
  const replayStage = replay?.stages.find((s) => s.stage === sel)
  const timing = meta?.stages[sel]

  const nodes: Node[] = useMemo(() => {
    if (!meta || !sources) return []
    const ioRows = [
      `${num(kinds.pdf)} PDF`,
      `${num(kinds.table)} ${t(C.workbooks)}`,
      `${num(kinds.docx)} DOCX`,
      `${num(kinds.html)} HTML`,
    ]
    const list: Node[] = []
    if (!wide) {
      const W = 300
      list.push({
        id: 'in',
        type: 'materials',
        position: { x: 0, y: 0 },
        style: { width: W },
        data: { title: t(C.inputLabel), total: num(meta.counts.sources), rows: ioRows, outPos: Position.Bottom } as unknown as Record<string, unknown>,
      })
      STAGES.forEach((s, i) => {
        list.push({
          id: s.key,
          type: 'stage',
          position: { x: 0, y: 200 + i * 168 },
          style: { width: W },
          data: {
            idx: `0${i + 1}`,
            zh: s.zh,
            en: s.en,
            accent: s.accent,
            meta: stageMeta(meta, s.key, t),
            short: s.short,
            active: sel === s.key,
            inPos: Position.Top,
            outPos: Position.Bottom,
          } as unknown as Record<string, unknown>,
        })
      })
      list.push({
        id: 'out',
        type: 'output',
        position: { x: 0, y: 200 + STAGES.length * 168 + 16 },
        style: { width: W },
        data: { title: t(C.outputLabel), rows: outputRows(meta), inPos: Position.Top } as unknown as Record<string, unknown>,
      })
    } else {
      // serpentine: three cards per row, 01→03 left to right, 04→06 right to left
      const W = 212
      const X = [0, 268, 536, 804]
      const Y = [0, 236]
      const cfg: { x: number; y: number; inPos: Position | null; outPos: Position | null }[] = [
        { x: X[1], y: Y[0], inPos: Position.Left, outPos: Position.Right },
        { x: X[2], y: Y[0], inPos: Position.Left, outPos: Position.Right },
        { x: X[3], y: Y[0], inPos: Position.Left, outPos: Position.Bottom },
        { x: X[3], y: Y[1], inPos: Position.Top, outPos: Position.Left },
        { x: X[2], y: Y[1], inPos: Position.Right, outPos: Position.Left },
        { x: X[1], y: Y[1], inPos: Position.Right, outPos: Position.Left },
      ]
      list.push({
        id: 'in',
        type: 'materials',
        position: { x: X[0], y: Y[0] },
        style: { width: W },
        data: { title: t(C.inputLabel), total: num(meta.counts.sources), rows: ioRows, outPos: Position.Right } as unknown as Record<string, unknown>,
      })
      STAGES.forEach((s, i) => {
        list.push({
          id: s.key,
          type: 'stage',
          position: { x: cfg[i].x, y: cfg[i].y },
          style: { width: W },
          data: {
            idx: `0${i + 1}`,
            zh: s.zh,
            en: s.en,
            accent: s.accent,
            meta: stageMeta(meta, s.key, t),
            short: s.short,
            active: sel === s.key,
            inPos: cfg[i].inPos,
            outPos: cfg[i].outPos,
          } as unknown as Record<string, unknown>,
        })
      })
      list.push({
        id: 'out',
        type: 'output',
        position: { x: X[0], y: Y[1] },
        style: { width: W },
        data: { title: t(C.outputLabel), rows: outputRows(meta), inPos: Position.Right } as unknown as Record<string, unknown>,
      })
    }
    return list
  }, [meta, sources, kinds, wide, sel, t])

  const edges: Edge[] = useMemo(() => {
    const ids = ['in', ...STAGES.map((s) => s.key), 'out']
    const mint = 'rgba(79,227,164,0.55)'
    return ids.slice(1).map((id, i) => ({
      id: `${ids[i]}-${id}`,
      source: ids[i],
      target: id,
      type: 'smoothstep',
      pathOptions: { borderRadius: 12 },
      className: reduce ? undefined : 'flow-line',
      style: { stroke: mint, strokeWidth: 1.15 },
      markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: mint },
    }))
  }, [reduce])

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const d = node.data as { kind?: string; key?: string }
      const key = STAGES.some((s) => s.key === node.id) ? node.id : d.key
      if (key && STAGES.some((s) => s.key === key)) select(key)
    },
    [select],
  )

  if (error) {
    return (
      <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16">
        <ErrorBox msg={error} />
      </div>
    )
  }

  if (!meta || !sources || !replay) {
    return (
      <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16">
        <Skeleton />
      </div>
    )
  }

  const counts = meta.counts
  const events = buildEvents(replay, sel)
  const stageIndex = STAGES.indexOf(stage) + 1

  return (
    <div className="bg-void">
      <style>{rfStyles}</style>

      {/* hero */}
      <section className="relative overflow-hidden border-b border-line bg-radial">
        <div className="relative mx-auto max-w-[1240px] px-5 md:px-8 pt-14 pb-12 md:pt-20 md:pb-14">
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, ease: [0.2, 0.7, 0.2, 1] }}
          >
            <div className="mono text-[11px] tracking-[0.24em] text-mint/80 uppercase">{t(C.kicker)}</div>
            <h1 className="display text-[2rem] leading-[1.1] sm:text-[2.5rem] md:text-[3rem] text-ink mt-5 max-w-[22em]">
              {t(C.title)}
            </h1>
            <p className="mt-6 text-[15px] leading-relaxed text-mute max-w-2xl">{t(C.intro)}</p>
          </motion.div>

          <div className="mt-10 grid grid-cols-2 gap-x-6 gap-y-7 sm:grid-cols-3 lg:grid-cols-6">
            <Stat n={<span className="tabular">{num(counts.sources)}</span>} label={t(C.statFiles)} accent />
            <Stat n={<span className="tabular">{num(counts.evidence)}</span>} label={t(C.statEvidence)} />
            <Stat n={<span className="tabular">{num(counts.objects)}</span>} label={t(C.statObjects)} />
            <Stat n={<span className="tabular">{num(counts.relations)}</span>} label={t(C.statRelations)} />
            <Stat n={<span className="tabular">{num(counts.artifacts)}</span>} label={t(C.statArtifacts)} />
            <Stat n={<span className="tabular">{num(meta.cost_total.model_calls)}</span>} label={t(C.statCalls)} />
          </div>
        </div>
      </section>

      {/* diagram */}
      <section className="mx-auto max-w-[1240px] px-5 md:px-8 pt-14 md:pt-20">
        <SectionHead kicker={t(C.graphKicker)} title={t(C.graphTitle)} intro={t(C.graphHint)} />
        <div className="mt-8">
          <Panel hover={false} className="overflow-hidden">
            <div className="flex flex-wrap items-center gap-2.5 px-4 py-3 border-b border-line">
              <Tag color="sky">input</Tag>
              <Tag color="mint">{t(C.stageCount)}</Tag>
              <Tag color="mint">output</Tag>
              <span className="ml-auto mono text-[10px] text-faint tabular">
                {t(C.bundle)} {meta.bundle_version} · {meta.built_at.slice(0, 10)}
              </span>
            </div>
            <div className="rf-wrap h-[600px] md:h-[540px]">
              <ReactFlow
                key={wide ? 'h' : 'v'}
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                fitView={wide}
                fitViewOptions={{ padding: 0.08, maxZoom: 1 }}
                defaultViewport={wide ? undefined : { x: 24, y: 20, zoom: 0.9 }}
                minZoom={0.3}
                maxZoom={1.4}
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable
                zoomOnScroll={false}
                zoomOnDoubleClick={false}
                panOnScroll={false}
                preventScrolling={false}
                onNodeClick={onNodeClick}
                colorMode="dark"
                className="h-full w-full"
              >
                <Background variant={BackgroundVariant.Dots} gap={26} size={1} color="rgba(214,234,223,0.10)" />
                <Controls showInteractive={false} position="bottom-right" />
              </ReactFlow>
            </div>
          </Panel>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="mono text-[10px] tracking-[0.2em] uppercase text-faint mr-1">{t(C.chipHint)}</span>
            {STAGES.map((s, i) => (
              <button
                key={s.key}
                type="button"
                onClick={() => select(s.key)}
                aria-pressed={sel === s.key}
                className={`mono text-[11px] px-3 py-1.5 rounded-sm border transition-colors tabular ${
                  sel === s.key ? 'border-mint/50 text-ink bg-mint/[0.06]' : 'border-line text-mute hover:text-ink hover:border-line-2'
                }`}
              >
                <span style={{ color: s.accent }}>0{i + 1}</span> {t({ zh: s.zh, en: s.en })}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* detail */}
      <section id="stage-detail" className="mx-auto max-w-[1240px] px-5 md:px-8 pt-10 md:pt-14 scroll-mt-24">
        <motion.div
          key={sel}
          initial={reduce ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: [0.2, 0.7, 0.2, 1] }}
        >
          <Panel hover={false} className="p-6 md:p-8">
            <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
              <div className="min-w-0">
                <div className="mono text-[10px] tracking-[0.22em] text-faint uppercase">
                  {t(C.detail)} · <span style={{ color: stage.accent }}>0{stageIndex}</span>
                </div>
                <h3 className="display text-2xl md:text-[2rem] text-ink mt-2">{t({ zh: stage.zh, en: stage.en })}</h3>
              </div>
              <div className="flex flex-wrap items-center gap-2 md:ml-auto">
                <Tag color="mint">
                  <span className="mono tabular">{timing?.seconds != null ? `${timing.seconds.toFixed(2)} s` : '–'}</span>
                </Tag>
                <Tag color="mute">
                  <span className="mono tabular">{num(timing?.model_calls)}</span> {t(C.calls)}
                </Tag>
                {replayStage && replayStage.warnings > 0 && (
                  <Tag color="amber">
                    <span className="mono tabular">{replayStage.warnings}</span> {t(C.warns)}
                  </Tag>
                )}
              </div>
            </div>

            <div className="grid gap-8 md:grid-cols-[1.05fr_1fr] mt-7">
              <div className="min-w-0">
                <div className="mono text-[10px] tracking-[0.2em] uppercase text-faint">{t(C.what)}</div>
                <p className="text-[14.5px] leading-relaxed text-ink/85 mt-3">{t(stage.what)}</p>

                <div className="mono text-[10px] tracking-[0.2em] uppercase text-faint mt-7">{t(C.events)}</div>
                <div className="mt-3 space-y-2">
                  {events.map((e, i) => (
                    <div key={`${e.t}-${i}`} className="panel rounded-sm px-3 py-2 min-w-0">
                      <div className="mono text-[10.5px] text-mute truncate" title={e.msg}>
                        <span className="text-faint tabular mr-2">{e.t.slice(11, 19)}</span>
                        {e.msg}
                      </div>
                    </div>
                  ))}
                  {events.length === 0 && <div className="text-[12px] text-faint">–</div>}
                </div>
                {replayStage && (
                  <div className="mono text-[10px] text-faint mt-3 truncate" title={replayStage.summary}>
                    {t(C.replayLine)} · {replayStage.summary}
                  </div>
                )}
              </div>

              <div className="min-w-0">
                <div className="mono text-[10px] tracking-[0.2em] uppercase text-faint">{t(C.numbers)}</div>
                <div className="mt-3 grid grid-cols-2 gap-px bg-line border border-line rounded-sm overflow-hidden">
                  {facts(sel, meta, replay).map((f, i) => (
                    <div key={`${f.zh}-${i}`} className="bg-panel px-4 py-4 min-w-0">
                      <div className={`display tabular text-[1.5rem] leading-none ${i === 0 ? 'text-mint' : 'text-ink'}`}>{f.v}</div>
                      <div className="text-[11px] text-mute leading-snug mt-2">{t({ zh: f.zh, en: f.en })}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="hairline mt-7 pt-4 flex flex-wrap items-center gap-x-4 gap-y-1">
              <span className="mono text-[10px] text-faint">
                {t(C.built)} {meta.built_at.replace('T', ' ').replace('Z', ' UTC')}
              </span>
              <span className="mono text-[10px] text-faint">bundle v{meta.bundle_version}</span>
              <span className="mono text-[10px] text-faint">
                {meta.model}
                {meta.extract_model ? ` / ${meta.extract_model}` : ''}
              </span>
              <span className="mono text-[10px] text-faint ml-auto tabular">
                {num(meta.cost_total.model_calls)} calls · ${meta.cost_total.cost_usd_estimate.toFixed(2)}
              </span>
            </div>
          </Panel>
        </motion.div>
      </section>

      {/* guarantees */}
      <section className="mx-auto max-w-[1240px] px-5 md:px-8 py-16 md:py-24">
        <SectionHead kicker={t(C.guaranteedKicker)} title={t(C.guaranteedTitle)} intro={t(C.guaranteedIntro)} />
        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {GUARANTEES.map((g, i) => {
            const gs = STAGES.find((s) => s.key === g.stage)
            return (
              <motion.div
                key={g.rule.zh}
                initial={reduce ? false : { opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.1 + i * 0.06, ease: [0.2, 0.7, 0.2, 1] }}
              >
                <button
                  type="button"
                  onClick={() => select(g.stage)}
                  className="panel panel-hover transition-colors rounded-sm p-5 text-left w-full h-full flex flex-col"
                >
                  <span className="mono text-[10px] tracking-[0.22em] text-faint">G{i + 1}</span>
                  <span className="display text-[17px] leading-snug text-ink mt-3">{t(g.rule)}</span>
                  <span className="mt-auto pt-6 flex flex-wrap items-center gap-2">
                    <Tag color={g.accent}>{t(g.evidence)}</Tag>
                  </span>
                  <span className="mono text-[10px] text-faint mt-2">
                    {gs ? t({ zh: gs.zh, en: gs.en }) : ''} →
                  </span>
                </button>
              </motion.div>
            )
          })}
        </div>
      </section>
    </div>
  )
}

/* ------------------------------------------------------------------ data */

function stageMeta(meta: Meta, key: string, t: Tr) {
  const s = meta.stages[key]
  const parts: string[] = []
  if (s?.seconds != null) parts.push(`${Math.round(s.seconds)} s`)
  if (s?.model_calls != null) parts.push(`${num(s.model_calls)} ${t({ zh: C.callUnit.zh, en: C.callUnit.en })}`)
  return parts.join(' · ') || '–'
}

function outputRows(meta: Meta) {
  const k = meta.counts.artifacts_by_kind
  return [
    { path: 'AGENTS.md', note: '' },
    { path: 'knowledge/', note: `${num(k.knowledge_doc ?? 0)}+${num(k.computation_doc ?? 0)}` },
    { path: '.agents/skills/', note: num(k.skill ?? 0) },
    { path: 'tools/', note: num(k.tool ?? 0) },
    { path: 'tests/', note: num(k.test ?? 0) },
    { path: 'sources/', note: '' },
  ]
}

function buildEvents(replay: Replay, key: string): { t: string; msg: string }[] {
  const st = replay.stages.find((s) => s.stage === key)
  const base = st ? pick3(st.items).map((i) => ({ t: i.t, msg: i.msg })) : []
  if (key === 'reconcile' && replay.relate_batches.length > 0) {
    const b = replay.relate_batches
    const extra = [b[Math.max(0, b.length - 3)], b[b.length - 1]].filter(Boolean).map((x) => ({ t: x.t, msg: x.msg }))
    return [...extra, ...base].slice(0, 3)
  }
  return base.slice(0, 3)
}

function facts(key: string, meta: Meta, replay: Replay): { v: string; zh: string; en: string }[] {
  const c = meta.counts
  const rel = c.relations_by_type
  const tools = c.tools_by_status
  const stage = meta.stages[key]
  const rs = replay.stages.find((s) => s.stage === key)
  const f = (v: string, zh: string, en: string) => ({ v, zh, en })

  if (key === 'ingest') {
    return [
      f(num(c.sources), '份研究资料', 'research files'),
      f(num(c.evidence), '个可定位证据单元', 'locatable evidence units'),
      f(stage?.seconds != null ? `${stage.seconds.toFixed(2)} s` : '–', '总耗时（无模型调用）', 'total wall time, no model calls'),
      f(num(stage?.model_calls ?? 0), '次模型调用', 'model calls'),
    ]
  }
  if (key === 'extract') {
    return [
      f(num(c.objects), '个知识对象', 'knowledge objects'),
      f(num(c.gaps), '个记录在案的待补项', 'gaps recorded'),
      f(num(meta.validation.checks.extract?.pass), '条引文校验通过', 'quote checks passed'),
      f(num(meta.validation.checks.extract?.fail), '条引文不足的陈述被拒绝', 'statements rejected for missing quotes'),
    ]
  }
  if (key === 'reconcile') {
    const uRaw = replay.relate_totals.map((x) => x.msg.match(/(\d+) umbrella concepts/)?.[1]).find(Boolean)
    return [
      f(num(c.relations), '条跨资料关系', 'cross-source relations'),
      f(num(rel.conflicts_with ?? 0), '组冲突并排保留', 'conflicts kept side by side'),
      f(uRaw ? num(Number(uRaw)) : '–', '个伞形概念归并分散条目', 'umbrella concepts grouping scattered entries'),
      f(num(c.gaps_resolved), '个待补项在此阶段解决', 'gaps resolved in this stage'),
    ]
  }
  if (key === 'plan') {
    const k = c.artifacts_by_kind
    return [
      f(num(k.knowledge_doc ?? 0), '份知识文档', 'knowledge docs'),
      f(num(k.computation_doc ?? 0), '份计算说明', 'computation docs'),
      f(num(k.tool ?? 0), '个工具', 'tools'),
      f(num(k.skill ?? 0), '个 skill', 'skills'),
    ]
  }
  if (key === 'compile') {
    return [
      f(num(c.artifacts), '个编译产物', 'compiled artifacts'),
      f(num(tools.verified ?? 0), '个工具已验证', 'tools verified'),
      f(num(tools.tested ?? 0), '个工具仅性质测试', 'tools property-tested only'),
      f(num(tools.failed ?? 0), '个工具撤回', 'tools withheld'),
    ]
  }
  const sum = meta.validation.summary
  return [
    f(num(sum.pass ?? 0), '项检查通过', 'checks passed'),
    f(num(sum.fail ?? 0), '项检查失败', 'checks failed'),
    f(num(sum.warn ?? 0), '项警告', 'warnings'),
    f(rs?.seconds != null ? `${rs.seconds.toFixed(2)} s` : stage?.seconds != null ? `${stage.seconds.toFixed(2)} s` : '–', '检查耗时', 'check runtime'),
  ]
}

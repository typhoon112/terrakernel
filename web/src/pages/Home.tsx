import { useMemo } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { Panel, Tag, SectionHead, Stat, Skeleton, ErrorBox } from '../components/ui'
import { Link } from '../lib/router'
import CompileField, { type FieldRow } from '../components/CompileField'
import Architecture from '../components/Architecture'
import { useLang, useT } from '../lib/i18n'
import { loadArtifacts, loadExhibits, loadLibrary, loadMeta, loadSources, useAsync, fmt } from '../lib/data'
import PlantChart from '../components/PlantChart'
import ChainFlow from '../components/ChainFlow'
import CorpusMap from '../components/CorpusMap'
import type { SourceRow } from '../lib/data'

/* ------------------------------------------------------------------ copy */

const C = {
  kicker: { zh: 'AI4Climate Hackathon 2026 · TerraKernel', en: 'AI4Climate Hackathon 2026 · TerraKernel' },
  h1: {
    zh: '把科研资料编译成 Agent 可以直接工作的仓库',
    en: 'Compiling research materials into a repository an agent can work in',
  },
  sub: {
    zh: '177 份资料先被切成 80,077 个可定位证据单元，再抽取成 16,827 个知识对象，最后编译为 34 个产物——知识文档、计算说明、Skills、工具与入口。每一步都能回到原文。',
    en: '177 materials are cut into 80,077 locatable evidence units, extracted into 16,827 knowledge objects, then compiled into 34 artifacts — knowledge docs, computation docs, skills, tools and entry points. Every step traces back to the source text.',
  },
  ctaReplay: { zh: '看一次真实构建', en: 'Watch a real build' },
  ctaLayers: { zh: '看看生成了什么', en: 'See what was built' },
  heroNote: {
    zh: '一次真实构建 · 2026-11-15 完成',
    en: 'One real build · completed 2026-11-15',
  },
  visualCaption: {
    zh: '示意动画：资料类型、知识类型与冲突的比例取自本次构建，右侧为真实生成的文件；粒子与连线的位置不代表真实图结构。',
    en: 'Schematic: the mix of material kinds, knowledge types and conflicts follows this build, and the files on the right are the ones it generated; particle and link positions are not the real graph.',
  },
  fieldAria: {
    zh: '编译流程示意：资料被切成证据，抽取并关联成知识，再编译成仓库里的文档、Skill 和工具',
    en: 'Compile schematic: materials are cut into evidence, extracted and related into knowledge, then compiled into the documents, skills and tools of a repository',
  },
  zMaterials: { zh: '资料', en: 'Materials' },
  zEvidence: { zh: '证据', en: 'Evidence' },
  zKnowledge: { zh: '知识', en: 'Knowledge' },
  zRepo: { zh: '仓库', en: 'Repository' },
  zEvidenceSub: { zh: '段落 · 表格 · 公式 · 图', en: 'paragraphs · tables · formulas · figures' },
  zRelations: { zh: '条关系', en: 'relations' },
  zConflicts: { zh: '处冲突保留', en: 'conflicts kept' },
  sIngest: { zh: '导入', en: 'ingest' },
  sExtract: { zh: '抽取 · 关联', en: 'extract · reconcile' },
  sCompile: { zh: '规划 · 生成 · 检查', en: 'plan · compile · validate' },
  gDoc: { zh: '知识文档', en: 'knowledge docs' },
  gSkill: { zh: 'Skills', en: 'skills' },
  gTool: { zh: '工具', en: 'tools' },
  kPdf: { zh: 'PDF', en: 'PDF' },
  kTable: { zh: '表格', en: 'workbooks' },
  kText: { zh: '文本', en: 'text' },
  carbonKicker: { zh: 'AI for Climate · 碳排放责任核算', en: 'AI for Climate · carbon responsibility accounting' },
  carbonTitle: { zh: '这次构建真正算的是碳：谁排放、谁承担', en: 'What this build actually computes: who emits, and who carries it' },
  carbonLead: {
    zh: '演示案例是一套碳排放责任核算方法：按产品基准值把直接排放分摊到产业链上，发电厂、汽车厂和终端消费者各自承担自己的责任。下面三张图的数据都取自这次构建读过的原文。',
    en: 'The demo case is a carbon responsibility method: direct emissions are allocated along the supply chain at product benchmarks, so plants, car makers and final consumers each carry their share. Every figure below is read from the materials this build processed.',
  },
  archKicker: { zh: '产品架构', en: 'Architecture' },
  archTitle: { zh: '两步编译：先建知识，再建仓库', en: 'Two builders: knowledge first, then the repository' },
  archMore: { zh: '查看六个阶段', en: 'See the six stages' },
  statsKicker: { zh: '一次构建的规模', en: 'The scale of one build' },
  statsTitle: { zh: '数字全部来自构建日志与仓库本身', en: 'Every number comes from the build log and the repository itself' },
  problemKicker: { zh: '问题', en: 'The problem' },
  problemTitle: { zh: '资料很多，能被直接使用的是另一回事', en: 'Plenty of material — but usable material is another matter' },
  p1h: { zh: '约定散落在数百页里', en: 'Conventions scattered across hundreds of pages' },
  p1: {
    zh: '口径、边界、单位和版本分散在 177 份资料的段落、表格与公式中，想用的时候很难一次找齐。',
    en: 'Bases, boundaries, units and versions live across paragraphs, tables and formulas in 177 materials; collecting them when you need them is hard.',
  },
  p2h: { zh: '答案无法回到原文', en: 'Answers that cannot be traced back' },
  p2: {
    zh: '常规摘要给结论，却说不清一句话来自哪一页、哪一节；复核时只能重新翻原文。',
    en: 'A normal summary gives the conclusion but not the page or section it came from; checking it means reopening the source.',
  },
  p3h: { zh: '每个会话都从零重读', en: 'Every session re-reads everything' },
  p3: {
    zh: '没有共享的证据层和知识层，每个 Agent 会话都要把同一批资料再读一遍、再解释一遍。',
    en: 'Without a shared evidence and knowledge layer, every agent session re-reads and re-interprets the same corpus.',
  },
  layersKicker: { zh: '生成结果', en: 'What was built' },
  layersTitle: { zh: '三层：知识、流程与可执行工具', en: 'Three layers: knowledge, procedure, executable tools' },
  layersIntro: {
    zh: '知识层保存有出处的对象，Skill 层把它们写成可执行的步骤，工具层把公式变成带单位和测试的代码。',
    en: 'The knowledge layer keeps sourced objects, the skill layer turns them into procedures, and the tool layer turns formulas into code with units and tests.',
  },
  kLayer: { zh: '知识层', en: 'Knowledge layer' },
  sLayer: { zh: 'Skill 层', en: 'Skill layer' },
  tLayer: { zh: '工具层', en: 'Tool layer' },
  kDesc: {
    zh: '方法对照、产品基准值责任法、发电厂、省际数据与披露标准，每段都带对象 ID 与原文位置。',
    en: 'Method comparison, benchmark responsibility, power plants, provincial data and disclosure standards — each passage with object IDs and source locations.',
  },
  sDesc: {
    zh: '把“读哪些文档、按什么顺序做、何时停下来记缺口”写成 SKILL.md，Agent 可以直接照着执行。',
    en: '“Which docs to read, in what order, and when to stop and record a gap” is written as SKILL.md an agent can execute.',
  },
  tDesc: {
    zh: '输入参数、单位、输出单位与知识文档一一对应；期望值取自原文算例，而不是实现本身。',
    en: 'Inputs, units and outputs map to a knowledge doc; expected values come from worked examples in the source, not from the implementation.',
  },
  example: { zh: '示例', en: 'Example' },
  docs: { zh: '文档', en: 'docs' },
  objects: { zh: '对象', en: 'objects' },
  verified: { zh: '已验证', en: 'verified' },
  tests: { zh: '测试', en: 'tests' },
  cases: { zh: '算例', en: 'cases' },
  blocked: { zh: '1 个标记受阻', en: '1 marked blocked' },
  stageKicker: { zh: '构建过程', en: 'The build' },
  stageTitle: { zh: '六个阶段，一次跑完', en: 'Six stages, one run' },
  stageIntro: {
    zh: '耗时与模型调用次数直接取自构建日志；完整时间线可以逐条回放。',
    en: 'Durations and model calls come straight from the build log; the full timeline can be replayed event by event.',
  },
  calls: { zh: '次调用', en: 'calls' },
  total: { zh: '合计', en: 'Total' },
  totalTime: { zh: '阶段耗时合计约 28 分钟', en: 'stage time ≈ 28 min' },
  modelLine: { zh: '模型调用 977 次 · 估算成本 $45.71', en: '977 model calls · est. $45.71' },
  replayLink: { zh: '打开构建回放', en: 'Open the replay' },
  closeTitle: { zh: '这套方法可以换一个领域再来一次', en: 'The same method can run again on another domain' },
  closeSub: {
    zh: 'TerraKernel 不绑定碳排放核算：换一批资料、换一组研究任务，证据、对象、关系、缺口与产物都由同一套流程重新生成。',
    en: 'TerraKernel is not tied to carbon accounting: swap the materials and the research tasks, and evidence, objects, relations, gaps and artifacts are regenerated by the same pipeline.',
  },
  honesty: { zh: '这是一次真实构建的真实数据；限制见', en: 'These are the real numbers of one real build; limits are in' },
} as const

/* --------------------------------------------------------------- helpers */

const num = (n: number | null | undefined) => (n == null ? '–' : Math.round(n).toLocaleString('en-US'))

const MINT = '#4fe3a4'
const AMBER = '#efb75a'
const SKY = '#74a9f7'
const MUTE = '#5e6a63'

/* ------------------------------------------------------------------ page */

const STAGE_ORDER = ['ingest', 'extract', 'reconcile', 'plan', 'compile', 'validate'] as const
const STAGE_LABEL: Record<string, { zh: string; en: string }> = {
  ingest: { zh: '资料导入', en: 'Ingest' },
  extract: { zh: '知识抽取', en: 'Extract' },
  reconcile: { zh: '跨资料关联', en: 'Reconcile' },
  plan: { zh: '仓库规划', en: 'Plan' },
  compile: { zh: '生成产物', en: 'Compile' },
  validate: { zh: '检查', en: 'Validate' },
}
const VIOLET = '#b39dfa'
const STAGE_TINT: Record<string, string> = { ingest: MUTE, extract: MINT, reconcile: VIOLET, plan: SKY, compile: AMBER, validate: MINT }

const fadeUp = (reduce: boolean, delay = 0) =>
  reduce
    ? {}
    : {
        initial: { opacity: 0, y: 16 },
        whileInView: { opacity: 1, y: 0 },
        viewport: { once: true, margin: '-60px' },
        transition: { duration: 0.6, ease: [0.2, 0.7, 0.2, 1] as const, delay },
      }

export default function Home() {
  const { lang } = useLang()
  const t = useT()
  const reduce = useReducedMotion() ?? false
  const { data, error } = useAsync(
    () => Promise.all([loadMeta(), loadSources(), loadArtifacts(), loadExhibits(), loadLibrary()]),
    [],
  )

  const kinds = useMemo(() => {
    const src: SourceRow[] = data?.[1] ?? []
    const k = { pdf: 0, table: 0, text: 0, other: 0 }
    for (const s of src) {
      if (s.kind === 'pdf') k.pdf++
      else if (s.kind === 'table') k.table++
      else if (s.kind === 'text') k.text++
      else k.other++
    }
    return k
  }, [data])

  if (error) return <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16"><ErrorBox msg={error} /></div>
  if (!data) return <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16"><Skeleton /></div>

  const [meta, , bundle] = data
  const c = meta.counts
  const arts = bundle.artifacts
  const byId = (id: string) => arts.find((a) => a.id === id)
  const skill = byId('skill:choose-accounting-boundary')
  const tool = byId('tool:plant_carbon_responsibility')
  const doc = byId('doc:methods/benchmark-responsibility-method.md')
  const toolInfo = tool?.tool

  const stageTotal = STAGE_ORDER.reduce((s, k) => s + (meta.stages[k]?.seconds ?? 0), 0)

  const exhibits = data[3]
  const library = data[4]
  const plantTable = exhibits['ev:source:item/item/item/t12']
  const plantFactors = exhibits['ev:source:item/item/item/t10']
  const oreBasis = exhibits['ev:source:item/item/p23']
  const oreTotals = exhibits['ev:source:item/item/p26']

  const fieldRows: FieldRow[] = arts.flatMap((a): FieldRow[] => {
    const path = a.path ?? ''
    if (a.kind === 'knowledge_doc') return [{ group: 'doc', label: path.split('/').pop() ?? a.id }]
    if (a.kind === 'skill') return [{ group: 'skill', label: path.split('/').slice(-2, -1)[0] ?? a.id, status: a.status }]
    if (a.kind === 'tool') return [{ group: 'tool', label: a.tool?.name ?? a.id, status: a.tool?.status ?? a.status }]
    return []
  })
  const kindLine = [
    kinds.pdf ? `${kinds.pdf} ${t(C.kPdf)}` : '',
    kinds.table ? `${kinds.table} ${t(C.kTable)}` : '',
    kinds.text ? `${kinds.text} ${t(C.kText)}` : '',
  ].filter(Boolean).join(' · ')

  return (
    <>
      {/* ------------------------------------------------------------ hero */}
      <section className="relative overflow-hidden bg-radial border-b border-line">
        <div className="absolute inset-0 bg-grid opacity-60 [mask-image:radial-gradient(ellipse_at_50%_30%,black_30%,transparent_80%)]" aria-hidden />
        <div className="relative min-h-[calc(100vh-4rem)] flex flex-col">
          <div className="mx-auto w-full max-w-[1240px] px-5 md:px-8 pt-12 md:pt-[7vh] [@media(max-height:800px)]:md:pt-8">
            <motion.div
              initial={reduce ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, ease: [0.2, 0.7, 0.2, 1] }}
              className="mono text-[11px] tracking-[0.24em] text-mint/85 uppercase"
            >
              {t(C.kicker)}
            </motion.div>
            <motion.h1
              initial={reduce ? false : { opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: [0.2, 0.7, 0.2, 1], delay: 0.08 }}
              className="display text-[2.3rem] leading-[1.08] sm:text-[3rem] xl:text-[3.7rem] [@media(max-height:800px)]:xl:text-[2.9rem] text-ink mt-5 max-w-[18em] text-glow"
            >
              {t(C.h1)}
            </motion.h1>
            <div className="mt-6 grid lg:grid-cols-[minmax(0,1fr)_auto] gap-x-12 gap-y-6 items-end">
              <motion.p
                initial={reduce ? false : { opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, ease: [0.2, 0.7, 0.2, 1], delay: 0.18 }}
                className="text-[15px] leading-relaxed text-mute max-w-[640px]"
              >
                {t(C.sub)}
              </motion.p>
              <motion.div
                initial={reduce ? false : { opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, ease: [0.2, 0.7, 0.2, 1], delay: 0.28 }}
                className="flex flex-wrap items-center gap-3"
              >
                <Link
                  to="/replay"
                  className="inline-flex items-center gap-2 bg-mint text-void text-[14px] font-medium px-5 py-2.5 rounded-sm hover:bg-[#69ecb4] transition-colors"
                >
                  {t(C.ctaReplay)}
                  <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M2 7h9M7.5 3.5 11 7l-3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>
                </Link>
                <Link
                  to="/layers"
                  className="inline-flex items-center gap-2 border border-line-2 text-ink text-[14px] px-5 py-2.5 rounded-sm hover:border-mint/40 hover:text-mint transition-colors"
                >
                  {t(C.ctaLayers)}
                </Link>
              </motion.div>
            </div>
          </div>
          <motion.div
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1.1, ease: [0.2, 0.7, 0.2, 1], delay: 0.35 }}
            className="mt-auto pt-10 md:pt-12 [@media(max-height:800px)]:md:pt-7"
          >
            <CompileField
              kinds={kinds}
              objectsByType={c.objects_by_type}
              conflictShare={c.relations ? (c.relations_by_type.conflicts_with ?? 0) / c.relations : 0}
              rows={fieldRows}
              zones={[
                { step: '01', title: t(C.zMaterials), value: num(c.sources), sub: kindLine },
                { step: '02', title: t(C.zEvidence), value: num(c.evidence), sub: t(C.zEvidenceSub) },
                {
                  step: '03',
                  title: t(C.zKnowledge),
                  value: num(c.objects),
                  sub: `${num(c.relations)} ${t(C.zRelations)} · ${num(c.relations_by_type.conflicts_with ?? 0)} ${t(C.zConflicts)}`,
                },
                {
                  step: '04',
                  title: t(C.zRepo),
                  value: num(c.artifacts),
                  sub: `${fieldRows.filter((r) => r.group === 'doc').length} ${t(C.gDoc)} · ${fieldRows.filter((r) => r.group === 'skill').length} ${t(C.gSkill)} · ${fieldRows.filter((r) => r.group === 'tool').length} ${t(C.gTool)}`,
                },
              ]}
              stages={[t(C.sIngest), t(C.sExtract), t(C.sCompile)]}
              groupTitles={{ doc: t(C.gDoc), skill: t(C.gSkill), tool: t(C.gTool) }}
              reduce={reduce}
              ariaLabel={t(C.fieldAria)}
            />
          </motion.div>
          <div className="mx-auto w-full max-w-[1240px] px-5 md:px-8 py-4 flex flex-wrap gap-x-8 gap-y-1 mono text-[10px] text-faint leading-relaxed">
            <span>{t(C.heroNote)} · {meta.model}</span>
            <span className="max-w-[760px]">{t(C.visualCaption)}</span>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------ carbon (the demo) */}
      <section className="relative border-t border-line bg-deep/40 overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-30 [mask-image:radial-gradient(ellipse_at_50%_0%,black_20%,transparent_75%)]" aria-hidden />
        <div className="relative mx-auto max-w-[1240px] px-5 md:px-8 py-16 md:py-24 space-y-20 md:space-y-28">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="mono text-[11px] tracking-[0.22em] text-mint/80 uppercase">{t(C.carbonKicker)}</div>
              <h2 className="display text-3xl md:text-[2.5rem] leading-[1.08] mt-3 max-w-[22em]">{t(C.carbonTitle)}</h2>
              <p className="mt-4 text-[14.5px] text-mute max-w-[680px] leading-relaxed">{t(C.carbonLead)}</p>
            </div>
          </div>
          {plantTable && <PlantChart table={plantTable} factors={plantFactors} />}
          {oreBasis && oreTotals && <ChainFlow basis={oreBasis} totals={oreTotals} />}
          {library.length > 0 && <CorpusMap sources={library} />}
        </div>
      </section>

      {/* ---------------------------------------------------- architecture */}
      <section className="mx-auto max-w-[1240px] px-5 md:px-8 py-16 md:py-20">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
          <div>
            <div className="mono text-[11px] tracking-[0.22em] text-mint/80 uppercase">{t(C.archKicker)}</div>
            <h2 className="display text-3xl md:text-[2.4rem] leading-[1.1] mt-3">{t(C.archTitle)}</h2>
          </div>
          <Link to="/workflow" className="mono text-[11.5px] text-mint hover:text-[#69ecb4]">{t(C.archMore)} →</Link>
        </div>
        <Architecture meta={meta} kinds={kinds} artifacts={arts} />
      </section>

      {/* ----------------------------------------------------------- stats */}
      <section className="mx-auto max-w-[1240px] px-5 md:px-8 py-16 md:py-20">
        <motion.div {...fadeUp(reduce)} className="flex items-end justify-between gap-6 flex-wrap">
          <div>
            <div className="mono text-[11px] tracking-[0.22em] text-mint/80 uppercase">{t(C.statsKicker)}</div>
            <h2 className="display text-2xl md:text-[1.9rem] text-ink mt-3">{t(C.statsTitle)}</h2>
          </div>
          <div className="mono text-[11px] text-faint">{new Date(meta.built_at).toISOString().slice(0, 16).replace('T', ' ')} UTC</div>
        </motion.div>
        <motion.div {...fadeUp(reduce, 0.08)} className="mt-10 hairline pt-8 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-6 gap-y-8">
          <Stat
            n={fmt(c.sources)}
            accent
            label={
              <>
                <span className="text-ink/85">{t({ zh: '资料', en: 'Materials' })}</span>
                <span className="block mt-1">{`${num(kinds.pdf)} PDF · ${num(kinds.table)} 表格 · ${num(kinds.text)} 文本`}</span>
              </>
            }
          />
          <Stat
            n={fmt(c.evidence)}
            label={
              <>
                <span className="text-ink/85">{t({ zh: '证据单元', en: 'Evidence units' })}</span>
                <span className="block mt-1">{t({ zh: '每段都带出处与位置', en: 'each with provenance and location' })}</span>
              </>
            }
          />
          <Stat
            n={fmt(c.objects)}
            label={
              <>
                <span className="text-ink/85">{t({ zh: '知识对象', en: 'Knowledge objects' })}</span>
                <span className="block mt-1">{t({ zh: '概念 · 约束 · 论断 · 方法 …', en: 'concept · constraint · claim · method …' })}</span>
              </>
            }
          />
          <Stat
            n={fmt(c.relations)}
            label={
              <>
                <span className="text-ink/85">{t({ zh: '关系', en: 'Relations' })}</span>
                <span className="block mt-1">{t({ zh: '9 种类型，含冲突与别名', en: '9 types, incl. conflicts and aliases' })}</span>
              </>
            }
          />
          <Stat
            n={fmt(c.artifacts)}
            label={
              <>
                <span className="text-ink/85">{t({ zh: '产物', en: 'Artifacts' })}</span>
                <span className="block mt-1">{`${num(c.artifacts_by_kind.knowledge_doc)} 知识文档 · ${num(c.artifacts_by_kind.computation_doc)} 计算说明 · ${num(c.artifacts_by_kind.skill)} Skills`}</span>
              </>
            }
          />
          <Stat
            n={fmt(c.tools)}
            label={
              <>
                <span className="text-ink/85">{t({ zh: '工具', en: 'Tools' })}</span>
                <span className="block mt-1">{`${num(c.tools_by_status.verified)} 已验证 · ${num(c.tools_by_status.tested)} 仅性质测试 · ${num(c.tools_by_status.failed)} 未开放`}</span>
              </>
            }
          />
        </motion.div>
        <motion.p {...fadeUp(reduce, 0.12)} className="mt-6 text-[12px] text-faint">
          {t({
            zh: `另有 ${num(c.gaps)} 个待确认问题被登记，其中 ${num(c.gaps_resolved)} 个已在关联阶段解决、${num(c.gaps_open)} 个仍开放。`,
            en: `${num(c.gaps)} open questions were registered; ${num(c.gaps_resolved)} were resolved during reconcile, ${num(c.gaps_open)} remain open.`,
          })}
        </motion.p>
      </section>

      {/* --------------------------------------------------------- problem */}
      <section className="border-t border-line bg-deep/40">
        <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16 md:py-20">
          <motion.div {...fadeUp(reduce)}>
            <SectionHead kicker={t(C.problemKicker)} title={t(C.problemTitle)} />
          </motion.div>
          <div className="mt-12 grid md:grid-cols-3 gap-px bg-line">
            {[
              { h: C.p1h, p: C.p1 },
              { h: C.p2h, p: C.p2 },
              { h: C.p3h, p: C.p3 },
            ].map((item, i) => (
              <motion.div key={i} {...fadeUp(reduce, 0.06 * (i + 1))} className="bg-void/95 p-7 md:p-8">
                <div className="mono text-[12px] text-mint/80 tabular">0{i + 1}</div>
                <h3 className="display text-[1.35rem] leading-snug text-ink mt-4">{t(item.h)}</h3>
                <p className="mt-3 text-[13.5px] leading-relaxed text-mute">{t(item.p)}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- layers */}
      <section className="mx-auto max-w-[1240px] px-5 md:px-8 py-16 md:py-20">
        <motion.div {...fadeUp(reduce)}>
          <SectionHead kicker={t(C.layersKicker)} title={t(C.layersTitle)} intro={t(C.layersIntro)} />
        </motion.div>
        <div className="mt-12 grid md:grid-cols-3 gap-5">
          <motion.div {...fadeUp(reduce, 0.04)}>
            <Panel className="p-7 h-full flex flex-col clip-corner">
              <div className="flex items-center justify-between">
                <Tag color="mint">{t(C.kLayer)}</Tag>
                <span className="mono text-[11px] text-faint tabular">{`${num(c.artifacts_by_kind.knowledge_doc)} ${t(C.docs)}`}</span>
              </div>
              <p className="mt-5 text-[13.5px] leading-relaxed text-mute flex-1">{t(C.kDesc)}</p>
              <div className="mt-6 hairline pt-4">
                <div className="mono text-[10px] uppercase tracking-[0.18em] text-faint">{t(C.example)}</div>
                <div className="mono text-[12px] text-ink/90 mt-2 break-all">{doc?.path ?? 'knowledge/methods/benchmark-responsibility-method.md'}</div>
                <div className="mono text-[11px] text-mute mt-1">
                  {doc ? `${num(doc.objects.length)} ${t(C.objects)}` : ''} · {t({ zh: '全部带出处', en: 'all sourced' })}
                </div>
              </div>
            </Panel>
          </motion.div>
          <motion.div {...fadeUp(reduce, 0.1)}>
            <Panel className="p-7 h-full flex flex-col clip-corner">
              <div className="flex items-center justify-between">
                <Tag color="amber">{t(C.sLayer)}</Tag>
                <span className="mono text-[11px] text-faint tabular">{`${num(c.artifacts_by_kind.skill)} skills`}</span>
              </div>
              <p className="mt-5 text-[13.5px] leading-relaxed text-mute flex-1">{t(C.sDesc)}</p>
              <div className="mt-6 hairline pt-4">
                <div className="mono text-[10px] uppercase tracking-[0.18em] text-faint">{t(C.example)}</div>
                <div className="mono text-[12px] text-ink/90 mt-2 break-all">{skill?.path ?? '.agents/skills/choose-accounting-boundary/SKILL.md'}</div>
                <div className="mono text-[11px] text-mute mt-1">
                  {skill ? `${num(skill.objects.length)} ${t(C.objects)}` : ''} · {t(C.blocked)}
                </div>
              </div>
            </Panel>
          </motion.div>
          <motion.div {...fadeUp(reduce, 0.16)}>
            <Panel className="p-7 h-full flex flex-col clip-corner">
              <div className="flex items-center justify-between">
                <Tag color="sky">{t(C.tLayer)}</Tag>
                <span className="mono text-[11px] text-faint tabular">{`${num(c.tools)} tools`}</span>
              </div>
              <p className="mt-5 text-[13.5px] leading-relaxed text-mute flex-1">{t(C.tDesc)}</p>
              <div className="mt-6 hairline pt-4">
                <div className="mono text-[10px] uppercase tracking-[0.18em] text-faint">{t(C.example)}</div>
                <div className="mono text-[12px] text-ink/90 mt-2 break-all">{tool?.path ?? 'tools/research_tools/tools/plant_carbon_responsibility.py'}</div>
                <div className="mono text-[11px] text-mute mt-1">
                  {toolInfo?.status ?? 'verified'} · {toolInfo ? `${toolInfo.tests?.passed ?? 0} ${t(C.tests)} · ${num(toolInfo.reference_cases)} ${t(C.cases)}` : ''}
                </div>
              </div>
            </Panel>
          </motion.div>
        </div>
        <motion.div {...fadeUp(reduce, 0.2)} className="mt-8">
          <Link to="/layers" className="inline-flex items-center gap-2 text-[13.5px] text-mint hover:text-ink transition-colors">
            {t({ zh: '打开产物清单', en: 'Open the artifact list' })}
            <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden><path d="M2 7h9M7.5 3.5 11 7l-3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>
          </Link>
        </motion.div>
      </section>

      {/* ---------------------------------------------------------- stages */}
      <section className="border-t border-line bg-deep/40">
        <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16 md:py-20">
          <motion.div {...fadeUp(reduce)} className="flex items-end justify-between gap-6 flex-wrap">
            <SectionHead kicker={t(C.stageKicker)} title={t(C.stageTitle)} intro={t(C.stageIntro)} />
            <Link to="/replay" className="text-[13.5px] text-mint hover:text-ink transition-colors inline-flex items-center gap-2 shrink-0">
              {t(C.replayLink)}
              <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden><path d="M2 7h9M7.5 3.5 11 7l-3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>
            </Link>
          </motion.div>
          <div className="mt-12 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-px bg-line">
            {STAGE_ORDER.map((k, i) => {
              const st = meta.stages[k]
              return (
                <motion.div key={k} {...fadeUp(reduce, 0.04 * i)} className="bg-void/95 p-5 flex flex-col min-h-[128px]">
                  <div className="flex items-center gap-2">
                    <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: STAGE_TINT[k] }} />
                    <span className="mono text-[10px] uppercase tracking-[0.16em] text-faint">{`0${i + 1}`}</span>
                  </div>
                  <div className="mt-3 text-[13px] text-ink/90">{lang === 'zh' ? STAGE_LABEL[k].zh : STAGE_LABEL[k].en}</div>
                  <div className="display tabular text-[1.55rem] leading-none mt-2 text-ink">{st?.seconds != null ? `${Math.round(st.seconds)}s` : '–'}</div>
                  <div className="mono text-[10.5px] text-faint mt-auto pt-3">
                    {st?.model_calls ? `${num(st.model_calls)} ${t(C.calls)}` : t({ zh: '无模型调用', en: 'no model calls' })}
                  </div>
                </motion.div>
              )
            })}
          </div>
          <motion.div {...fadeUp(reduce, 0.1)} className="mt-6 flex flex-wrap gap-x-8 gap-y-2 mono text-[11.5px] text-mute">
            <span>{t({ zh: '阶段耗时合计', en: 'Stage time total' })} ≈ {Math.round(stageTotal / 60)} min</span>
            <span>{`${num(meta.cost_total.model_calls)} ${t(C.calls)}`} · ${meta.cost_total.cost_usd_estimate.toFixed(2)} {t({ zh: '估算', en: 'est.' })}</span>
            <span>{`validate: ${num(meta.validation.summary.pass)} pass · ${num(meta.validation.summary.warn)} warn`}</span>
          </motion.div>
        </div>
      </section>

      {/* ---------------------------------------------------------- closing */}
      <section className="relative overflow-hidden bg-radial">
        <div className="relative mx-auto max-w-[1240px] px-5 md:px-8 py-20 md:py-28 text-center">
          <motion.div {...fadeUp(reduce)}>
            <h2 className="display text-[2rem] md:text-[2.8rem] leading-[1.08] text-ink max-w-3xl mx-auto">{t(C.closeTitle)}</h2>
            <p className="mt-6 text-[15px] leading-relaxed text-mute max-w-2xl mx-auto">{t(C.closeSub)}</p>
            <div className="mt-9 flex flex-wrap justify-center gap-3">
              <Link
                to="/replay"
                className="inline-flex items-center gap-2 bg-mint text-void text-[14px] font-medium px-5 py-2.5 rounded-sm hover:bg-[#69ecb4] transition-colors glow-mint"
              >
                {t(C.ctaReplay)}
              </Link>
              <Link
                to="/layers"
                className="inline-flex items-center gap-2 border border-line-2 text-ink text-[14px] px-5 py-2.5 rounded-sm hover:border-mint/40 hover:text-mint transition-colors"
              >
                {t(C.ctaLayers)}
              </Link>
            </div>
          </motion.div>
        </div>
      </section>
    </>
  )
}

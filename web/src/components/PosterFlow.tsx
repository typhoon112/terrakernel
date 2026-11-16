import type { ReactNode } from 'react'
import { useT } from '../lib/i18n'
import type { Artifact, Meta, SourceRow } from '../lib/data'
import { CoalPlant, Document, Factory, Household, Kernel, Pylon, SolarPlant, WindTurbine } from './ClimateIcons'
import { StepsIcon } from './artifactGlyph'

/**
 * The poster: one picture of what this build produced. Materials on the left, the two builders in
 * the middle, the repository on the right, and the carbon case running underneath.
 *
 * Everything is laid out in ONE coordinate system (a 1200×640 SVG viewBox); HTML blocks are placed
 * with <foreignObject>, so connectors and boxes cannot drift apart at any width.
 */

const C = {
  tagline: { zh: '从科研资料到 Agent 可用的仓库', en: 'From research materials to agent-ready repositories' },
  demo: { zh: '演示案例 · 碳排放责任核算', en: 'Demo · carbon responsibility accounting' },
  materials: { zh: '科研资料', en: 'Research materials' },
  mid: { zh: '证据与知识', en: 'Evidence & knowledge' },
  repo: { zh: 'Agent 可用的仓库', en: 'Agent-ready repository' },
  fmt_pdf: { zh: '论文 · 标准 · 报告', en: 'Papers · standards · reports' },
  fmt_sheet: { zh: '数据表', en: 'Data workbooks' },
  fmt_doc: { zh: '专著书稿', en: 'Monograph' },
  fmt_web: { zh: '网页快照', en: 'Web snapshot' },
  fmt_other: { zh: '其他资料', en: 'Other' },
  kb: { zh: '知识构建', en: 'Knowledge Builder' },
  rb: { zh: '仓库构建', en: 'Repository Builder' },
  core: { zh: '碳排放责任核算', en: 'Carbon accounting' },
  objects: { zh: '条知识', en: 'knowledge objects' },
  evidence: { zh: '条证据', en: 'evidence units' },
  method: { zh: '方法', en: 'Method' },
  constraint: { zh: '约束', en: 'Constraint' },
  concept: { zh: '概念', en: 'Concept' },
  conflict: { zh: '冲突并存', en: 'Conflicts kept' },
  open: { zh: '待确认', en: 'Open questions' },
  entry: { zh: 'Agent 入口', en: 'Agent entry' },
  knowledge: { zh: '知识', en: 'Knowledge' },
  knowledgeSub: { zh: '方法与定义', en: 'Methods & definitions' },
  skills: { zh: 'Skills', en: 'Skills' },
  skillsSub: { zh: '研究流程', en: 'Research procedures' },
  tools: { zh: '工具', en: 'Tools' },
  toolsSub: { zh: '可执行计算', en: 'Executable calculations' },
  formula: { zh: '碳排放责任 = 直接排放 + 购入产品责任 − 售出产品责任', en: 'Responsibility = Direct emissions + Input responsibility − Output responsibility' },
  formulaSrc: { zh: '资料中的核算公式 · 由仓库里的工具实现', en: 'The accounting formula in the materials · implemented by the repository’s tools' },
  solar: { zh: '光伏', en: 'Solar PV' },
  wind: { zh: '风电', en: 'Wind' },
  plant: { zh: '火电厂', en: 'Power plant' },
  grid: { zh: '电网', en: 'Grid' },
  industry: { zh: '工业', en: 'Industry' },
  demand: { zh: '终端消费', en: 'Final demand' },
  flowPower: { zh: '电力与产品流', en: 'Power / product flow' },
  flowResp: { zh: '责任分配', en: 'Responsibility allocation' },
  verified: { zh: '已用原文算例验证', en: 'verified on worked examples' },
}

const MINT = '#4fe3a4'
const AMBER = '#efb75a'
const SKY = '#74a9f7'
const VIOLET = '#b39dfa'
const INK = '#e9efe9'
const MUTE = '#8d9a92'

const n = (v: number) => v.toLocaleString('en-US')

/** HTML placed in SVG user units. */
function Box({ x, y, w, h, children }: { x: number; y: number; w: number; h: number; children: ReactNode }) {
  return (
    <foreignObject x={x} y={y} width={w} height={h}>
      <div style={{ width: w, height: h }}>{children}</div>
    </foreignObject>
  )
}

function MaterialCard({ x, y, color, title, tag, count, lines }: { x: number; y: number; color: string; title: string; tag: string; count: number; lines: number[] }) {
  return (
    <g>
      <rect x={x + 5} y={y + 5} width={176} height={58} rx={5} fill="#0b110e" stroke="rgba(214,234,223,0.07)" />
      <rect x={x} y={y} width={176} height={58} rx={5} fill="#101915" stroke="rgba(214,234,223,0.16)" />
      <rect x={x} y={y} width={3} height={58} rx={1.5} fill={color} />
      <text x={x + 14} y={y + 20} fill={INK} fontSize="11.5" fontFamily="var(--font-sans)">{title}</text>
      <text x={x + 164} y={y + 20} fill={color} fontSize="12" textAnchor="end" fontFamily="var(--font-mono)">{count}</text>
      <text x={x + 164} y={y + 49} fill={color} fillOpacity="0.7" fontSize="8.5" textAnchor="end" fontFamily="var(--font-mono)">{tag}</text>
      {lines.map((w, i) => (
        <rect key={i} x={x + 14} y={y + 30 + i * 7} width={w} height={2.4} rx={1.2} fill={i === 1 ? AMBER : 'rgba(233,239,233,0.2)'} opacity={i === 1 ? 0.85 : 1} />
      ))}
    </g>
  )
}

function Satellite({ x, y, label, value, color }: { x: number; y: number; label: string; value: string; color: string }) {
  return (
    <g>
      <rect x={x - 46} y={y - 17} width={92} height={34} rx={5} fill="#0c1310" stroke={color} strokeOpacity={0.55} />
      <text x={x} y={y - 3} fill={color} fontSize="10" textAnchor="middle" fontFamily="var(--font-sans)">{label}</text>
      <text x={x} y={y + 10} fill={INK} fontSize="10.5" textAnchor="middle" fontFamily="var(--font-mono)">{value}</text>
    </g>
  )
}

const FORMATS: { key: 'pdf' | 'sheet' | 'doc' | 'web' | 'other'; ext: RegExp; tag: string; color: string }[] = [
  { key: 'pdf', ext: /\.pdf$/i, tag: 'PDF', color: MINT },
  { key: 'sheet', ext: /\.(xlsx?|xlsm|csv|tsv|parquet|nc)$/i, tag: 'XLS', color: AMBER },
  { key: 'doc', ext: /\.(docx?|md|txt)$/i, tag: 'DOCX', color: VIOLET },
  { key: 'web', ext: /\.html?$/i, tag: 'HTML', color: SKY },
]

export default function PosterFlow({ meta, artifacts, sources }: { meta: Meta; artifacts: Artifact[]; sources: SourceRow[] }) {
  const t = useT()
  const c = meta.counts
  const formats = FORMATS.map((f) => ({ ...f, n: sources.filter((x) => f.ext.test(x.path)).length })).filter((f) => f.n > 0).slice(0, 4)
  const docs = (c.artifacts_by_kind.knowledge_doc ?? 0) + (c.artifacts_by_kind.computation_doc ?? 0)
  const skills = c.artifacts_by_kind.skill ?? 0
  const tools = artifacts.filter((a) => a.kind === 'tool')
  const verified = tools.filter((a) => a.tool?.status === 'verified').length
  const chain = [
    { x: 392, icon: <SolarPlant size={40} />, label: t(C.solar), color: MINT },
    { x: 510, icon: <WindTurbine size={40} />, label: t(C.wind), color: MINT },
    { x: 628, icon: <CoalPlant size={40} />, label: t(C.plant), color: AMBER },
    { x: 776, icon: <Pylon size={40} />, label: t(C.grid), color: SKY },
    { x: 924, icon: <Factory size={40} />, label: t(C.industry), color: VIOLET },
    { x: 1072, icon: <Household size={40} />, label: t(C.demand), color: AMBER },
  ]

  return (
    <div className="relative">
      <div className="absolute inset-0 bg-grid opacity-25" aria-hidden />
      <div className="absolute inset-0 bg-[radial-gradient(900px_460px_at_55%_-10%,rgba(34,181,124,0.16),transparent_65%)]" aria-hidden />

      {/* ------------------------------------------------ desktop poster */}
      <div className="relative mx-auto hidden lg:block max-w-[1320px] px-4">
        <svg viewBox="0 0 1200 640" className="block w-full h-auto" role="img" aria-label={t(C.tagline)}>
          <defs>
            <marker id="pm" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0 0 L10 5 L0 10 z" fill={MINT} />
            </marker>
            <marker id="pa" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0 0 L10 5 L0 10 z" fill={AMBER} />
            </marker>
            <linearGradient id="pg" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#14271e" />
              <stop offset="1" stopColor="#0a120e" />
            </linearGradient>
          </defs>

          {/* ---- title block */}
          <Box x={36} y={44} w={300} h={300}>
            <div className="mono text-[11px] tracking-[0.3em] uppercase" style={{ color: MINT }}>AI for Climate</div>
            <div className="mt-2 h-[2px] w-16" style={{ background: MINT }} />
            <div className="mt-5 flex items-center gap-2.5">
              <Kernel size={34} />
              <span className="display text-[40px] leading-none text-ink">TerraKernel</span>
            </div>
            <div className="display text-[21px] leading-[1.3] text-ink/85 mt-5">{t(C.tagline)}</div>
            <div className="mt-6 inline-block rounded-[5px] border px-3.5 py-2.5" style={{ borderColor: `${AMBER}99` }}>
              <span className="text-[13px] leading-snug" style={{ color: AMBER }}>{t(C.demo)}</span>
            </div>
          </Box>

          {/* ---- column headers */}
          {[
            { x: 462, label: t(C.materials) },
            { x: 742, label: t(C.mid) },
            { x: 1058, label: t(C.repo) },
          ].map((h) => (
            <g key={h.label}>
              <text x={h.x} y={50} fill={INK} fontSize="14" fontWeight="600" textAnchor="middle" fontFamily="var(--font-sans)">{h.label}</text>
              <line x1={h.x - 78} y1={60} x2={h.x + 78} y2={60} stroke={MINT} strokeWidth="1.6" />
            </g>
          ))}

          {/* ---- materials */}
          {formats.map((f, i) => (
            <MaterialCard
              key={f.key}
              x={i % 2 === 0 ? 372 : 384}
              y={84 + i * 72}
              color={f.color}
              title={t(C[`fmt_${f.key}` as 'fmt_pdf'])}
              tag={f.tag}
              count={f.n}
              lines={[[120, 96, 132], [132, 104, 118], [108, 126, 92], [126, 88, 112]][i]}
            />
          ))}
          <text x={462} y={384} fill={MUTE} fontSize="10.5" textAnchor="middle" fontFamily="var(--font-mono)">
            {n(c.evidence)} {t(C.evidence)}
          </text>

          {/* ---- materials → knowledge builder → core */}
          {formats.map((f, i) => {
            const y = 113 + i * 72
            return <path key={f.key} d={`M${i % 2 === 0 ? 548 : 560} ${y} C 590 ${y}, 590 221, 620 221`} stroke={MINT} strokeOpacity="0.55" strokeWidth="1.3" fill="none" />
          })}
          <path d="M620 221 H658" stroke={MINT} strokeWidth="2.6" fill="none" markerEnd="url(#pm)" className="flow-right" />
          <text x={614} y={200} fill={MINT} fontSize="10.5" textAnchor="middle" fontFamily="var(--font-sans)">{t(C.kb)}</text>

          {/* ---- knowledge core + satellites */}
          <rect x={664} y={188} width={156} height={66} rx={8} fill="url(#pg)" stroke={MINT} strokeOpacity="0.85" style={{ filter: 'drop-shadow(0 0 14px rgba(79,227,164,0.35))' }} />
          <text x={742} y={216} fill={INK} fontSize="13.5" fontWeight="600" textAnchor="middle" fontFamily="var(--font-sans)">{t(C.core)}</text>
          <text x={742} y={236} fill={MUTE} fontSize="10.5" textAnchor="middle" fontFamily="var(--font-mono)">{n(c.objects)} {t(C.objects)}</text>

          <path d="M700 188 V150" stroke={MINT} strokeWidth="1.2" />
          <path d="M790 188 C 790 164, 800 150, 812 142" stroke={AMBER} strokeWidth="1.2" strokeDasharray="3 4" fill="none" />
          <path d="M690 254 V300 M742 254 V300 M794 254 V300" stroke={MINT} strokeWidth="1.2" />
          <Satellite x={700} y={132} label={t(C.method)} value={n(c.objects_by_type.method ?? 0)} color={VIOLET} />
          <Satellite x={812} y={124} label={t(C.open)} value={n(c.gaps_open)} color={AMBER} />
          <Satellite x={672} y={318} label={t(C.concept)} value={n(c.objects_by_type.concept ?? 0)} color={MINT} />
          <Satellite x={772} y={318} label={t(C.constraint)} value={n(c.objects_by_type.constraint ?? 0)} color={AMBER} />
          <Satellite x={872} y={318} label={t(C.conflict)} value={n(c.relations_by_type.conflicts_with ?? 0)} color="#ef7a7a" />
          <path d="M820 240 C 850 250, 872 270, 872 300" stroke="#ef7a7a" strokeWidth="1.2" strokeDasharray="3 4" fill="none" />

          {/* ---- core → repository builder → repository */}
          <path d="M820 221 H900" stroke={MINT} strokeWidth="2.6" fill="none" markerEnd="url(#pm)" className="flow-right" />
          <text x={860} y={200} fill={MINT} fontSize="10.5" textAnchor="middle" fontFamily="var(--font-sans)">{t(C.rb)}</text>
          <path d="M906 221 C 926 221, 926 150, 946 150 M906 221 H946 M906 221 C 926 221, 926 292, 946 292" stroke={MINT} strokeOpacity="0.7" strokeWidth="1.3" fill="none" />

          {/* ---- repository folder */}
          <path d="M934 96 H1066 L1078 82 H1172 Q1180 82 1180 90 V340 Q1180 348 1172 348 H942 Q934 348 934 340 Z" fill="url(#pg)" stroke={MINT} strokeOpacity="0.6" />
          <text x={1125} y={99} fill={INK} fontSize="10.5" textAnchor="middle" fontFamily="var(--font-sans)">{t(C.entry)}</text>
          {[
            { y: 116, icon: <Document size={26} />, title: t(C.knowledge), sub: t(C.knowledgeSub), v: docs, color: MINT },
            { y: 188, icon: <StepsIcon size={26} />, title: t(C.skills), sub: t(C.skillsSub), v: skills, color: AMBER },
            { y: 260, icon: <span className="mono text-[13px]">ƒ(x)</span>, title: t(C.tools), sub: `${verified}/${tools.length} ${t(C.verified)}`, v: tools.length, color: SKY },
          ].map((r) => (
            <g key={r.title}>
              <rect x={948} y={r.y} width={218} height={62} rx={6} fill="#0b120f" stroke={r.color} strokeOpacity="0.45" />
              <circle cx={946} cy={r.y + 31} r={3.2} fill="#0b120f" stroke={MINT} strokeWidth="1.2" />
              <Box x={958} y={r.y + 10} w={200} h={44}>
                <div className="flex items-center gap-3 h-full">
                  <span style={{ color: r.color }}>{r.icon}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-[13.5px] font-semibold leading-none text-ink">{r.title}</div>
                    <div className="text-[9.5px] leading-tight text-mute mt-1.5 truncate">{r.sub}</div>
                  </div>
                  <span className="display tabular text-[24px] leading-none" style={{ color: r.color }}>{r.v}</span>
                </div>
              </Box>
            </g>
          ))}

          {/* ---- formula ribbon */}
          <path d="M742 336 V396" stroke={MINT} strokeWidth="1.2" />
          <path d="M1058 348 C 1058 420, 1000 420, 984 420" stroke={MINT} strokeWidth="1.3" fill="none" markerEnd="url(#pm)" />
          <rect x={500} y={396} width={480} height={54} rx={8} fill="url(#pg)" stroke={MINT} strokeOpacity="0.6" />
          <text x={740} y={420} fill={INK} fontSize="13.5" fontWeight="600" textAnchor="middle" fontFamily="var(--font-sans)">{t(C.formula)}</text>
          <text x={740} y={438} fill={MUTE} fontSize="9.5" textAnchor="middle" fontFamily="var(--font-sans)">{t(C.formulaSrc)}</text>

          {/* ---- the carbon case: generation → grid → industry → demand */}
          <rect x={352} y={488} width={338} height={118} rx={10} fill="none" stroke={MINT} strokeOpacity="0.45" />
          {chain.map((s, i) => (
            <g key={s.label}>
              <Box x={s.x - 26} y={506} w={52} h={52}>
                <div className="flex h-full w-full items-center justify-center rounded-[7px] border bg-[#0b120f]" style={{ color: s.color, borderColor: `${s.color}66` }}>{s.icon}</div>
              </Box>
              <rect x={s.x - 40} y={568} width={80} height={20} rx={4} fill="#0b120f" stroke="rgba(214,234,223,0.2)" />
              <text x={s.x} y={582} fill={INK} fontSize="10.5" textAnchor="middle" fontFamily="var(--font-sans)">{s.label}</text>
              {i >= 2 && i < chain.length - 1 && (
                <path d={`M${s.x + 30} 532 H${chain[i + 1].x - 34}`} stroke={MINT} strokeWidth="2" markerEnd="url(#pm)" className="flow-right" />
              )}
            </g>
          ))}
          {/* responsibility allocation: from the formula down to each actor */}
          {[628, 776, 924, 1072].map((x) => (
            <path key={x} d={`M${Math.min(960, Math.max(520, x))} 450 C ${Math.min(960, Math.max(520, x))} 478, ${x} 470, ${x} 500`} stroke={AMBER} strokeWidth="1.3" strokeDasharray="5 5" fill="none" markerEnd="url(#pa)" />
          ))}

          {/* ---- legend */}
          <g>
            <rect x={784} y={606} width={388} height={26} rx={6} fill="#0b120f" stroke={MINT} strokeOpacity="0.35" />
            <line x1={800} y1={619} x2={836} y2={619} stroke={MINT} strokeWidth="2" markerEnd="url(#pm)" />
            <text x={846} y={623} fill={INK} fontSize="10.5" fontFamily="var(--font-sans)">{t(C.flowPower)}</text>
            <line x1={980} y1={619} x2={1016} y2={619} stroke={AMBER} strokeWidth="1.6" strokeDasharray="5 4" markerEnd="url(#pa)" />
            <text x={1026} y={623} fill={INK} fontSize="10.5" fontFamily="var(--font-sans)">{t(C.flowResp)}</text>
          </g>
        </svg>
      </div>

      {/* ------------------------------------------------ small screens: the same story, stacked */}
      <div className="relative lg:hidden px-5 pt-10 pb-8">
        <div className="mono text-[10px] tracking-[0.3em] uppercase text-mint">AI for Climate</div>
        <div className="mt-3 flex items-center gap-2"><Kernel size={26} /><span className="display text-[1.9rem] leading-none">TerraKernel</span></div>
        <div className="display text-[1.05rem] text-mute mt-2">{t(C.tagline)}</div>
        <div className="mt-3 inline-block rounded border px-2.5 py-1.5 text-[11px]" style={{ borderColor: `${AMBER}88`, color: AMBER }}>{t(C.demo)}</div>
        <div className="mt-6">
          {[
            { title: t(C.materials), v: n(c.sources), sub: `${n(c.evidence)} ${t(C.evidence)}`, icon: <Document size={26} />, color: MINT, tag: t(C.kb) },
            { title: t(C.core), v: n(c.objects), sub: `${n(c.relations_by_type.conflicts_with ?? 0)} ${t(C.conflict)} · ${n(c.gaps_open)} ${t(C.open)}`, icon: <Kernel size={26} />, color: VIOLET, tag: t(C.rb) },
            { title: t(C.knowledge), v: String(docs), sub: t(C.knowledgeSub), icon: <Document size={26} />, color: MINT, tag: '' },
            { title: t(C.skills), v: String(skills), sub: t(C.skillsSub), icon: <StepsIcon size={26} />, color: AMBER, tag: '' },
            { title: t(C.tools), v: String(tools.length), sub: `${verified}/${tools.length} ${t(C.verified)}`, icon: <span className="mono text-[12px]">ƒ(x)</span>, color: SKY, tag: '' },
          ].map((row, i, all) => (
            <div key={row.title}>
              <div className="flex items-center gap-3 rounded-sm border border-line-2 bg-void/70 px-3 py-2.5" style={{ borderLeft: `2px solid ${row.color}` }}>
                <span style={{ color: row.color }}>{row.icon}</span>
                <div className="min-w-0"><div className="text-[13px] text-ink">{row.title}</div><div className="mono text-[10px] text-mute truncate">{row.sub}</div></div>
                <span className="ml-auto display tabular text-[1.4rem]" style={{ color: row.color }}>{row.v}</span>
              </div>
              {i < all.length - 1 && (
                <div className="ml-6 flex items-center gap-2 h-6">
                  <span className="h-full w-px bg-mint/60" />
                  {row.tag && <span className="mono text-[9.5px] text-mint">{row.tag}</span>}
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="mt-5 rounded-sm border border-mint/40 px-3 py-2.5 text-[12px] text-ink leading-snug">{t(C.formula)}</div>
        <div className="mt-4 flex justify-between">
          {chain.map((s) => (
            <div key={s.label} className="flex flex-col items-center gap-1" style={{ color: s.color }}>
              <span className="[&>svg]:h-7 [&>svg]:w-7">{s.icon}</span>
              <span className="text-[9.5px] text-mute">{s.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

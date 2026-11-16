import { useEffect, useState, type ReactNode } from 'react'
import { ErrorBox, Skeleton } from '../components/ui'
import { Link } from '../lib/router'
import { useT } from '../lib/i18n'
import { loadArtifacts, loadMeta, loadReplay, loadSources, useAsync } from '../lib/data'

const C = {
  kicker: { zh: '方法与限制', en: 'Method & limits' },
  title: { zh: '这个网站展示的是什么，不是什么', en: 'What this site shows, and what it does not' },
  s1: { zh: '一次真实构建', en: 'One real build' },
  s2: { zh: '数据如何到达浏览器', en: 'How the data reaches the browser' },
  s3: { zh: '精确的与压缩的', en: 'Exact and compressed' },
  s4: { zh: '不声称什么', en: 'What is not claimed' },
  s5: { zh: '一个核对过的算例', en: 'One checked example' },
  s6: { zh: '如何复现', en: 'Reproduce' },
  materials: { zh: '份资料', en: 'materials' },
  buildModel: { zh: '构建模型', en: 'Build model' },
  extractModel: { zh: '抽取模型', en: 'Extraction model' },
  builtAt: { zh: '构建时间', en: 'Built at' },
  calls: { zh: '次模型调用', en: 'model calls' },
  cost: { zh: '估算费用（按官方标价）', en: 'estimated cost (list prices)' },
  stage: { zh: '阶段', en: 'Stage' },
  seconds: { zh: '用时', en: 'Time' },
  runs: { zh: '运行次数', en: 'Runs' },
  s2a: {
    zh: 'terrakernel export-web 把构建结果导出为静态数据包。网页不连接数据库、不调用模型，也没有自己的数据。',
    en: 'terrakernel export-web writes the build result as a static bundle. The web app queries no database, calls no model and has no data of its own.',
  },
  leak: { zh: '导出时的密钥与本机路径检查', en: 'Secret and local-path check at export' },
  clean: { zh: '未发现', en: 'nothing found' },
  exact: { zh: '精确', en: 'Exact' },
  approx: { zh: '压缩或近似', en: 'Compressed or approximate' },
  exactList: {
    zh: ['数量、文件路径、页码', '原文摘录与页面截图', '工具状态与测试结果', '阶段顺序与每份资料的处理顺序'],
    en: ['Counts, file paths, page numbers', 'Quotes and page images', 'Tool statuses and test results', 'Stage order and the order of materials'],
  },
  approxList: {
    zh: [
      '回放把真实时间压缩到约 84 秒',
      '关联阶段只显示批次计数：日志没有记录每条关系的先后',
      '抽取阶段的累计数是各资料的抽取量，关联后目录还会合并与新增',
      '首页的编译流画面是示意：比例取自构建，位置不代表真实结构',
    ],
    en: [
      'The replay compresses real time into about 84 seconds',
      'Reconcile shows batch counts only: the log did not record the order of relations',
      'Running totals during extraction are per-material yields; reconcile later merges and adds objects',
      'The compile field on the home page is a schematic: proportions follow the build, positions are not the real structure',
    ],
  },
  notClaimed: {
    zh: [
      '检查通过只说明结构、引用和测试成立，不代表研究结论已被核实。',
      '没有在这个案例上做模型对比评测，不对准确率或成本作任何结论。',
    ],
    en: [
      'Passing the checks means structure, citations and tests hold; it does not verify research conclusions.',
      'No model-comparison benchmark was run on this case; no accuracy or cost claim is made.',
    ],
  },
  review: { zh: '条知识标记为待复核，未被任何产物使用', en: 'objects are marked needs-review and used by no artifact' },
  quoteFail: { zh: '条引文未通过逐字核对', en: 'quotes failed the verbatim check' },
  open: { zh: '个待确认问题仍开放（按批次提出的候选，不等于确认的缺失）', en: 'questions remain open (candidates raised per batch, not confirmed omissions)' },
  withheld: { zh: '个工具未开放', en: 'tool withheld' },
  propOnly: { zh: '个工具仅做了性质测试', en: 'tools are property-tested only' },
  notes: { zh: '据项目交付说明', en: 'Per the project’s delivery notes' },
  notesList: {
    zh: ['种子专著第 5 章没有正文，4.4 案例只保留小标题', '11 张 WMF/EMF 图片与 9 个 OLE 对象未解析', '原始省际 MRIO 矩阵未随资料提供'],
    en: ['Chapter 5 of the seed monograph has no body text; case 4.4 keeps headings only', '11 WMF/EMF images and 9 OLE objects were not parsed', 'The original provincial MRIO matrices were not among the materials'],
  },
  exIntro: {
    zh: '用生成的工具复算专著中的第 52 号光伏电厂，与原表在其显示精度下一致。负的责任量是分配结果，不代表物理碳移除。',
    en: 'Photovoltaic plant no. 52 from the monograph, recomputed with the generated tool, agrees with the source table at its displayed precision. A negative responsibility is an allocation result, not physical carbon removal.',
  },
  exSource: { zh: '原表', en: 'Source table' },
  copyright: {
    zh: '资料为第三方出版物与标准，此处仅以短摘录和页面截图说明可追溯性，版权归各自权利人。',
    en: 'The materials are third-party publications and standards, shown here as short excerpts and page images to demonstrate traceability; copyright remains with their owners.',
  },
  toReplay: { zh: '看构建回放', en: 'Watch the replay' },
}

const FILE_NOTE: Record<string, { zh: string; en: string }> = {
  'meta.json': { zh: '仓库信息、数量、阶段、检查结果', en: 'identity, counts, stages, checks' },
  'sources.json': { zh: '资料清单', en: 'source inventory' },
  'catalog.jsonl': { zh: '全部知识对象', en: 'all knowledge objects' },
  'artifacts.json': { zh: '产物及其内容', en: 'artifacts and their content' },
  'chains.json': { zh: '出处链与原文摘录', en: 'provenance chains and quotes' },
  'graph.json': { zh: '资料、知识、产物之间的连接', en: 'links between sources, objects and artifacts' },
  'replay.json': { zh: '构建日志事件', en: 'build log events' },
  media: { zh: '原文页面截图', en: 'page images' },
}

type Summary = { sizes_mb: Record<string, number>; crops: number; media_files: number; leaks: string[] }
const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`
const num = (n: number) => n.toLocaleString('en-US')

export default function Method() {
  const t = useT()
  const { data, error } = useAsync(() => Promise.all([loadMeta(), loadReplay(), loadSources(), loadArtifacts()]), [])
  const [summary, setSummary] = useState<Summary | null>(null)
  useEffect(() => {
    fetch('data/export-summary.json').then((r) => (r.ok ? r.json() : null)).then(setSummary).catch(() => setSummary(null))
  }, [])

  if (error) return <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16"><ErrorBox msg={error} /></div>
  if (!data) return <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16"><Skeleton /></div>
  const [meta, replay, sources, bundle] = data
  const c = meta.counts
  const kinds = sources.reduce((m, s) => m.set(s.kind, (m.get(s.kind) ?? 0) + 1), new Map<string, number>())
  const tools = bundle.artifacts.filter((a) => a.kind === 'tool')
  const withheld = tools.filter((x) => x.tool?.status === 'failed')
  const propOnly = tools.filter((x) => x.tool?.status === 'tested')
  const quoteFails = meta.validation.checks.extract?.fail ?? 0
  const needsReview = c.objects_by_status?.needs_review ?? 0
  const sizes = summary ? Object.entries(summary.sizes_mb).filter(([k]) => k !== '_total' && k in FILE_NOTE).sort((a, b) => b[1] - a[1]) : []
  const maxSize = sizes[0]?.[1] || 1

  return (
    <div className="pb-10">
      <section className="mx-auto max-w-[1240px] px-5 md:px-8 pt-12 md:pt-14">
        <div className="mono text-[11px] tracking-[0.22em] text-mint/80 uppercase">{t(C.kicker)}</div>
        <h1 className="display text-[2rem] md:text-[2.7rem] leading-[1.1] mt-4 max-w-[20em]">{t(C.title)}</h1>
      </section>

      <div className="mx-auto max-w-[1240px] px-5 md:px-8 mt-10 space-y-6">
        <Block n="01" title={t(C.s1)}>
          <div className="grid lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] gap-8">
            <div>
              <div className="flex items-baseline gap-3">
                <span className="display tabular text-[3rem] leading-none text-mint">{c.sources}</span>
                <span className="text-[13px] text-mute">{t(C.materials)}</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {[...kinds.entries()].map(([k, n]) => (
                  <span key={k} className="mono text-[11px] border border-line-2 rounded-full px-2.5 py-0.5 text-mute">{k} <span className="text-ink tabular">{n}</span></span>
                ))}
              </div>
              <dl className="mt-5 text-[12.5px]">
                <KV k={t(C.buildModel)} v={meta.model} />
                <KV k={t(C.extractModel)} v={meta.extract_model ?? '—'} />
                <KV k={t(C.builtAt)} v={`${meta.built_at.replace('T', ' ').replace('Z', '')} UTC`} />
                <KV k={t(C.calls)} v={num(meta.cost_total.model_calls)} />
                <KV k={t(C.cost)} v={`$${meta.cost_total.cost_usd_estimate.toFixed(2)}`} />
              </dl>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[380px] text-[12.5px]">
                <thead>
                  <tr className="text-left mono text-[10px] text-faint">
                    <th className="font-normal pb-2">{t(C.stage)}</th>
                    <th className="font-normal pb-2 text-right">{t(C.seconds)}</th>
                    <th className="font-normal pb-2 text-right">{t(C.calls)}</th>
                    <th className="font-normal pb-2 text-right">{t(C.runs)}</th>
                  </tr>
                </thead>
                <tbody>
                  {replay.stages.map((s) => (
                    <tr key={s.stage} className="border-t border-line">
                      <td className="py-2 text-ink/90">{t({ zh: s.zh, en: s.en })} <span className="mono text-[10.5px] text-faint">{s.stage}</span></td>
                      <td className="py-2 mono tabular text-right text-mute">{clock(s.seconds)}</td>
                      <td className="py-2 mono tabular text-right text-mute">{s.model_calls}</td>
                      <td className="py-2 mono tabular text-right" style={{ color: s.attempts.length > 1 ? '#efb75a' : '#8d9a92' }}>{s.attempts.length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Link to="/replay" className="inline-block mt-3 mono text-[11px] text-mint hover:text-[#69ecb4]">{t(C.toReplay)} →</Link>
            </div>
          </div>
        </Block>

        <Block n="02" title={t(C.s2)}>
          <p className="text-[13.5px] text-mute leading-relaxed max-w-[68ch]">{t(C.s2a)}</p>
          <div className="mt-5 space-y-2 max-w-[760px]">
            {sizes.map(([k, v]) => (
              <div key={k} className="grid grid-cols-[120px_minmax(0,1fr)_64px] sm:grid-cols-[120px_minmax(0,1fr)_64px_minmax(0,220px)] items-center gap-3">
                <span className="mono text-[11px] text-ink/90">{k}</span>
                <div className="h-2 bg-white/[0.05] rounded-[1px] overflow-hidden">
                  <div className="h-full bg-mint/60" style={{ width: `${Math.max(1.5, (v / maxSize) * 100)}%` }} />
                </div>
                <span className="mono text-[11px] tabular text-right text-mute">{v.toFixed(2)} MB</span>
                <span className="hidden sm:block text-[11.5px] text-faint truncate">{t(FILE_NOTE[k])}</span>
              </div>
            ))}
          </div>
          {summary && (
            <div className="mt-4 mono text-[11px] text-mute">
              {t(C.leak)}: <span className={summary.leaks.length ? 'text-rose' : 'text-mint'}>{summary.leaks.length ? summary.leaks.length : t(C.clean)}</span>
            </div>
          )}
        </Block>

        <Block n="03" title={t(C.s3)}>
          <div className="grid md:grid-cols-2 gap-8">
            <List title={t(C.exact)} color="#4fe3a4" items={t(C.exactList)} />
            <List title={t(C.approx)} color="#efb75a" items={t(C.approxList)} />
          </div>
        </Block>

        <Block n="04" title={t(C.s4)}>
          <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-x-6 gap-y-5">
            <Fig n={num(c.gaps_open)} label={t(C.open)} color="#efb75a" />
            <Fig n={num(quoteFails)} label={t(C.quoteFail)} color="#efb75a" />
            <Fig n={num(needsReview)} label={t(C.review)} color="#efb75a" />
            <Fig n={String(withheld.length)} label={`${t(C.withheld)}${withheld[0] ? ` · ${withheld[0].tool?.name}` : ''}`} color="#ef7a7a" />
            <Fig n={String(propOnly.length)} label={t(C.propOnly)} color="#efb75a" />
          </div>
          {withheld[0]?.tool?.problems[0] && (
            <blockquote className="mt-5 border-l-2 border-rose/60 pl-4 text-[12.5px] leading-relaxed text-mute max-w-[80ch] break-words">{withheld[0].tool.problems[0]}</blockquote>
          )}
          <ul className="mt-5 space-y-1.5 text-[13px] text-ink/90 max-w-[80ch]">
            {t(C.notClaimed).map((x) => <li key={x} className="pl-3 border-l border-line-2">{x}</li>)}
          </ul>
          <div className="mt-5 mono text-[10.5px] tracking-[0.16em] uppercase text-faint">{t(C.notes)}</div>
          <ul className="mt-2 space-y-1.5 text-[12.5px] text-mute max-w-[80ch]">
            {t(C.notesList).map((x) => <li key={x} className="pl-3 border-l border-line-2">{x}</li>)}
          </ul>
        </Block>

        <Block n="05" title={t(C.s5)}>
          <p className="text-[13.5px] text-mute leading-relaxed max-w-[68ch]">{t(C.exIntro)}</p>
          <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-3 mono text-[13px]">
            <Term v="0" u="tCO₂" />
            <Op>+</Op>
            <Term v="0" u="tCO₂" />
            <Op>−</Op>
            <Term v="670,000,000" u="kWh" />
            <Op>×</Op>
            <Term v="630" u="gCO₂/kWh" />
            <Op>=</Op>
            <span className="display tabular text-[1.9rem] text-mint leading-none">−422,100 <span className="mono text-[11px] text-mute">tCO₂</span></span>
            <span className="mono text-[11px] text-faint">{t(C.exSource)}: −42 ×10⁴ tCO₂</span>
          </div>
        </Block>

        <Block n="06" title={t(C.s6)}>
          <pre className="mono text-[12px] leading-[1.9] text-ink/90 overflow-x-auto">
{`terrakernel build <materials> --goal "<goal>" --output <repo>
terrakernel export-web <repo> --out web/public/data
npm --prefix web ci && npm --prefix web run build`}
          </pre>
          <p className="mt-4 text-[12px] text-faint leading-relaxed max-w-[80ch]">{t(C.copyright)}</p>
        </Block>
      </div>
    </div>
  )
}

function Block({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return (
    <section className="panel rounded-sm p-5 md:p-7">
      <div className="flex items-baseline gap-4">
        <span className="mono text-[11px] text-mint/80">{n}</span>
        <h2 className="display text-[1.35rem] leading-snug">{title}</h2>
      </div>
      <div className="mt-5">{children}</div>
    </section>
  )
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid grid-cols-[150px_minmax(0,1fr)] gap-3 py-1.5 border-t border-line">
      <dt className="text-mute">{k}</dt>
      <dd className="mono text-[11.5px] text-ink/90 break-words">{v}</dd>
    </div>
  )
}

function List({ title, color, items }: { title: string; color: string; items: string[] }) {
  return (
    <div>
      <div className="mono text-[10.5px] tracking-[0.18em] uppercase" style={{ color }}>{title}</div>
      <ul className="mt-3 space-y-2 text-[13px] text-ink/90">
        {items.map((x) => <li key={x} className="pl-3 border-l" style={{ borderColor: `${color}66` }}>{x}</li>)}
      </ul>
    </div>
  )
}

function Fig({ n, label, color }: { n: string; label: string; color: string }) {
  return (
    <div>
      <div className="display tabular text-[1.9rem] leading-none" style={{ color }}>{n}</div>
      <div className="text-[11.5px] text-mute mt-2 leading-snug break-words">{label}</div>
    </div>
  )
}

function Term({ v, u }: { v: string; u: string }) {
  return <span className="border border-line-2 rounded-sm px-2.5 py-1.5 text-ink tabular">{v} <span className="text-[10.5px] text-mute">{u}</span></span>
}
function Op({ children }: { children: ReactNode }) {
  return <span className="text-mint">{children}</span>
}

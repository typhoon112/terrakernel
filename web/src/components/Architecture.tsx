import { useMemo, useState, type ReactNode } from 'react'
import { go } from '../lib/router'
import { useT } from '../lib/i18n'
import { kindLabel, typeColor } from '../lib/data'
import type { Artifact, Meta } from '../lib/data'

/** The product as a layered architecture: every block is a real layer of the build, with its real size. */

const C = {
  kb: { zh: 'Knowledge Builder', en: 'Knowledge Builder' },
  rb: { zh: 'Repository Builder', en: 'Repository Builder' },
  materials: { zh: '原始资料', en: 'Materials' },
  evidence: { zh: '证据层', en: 'Evidence layer' },
  knowledge: { zh: '知识层', en: 'Knowledge layer' },
  repo: { zh: '科研仓库', en: 'Research repository' },
  agent: { zh: 'Agent', en: 'Agent' },
  evidenceSub: { zh: '每条都带页码与坐标', en: 'each with page and position' },
  relations: { zh: '关系', en: 'relations' },
  conflicts: { zh: '冲突并存', en: 'conflicts kept' },
  gaps: { zh: '待确认', en: 'open questions' },
  docs: { zh: '知识文档', en: 'Knowledge docs' },
  skills: { zh: 'Skills', en: 'Skills' },
  tools: { zh: '工具', en: 'Tools' },
  entry: { zh: 'Agent 入口', en: 'Agent entry' },
  calls: { zh: '次模型调用', en: 'model calls' },
  open: { zh: '打开', en: 'Open' },
}

const MINT = '#4fe3a4'
const AMBER = '#efb75a'
const SKY = '#74a9f7'
const ROSE = '#ef7a7a'
const KIND_COLOR: Record<string, string> = { pdf: '#8fd3b6', table: AMBER, text: SKY }
const clock = (s?: number | null) => (s == null ? '' : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`)
const num = (n: number) => n.toLocaleString('en-US')

type Props = { meta: Meta; kinds: Record<string, number>; artifacts: Artifact[] }

export default function Architecture({ meta, kinds, artifacts }: Props) {
  const t = useT()
  const [hot, setHot] = useState<string | null>(null)
  const c = meta.counts
  const st = meta.stages
  const types = Object.entries(c.objects_by_type).sort((a, b) => b[1] - a[1])
  const kindList = Object.entries(kinds).filter(([, n]) => n > 0)
  const totalKinds = kindList.reduce((s, [, n]) => s + n, 0) || 1
  const docs = artifacts.filter((a) => a.kind === 'knowledge_doc')
  const comps = artifacts.filter((a) => a.kind === 'computation_doc')
  const skills = artifacts.filter((a) => a.kind === 'skill')
  const tools = artifacts.filter((a) => a.kind === 'tool')
  const entries = artifacts.filter((a) => a.kind === 'entry' || a.kind === 'adapter')
  const ticks = useMemo(() => {
    let a = 42
    return Array.from({ length: 150 }, () => {
      a = (a * 1664525 + 1013904223) >>> 0
      return 0.25 + (a / 4294967296) * 0.75
    })
  }, [])
  const stage = (k: string) => ({ name: k, sec: st[k]?.seconds, calls: st[k]?.model_calls ?? 0 })
  const dim = (id: string) => (hot && hot !== id ? 'opacity-45' : 'opacity-100')
  const slab = (id: string, to: string) => ({
    onMouseEnter: () => setHot(id),
    onMouseLeave: () => setHot(null),
    onClick: () => go(to),
    className: `group w-full text-left panel clip-corner transition-all duration-300 cursor-pointer ${dim(id)} ${hot === id ? 'border-mint/50 glow-mint' : ''}`,
  })

  return (
    <div className="relative">
      <Group label={t(C.kb)} color={MINT}>
        <button {...slab('m', '/replay')}>
          <Row step="01" title={t(C.materials)} value={num(c.sources)}>
            <div className="flex h-7 gap-[3px]">
              {kindList.map(([k, n]) => (
                <div key={k} className="h-full rounded-[2px]" style={{ flexGrow: Math.max(n / totalKinds, 0.035), backgroundColor: KIND_COLOR[k] ?? '#8d9a92', opacity: 0.85 }} />
              ))}
            </div>
            <Legend items={kindList.map(([k, n]) => ({ label: k.toUpperCase(), n, color: KIND_COLOR[k] ?? '#8d9a92' }))} />
          </Row>
        </button>
        <Flow chips={[stage('ingest')]} callsLabel={t(C.calls)} />
        <button {...slab('e', '/replay')}>
          <Row step="02" title={t(C.evidence)} value={num(c.evidence)}>
            <div className="flex h-7 items-end gap-[2px] overflow-hidden">
              {ticks.map((h, i) => (
                <div key={i} className="w-[3px] shrink-0 grow rounded-[1px] bg-ink/45 group-hover:bg-mint/70 transition-colors" style={{ height: `${h * 100}%` }} />
              ))}
            </div>
            <div className="mono text-[10.5px] text-mute mt-2.5">{t(C.evidenceSub)}</div>
          </Row>
        </button>
        <Flow chips={[stage('extract'), stage('reconcile')]} callsLabel={t(C.calls)} />
        <button {...slab('k', '/layers')}>
          <Row step="03" title={t(C.knowledge)} value={num(c.objects)}>
            <div className="flex h-7 gap-[3px]">
              {types.map(([k, n]) => (
                <div key={k} className="h-full rounded-[2px]" style={{ flexGrow: Math.max(n / c.objects, 0.012), backgroundColor: typeColor[k], opacity: 0.9 }} />
              ))}
            </div>
            <div className="mt-2.5 flex flex-wrap items-center gap-x-5 gap-y-1">
              <Legend items={types.map(([k, n]) => ({ label: kindLabel[k] ? t(kindLabel[k]) : k, n, color: typeColor[k] }))} inline />
              <span className="mono text-[10.5px] text-mute ml-auto">
                {num(c.relations)} {t(C.relations)} · <span className="text-rose">{num(c.relations_by_type.conflicts_with ?? 0)} {t(C.conflicts)}</span> ·{' '}
                <span className="text-amber">{num(c.gaps_open)} {t(C.gaps)}</span>
              </span>
            </div>
          </Row>
        </button>
      </Group>
      <Flow chips={[stage('plan'), stage('compile'), stage('validate')]} callsLabel={t(C.calls)} indent />
      <Group label={t(C.rb)} color={AMBER}>
        <button {...slab('r', '/layers')}>
          <Row step="04" title={t(C.repo)} value={num(c.artifacts)}>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
              <Tile title={t(C.docs)} n={`${docs.length}+${comps.length}`} color={MINT} dots={[...docs.map(() => MINT), ...comps.map(() => '#2f8f6a')]} />
              <Tile title={t(C.skills)} n={String(skills.length)} color={AMBER} dots={skills.map((s) => (s.status === 'blocked' ? ROSE : AMBER))} />
              <Tile
                title={t(C.tools)}
                n={String(tools.length)}
                color={SKY}
                dots={tools.map((x) => (x.tool?.status === 'verified' ? MINT : x.tool?.status === 'tested' ? AMBER : ROSE))}
              />
              <Tile title={t(C.entry)} n={String(entries.length)} color="#b39dfa" dots={entries.map(() => '#b39dfa')} />
            </div>
          </Row>
        </button>
      </Group>
      <Flow chips={[]} callsLabel="" indent />
      <div className={`lg:ml-[52px] rounded-sm border border-mint/40 glow-mint px-5 py-3.5 flex flex-wrap items-center gap-x-6 gap-y-1 transition-opacity duration-300 ${dim('a')}`}>
        <span className="mono text-[10.5px] tracking-[0.2em] text-mint uppercase">05 · {t(C.agent)}</span>
        <span className="mono text-[12px] text-ink/90">Claude Code · Codex · MCP</span>
        <span className="mono text-[11px] text-mute ml-auto">AGENTS.md → Skills → tools</span>
      </div>
    </div>
  )
}

function Group({ label, color, children }: { label: string; color: string; children: ReactNode }) {
  return (
    <div className="relative lg:pl-[52px]">
      <div className="hidden lg:block absolute left-0 top-0 bottom-0 w-[34px] border-l border-y rounded-l-sm" style={{ borderColor: `${color}55` }}>
        <div
          className="absolute left-1/2 top-1/2 mono text-[10px] tracking-[0.22em] uppercase whitespace-nowrap"
          style={{ color, transform: 'translate(-50%, -50%) rotate(-90deg)' }}
        >
          {label}
        </div>
      </div>
      {children}
    </div>
  )
}

function Row({ step, title, value, children }: { step: string; title: string; value: string; children: ReactNode }) {
  return (
    <div className="grid md:grid-cols-[230px_minmax(0,1fr)] gap-x-8 gap-y-4 items-center px-5 md:px-7 py-5">
      <div>
        <div className="mono text-[10.5px] tracking-[0.2em] uppercase text-mint/80">
          {step} <span className="text-mute">· {title}</span>
        </div>
        <div className="display tabular text-[2.3rem] md:text-[2.7rem] leading-none mt-2">{value}</div>
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

function Legend({ items, inline = false }: { items: { label: string; n: number; color: string }[]; inline?: boolean }) {
  return (
    <div className={`flex flex-wrap gap-x-4 gap-y-1 mono text-[10.5px] text-mute ${inline ? '' : 'mt-2.5'}`}>
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-[1px]" style={{ backgroundColor: i.color }} />
          {i.label} <span className="tabular text-ink/80">{i.n.toLocaleString('en-US')}</span>
        </span>
      ))}
    </div>
  )
}

function Tile({ title, n, color, dots }: { title: string; n: string; color: string; dots: string[] }) {
  return (
    <div className="border border-line-2 rounded-sm px-3.5 py-3 bg-void/50 group-hover:border-line-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[12.5px] text-ink/90">{title}</span>
        <span className="display tabular text-[1.35rem] leading-none" style={{ color }}>{n}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {dots.map((d, i) => (
          <span key={i} className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: d, boxShadow: `0 0 6px ${d}88` }} />
        ))}
      </div>
    </div>
  )
}

function Flow({ chips, callsLabel, indent = false }: { chips: { name: string; sec?: number | null; calls: number }[]; callsLabel: string; indent?: boolean }) {
  return (
    <div className={`flex items-center gap-4 h-11 pl-[34px] md:pl-[60px] ${indent ? 'lg:ml-[52px]' : ''}`}>
      <svg width="12" height="44" viewBox="0 0 12 44" className="shrink-0" aria-hidden>
        <path d="M6 0V44" stroke="#4fe3a4" strokeWidth="1.3" className="flow-line" />
        <path d="M2 37l4 6 4-6" fill="none" stroke="#4fe3a4" strokeWidth="1.3" />
      </svg>
      <div className="flex flex-wrap gap-2">
        {chips.map((ch) => (
          <span key={ch.name} className="mono text-[10.5px] border border-line-2 rounded-full px-2.5 py-0.5 text-mute bg-void/60">
            <span className="text-mint">{ch.name}</span> · {clock(ch.sec)}
            {ch.calls ? ` · ${ch.calls} ${callsLabel}` : ''}
          </span>
        ))}
      </div>
    </div>
  )
}

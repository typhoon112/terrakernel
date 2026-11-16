import type { ReactNode } from 'react'
import { useLang } from '../lib/i18n'

export function Panel({ children, className = '', hover = true }: { children: ReactNode; className?: string; hover?: boolean }) {
  return <div className={`panel ${hover ? 'panel-hover transition-colors' : ''} rounded-sm ${className}`}>{children}</div>
}

export function Tag({ children, color = 'mint', soft = true }: { children: ReactNode; color?: 'mint' | 'amber' | 'sky' | 'rose' | 'violet' | 'mute'; soft?: boolean }) {
  const map: Record<string, string> = {
    mint: 'text-mint border-mint/30',
    amber: 'text-amber border-amber/30',
    sky: 'text-sky border-sky/30',
    rose: 'text-rose border-rose/30',
    violet: 'text-violet border-violet/30',
    mute: 'text-mute border-line-2',
  }
  return (
    <span className={`inline-flex items-center gap-1 border px-2 py-0.5 rounded-full text-[11px] tracking-wide ${map[color]} ${soft ? 'bg-white/[0.02]' : ''}`}>
      {children}
    </span>
  )
}

export function SectionHead({ kicker, title, intro }: { kicker?: string; title: ReactNode; intro?: ReactNode }) {
  return (
    <div className="max-w-3xl">
      {kicker && <div className="mono text-[11px] tracking-[0.22em] text-mint/80 uppercase mb-4">{kicker}</div>}
      <h2 className="display text-3xl md:text-[2.6rem] leading-[1.08] text-ink">{title}</h2>
      {intro && <p className="mt-5 text-[15px] leading-relaxed text-mute max-w-2xl">{intro}</p>}
    </div>
  )
}

export function Stat({ n, label, accent = false }: { n: ReactNode; label: ReactNode; accent?: boolean }) {
  return (
    <div className="min-w-0">
      <div className={`display tabular text-[2rem] leading-none ${accent ? 'text-mint' : 'text-ink'}`}>{n}</div>
      <div className="mt-2 text-[12px] text-mute leading-snug">{label}</div>
    </div>
  )
}

export function Skeleton({ label }: { label?: string }) {
  const { lang } = useLang()
  return (
    <div className="flex items-center gap-3 py-16 text-mute text-sm">
      <span className="inline-block h-2 w-2 rounded-full bg-mint animate-pulse" />
      {label ?? (lang === 'zh' ? '正在读取构建数据…' : 'Loading build data…')}
    </div>
  )
}

export function StatusDot({ status }: { status: string }) {
  const color = status === 'verified' ? 'bg-mint' : status === 'tested' ? 'bg-amber' : status === 'failed' ? 'bg-rose' : status === 'blocked' ? 'bg-rose' : 'bg-sky'
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ${color}`} />
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="text-sm text-faint py-10">{children}</div>
}

export function ErrorBox({ msg }: { msg: string }) {
  const { lang } = useLang()
  return (
    <div className="panel border-rose/30 p-6 text-sm text-rose/90">
      <div className="mono text-[11px] uppercase tracking-widest mb-2">{lang === 'zh' ? '数据读取失败' : 'Data error'}</div>
      {msg}
      <div className="text-mute mt-3 text-[12px]">
        {lang === 'zh'
          ? '先生成数据包：terrakernel export-web <仓库> --out web/public/data，然后重新构建。'
          : 'Generate the bundle first: terrakernel export-web <repo> --out web/public/data, then rebuild.'}
      </div>
    </div>
  )
}

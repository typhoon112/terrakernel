import { useEffect, useState } from 'react'
import { Link } from '../lib/router'
import { useLang, useUI } from '../lib/i18n'
import { Kernel } from './ClimateIcons'

export function Nav({ active }: { active?: string }) {
  const { lang, setLang } = useLang()
  const ui = useUI()
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8)
    on()
    window.addEventListener('scroll', on, { passive: true })
    return () => window.removeEventListener('scroll', on)
  }, [])
  const nav = [
    { to: '/workflow', key: 'nav.workflow' },
    { to: '/replay', key: 'nav.replay' },
    { to: '/layers', key: 'nav.layers' },
    { to: '/knowledge', key: 'nav.knowledge' },
  ]
  return (
    <header
      className={`fixed top-0 inset-x-0 z-50 transition-colors ${scrolled || open ? 'bg-void/85 backdrop-blur-md border-b border-line' : 'border-b border-transparent'}`}
    >
      <div className="mx-auto max-w-[1240px] px-5 md:px-8 h-16 flex items-center gap-6">
        <Link to="/" className="flex items-center gap-2.5 shrink-0" onClick={() => setOpen(false)}>
          <Kernel size={24} />
          <span className="display text-[17px] tracking-tight">TerraKernel</span>
        </Link>
        <nav className="hidden md:flex items-center gap-1 ml-2">
          {nav.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              className={`px-3 py-1.5 text-[13.5px] rounded-sm transition-colors ${active === n.to ? 'text-ink bg-white/[0.05]' : 'text-mute hover:text-ink'}`}
            >
              {ui(n.key)}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
            className="mono text-[11px] tracking-wider border border-line-2 text-mute hover:text-ink px-2.5 py-1 rounded-full transition-colors"
            aria-label="switch language"
          >
            {lang === 'zh' ? 'EN' : '中文'}
          </button>
          <button
            className="md:hidden text-mute hover:text-ink px-1"
            onClick={() => setOpen((o) => !o)}
            aria-label="menu"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </button>
        </div>
      </div>
      {open && (
        <nav className="md:hidden border-t border-line bg-void/95 backdrop-blur-md px-5 py-3 flex flex-col">
          {nav.map((n) => (
            <Link key={n.to} to={n.to} className="py-2.5 text-sm text-mute" onClick={() => setOpen(false)}>
              {ui(n.key)}
            </Link>
          ))}
        </nav>
      )}
    </header>
  )
}

export function Footer() {
  const { lang } = useLang()
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-10 flex flex-wrap items-center gap-x-8 gap-y-3 text-[12px] text-faint">
        <span className="display text-[14px] text-mute">TerraKernel</span>
        <span className="mono">AI4Climate Hackathon 2026</span>
        <span className="mono">
          {lang === 'zh' ? '本页所有数字与原文截图均来自一次真实构建' : 'Every number and quote on this site comes from one real build'}
        </span>
        <a href="https://github.com/typhoon112/terrakernel" className="ml-auto text-mute hover:text-mint transition-colors" target="_blank" rel="noreferrer">
          GitHub →
        </a>
      </div>
    </footer>
  )
}

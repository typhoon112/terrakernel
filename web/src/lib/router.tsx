import { useEffect, useMemo, useState, type ReactNode } from 'react'

/** Minimal hash router: GitHub Pages serves index.html for '/', hash routes need no 404 shim. */

export type Route = { name: string; param?: string; hash: Record<string, string> }

export function parseHash(h: string): Route {
  const raw = h.replace(/^#/, '') || '/'
  const [path, qs] = raw.split('?')
  const parts = path.split('/').filter(Boolean)
  const hash: Record<string, string> = {}
  if (qs) for (const p of qs.split('&')) {
    const [k, v] = p.split('=')
    if (k) hash[decodeURIComponent(k)] = decodeURIComponent(v ?? '')
  }
  return { name: parts[0] || 'home', param: parts[1] ? decodeURIComponent(parts.slice(1).join('/')) : undefined, hash }
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseHash(window.location.hash))
  useEffect(() => {
    const on = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

export function go(to: string) {
  if (window.location.hash === `#${to}`) return
  window.location.hash = to.startsWith('/') ? to : `/${to}`
}

export function Link({ to, children, className, onClick }: { to: string; children: ReactNode; className?: string; onClick?: () => void }) {
  return (
    <a
      href={`#${to.startsWith('/') ? to : `/${to}`}`}
      className={className}
      onClick={() => {
        onClick?.()
      }}
    >
      {children}
    </a>
  )
}

export function useInView<T extends HTMLElement>(threshold = 0.15) {
  const [el, setEl] = useState<T | null>(null)
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    if (!el || seen) return
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setSeen(true)),
      { threshold },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [el, seen, threshold])
  return useMemo(() => ({ ref: setEl, seen }), [seen])
}

export function scrollToId(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

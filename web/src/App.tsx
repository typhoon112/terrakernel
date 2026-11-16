import { useEffect } from 'react'
import { useRoute } from './lib/router'
import { LangProvider } from './lib/i18n'
import { Nav, Footer } from './components/Nav'
import Home from './pages/Home'
import Workflow from './pages/Workflow'
import ReplayPage from './pages/ReplayPage'
import Layers from './pages/Layers'
import ArtifactPage from './pages/ArtifactPage'
import Knowledge from './pages/Knowledge'

function Routed() {
  const route = useRoute()
  const page = (() => {
    switch (route.name) {
      case 'workflow':
        return <Workflow />
      case 'replay':
        return <ReplayPage />
      case 'layers':
        return <Layers />
      case 'artifact':
        return <ArtifactPage id={route.param ?? ''} />
      case 'knowledge':
        return <Knowledge />
      default:
        return <Home />
    }
  })()
  const active =
    route.name === 'artifact' ? '/layers' : route.name === 'home' ? '' : `/${route.name}`
  return (
    <div className="min-h-screen bg-void text-ink noise">
      <Nav active={active} />
      <main className="pt-16">{page}</main>
      <Footer />
    </div>
  )
}

export default function App() {
  useEffect(() => {
    if (!window.location.hash) window.location.hash = '#/'
    const on = () => window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior })
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return (
    <LangProvider>
      <Routed />
    </LangProvider>
  )
}

import { useState } from 'react'
import PosterFlow from '../components/PosterFlow'
import LayersVisual from '../components/LayersVisual'
import RepoMap from '../components/RepoMap'
import Layers from './Layers'
import { ErrorBox, Skeleton } from '../components/ui'
import { useT } from '../lib/i18n'
import { loadArtifacts, loadChains, loadMeta, loadSources, useAsync } from '../lib/data'

const C = {
  more: { zh: '展开完整的文字清单', en: 'Show the full written inventory' },
  less: { zh: '收起文字清单', en: 'Hide the written inventory' },
}

/** "What was built": the poster, then every document, skill and tool as a drawn card. */
export default function Built() {
  const t = useT()
  const [detail, setDetail] = useState(false)
  const { data, error } = useAsync(() => Promise.all([loadMeta(), loadArtifacts(), loadSources(), loadChains()]), [])
  if (error) return <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16"><ErrorBox msg={error} /></div>
  if (!data) return <div className="mx-auto max-w-[1240px] px-5 md:px-8 py-16"><Skeleton /></div>
  const [meta, bundle, sources, chains] = data
  return (
    <div>
      <section className="border-b border-line">
        <PosterFlow meta={meta} artifacts={bundle.artifacts} sources={sources} />
      </section>
      <RepoMap meta={meta} artifacts={bundle.artifacts} chains={chains} />
      <LayersVisual meta={meta} artifacts={bundle.artifacts} chains={chains} sources={sources} />
      <div className="mx-auto max-w-[1240px] px-5 md:px-8 pb-10">
        <button onClick={() => setDetail((x) => !x)} className="mono text-[11.5px] text-mute hover:text-mint border border-line-2 rounded-sm px-3 py-2 transition-colors">
          {detail ? '−' : '+'} {detail ? t(C.less) : t(C.more)}
        </button>
      </div>
      {detail && <Layers />}
    </div>
  )
}

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type Lang = 'zh' | 'en'

const LangCtx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: 'zh', setLang: () => {} })

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => (localStorage.getItem('tk-lang') as Lang) || 'zh')
  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  }, [lang])
  const setLang = (l: Lang) => {
    localStorage.setItem('tk-lang', l)
    setLangState(l)
  }
  return <LangCtx.Provider value={{ lang, setLang }}>{children}</LangCtx.Provider>
}

export const useLang = () => useContext(LangCtx)

/** Pick a bilingual string from the page copy. */
export function useT() {
  const { lang } = useLang()
  return <T,>(t: { zh: T; en: T }): T => t[lang]
}

type Dict = Record<string, { zh: string; en: string }>

const UI: Dict = {
  'nav.workflow': { zh: '工作流', en: 'Workflow' },
  'nav.replay': { zh: '构建回放', en: 'Replay' },
  'nav.layers': { zh: '生成结果', en: 'What was built' },
  'nav.knowledge': { zh: '知识目录', en: 'Knowledge' },
  'nav.method': { zh: '方法与限制', en: 'Method & limits' },
  'brand.tag': { zh: '从科研资料到 Agent 可用的研究仓库', en: 'From research materials to a research repository an agent can use' },
  'cta.start': { zh: '看一次真实构建', en: 'Watch a real build' },
  'cta.layers': { zh: '看看生成了什么', en: 'See what was built' },
  'common.loading': { zh: '正在读取构建数据…', en: 'Loading build data…' },
  'common.error': { zh: '数据读取失败', en: 'Could not load the data bundle' },
  'common.sources': { zh: '资料', en: 'Materials' },
  'common.evidence': { zh: '证据单元', en: 'Evidence units' },
  'common.objects': { zh: '知识与概念', en: 'Knowledge objects' },
  'common.artifacts': { zh: '产物', en: 'Artifacts' },
  'common.tools': { zh: '工具', en: 'Tools' },
  'common.skills': { zh: 'Skills', en: 'Skills' },
  'common.docs': { zh: '知识文档', en: 'Knowledge docs' },
  'common.gaps': { zh: '待确认问题', en: 'Open questions' },
  'common.conflicts': { zh: '冲突', en: 'Conflicts' },
  'common.relations': { zh: '关系', en: 'Relations' },
  'common.back': { zh: '返回', en: 'Back' },
  'common.quote': { zh: '原文', en: 'Source text' },
  'common.evidenceOf': { zh: '证据', en: 'Evidence' },
  'common.from': { zh: '来自', en: 'from' },
}

export function useUI() {
  const { lang } = useLang()
  return (key: string) => UI[key]?.[lang] ?? key
}

export const tr = (lang: Lang, zh: string, en: string) => (lang === 'zh' ? zh : en)

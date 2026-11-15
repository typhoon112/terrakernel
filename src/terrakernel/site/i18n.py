"""Text for the site UI in English and Chinese.

Content generated from the repository (knowledge documents, summaries, skill text) is English
only; interface labels, navigation and explanatory prose are bilingual. Each string is rendered
once with both languages in the HTML, and a small script swaps them.
"""

from __future__ import annotations

from html import escape

T: dict[str, tuple[str, str]] = {
    # navigation
    "site.title": ("TerraKernel · compiled research repository", "TerraKernel · 编译出的科研仓库"),
    "nav.gallery": ("All examples", "全部示例"),
    "gallery.kicker": ("Compiled research repositories", "编译出来的科研仓库"),
    "gallery.title": ("From research materials to a repository an agent can work in",
                      "把科研资料编译成 Agent 可以直接工作的仓库"),
    "gallery.lede": (
        "Each example below was compiled by TerraKernel from a folder of papers, data, notes and old code. "
        "Open one to see what the materials say, what was recorded, which tools were verified and how an "
        "agent performed with and without the repository.",
        "下面每个示例都由 TerraKernel 从一个资料文件夹（论文、数据、说明、旧代码）编译而成。"
        "打开任意一个，可以看到资料怎么说、记录了什么、哪些工具通过了验证，以及 Agent 在有无仓库时的表现。"),
    "gallery.open": ("Open example", "打开示例"),
    "gallery.runs": ("graded agent runs", "次已评分的 Agent 运行"),
    "nav.overview": ("Overview", "总览"),
    "nav.steps": ("How it works", "三步看懂"),
    "nav.cases": ("Cases", "案例"),
    "nav.repo": ("Repository", "生成的仓库"),
    "nav.results": ("Results", "评测结果"),
    "nav.limits": ("Evidence & limits", "证据与局限"),
    "nav.knowledge": ("Knowledge", "知识库"),
    "nav.lang": ("中文", "English"),
    # hero
    "hero.kicker": ("A compiled research repository", "一个编译出来的科研仓库"),
    "hero.lede": (
        "Explore knowledge with source locations and review flags. Tools show whether they were verified "
        "against reference values, tested for properties, or withheld after failed checks.",
        "查看知识及其证据来源，识别待复核内容。工具分别显示参考值验证、性质测试或检查失败后不可用的状态。",
    ),
    "hero.goto": ("Start with the cases", "从案例看起"),
    "hero.tasks": ("Choose a research task", "选择研究任务"),
    "hero.repo": ("Inspect the repository", "查看生成的仓库"),
    "tasks.title": ("Start your research", "开始研究"),
    "tasks.intro": ("Choose a task to open its workflow, required inputs and steps.",
                    "选择研究任务，查看对应流程、所需输入和操作步骤。"),
    "tasks.open": ("Open workflow", "打开任务流程"),
    "tasks.pending": ("Available after the workflow is built.", "任务流程构建完成后可用。"),
    # stats
    "stat.sources": ("materials", "份资料"),
    "stat.evidence": ("evidence units", "个证据单元"),
    "stat.objects": ("knowledge objects", "条知识"),
    "stat.conflicts": ("conflicts kept", "处冲突保留"),
    "stat.gaps": ("open questions", "个待确认问题"),
    "stat.tools": ("verified tools", "个已验证工具"),
    "stat.skills": ("agent skills", "个 Agent Skill"),
    "stat.checks": ("structure checks passed", "项结构检查通过"),
    # steps
    "steps.title": ("From materials to a repository an agent can use", "从资料到 Agent 可用的仓库"),
    "steps.1.t": ("01 · Evidence", "01 · 证据"),
    "steps.1.d": (
        "Papers, data files and code are split into units that can be found again: a page and region in a PDF, "
        "a heading and line range in Markdown, a column in a data file, a function and line range in code.",
        "论文、数据文件和代码被拆成能再次定位的单元：PDF 的页码与区域、Markdown 的章节与行号、数据的每一列、代码的函数与行号。",
    ),
    "steps.2.t": ("02 · Knowledge", "02 · 知识"),
    "steps.2.d": (
        "Each statement cites evidence and a verbatim quote; facts stated by the materials, derived by the model "
        "and measured from data are kept apart; conflicting definitions are kept side by side, never merged.",
        "每条知识都引用证据和逐字摘录；资料陈述、模型推导、数据实测分开记录；定义冲突并列保留，绝不合并。",
    ),
    "steps.3.t": ("03 · Repository", "03 · 仓库"),
    "steps.3.d": (
        "Knowledge becomes documents, tested tools, skills and configuration. Units, timestamp conventions and "
        "time-varying parameters are compiled into executable configuration.",
        "知识被编译成文档、经过测试的工具、Skill 和配置。单位、时间戳约定和时变参数都变成可执行的配置。",
    ),
    "steps.4.t": ("04 · Update", "04 · 更新"),
    "steps.4.d": (
        "When materials change, the evidence that changed is found, only affected objects are re-examined, and "
        "only affected files are rebuilt. Questions the materials answer are closed; the rest stay open.",
        "资料变化时，先找出变化的证据，只重新检查受影响的知识，只重建受影响的文件。资料能回答的问题被关闭，其余保持开放。",
    ),
    # cases
    "cases.title": ("Cases", "案例"),
    "cases.intro": (
        "Each case is one point where the materials needed interpretation: a conflict, a question they leave open, "
        "a documented rule that became executable configuration, or a computation that had to be verified.",
        "每个案例都是资料需要解释的一处：一处冲突、一个没有答案的问题、一条变成可执行配置的规则，或一个需要验证的计算。",
    ),
    "cases.all": ("All", "全部"),
    "cases.search": ("Search cases", "搜索案例"),
    "cases.shown": ("shown", "已显示"),
    "cases.more": ("Show 24 more", "再显示 24 条"),
    "cases.empty": ("No cases match your search and filter.", "没有符合搜索及筛选条件的案例。"),
    "cases.source": ("What the materials say", "资料怎么说"),
    "cases.knowledge": ("What TerraKernel recorded", "TerraKernel 记下了什么"),
    "cases.became": ("What it became", "变成了什么"),
    "cases.agent": ("Did it help the agent?", "对 Agent 有没有用"),
    "cases.none": (
        "The recorded agent runs did not exercise this case.",
        "已记录的 Agent 运行没有涉及这个案例。",
    ),
    "cases.object": ("Knowledge object", "知识对象"),
    "case.conflict": ("Conflict", "冲突"),
    "case.gap": ("Open question", "待确认问题"),
    "case.answered": ("Answered by a person", "人工回答"),
    "case.resolved": ("Resolved questions", "已解决问题"),
    "case.human": ("Answered by a person", "人工回答"),
    "case.model": ("Resolved by model reconciliation", "模型跨来源关联解决"),
    "case.other": ("Recorded resolution", "已记录解决方式"),
    "case.tool": ("Tool", "工具"),
    "case.update": ("Update", "更新"),
    "case.review": ("Needs review", "需要复核"),
    # repo
    "repo.title": ("The generated repository", "生成的仓库"),
    "repo.intro": (
        "A plain folder. Claude Code and Codex read AGENTS.md, load knowledge on demand, and call the verified "
        "tools directly or over MCP.",
        "一个普通文件夹。Claude Code 和 Codex 读取 AGENTS.md，按需加载知识，直接或通过 MCP 调用已验证的工具。",
    ),
    "repo.artifacts": ("Artifacts", "产物"),
    "repo.file": ("File", "文件"),
    "repo.kind": ("Kind", "类型"),
    "repo.status": ("Status", "状态"),
    "repo.objects": ("Based on", "依据"),
    "repo.depends": ("Depends on", "依赖"),
    "repo.download": ("Download the repository", "下载整个仓库"),
    "repo.deps": ("Dependencies between artifacts", "产物之间的依赖"),
    "repo.tools": ("Tools and their verification", "工具与验证"),
    # results
    "results.title": ("Results", "评测结果"),
    "results.intro": (
        "The same agent, prompt and tools run in three workspaces: only the raw materials (raw), the materials plus "
        "the compiled knowledge (knowledge), and the complete repository (full). Each answer is graded against an "
        "independent reference solution.",
        "同一个 Agent、同一提示、同一工具，在三种环境里运行：只有原始资料（raw）、资料加编译好的知识（knowledge）、完整仓库（full）。每个答案都和独立参考解对照评分。",
    ),
    "results.table": ("Runs", "运行次数"),
    "results.correct": ("All values correct", "全部数值正确"),
    "results.tokens": ("Tokens per run", "单次 token"),
    "results.cost": ("Estimated cost", "估算费用"),
    "results.build": ("Build cost so far (all builds and updates)", "累计构建费用（含历次构建与更新）"),
    "results.note": (
        "These examples are small and well documented: a strong model reads the raw materials and gets the same "
        "answer. The repository shows its value when materials exceed what a model can read, conventions are "
        "scattered, and tasks repeat.",
        "这两个样例都很小、说明清楚：强模型只读原始资料也能得到同样的答案。当资料超出模型一次能读的范围、约定分散、任务反复执行时，仓库才显出价值。",
    ),
    # limits
    "limits.title": ("Evidence and limits", "证据与局限"),
    "limits.claims": ("What this repository does support", "这个仓库能支持的"),
    "limits.nonclaims": ("What it does not claim", "它不声称的"),
    "limits.sources": ("Materials and licenses", "资料与许可"),
    "limits.units_t": ("Units and conventions", "单位与约定"),
    # knowledge pages
    "kdoc.objects": ("Knowledge objects in this document", "本文档涉及的知识对象"),
    "kdoc.back": ("Back to the overview", "返回总览"),
    "kdoc.cited": ("Cited evidence", "引用的证据"),
    # object pages
    "obj.attributes": ("Attributes", "属性"),
    "obj.evidence": ("Evidence", "证据"),
    "obj.relations": ("Relations", "关系"),
    "obj.usedby": ("Used by", "被谁使用"),
    "obj.basis": ("Basis", "来源"),
    "obj.status": ("Status", "状态"),
    # run pages
    "run.steps": ("Steps", "步骤"),
    "run.answer": ("Answer", "回答"),
    "run.grade": ("Grade", "评分"),
    "run.usage": ("Usage", "用量"),
    # common
    "common.verified": ("verified", "已验证"),
    "common.tested": ("tested", "已测试"),
    "common.failed": ("failed", "失败"),
    "common.needs_review": ("needs review", "需复核"),
    "common.open": ("open", "开放"),
    "common.blocking": ("blocking", "阻断"),
    "common.warning": ("warning", "提示"),
    "common.conflict": ("conflict", "冲突"),
    "common.human": ("confirmed by a person", "人工确认"),
    "common.replay": ("Replay", "回放"),
    "common.play": ("Play", "播放"),
    "common.pause": ("Pause", "暂停"),
    "common.page": ("page", "第"),
    "common.read_more": ("Open", "查看"),
    "footer.made": ("Compiled by TerraKernel from the materials in sources/.", "由 TerraKernel 从 sources/ 中的资料编译生成。"),
}


def tw(key: str, default_en: str | None = None) -> str:
    """Return an inline element carrying both languages; the script swaps text on toggle."""
    en, zh = T.get(key, (default_en or key, default_en or key))
    return (f'<span class="i18n" data-en="{escape(en)}" data-zh="{escape(zh)}">{escape(en)}</span>')


def bi(en: str, zh: str | None = None) -> str:
    """Inline element for text given directly in both languages (falls back to English)."""
    if not zh:
        return escape(en)
    return f'<span class="i18n" data-en="{escape(en)}" data-zh="{escape(zh)}">{escape(en)}</span>'

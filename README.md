# TerraKernel

TerraKernel 是 AI4Climate 黑客松参赛项目，也是一个可在本机运行的科研资料编译工具。

它把一批多模态科研资料编译成 Agent 可以直接使用的 **AI-Native 科研仓库**。资料可以是论文 PDF、数据说明、CSV 数据、已有代码和图表。

```
原始资料 ──ingest──▶ 证据单元 ──extract──▶ 结构化知识 ──reconcile──▶ 关联、冲突、缺口
                                                        │
             AI-Native 仓库 ◀──compile── Repository Spec ◀──plan──┘
             （知识、工具、Skills、入口）        │
                       └──validate──▶ 结构检查、工具测试、任务验证
资料变化 ──update──▶ 局部重抽取 → 影响追踪 → 只重建受影响产物 → 复验
```

生成的仓库是一个普通文件夹。Claude Code、Codex 等 Agent 进入后可以直接读取知识、调用工具、按 Skill 完成科研任务。仓库同时保留每一条知识的原文证据和每个工具的验证记录。

## 产品交付与下一步

交付给使用者的是 **可安装的 TerraKernel 命令行工具、使用说明和完整示例**。本 GitHub 仓库提供工具源码；使用者输入自己的外部资料和研究目标后，工具生成可交给 Agent 使用的科研仓库。这里的“输入入口”指资料接入，第一版使用本地资料目录。

当前已有分开的 `init`、`build` 命令和完整构建流水线，以及更新、人工回答和静态展示能力。下一阶段按以下顺序完善使用流程；这些是待完成的交付要求：

1. **统一构建入口。** 一次调用接收资料目录、研究目标和输出目录，复用现有初始化与构建流程，并保留已有命令。普通构建不要求任务 YAML 或标准答案。完成标准：首次使用者按一条文档命令即可从自己的资料开始构建，无须修改源码或示例配置。
2. **完善导入反馈和结果交接。** 明确列出已识别、已解析、跳过和解析失败的文件及原因；输入无效或构建失败时给出可操作提示。完成后输出生成目录、`AGENTS.md` 入口、待确认问题及更新方式。完成标准：使用者能确认哪些资料实际参与构建，并知道失败后如何处理、成功后如何使用结果。
3. **完成独立交付验收。** 核对完整构建所需的运行依赖，从分发包在干净环境安装，用一批内置样例之外的资料走通导入、构建、验证、产物使用和资料更新。完成标准：生成仓库的知识、工具和 Skills 可从统一入口找到并使用，流程不依赖开发机路径或样例专用配置；仅安装成功或运行 `init` 不代表该项完成。

实施时复用现有模块与流水线，优先完成上述资料接入流程。模型对比评测用于补充验证，网页用于浏览结果；它们不作为第一版资料输入入口的交付前提。

## 设计原则

- **证据优先**：资料先被拆成可定位的证据单元（PDF 页码与坐标、Markdown 行号、CSV 列、代码函数与行号）。抽取出的每条知识都必须引用证据并附逐字摘录，由代码校验；对不上原文的知识不会被当作可信知识。
- **来源分类**：知识按来源分为“资料陈述 / 模型推导 / 工具实测 / 人工确认”四类，分别记录，不合成一个置信度。
- **冲突保留**：同名但定义不同的内容（例如两种 NRMSE）保留为两个方法，挂在同一个上位概念下，并标注冲突。资料中有约定时，由约定决定采用哪一个。
- **缺口不补**：资料没写的内容（单位、时间戳语义、预测发布时间等）记录为缺口，不用常识补默认值，并在仓库入口列为待确认问题。
- **工具先验证再开放**：
  - 已有代码原样复用，只加输入检查。
  - 只有公式的方法由模型实现，但必须通过从资料中**摘录**的算例（输入与期望值都来自原文并附出处）才标记为 verified。
  - 实现代码看不到期望值；测试期望值也不允许由实现计算得出。
- **数据语义可执行**：单位、时间戳约定、时变参数（如装机容量生效日期）被编译成配置。生成仓库的数据运行时按配置自动换算，Agent 不必自己推断。
- **兼容现有生态**：知识层遵循 Google Open Knowledge Format v0.2；Skills 遵循 Agent Skills 规范（`.agents/skills`，并镜像到 `.claude/skills`）；工具通过 MCP 暴露；入口文件为 `AGENTS.md` 和 `CLAUDE.md`。
- **可管理**：记录“资料 → 证据 → 知识 → 产物”的依赖。资料更新后，只重抽取受影响的知识；未变的产物来自缓存，文件不被改动。

## 安装

需要 [uv](https://docs.astral.sh/uv/) 和 Python 3.12（由 uv 管理）。

下载或克隆本仓库后，在项目根目录执行：

```bash
uv sync
uv run terrakernel --help
```

支持的资料格式：PDF（含双栏排版）、Markdown、纯文本、CSV/TSV、Excel（按工作表）、Parquet、NetCDF（读取文件自带的单位、cell_methods 等属性）、Python 脚本与 Notebook、图片。

大模型调用使用 Anthropic Python SDK。运行前在环境变量中配置 `ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN`；使用兼容网关时同时设置 `ANTHROPIC_BASE_URL`。密钥不写入项目文件。

`uv run terrakernel doctor` 用于检查模型端点及其结构化输出支持；程序会为不支持原生结构化输出的端点尝试兼容方式。模型可在初始化时通过 `--model` 指定。

## 使用自己的资料

外部资料的入口是一个目录。把论文、说明、数据和已有代码放在该目录中，再提供一句研究目标；任务文件和标准答案都不是构建的必填项。当前版本需要分别执行 `init` 和 `build`。

以下命令在本仓库根目录运行。将 `/path/to/materials` 替换为资料目录，将 `YYYYMMDD` 替换为运行日期。生成结果和运行记录放在已忽略的 `artifacts/` 内。

```bash
# 初始化：只创建项目配置，不调用模型
uv run terrakernel init /path/to/materials \
  --goal "整理这些科研资料，支持城市热浪分析" \
  --output artifacts/YYYYMMDD/my-research

# 构建：调用模型，生成知识、工具、Skills 和统一入口
uv run terrakernel build artifacts/YYYYMMDD/my-research

# 查看结果和需要补充的信息
uv run terrakernel status artifacts/YYYYMMDD/my-research
uv run terrakernel gaps artifacts/YYYYMMDD/my-research
```

构建后，先阅读生成目录中的 `AGENTS.md`，再让 Agent 打开该目录开展任务。资料变化后，对同一生成目录执行 `terrakernel update`；需要浏览或下载结果时执行 `terrakernel site` 导出静态页面。静态页面目前不提供上传或发起构建功能。

## 示例与进阶命令

以开发样例（风电预测评测，合成数据）为例：

```bash
# 1. 创建仓库：指定资料目录、研究目标和任务
uv run terrakernel init examples/wind-forecast-eval/materials -o artifacts/YYYYMMDD/example/wind-repo \
  --goal "Evaluate and compare day-ahead wind power forecasts following the group's evaluation convention." \
  --tasks examples/wind-forecast-eval/tasks.yaml

# 2. 构建：ingest → extract → reconcile → plan → compile → validate
uv run terrakernel build artifacts/YYYYMMDD/example/wind-repo

# 3. 查看知识库、缺口、关系
uv run terrakernel status artifacts/YYYYMMDD/example/wind-repo
uv run terrakernel kb artifacts/YYYYMMDD/example/wind-repo --gaps

# 4. 验证生成的仓库（OKF、Skills 规范、链接、工具测试、MCP）
uv run terrakernel validate artifacts/YYYYMMDD/example/wind-repo

# 5. 让内置 Agent 完成任务，并对照标准答案评分
uv run terrakernel run-task artifacts/YYYYMMDD/example/wind-repo compare-forecast-models --setting full --model haiku

# 6. 对比实验：同一 Agent 在 raw（原始资料）/ knowledge（加知识）/ full（完整仓库）下的表现
uv run terrakernel eval artifacts/YYYYMMDD/example/wind-repo --models opus,sonnet,haiku --repeats 3 --out artifacts/YYYYMMDD/eval

# 7. 资料变化后同步仓库，输出影响报告
uv run terrakernel update artifacts/YYYYMMDD/example/wind-repo --materials <新资料目录>

# 8. 查看待确认问题，并由人回答（回答会成为“人工确认”的知识，并触发局部更新）
uv run terrakernel gaps artifacts/YYYYMMDD/example/wind-repo
uv run terrakernel answer artifacts/YYYYMMDD/example/wind-repo 3 "回答内容" --by <姓名>

# 9. 导出展示站点并在本机提供访问（只读静态页面，中英可切换）
uv run terrakernel site artifacts/YYYYMMDD/example/wind-repo
uv run terrakernel serve artifacts/YYYYMMDD/example/wind-repo/site --port 8765

# 10. 多个仓库合成一个站点（带共同入口页）
uv run terrakernel gallery artifacts/YYYYMMDD/example/wind-repo artifacts/YYYYMMDD/example/heat-repo --out artifacts/YYYYMMDD/example/site
```

资料更新后，标准答案通常也会变化。重新运行独立参考解生成新的标准答案后，可以不调用模型，直接对已保存的 Agent 运行重新评分：

```bash
uv run terrakernel eval artifacts/YYYYMMDD/example/wind-repo --regrade --tag eval --expected <新标准答案.json>
```

一条命令构建两个样例并导出站点（会调用模型，约十几分钟）：

```bash
uv run terrakernel demo --out artifacts/YYYYMMDD/demo
uv run terrakernel serve artifacts/YYYYMMDD/demo/site --port 8765
```

**任务文件**（`tasks.yaml`）包含以下内容：
- 研究目标；
- 每个任务的描述、验收标准和需要报告的数值；
- 可选：标准答案文件，由独立参考解生成，仅用于评分，Agent 看不到。

**缓存**：模型调用按请求内容缓存在 `<repo>/.terrakernel/llm-cache/`。重复构建只为发生变化的部分付费。设置 `TK_LLM_MODE=replay` 可以完全离线重放。

## 展示站点

`terrakernel site` 从构建结果生成静态站点，内容全部来自仓库本身，不需要手写：

- **总览**：资料、证据、知识、冲突、待确认问题、已验证工具的数量，以及从资料到仓库的四步。
- **案例**：每处冲突、每个待确认问题、每个人工回答、每个工具、每次更新各成一个案例。每个案例分四栏：
  资料怎么说（PDF 截图加高亮框、代码行、数据列）、TerraKernel 记下了什么、变成了什么、对 Agent 有没有用。
- **生成的仓库**：产物清单、依赖关系图、工具验证状态，可下载整个仓库。
- **评测结果**：raw / knowledge / full 的对比，以及每次 Agent 运行的逐步回放。
- **证据与局限**：能支持什么、不声称什么、资料清单。

站点不引用任何外部资源（字体为自托管的 IBM Plex，OFL 许可），导出时会检查并拒绝写入密钥和本机路径。

## 生成的仓库

```
AGENTS.md / CLAUDE.md            入口：用途、规则、任务与 Skill、工具、数据、冲突、待确认问题
knowledge/                       OKF v0.2 知识包（index.md、各主题文档、Attested Computation、log.md）
.agents/skills/<name>/SKILL.md   领域 Skills（.claude/skills/ 为逐字镜像）
tools/research_tools/            数据运行时 + 已验证工具 + config/（数据语义）+ registry.json
tools/mcp_server.py              MCP 服务（只暴露已验证工具）；.mcp.json、.codex/config.toml
tests/                           工具与运行时测试（参考算例来自资料原文）
sources/                         原始资料副本（证据定位基准）
.terrakernel/                    知识库 kb.sqlite、spec.yaml、lineage.json、validation.json、运行记录
```

## 项目结构

```
src/terrakernel/
  ingest/      资料解析为证据单元（pdf、markdown、text、table、code、image）
  extract/     抽取 + 来源校验（grounding）
  reconcile/   跨资料关联、上位概念、冲突与缺口
  plan/        Repository Spec 规划与校验
  compile/     工具（复用 / 实现 + 验证）、知识文档、Skills、入口、适配器
  validate/    结构、规范、链接、测试、MCP 检查
  site/        展示站点生成器（页面、图表、原文截图、字体）
  update/      资料变化后的增量同步与影响报告
  agent/       内置 Agent、沙箱、评分、对比实验
  builtin/     Builder Skills（各阶段的模型指令）与生成仓库的模板
examples/wind-forecast-eval/   开发样例 1：风电预测评测（CSV、Markdown、PDF、旧脚本）
examples/heatwave-days/        开发样例 2：城市热浪天数（NetCDF、Markdown、PDF、旧脚本）
demo/                          展示站点的标题配置与说明
tests/                         离线单元测试（不调用模型）
```

## 范围与限制

- 当前提供命令行构建、资料更新、人工回答待确认问题，以及只读静态展示站点。
- 两个合成样例分别覆盖风电预测评测和城市热浪统计；样例不能代表所有真实科研资料的适配情况，也不能证明生成仓库一定提升 Agent 的准确率或降低成本。
- `validate` 检查结构、引用链接、工具和接口；科研结论仍应由使用者结合原始资料复核。
- 构建和 Agent 任务会调用所配置的模型并产生费用。模型响应缓存位于生成仓库的 `.terrakernel/llm-cache/`，可用 `TK_LLM_MODE=replay` 离线重放已有请求。

开发记录、运行日志和逐次评测结果保存在本地 `artifacts/YYYYMMDD/<任务>/`，不随源码分发。协作约定见 [AGENTS.md](AGENTS.md)。

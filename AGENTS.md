# 黑客松项目协作入口

- 先读 [README.md](README.md)，在本目录内开展黑客松项目开发。
- 本项目是独立的科研资料编译工具；核心框架保持领域无关。
- 产品范围、安装和使用流程维护在 README；更新行为时同步维护相关说明。
- 当前开发优先级和完成标准以 README 的 [产品交付与下一步](README.md#产品交付与下一步) 为准；围绕外部资料接入复用现有流水线，明确区分已实现、待实现和待验收。
- 不因本项目开发修改其他项目；需要参考其他项目时按任务要求只读查看。

## 开发命令

- 安装：`uv sync`（Python 3.12，由 uv 管理）。
- 静态检查：`uv run ruff check src examples tests`。
- 离线测试（不调用模型）：`uv run pytest tests`。
- 模型端点检查：`uv run terrakernel doctor`。
- 端到端（会调用模型并产生费用，结果写入 `artifacts/YYYYMMDD/<任务>/`）：默认使用 `build <资料目录> --goal <目标> --output <生成目录>`，再核对 `validate` 与产物使用；原 `init` → `build <生成目录>` 流程继续兼容。涉及资料更新时验证 `update`；对比实验需要时再执行 `eval`，普通导入不以评测为前置。

## 约定

- **核心代码保持领域无关。** 不在 `src/terrakernel` 中写入特定领域的逻辑。领域知识只能来自资料，经抽取进入知识库。`examples/wind-forecast-eval` 只是开发样例。
- **模型输出必须由代码校验。** 包括证据引用、计划、测试用例、实现代码和链接。校验失败时，只允许修复、降级或标记，不得静默接受。
- **测试期望值只能来自资料摘录，或由独立参考解计算。** 不得由被测实现生成。
- **示例资料可复现。** `examples/*/materials` 由同目录的 `make_materials.py` 生成；标准答案由 `reference/solution.py` 生成。修改资料后需重新生成二者。

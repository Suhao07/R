# 研究代码工作区说明

这些说明适用于以 `/home/ubuntu/WorkSpace/project/SR/Code` 为根目录的研究代码工作区。

## 组合层入口

在执行跨仓任务、调整项目治理、创建 run/release，或把参考方法提升到主框架之前，先阅读
`ResearchWorkflow/AGENTS.md` 和 `ResearchWorkflow/README.md`。

组合层定义三类仓库角色：

- 主框架：`Urban-Nav-SR` 和 `ms-swift`。项目正式实现和研究实现归属这两个仓库。
- 集成控制：`SideWalkNavigation`。负责实验或系统集成协调，但不取代实现归属。
- 参考仓：`ResearchWorkflow/repos.json` 中登记的其他方法仓和数据仓，默认只读。

不能仅因为某个参考实现有用就直接修改参考仓。应先提取其设计思想，并确认 license、接口、
前提假设和目标 owner。直接修改参考仓需要用户明确要求，或已有记录完备的 promotion 决策。

## 恢复顺序

1. 阅读本文件。
2. 阅读 `ResearchWorkflow/USER.html`。
3. 阅读当前组合层 workstream 的 `SPEC.html` 和 `STATUS.html`。
4. 阅读 `ResearchWorkflow/repos.json` 和当前仓库快照。
5. 阅读目标仓自身的 `AGENTS.md`、配置和测试。
6. SideWalk 任务继续遵循 `SideWalkNavigation/AGENTS.md` 及其当前集成 workstream。
7. 在依赖已记录状态前，重新核验 Git 和产物事实。

更具体的仓库级或子目录级 `AGENTS.md` 会在其作用域内细化本规则。它们可以增加更严格的要求，
但不能在没有显式决策的情况下把参考仓变为项目自有实现目标。

## 责任边界

`Urban-Nav-SR` 负责导航 runtime、RouteServer tools/session、canonical reasoning/data
contracts、annotation 以及 benchmark/evaluation 逻辑。

`ms-swift` 负责模型数据适配、training views、loss masks、训练、checkpoint sidecars、
推理、模型评测和导出。

`SideWalkNavigation` 负责跨仓 pin、workstream evidence、smoke gates 和 release
composition，不负责复制实现代码。

参考仓提供比较方法、可复用思想和上游证据。正式采用的实现必须落入某个主框架，并记录来源和
有针对性的 compatibility test。

## 共享代码质量

Python 文档、架构和测试的共同要求见
`ResearchWorkflow/policies/python-code-quality.md`。仓库原生 formatter 和 linter
仍是机器可执行权威：

- `ms-swift/setup.cfg` 和 `ms-swift/.pre-commit-config.yaml` 定义当前 isort、
  YAPF、flake8 和文件卫生规则。
- RouteServer 的 `pyproject.toml` 当前没有仓库级 formatter 配置；应遵循本地风格及其
  子目录 `AGENTS.md` 中的文档和 benchmark 规则，不能虚构一个 formatter。

禁止对整个工作区做无关格式化。只格式化和检查当前变更范围内的文件。

## 科研证据

实现状态、验证等级和验证范围必须独立记录。重要 run 需要保存精确 commit、dirty-state
说明、数据 fingerprint、模型身份、命令、环境、产物、gates 和限制。

synthetic、mini-sample 或 optimizer smoke 证据不能表述为语义收敛、benchmark
validation 或 release。

## 实验文档

新建或实质性重写实验记录时，必须遵循
`ResearchWorkflow/policies/experiment-documentation.md`，并从
`ResearchWorkflow/templates/EXPERIMENT_RECORD.md` 创建。实验记录必须包含目的、setting、
正负结果、原因分析、用户讨论与决策记录，以及项目负责人基于证据主动提出的下一实验。提出实验
计划不等于获得昂贵运行、外部调用或数据传输授权。

## Git、数据与外部操作

- 保留所有已有 dirty worktree，尤其是参考仓。
- 禁止跨仓 broad staging。
- 实现代码提交到责任仓，组合层证据提交到 `ResearchWorkflow`。
- 组合层不得保存秘密、private token、大型数据、媒体或 checkpoint，只保存必要的路径、
  哈希、计数和来源。
- 外部数据传输、付费服务、publication、push、tag、release 和破坏性操作需要相应的明确授权。

交付前，运行目标仓的 focused checks 和
`python ResearchWorkflow/scripts/portfolio_doctor.py`，并报告精确修改仓、跳过的
gates、参考仓 dirty state 和唯一下一步。

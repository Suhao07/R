# Python 代码质量规范

本规范适用于 `Urban-Nav-SR` 和 `ms-swift` 中由项目维护的 Python 实现。当仓库本地说明或
机器可执行 formatter 配置更严格、更具体时，以仓库本地配置为准。

## 文档约定

- 所有新增或实质修改的 public class、public function 和 public method 都必须有 docstring。
- public docstring 应包含简短用途说明、参数的 `Args:`、有返回值时的 `Returns:`，以及
  meaningful exception 的 `Raises:`。
- Dataclass docstring 应在 `Args:` 下说明 constructor fields。
- private helper 的行为不直观，或承载 benchmark、schema、ranking、geometry、loss
  语义时，需要简洁 docstring。
- 核心算法、metrics、ranking rules、geometry 和 loss 计算在适用时应包含数学定义；
  可在 docstring 或相邻设计文档中使用清晰的 LaTeX-style 公式。
- 注释用于解释 invariant 和设计意图，不逐行复述代码。
- 核心合同校验、数据投影、泄漏门禁、采样和 loss 等关键区域必须写必要的中文行内注释，
  使用 `# ...` 说明“为什么必须这样做”及其 fail-closed 边界；普通赋值、显而易见的控制流和
  机械样板代码不要求逐行加注释。

## 架构约定

- 分离 schemas、IO、builders/adapters、providers/backends、runners/trainers、
  metrics/evaluators、exporters 和 CLI orchestration。
- CLI script 应保持轻量：解析参数、调用库逻辑并写入声明过的产物。
- 优先扩展稳定 interface，或使用 adapter、小型 composition layer，避免增加近似重复的
  versioned implementation。
- 版本差异通过 type、configuration 或 strategy 显式表达，不能散落为无关代码中的隐藏条件。
- 两个或以上维护中的调用点需要相同非平凡行为时，应提取 shared helper。
- 不要把 provider-specific branches、多代 feature 和通用 utilities 堆进同一个不断增长的脚本。

## 仓库原生格式规范

`ms-swift` 的机器可执行权威是：

- `setup.cfg`：isort line length 120、以 PEP8 为基础且 column limit 120 的 YAPF，
  以及 max line length 120 和仓库指定 select/ignore 规则的 flake8。
- `.pre-commit-config.yaml`：flake8、isort、YAPF、trailing whitespace、YAML、
  end-of-file、requirements、double-quote、merge-conflict 和 LF 检查。

不要重排无关的 ms-swift 文件。可行时只对当前变更文件运行 hooks。

RouteServer 当前的 `pyproject.toml` 定义 packaging 和 dependencies，但没有
formatter/linter policy。在仓库正式引入 formatter 前，应匹配本地文件风格并执行上述文档和
架构约定；不能声称已经配置 Black、Ruff 或其他 formatter。

## 测试与验证

- 根据变更内容，为 schema parsing、IO roundtrip、mask、adapter、metric、save/load
  和 edge case 增加 focused tests。
- 先运行最窄的相关测试，再运行已记录的 regression gate。
- 使用 run manifest 中记录的仓库专属 interpreter 或 environment。
- 因 interpreter 选择错误导致的 collection failure 属于环境诊断，不能当作代码通过或失败。
- 准确标注 fixture、mini sample、review subset、full split 和 frozen benchmark。

## 修改纪律

- 每次修改保持在一个责任域内。
- 保留无关的 dirty-worktree 变更。
- 避免 broad refactor 和 workspace-wide formatting。
- 脚本已经混入无关工具或多个 feature version 时，应先拆分再继续扩展。
- 交付时报告精确通过、失败和跳过的检查。

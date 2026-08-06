# 参考仓规范

角色为 `reference_*` 的仓库默认只读。

无需 promotion 即可执行：

- 检查 code、documentation、license、config 和 tests；
- 执行非写入诊断或本地 comparison smoke；
- 在记录来源的前提下引用 design、interface 或 algorithm；
- 在项目自有主框架中实现适配后的版本。

默认不允许：

- 修复、格式化或重构 reference worktree；
- 把项目专属行为提交到参考仓；
- 把参考仓 branch、metrics 或 schemas 当作项目自有 release contract；
- 未检查 license 和 attribution obligations 就静默复制代码。

正式采用前，创建 promotion record，记录 source repository 和 commit、license、
选中的 concept/files、assumptions、target owner、adaptation plan、tests 和
maintenance boundary。runtime/contracts/evaluation 默认进入 `Urban-Nav-SR`；
training/inference/export 默认进入 `ms-swift`。

参考仓已有 dirty state 必须保留并以 warning 报告。除非某个 run 或 release 明确依赖该
reference worktree 的精确状态，否则它不会自动成为主框架 release blocker。

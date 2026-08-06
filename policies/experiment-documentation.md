# 实验文档规范

本规范适用于 `Urban-Nav-SR`、`ms-swift` 和 `SideWalkNavigation` 中自 2026-08-04 起新建或
实质性重写的实验记录。历史文档不要求一次性机械迁移；再次作为活跃实验依据时，应按本规范补齐。

## 权威模板

实验文档必须从以下模板创建：

```text
ResearchWorkflow/templates/EXPERIMENT_RECORD.md
```

责任仓仍拥有实验文档：训练和模型评测通常进入 `ms-swift/docs/Experiments`，canonical 数据、
annotation 和 benchmark 实验通常进入 `Urban-Nav-SR/Agent_part/RouteServer/docs`；跨仓组合证据
进入对应 integration workstream。组合层不复制大型日志、数据或 checkpoint。

## 必需章节

每份实验文档必须保留以下章节名和顺序：

```text
实验的目的
实验的 setting
记录实验结果
分析实验结果，可能的原因
用户讨论与决策记录
接下来要做的实验
```

允许在这些章节内部增加子章节，但不能用自定义标题替代其职责。

## 内容要求

### 实验的目的

- 说明工程目标、研究目标和非目标；
- 给出可证伪假设和预期证据；
- 不得以“跑一下看看”代替研究问题。

### 实验的 setting

- 记录精确代码 commit、dirty-state、数据 fingerprint、模型、环境、命令和 seed；
- 说明数据 split、采样、标签来源、模态和已知限制；
- 明确相对 baseline 的算法变化、对照组和不变量；
- 记录 checkpoint 选择规则，禁止使用 test 选择模型后再把它称为正式 test。

### 可视化与导出计划

每个新建的 GPU 训练、生成或正式评测在写入 `started` receipt 前，必须定义可恢复的
`visualization_root`，且位于该 run 的持久 artifact root 内。计划不是“训练结束后再画图”的
占位说明；它必须说明运行中如何观察、运行后如何导出，以及谁可以从本机安全访问。

- 训练必须写入 run 专属的 TensorBoard event log，不能把不同 run 混入同一个 logdir；计划中要列出
  TensorBoard logdir、loopback dashboard 端口、受信 SSH 转发方式、刷新频率和日志保留位置。
- 训练 dashboard 至少包含总 loss、各任务/section loss、active-token 或 sample denominator、learning
  rate、gradient norm、token accuracy、throughput、显存和 GPU 利用率；有 validation 时同时记录
  validation 指标和 checkpoint 对应关系。
- 评测必须导出 machine-readable scorecard、分层 CSV/JSON、混淆或误差图、coverage/parse/reject
  统计和可定位的 prediction 证据。含图像、轨迹、BEV 或 reasoning 的评测还必须给出抽样 review HTML
  或等价的可视化 bundle，能够从 sample ID 回到输入与预测。
- 每个 plan 明确 `visualization_manifest`、曲线/图表、review、原始日志和最终导出文件的精确路径。
  某一项确实不适用时，必须写 `N/A` 及原因，不能静默省略。
- dashboard 默认只监听服务器 loopback；跨跳板访问必须使用本地 SSH 转发，不得为了查看曲线开放
  公网端口或把私有媒体暴露到外部服务。

### 记录实验结果

- 同时记录效果好和效果不好的结果；
- 保留 denominator、support、主指标、分层指标、运行效率和可视化路径；
- 失败、取消、格式错误、异常峰值和无显著差异都属于结果；
- smoke、review subset 和 full split 的验证范围必须分开表述。

### 分析实验结果，可能的原因

- 对每个假设给出 `supported / contradicted / inconclusive`；
- 区分证据支持的原因、未验证假设和已排除原因；
- 不从 tokenizer、loss、单个样本或 plumbing smoke 推断语义收敛；
- 发现结果不符合预期时，必须提出可区分不同原因的后续实验。

### 用户讨论与决策记录

- 记录用户对目标、setting、结果解释、风险、优先级和下一步的讨论摘要；
- 记录采用、拒绝、待定及其对实验的影响；
- 讨论记录按时间追加，决定被替代时保留历史并引用新决定；
- 不记录 credential、private token、原始私密聊天或大型附件；
- 用户的讨论不自动等于外部传输、付费调用或昂贵 batch 的执行授权。

### 接下来要做的实验

- 项目负责人必须主动列出基于当前证据的下一实验，不得只写“等待 instructions”；
- 每项包含假设、唯一主要变量、所需证据、通过/停止条件、依赖和授权状态；
- 优先安排能排除根因或改变决策的实验，不按模型/数据规模机械扩张；
- 未获授权的昂贵运行、外部调用和数据传输只能列为 proposed，不能直接启动。

## 更新时机

实验文档至少在以下时点更新：

1. 启动前：目的、setting、run identity、通过和停止条件；
2. 重要讨论或 setting 变化后：追加讨论与决定；
3. 首个可恢复 checkpoint 或异常出现后：记录中间结果；
4. 运行结束后：记录正负结果、分析和下一实验；
5. 发布结论前：核验 evidence path、validation scope 和已知限制。

可视化计划在启动前必须完成；第一次 event/预测产生后必须记录实际入口和文件路径；运行结束后必须
补齐图表、review、可下载 scorecard 及其完整性结果。

## 可执行绑定

章节结构校验本身不能阻止“先跑昂贵 GPU 任务、事后补写结果”。对于新建的训练、生成或正式评测
runner，必须把记录绑定变为可执行门禁：

1. 启动前，runner 必须要求 `EXPERIMENT_RECORD`，并调用
   `ResearchWorkflow/scripts/experiment_run_receipt.py --phase started`；该命令会先验证记录结构，再
   对冻结输入和 runner 命令写入 SHA256 receipt。新 runner 还必须在持久
   `visualization_root` 生成 `visualization_manifest.json`，并将其作为 started receipt artifact；没有
   可视化计划或 manifest 的正式训练/评测不得启动。
2. 正常结束后，runner 必须调用同一工具的 `--phase finished`，对 scorecard、预测、manifest 等
   最终产物写入第二份 receipt；finished receipt 必须同时绑定可导出的 visual index、图表或 review
   bundle 以及最终 metrics。
3. 组合层 `runs/<run_id>.json` 必须通过 `experiment_record` 链接该 Markdown 记录；
   `portfolio_validate.py` 会验证该链接指向的记录。没有记录、记录有占位符或必需章节缺失时，
   新式 run manifest 不通过。
4. 历史运行可以如实补建 finished 结果记录，但不得伪造 start receipt 或假装它在运行前已通过门禁。

该绑定只保证“输入、输出和文档能追溯到同一实验身份”，不替代数据泄漏审计、语义评测、人工检阅或
研究结论判断。

## 校验

结构校验命令：

```bash
python ResearchWorkflow/scripts/validate_experiment_record.py path/to/experiment.md
python ResearchWorkflow/scripts/experiment_run_receipt.py --help
```

校验器只验证版本标记、必需章节、顺序和占位内容；它不能验证实验结论真实性。正式交付仍需运行
责任仓 focused checks 和 `ResearchWorkflow/scripts/portfolio_doctor.py`。

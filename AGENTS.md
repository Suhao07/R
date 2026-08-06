# ResearchWorkflow 组合层说明

本项目是研究代码工作区的治理、恢复和证据控制面，不包含模型、benchmark 或 runtime 实现。

## 恢复顺序

1. 阅读 `USER.html`。
2. 阅读 `workstreams/core-framework/SPEC.html` 和 `STATUS.html`。
3. 阅读 `repos.json`、`policies/policy-matrix.json` 和
   `snapshots/repo_snapshot_current.json`。
4. 任务属于 `SideWalkNavigation` 时，继续进入其链接的集成工作流。
5. 只有相关组合层决策需要历史依据时才阅读 `MEMORY.html`；只有角色或证据术语含义不清时
   才阅读 `CONTEXT.html`。

## 组合层权威

- `repos.json` 负责仓库角色、mutation policy 和责任归属。
- `policies/` 负责共享工程要求和证据要求。
- 仓库本地 `AGENTS.md` 和 formatter 配置负责更严格的仓内规则。
- Workstream HTML 负责可恢复计划和当前状态。
- Snapshot、run、claim 和 release manifests 负责易变化证据。
- 参考仓保持只读，除非 promotion 记录明确改变其角色。

禁止把实现代码复制到本项目。本项目只保存 policies、manifests、小型 validators、
snapshots 和外部产物链接。

## 修改规则

- 改变角色时，必须同时修改 `repos.json`、`policy-matrix.json`、当前 workstream
  status 和一条 decision entry。
- 修改共享 policy 时，必须保留仓库原生的机器可执行配置，或者明确记录迁移过程。
- Snapshot 必须机械生成，禁止手工修改 commit 或 dirty-state 字段。
- 秘密和大型产物必须保存在本仓之外。
- 未经用户相应要求，不执行 commit、push、tag 或 release。

## 实验记录

- 新建或实质性重写实验文档时，遵循 `policies/experiment-documentation.md`，并从
  `templates/EXPERIMENT_RECORD.md` 创建。
- 实验文档必须记录目的、setting、正负结果、原因分析、用户讨论与决策，以及负责人主动提出的
  下一步实验。
- 每次训练、生成或正式评测在启动 receipt 前必须写入 run 专属 `visualization_manifest.json`；训练
  需要 TensorBoard 与恢复证据，评测需要 scorecard、分层图表和可定位 review。结束 receipt 必须绑定
  `visualization_index.json`，服务只能通过 loopback 和受信 SSH 本地转发查看。
- 讨论记录保存影响实验的摘要、决定和未解决项，不复制 credential、私密原始聊天或大型附件。
- 主动提出下一实验不等于自动获得昂贵运行、外部调用或数据传输授权；这些操作继续遵循授权门禁。

## 验证

运行：

```bash
python scripts/portfolio_snapshot.py
python scripts/portfolio_validate.py
python scripts/portfolio_doctor.py
```

Doctor 成功表示控制面和保存的 snapshot 与 live state 一致；它仍可能报告 release
blockers 或被保留的 dirty 参考仓。

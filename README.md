# ResearchWorkflow

`ResearchWorkflow` 是 `/home/ubuntu/WorkSpace/project/SR/Code` 的项目组合层。

## 责任模型

- `Urban-Nav-SR`：主要 navigation、agent/runtime、canonical contracts、annotation
  和 benchmark 框架。
- `ms-swift`：主要训练、推理、checkpoint 和 export 框架。
- `SideWalkNavigation`：集成控制面，也是第一个完成验证的工作流试点。
- 其余登记仓：参考方法或参考数据集，默认只读。

组合层负责工作路由和证据记录，不合并各仓 source tree。

## 使用入口

1. 阅读 `../AGENTS.md` 和 `AGENTS.md`。
2. 打开 `workstreams/core-framework/STATUS.html`。
3. 检查 `repos.json` 和 `snapshots/repo_snapshot_current.json`。
4. 阅读适用的 policy 和仓库本地 `AGENTS.md`。

## 目录职责

- `workstreams/`：稳定计划和当前恢复状态。
- `policies/`：共享 policy，以及仓库专属机器配置的权威来源。
- `templates/v3/` 和 `schemas/`：canonical recovery document contract。
- `templates/EXPERIMENT_RECORD.md`：跨主框架统一实验记录模板。
- `runs/`、`claims/`、`releases/`：结构化证据和 release gates。
- `snapshots/`：机械生成的 live repository state。
- `integrations/`：项目专属工作流链接。
- `evidence/`：小型验证记录和迁移记录。
- `workspace/AGENTS.md`：工作区根路由文件的可版本化镜像。
- `policies/experiment-documentation.md`：实验目的、setting、正负结果、讨论和下一实验的强制规则。

实验文档结构检查：

```bash
python scripts/validate_experiment_record.py path/to/experiment.md
```

对于新建 GPU 训练、生成或正式评测，runner 还应写入 lifecycle receipt：

```bash
python scripts/experiment_run_receipt.py --help
```

它会在启动和结束两个阶段绑定实验记录 SHA256 与实际输入/输出 artifact hash；详情见
`policies/experiment-documentation.md`。

每个新建的训练、生成或正式评测还必须在启动前建立 run 专属 `visualization_root` 与
`visualization_manifest.json`：训练交付 TensorBoard 和恢复证据，评测交付 scorecard、分层图表与可定位
review。服务只能监听 loopback，并通过受信 SSH 本地转发访问。

## 常用命令

```bash
python scripts/portfolio_snapshot.py
python scripts/portfolio_validate.py
python scripts/portfolio_doctor.py
```

Doctor 会区分结构或 snapshot 失败、主框架 release blockers，以及参考仓中需要保留的
dirty state。

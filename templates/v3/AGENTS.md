# 工作流恢复协议 v3

本文件适用于一个已经实例化的研究 workstream。使用本协议前，组合层或集成层
`AGENTS.md` 必须先把任务路由到目标 workstream。

## 恢复顺序

1. 完整阅读本文件。
2. 阅读 `SPEC.html`、`STATUS.html` 和共享 `USER.html`。
3. 修改责任仓代码前，阅读 `workflow/repos.json` 和 active run manifest。
4. 只有当前决策依赖历史时才阅读 `MEMORY.html`。
5. 只有项目术语或路径含义不清时才阅读 `CONTEXT.html`。
6. 已记录状态可能漂移时，重新核验当前 Git、filesystem、artifact 和 service facts。

不要通过读取所有历史文件恢复任务。应沿 active status 和 manifests 中的显式 evidence
link 定向读取。

## 字段归属

- `SPEC.html` 负责稳定 mission、scope、success criteria、phase boundaries、
  persistent constraints 和 non-goals。
- `STATUS.html` 负责当前 execution state、current goal、blockers、evidence links
  和唯一的 `next-atomic-step`。
- `USER.html` 负责长期 collaboration、authorization、privacy、editing 和
  verification preferences。
- `workflow/repos.json` 负责 repository responsibilities 和 integration pins。
- Dataset manifests 负责 sample identity、provenance、count 和 fingerprint。
- 运行 manifests 负责单次执行的精确 commits、dirty-state 说明、model identity、
  command、environment、artifacts、gates 和 limitations。
- Claim manifests 负责由一个或多个 run 支持的边界明确的 statement。
- Release manifests 负责 release-required gates 和不可变 component pins。
- `MEMORY.html` 负责长期决策；superseded decision 应作为历史保留，不能静默删除。
- `CONTEXT.html` 只负责项目本地术语。

字段冲突时，先信任负责该字段的文档，再现场核验易漂移事实。应记录修正，不能静默依赖 stale
value。

## 证据模型

以下维度必须始终独立：

- implementation state：proposed、partial、implemented 或 superseded；
- verification level：从 unverified 到 released；
- validation scope：fixture、mini sample、review subset、full split、frozen
  benchmark 或 production runtime。

Tokenizer、forward、optimizer 或 generation smoke 只能证明其记录范围内的 mechanics，
不能证明 semantic convergence、benchmark improvement、runtime integration 或
release readiness。只有所有 required gate 通过，且每个引用 component 都 pin 到精确测试
状态时，release 才能标记为 `released`。

使用精确证据用语：

- `implemented` 表示 code 或 artifacts 已存在；
- `passed` 表示具名 command 或 gate 已通过；
- `supported` 表示边界明确的 claim 已链接 evidence；
- `released` 表示 release manifest 没有失败的 required gate，且已实际执行获得授权的
  release 操作。

## 工作与更新纪律

- 只读分析不修改 recovery state。
- 在可持久恢复 checkpoint，以及长时间、昂贵、破坏性、privileged 或 external 操作前后，
  立即更新 status。
- 昂贵 run 前创建 run manifest；结束后根据实际 artifacts 完成记录，不能使用计划值冒充。
- Recovery document 只保存 summary 和 evidence path，不保存大型 raw log、checkpoint、
  dataset 或生成媒体。
- 禁止保存 credential、access token、private endpoint 或 raw secret。
- 保留无关用户变更；dirty worktree 中避免 broad staging。
- Generated snapshot 必须机械生成且可复现。
- 显式记录失败或跳过的 gate，不能为了让 workflow 看起来完成而删除它。

## 授权门禁

向外部服务发送 private/local data、publish、push、tag、release、删除重要 artifact，
或启动任务未授权的昂贵 batch 前，必须获得明确授权。授权范围记录在相关 run 或 release
manifest 中。

新 annotation 或 training batch 扩大规模前，优先提供 human-reviewable mini sample、
实测 latency/cost 和 durable artifact root。

## HTML 与 Manifest 约定

- 所有 recovery HTML 必须声明 `data-schema-version="3"`。
- Canonical template 使用 `data-template-status="canonical"` 和
  `instance-status=canonical-template`。
- 实例化文档使用 `data-template-status="active"` 和
  `instance-status=active-instance`。
- 每个 required field 精确出现一次，并包含一个稳定的 `data-value="true"` slot 和准确的
  `data-empty` 值。
- 不能只用视觉样式编码 operational truth；validator 必须能从结构中读取。
- Structured manifest 必须使用 stable ID、精确 40-character Git commit、可复现所需的
  absolute artifact path 和显式 gate boolean。

## 完成条件

交付前：

1. 运行 workflow validator 和 doctor。
2. 验证每个 required artifact 和 evidence reference。
3. 重新生成 repository snapshot，并检查 drift/pin mismatch。
4. 按已记录 validation scope 运行相关 repository checks。
5. 记录失败、跳过或未获授权的 gates。
6. 保留且只保留一个有意义的 `next-atomic-step`。
7. 报告 changed repositories、tests、artifacts、limitations、dirty state，以及是否执行
   commit、tag、push、external transfer 或 release。

# UrbanNav 基准与评测规范

本规范适用于 UrbanNav dataset、benchmark 和 evaluator 代码，不自动施加到参考 benchmark。

## 确定性与职责分离

- 分离 schema、IO、metrics、runner、exporter 和 CLI 职责。
- 正式 evaluation 必须 offline 且 deterministic。
- 正式 evaluator 不调用 live map、LLM 或可变的外部服务。
- 使用 frozen cache、replay data 和 stable ID 保证可复现。
- 优先用 stable ID 匹配 prediction 和 ground truth；坐标匹配是显式 fallback tolerance，
  不是 metric。
- tool-call trace 保持 diagnostic，除非 frozen protocol 明确提升为 tool-quality metric。
- primary metrics 保持精简；其他数值先作为 debug 或 slice analysis，除非被明确提升。

## 指令到目的地再到路线

- 在数据提供时保留 `acceptable_destinations`、`ranked_destinations`、
  `optimality_scope` 和 `cache_keys`。
- prediction 匹配非 rank-1 acceptable destination 时，route metrics 必须使用该
  matched destination 的 reference route 和 distance。
- 禁止把另一个 acceptable target 的 route 与 rank-1 route ground truth 比较。
- 已确立的 single-target metrics 是 `destination_success`、`hit@5`、
  `route_success`、`median_route_ratio` 和 `spl`。
- coordinate-radius 参数是 fallback matching tolerance，不是 metric 名称。

## 必需的专项测试

新增或修改行为时，应覆盖相关 schema parsing、IO roundtrip、destination matching、
route success、SPL 和 edge case。只要 matched destination 会改变 route metrics，
就必须包含非 rank-1 acceptable-destination 测试。

Frozen benchmark claim 必须引用精确 package、split、denominator、evaluator commit
和 artifact root。计划配额和旧 benchmark 结果表不能作为新版 frozen package 的证据。

# 科研证据与发布规范

每个重要实验或跨仓 release 都必须记录：

- 精确 repository commits 和相关 dirty-state 说明；
- dataset identity、row count、split、provenance 和 fingerprint；
- model identity、base checkpoint 和 adapter/bundle identity；
- 精确 command、working directory、environment/container 和 seed；
- artifact root、required files、metrics、gates 和 known limitations；
- external-service 和 private-data-transfer 状态。

Implementation、verification 和 validation scope 是三个独立维度。一个 run 可以在
mechanical 层通过，同时 semantic gate 或 release gate 失败。

Release 需要：

1. 所有 required gate 通过；
2. component 使用精确且 clean 的 commits；
3. 被引用的 evidence 和 artifacts 存在；
4. canonical contract、training consumer 和 runtime consumer 之间兼容；
5. 已实际执行获得授权的 release 操作。

不能仅因为生成了文件就把 candidate 标记为 `released`。不能从 tokenizer、forward、
optimizer 或 generation plumbing 推断语义收敛，也不能从 mini sample 推断
benchmark improvement。

外部数据传输、paid annotation、push、tag、publication 和破坏性 artifact deletion
需要明确授权。Secrets 和大型 raw artifacts 不得进入 workflow manifests。

# 实验记录：{{实验名称}}

experiment_record_version: 1

> 使用说明：复制本模板到责任仓的实验文档目录，删除所有占位提示后再开始正式运行。实验过程中
> 持续更新，不要只在实验成功后补写。验证命令：
> `python ResearchWorkflow/scripts/validate_experiment_record.py <文档路径>`。

## 实验元数据

| 字段 | 记录 |
| --- | --- |
| 实验 ID | `{{稳定且唯一的 experiment_id}}` |
| 状态 | `planned / running / passed / failed / blocked / cancelled` |
| 负责人 | `{{owner}}` |
| 开始/结束时间 | `{{ISO-8601}}` |
| 代码版本 | `{{repo + commit + dirty-state}}` |
| 数据版本 | `{{manifest path + row count + split + fingerprint}}` |
| 模型版本 | `{{base/checkpoint/adapter + digest}}` |
| 环境 | `{{host/container/env/CUDA/framework}}` |
| 运行入口 | `{{command or durable script path}}` |
| 产物根目录 | `{{absolute artifact root}}` |
| 可视化与导出 | `{{visualization_root + manifest + local-access plan}}` |
| 验证范围 | `fixture / mini-sample / review-subset / full-split / frozen-benchmark` |

## 实验的目的

描述为什么做这个实验、需要验证的研究问题、可证伪假设和预期获得的证据。区分：

- 工程目标：验证代码、数据或训练链路是否可运行；
- 研究目标：验证方法或数据变化是否改善具名指标；
- 非目标：本实验不能回答的问题。

## 实验的 setting

### 数据

记录数据来源、样本数、split、采样分布、过滤规则、标签来源、模态、fingerprint 和已知限制。

### 算法和改动

记录相对 baseline 的唯一变量、模型结构、loss、采样、prompt、推理配置和兼容性改动。

### 训练与评测配置

记录 seed、batch、学习率、epoch/step、硬件、精度、checkpoint 选择方式、主指标、分层指标和
停止条件。若不是冻结 benchmark，必须明确证据等级。

### 对照组与不变量

说明 baseline、control、保持不变的配置，以及如何排除 parser、数据泄漏或 checkpoint 选择偏差。

### 可视化与导出计划

在启动前填写下表。训练必须使用 run 专属 TensorBoard event log；评测必须提供可导出的 scorecard、
分层图表和可定位的 review。所有入口仅允许服务器 loopback 加受信 SSH 本地转发，不能公开暴露。

| 类型 | 必需内容 | 持久路径/本地入口 | 更新频率与完整性门禁 |
| --- | --- | --- | --- |
| 训练曲线 | `loss`、分组 loss、token 分母、LR、grad norm、吞吐、显存/GPU、validation/checkpoint | `{{TensorBoard logdir + loopback port + tunnel command}}` | `{{logging/eval cadence + event freshness check}}` |
| 评测指标 | scorecard、分层 metrics、coverage/parse/reject、混淆或误差图 | `{{JSON/CSV/plot root}}` | `{{per shard/per slice/final export}}` |
| 定性检阅 | FPV/BEV/trajectory/reasoning 或失败案例 HTML | `{{review root + index}}` | `{{sampling policy + asset path validation}}` |
| 可视化清单 | `visualization_manifest.json`、日志与导出索引 | `{{visualization_root}}` | `{{started/finished receipt artifact}}` |

## 记录实验结果

### 量化结果

记录完整 denominator、主指标、置信区间或方差、分层结果和运行效率。不能只记录最好结果。

| 实验臂/切片 | 样本数 | 主指标 | 辅助指标 | 状态 |
| --- | ---: | ---: | ---: | --- |
| `{{arm}}` | `{{N}}` | `{{value}}` | `{{value}}` | `{{passed/failed/inconclusive}}` |

### 效果好的结果

记录符合预期的结果、对应证据和可复现产物。

### 效果不好的结果

记录失败、退化、异常峰值、格式错误、人工校阅问题和负结果。禁止删除失败臂或只保留成功数字。

### 可视化与产物

必须写明实际产生的 TensorBoard、HTML review、图表、日志、checkpoint、prediction 和 evaluator
报告路径，并记录没有产生的项及原因。不要只写“见 run root”。

| 类型 | 实际路径/入口 | 导出内容 | 验证结果 |
| --- | --- | --- | --- |
| TensorBoard / 运行中曲线 | `{{path or N/A with reason}}` | `{{tags}}` | `{{event/HTTP/tunnel check}}` |
| 量化图表与 scorecard | `{{path}}` | `{{JSON/CSV/PDF/PNG}}` | `{{row count/hash/check}}` |
| 定性 review | `{{path}}` | `{{HTML/assets}}` | `{{sample/media validation}}` |
| 原始日志与 checkpoint | `{{path}}` | `{{log/checkpoint/sidecar}}` | `{{resume/load audit}}` |

## 分析实验结果，可能的原因

### 是否符合预期

对照实验目的逐项判断 `supported / contradicted / inconclusive`，不得用训练 loss 代替任务指标。

### 已有证据支持的原因

只写被日志、切片、消融、人工校阅或独立审计支持的原因。

### 尚未验证的假设

列出可能原因、反证条件和需要的下一项实验。假设不能写成已确认事实。

### 已排除的原因

记录已经通过对照或审计排除的问题，避免后续重复调查。

## 用户讨论与决策记录

只记录与实验设计、解释或下一步有关的讨论摘要，不复制密钥、私有 endpoint、原始聊天或无关内容。
该表按时间追加；改变既有决定时新增一行并引用被替代决定，禁止静默覆写历史。

| 时间 | 用户讨论/关注点 | 最终决定 | 对实验的影响 | 未解决问题 |
| --- | --- | --- | --- | --- |
| `{{ISO-8601}}` | `{{忠实概括用户观点}}` | `{{采用/拒绝/待定}}` | `{{setting/analysis/queue change}}` | `{{none or question}}` |

## 接下来要做的实验

项目负责人必须基于当前证据主动提出下一轮，而不是只写“等待指令”。每项实验应改变一个主要变量，
给出预期证据和停止条件。列出实验不等于获得昂贵运行、外部调用或数据传输授权。

| 优先级 | 下一实验 | 假设 | 唯一主要变量 | 所需证据 | 通过/停止条件 | 依赖或授权 |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | `{{experiment}}` | `{{falsifiable hypothesis}}` | `{{one primary variable}}` | `{{metrics/review}}` | `{{gate}}` | `{{dependency/approval}}` |

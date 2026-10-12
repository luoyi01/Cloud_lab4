# 分类截图与证据索引

报告第 4.5 节新增 25 张操作截图（图 4–28），捕获本机实时命令执行界面：`scripts/live_validation.py` 在 WSL2 执行固定命令，浏览器显示真实 stdout/stderr、命令和 UTC 时间。页面不是模拟终端。完整日志、请求 CSV 与截图映射保存在 `results/screenshot-validation/`；原实验数据保持不变。图 25 的热启动材料明确为读取原始记录的复核，不作为补拍日的新测量。

每张新图均有验证项编号、图题、必要说明和北京时间。V01–V10 覆盖基础验证，B01 为 StatefulSet/PVC/PDB，B02 为 API worker 故障。

| 图号 | 验证项 | 操作截图 | 命令和输出 | 图题 |
| --- | --- | --- | --- | --- |
| 图 4 | V01 | [查看](08-live-validation/01-env.png) | [原始日志](../results/screenshot-validation/01-env.txt) | 环境和工具实际版本 |
| 图 5 | V02 | [查看](08-live-validation/02-build.png) | [原始日志](../results/screenshot-validation/02-build.txt) | 独立构建并运行 Dockerfile 镜像 |
| 图 6 | V03 | [查看](08-live-validation/03-compose-config.png) | [原始日志](../results/screenshot-validation/03-compose-config.txt) | 端口 环境变量 命名卷和内部发现 |
| 图 7 | V04 V09 | [查看](08-live-validation/04-compose-before.png) | [原始日志](../results/screenshot-validation/04-compose-before.txt) | Compose 原始部署与共享业务验证 |
| 图 8 | V05 | [查看](08-live-validation/05-k8s-resources.png) | [原始日志](../results/screenshot-validation/05-k8s-resources.txt) | 三节点集群和应用资源就绪 |
| 图 9 | V06 | [查看](08-live-validation/06-k8s-config.png) | [原始日志](../results/screenshot-validation/06-k8s-config.txt) | ConfigMap 和 Secret 引用及运行时注入 |
| 图 10 | V07 | [查看](08-live-validation/07-heal-before.png) | [原始日志](../results/screenshot-validation/07-heal-before.txt) | 原始 3 副本和连续业务请求 |
| 图 11 | V07 | [查看](08-live-validation/08-heal-inject.png) | [原始日志](../results/screenshot-validation/08-heal-inject.txt) | 手动删除和替代 Pod 创建过程 |
| 图 12 | V07 | [查看](08-live-validation/09-heal-after.png) | [原始日志](../results/screenshot-validation/09-heal-after.txt) | 恢复到 3 副本和请求连续性 |
| 图 13 | V08 | [查看](08-live-validation/10-scale-one.png) | [原始日志](../results/screenshot-validation/10-scale-one.txt) | 伸缩起点 1 副本与资源用量 |
| 图 14 | V08 | [查看](08-live-validation/11-scale-three.png) | [原始日志](../results/screenshot-validation/11-scale-three.txt) | 扩容到 3 副本与资源用量 |
| 图 15 | V08 | [查看](08-live-validation/12-scale-five.png) | [原始日志](../results/screenshot-validation/12-scale-five.txt) | 扩容到 5 副本与资源用量 |
| 图 16 | V08 | [查看](08-live-validation/13-scale-back.png) | [原始日志](../results/screenshot-validation/13-scale-back.txt) | 缩回 3 副本与资源用量 |
| 图 17 | V03 V10 B01 | [查看](08-live-validation/14-persist-before.png) | [原始日志](../results/screenshot-validation/14-persist-before.txt) | 重启前写入标记和确认存储 |
| 图 18 | V10 B01 | [查看](08-live-validation/15-persist-inject.png) | [原始日志](../results/screenshot-validation/15-persist-inject.txt) | Redis 容器重启与 StatefulSet Pod 重建 |
| 图 19 | V03 V10 B01 | [查看](08-live-validation/16-persist-after.png) | [原始日志](../results/screenshot-validation/16-persist-after.txt) | 恢复后读回原记录并确认 PVC |
| 图 20 | V09 | [查看](08-live-validation/17-compose-inject.png) | [原始日志](../results/screenshot-validation/17-compose-inject.txt) | 删除容器后 15 秒仍为 2 副本 |
| 图 21 | V09 | [查看](08-live-validation/18-compose-after.png) | [原始日志](../results/screenshot-validation/18-compose-after.txt) | 显式执行 Compose 恢复 3 副本 |
| 图 22 | B01 | [查看](08-live-validation/19-pdb-before.png) | [原始日志](../results/screenshot-validation/19-pdb-before.txt) | 3 副本时的可驱逐预算 |
| 图 23 | B01 | [查看](08-live-validation/20-pdb-inject.png) | [原始日志](../results/screenshot-validation/20-pdb-inject.txt) | 2 副本时拒绝 Eviction |
| 图 24 | B01 | [查看](08-live-validation/21-pdb-after.png) | [原始日志](../results/screenshot-validation/21-pdb-after.txt) | 恢复 3 副本和预算 |
| 图 25 | V09 | [查看](08-live-validation/22-comparison.png) | [原始日志](../results/screenshot-validation/22-comparison.txt) | 两条路径各五次热启动原始记录 |
| 图 26 | B02 | [查看](08-live-validation/23-node-before.png) | [原始日志](../results/screenshot-validation/23-node-before.txt) | 故障前节点与 Pod 分布 |
| 图 27 | B02 | [查看](08-live-validation/24-node-inject.png) | [原始日志](../results/screenshot-validation/24-node-inject.txt) | 停止 worker 并观察 NotReady |
| 图 28 | B02 | [查看](08-live-validation/25-node-after.png) | [原始日志](../results/screenshot-validation/25-node-after.txt) | 存活节点重新调度和故障节点恢复 |

## 前、中、后对照组

| 验证内容 | 原始部署 / 操作前 | 故障或操作过程 | 恢复后 |
| --- | --- | --- | --- |
| V07 Pod 自愈 | 图 10 | 图 11 | 图 12 |
| V10/B01 持久化 | 图 17 | 图 18 | 图 19：新 UID、Ready、记录相等 |
| V09 Compose 删除 | 图 7 | 图 20 | 图 21：显式 up 补回 |
| B01 PDB | 图 22 | 图 23：预算零、Eviction 拒绝 | 图 24 |
| B02 API worker | 图 26 | 图 27：NotReady | 图 28：存活节点调度、故障节点重启 |

V08 扩缩容按图 13–16 展示两条路径的 1→3→5→3 和全部当前 API 的 CPU/内存。持久化恢复先确认 Redis 新 UID、非删除状态与 Ready，扩容先等待全部 Ready API 有 metrics，再截图。PDB 仅保护自愿驱逐，单机 Kind 和单实例 Redis 的限制见报告。

## 原应用截图与统计复核视图

下表保留原材料：应用截图来自实际页面；其他图为 `scripts/evidence.py` 从原 JSON/CSV/命令输出生成的“原始记录核对视图”，不当作现场操作截图。报告图 2/3 是应用页面，图 30/31 是原结果复核；架构与资源分析图在 `docs/figures/`。

| 分类 / 截图 | 已执行操作或命令 | 对应原始材料与含义 |
| --- | --- | --- |
| `01-compose/message-board.png` | `bash scripts/lab.sh compose-up`，浏览器发布留言 | localhost:8090 实际应用、操作反馈、容器身份与共享留言 |
| `02-k8s/message-board.png` | `bash scripts/lab.sh k8s-up`，浏览器发布留言 | localhost:8080 实际应用；下方显示 Pod 与节点身份 |
| `02-k8s/resources.png` | `python3 scripts/experiments.py capture` | `results/deployment/nodes.txt`、`workloads.txt`；三节点 Ready、API 3/3、Redis/Web Ready |
| `02-k8s/storage-pdb.png` | 同上，页面下半部分 | PVC Bound、NodePort、PDB 预算及 Pod 分布 |
| `03-self-heal/evidence.png` | `python3 scripts/experiments.py self-heal` | `results/self-heal/event.json`、`requests.csv`；旧新 UID、恢复时间及业务请求 |
| `04-scale/evidence.png` | `python3 scripts/experiments.py scale` | `results/scale/`、`summary.json`；1→3→5→3 的八组实测用量 |
| `04-scale/dataset.png` | 同上，页面下半部分 | 两条路径各 100 条留言，数据 SHA-256 相等 |
| `05-persistence/evidence.png` | `python3 scripts/experiments.py persistence` | `results/persistence/`；优雅重启后的标记读回一致 |
| `06-comparison/warm-start.png` | `python3 scripts/experiments.py warm-start` | `results/comparison/warm-start.json`；每条路径五轮热启动 |
| `06-comparison/compose-delete.png` | `python3 scripts/experiments.py compose-delete` | `results/compose-delete/event.json`；删除后 15 秒仍为两副本 |
| `07-bonus/pdb.png` | `python3 scripts/experiments.py pdb` | `results/pdb/eviction.json`；预算零、驱逐拒绝、原 Pod 仍 Ready |
| `07-bonus/node-failure.png` | `python3 scripts/experiments.py node-failure` | `results/node-failure/`；停止 API worker 后的重新调度与真实请求失败 |

`figure-manifest.json` 记录每张补图的验证项、图号、描述、UTC、日志路径和 PNG SHA-256，可核对 Word 内嵌图片与仓库原图。失败尝试另存，未选作报告验证证据，说明见 `results/screenshot-validation/failure-attempts.md`。

# 分类截图与证据索引

应用截图直接捕获本机实际运行的页面。其余截图为浏览器显示的“原始记录核对视图”，由 `python3 scripts/evidence.py` 读取真实 JSON、CSV 与命令输出生成；页面明确标注来源。它们不是终端直接截屏，也没有填充模拟数据。完整输出保存在 `results/`，截图展示其中可读的关键部分。

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

报告中的图题与正文解释对应上述材料。架构图及资源图位于 `docs/figures/`，由 `scripts/build_report.py` 生成。移动宽度 390px 的 DOM 检查未发现横向溢出；交付截图采用正常桌面视口。

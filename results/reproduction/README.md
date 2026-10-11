# 全新克隆部署验收

业务部署基线为 `5cd20a7aed74395667bb97e525caeb75a62979b4`。在同一台主机的 `.local/repro/source` 中，通过 `git clone --no-hardlinks --branch codex/implementation` 从该提交克隆；没有复制 `.env`、kubeconfig、工具二进制或数据。实际状态见 `verification.json`，构建、测试和 Compose 启动输出见 `deploy-attempt1.log`，后续 Kind 部署与验收输出见 `deploy.log`，业务身份与共享留言检查见两个 `*-check.json`。

为了验证首次安装，初始 PATH 只保留 `/usr/bin:/bin`，不使用原来位于 `/usr/local/bin` 的 kubectl。bootstrap 从官方源下载工具并校验摘要；后续另外去掉 PATH 中的 `.local/bin`，直接运行 Python `wait_api.py`，验证它能解析本地 kubectl。

使用以下环境变量隔离主实验，依次执行 README 的 bootstrap、build、test、compose-up、k8s-up、check 和 status：

首次下载 kubectl 的连接较慢，并出现一次暂时 TLS 错误；通过官方地址断点续传剩余数据，再核验官方 SHA-256 后继续 bootstrap。该版本的 kubectl 摘要为 `629d3f410e09bf49b64ae7079f7f0bda1191efed311f7d37fdbab0ad5b0ec2b7`。这是网络下载的重试，没有从原工程复制工具。

首次启动 Compose 后，Python 解析当前工作目录时暂时返回 `FileNotFoundError`。新 WSL 会话重新进入同一目录后，未经源码修改即可通过业务检查，因此保留该次错误并继续后续部署。没有把这次中断删去或记为首次全流程成功。

```bash
export LAB_PROJECT=cloudlab-repro LAB_CLUSTER=cloudlab-repro
export LAB_COMPOSE_PORT=8091 LAB_KIND_PORT=8081
bash scripts/lab.sh bootstrap
export PATH="$PWD/.local/bin:$PATH"
bash scripts/lab.sh build
bash scripts/lab.sh test
bash scripts/lab.sh compose-up
python3 scripts/check.py --url http://127.0.0.1:8091
bash scripts/lab.sh k8s-up
python3 scripts/check.py --url http://127.0.0.1:8081
bash scripts/lab.sh status
```

两条 Redis 使用新的卷/PVC和独立生成的凭证；Docker 镜像及构建缓存是同主机的已有缓存。此验收证明从提交文件到业务部署的复现，没有声称是空 Docker 缓存或跨主机复现。指标组件及故障实验已经在主集群测量，本轮独立克隆不重复这些故障。验收结束后仅清理本轮创建的 `cloudlab-repro` 项目及集群，保留主实验 `cloudlab`。

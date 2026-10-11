# metrics-server 本地实验变更

原始清单来自官方 v0.9.0 components.yaml：
https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.9.0/components.yaml

下载时原始 SHA-256：`1cec29a5267809306a2c6ec74a3e449abbb705b4a8beed0c8a1963910f72c79b`。

本地清单只增加/固定以下内容：

- Deployment `replicas: 1`，保证暂停后再次应用能恢复。
- 官方 amd64 镜像摘要 `25d291fde59974547bac6f07fa9d6cf6f5bedd1f19d60c893311c5e741e0a42f`。
- `--kubelet-insecure-tls`：Kind kubelet 自签证书缺少 IP SAN，原始失败证据在 `results/issues/metrics-tls-red.log`。仅用于本地实验，不照搬生产。

镜像由 `scripts/fetch_metrics.py` 下载固定的官方多架构索引、amd64 manifest 和各层，逐层校验摘要，再生成 OCI 归档供 Kind 导入。不使用来源不明镜像，不关闭下载证书验证，不修改用户代理。

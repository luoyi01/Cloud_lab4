# 未选入报告的失败尝试

`03-compose-config-first-failure.json` 保留了错误访问 Web 未代理的健康路由所产生的 404。`03-compose-config-unchecked-failure.json` 保留了硬编码容器名不存在的输出；早期多命令 shell 未开启严格错误检查，使最后成功的 curl 掩盖前面错误，页面状态不能作为通过依据。

当前脚本分别检查命令退出状态，并对 shell 开启 `set -e -o pipefail`；Compose API 容器名从实际运行列表获取。报告图 6 采用修复后重新执行的 `03-compose-config.json/.txt` 和对应 PNG，命令均成功。以上两次失败仅作为排查记录，不参与验证通过或截图映射。

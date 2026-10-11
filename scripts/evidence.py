"""Render selected real experiment logs for readable, explicitly labeled screenshots."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / ".local/evidence-site"
SITE.mkdir(parents=True, exist_ok=True)
CSS = "body{margin:0;background:#f7f8f4;color:#20362a;font:16px/1.6 'Segoe UI','Microsoft YaHei',sans-serif}main{max-width:1100px;margin:28px auto;padding:0 30px}h1{font-size:27px;margin:0 0 8px}p{margin:8px 0;color:#526c5a}.label{font-size:12px;letter-spacing:2px;color:#667e6a}code,pre{font-family:Consolas,'Microsoft YaHei',monospace;font-size:13px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#fff;border:1px solid #d7dfd3;padding:18px}table{border-collapse:collapse;width:100%;font-size:14px;background:#fff;margin:20px 0}td,th{border:1px solid #d7dfd3;padding:10px;text-align:left}th{background:#e5eee1}footer{border-top:1px solid #d7dfd3;font-size:12px;padding-top:16px;margin-top:20px;color:#738575}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}@media(max-width:700px){.grid{grid-template-columns:1fr}main{padding:0 18px}td,th{padding:7px;font-size:12px}}"


def read(path):
    return json.loads((ROOT / "results" / path).read_text(encoding="utf-8"))


def pre(value):
    text = json.dumps(value,ensure_ascii=False,indent=2) if not isinstance(value,str) else value
    return "<pre>"+html.escape(text)+"</pre>"


def table(headers, rows):
    return "<table><tr>"+"".join("<th>"+html.escape(str(h))+"</th>" for h in headers)+"</tr>"+"".join("<tr>"+"".join("<td>"+html.escape(str(c))+"</td>" for c in row)+"</tr>" for row in rows)+"</table>"


def page(name,title,command,content,source):
    text=f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{title}</title><style>{CSS}</style><main><p class="label">CLOUD LAB 04 / 原始记录核对视图</p><h1>{title}</h1><p>已执行命令：<code>{html.escape(command)}</code></p>{content}<footer>来源：{html.escape(source)}<br>本页由原始 JSON / 命令输出渲染；不是终端直接截屏。未填充或模拟测量结果。</footer></main></html>'
    (SITE/f"{name}.html").write_text(text,encoding="utf-8")


def main():
    events=read("self-heal/event.json")
    keys=("fault_utc","old_name","old_uid","new_name","new_uid","new_node","replacement_ready_s")
    traffic=events["traffic"]
    page("self-heal","API Pod 自动重建与连续业务请求","python3 scripts/experiments.py self-heal",
         pre({key:events[key] for key in keys})+table(["采样时长/s","请求","错误","成功率","P95/ms","客户端重试"],[[traffic[k] for k in ("duration_s","requests","errors","success_percent","p95_ms","client_retries")]]),"results/self-heal/event.json；requests.csv")
    pdb=read("pdb/eviction.json")
    page("pdb","PDB 自愿驱逐预算验证","python3 scripts/experiments.py pdb",pre(pdb),"results/pdb/eviction.json")
    node=read("node-failure/event.json")
    fields=("fault_utc","worker","affected_api_pods","node_not_ready_s","all_api_ready_on_survivor_s")
    traffic=node["traffic"]
    page("node-failure","API worker 故障：恢复能力与中断窗口","python3 scripts/experiments.py node-failure",pre({key:node[key] for key in fields})+table(["时长/s","实际请求","失败","成功率/%","客户端重试"],[[traffic[k] for k in ("duration_s","requests","errors","success_percent","client_retries")]]),"results/node-failure/event.json；requests.csv")
    content='<div class="grid">'+''.join('<section><h2>'+scheme+'</h2>'+pre(read(f"persistence/{scheme}.json"))+'</section>' for scheme in ("compose","k8s"))+'</div>'
    page("persistence","Redis 重启后持久化数据读回","python3 scripts/experiments.py persistence",content,"results/persistence/compose.json；k8s.json")
    workload=(ROOT/"results/deployment/workloads.txt").read_text(encoding="utf-8")
    nodes=(ROOT/"results/deployment/nodes.txt").read_text(encoding="utf-8")
    page("deployment","三节点 Kind 与应用资源状态","python3 scripts/experiments.py capture",pre(nodes)+pre(workload),"results/deployment/nodes.txt；workloads.txt")
    warm=read("comparison/warm-start.json")
    deletion=read("compose-delete/event.json")
    content=table(["路径","轮次","热启动/s"],[[r["scheme"],r["run"],r["ready_s"]] for r in warm])+pre({k:v for k,v in deletion.items() if k!="traffic"})
    page("comparison","五次热启动与 Compose 删除对照","python3 scripts/experiments.py warm-start / compose-delete",content,"results/comparison/warm-start.json；compose-delete/event.json")
    summary=read("summary.json")
    if "scale" in summary:
        content=table(["路径/步骤","副本","Ready/s","API CPU/m","API MiB","应用 MiB","请求/错误"],[[f"{r['scheme']}/{r['step']}",r["replicas"],r["ready_s"],r["api_cpu_m"],r["api_memory_mib"],r["app_memory_mib"],f"{r['requests']}/{r['errors']}"] for r in summary["scale"]])
        content+=pre({s:read(f"scale/{s}-dataset.json") for s in ("compose","k8s")})
        page("scale","1 → 3 → 5 → 3：固定数据与负载采样","python3 scripts/experiments.py scale",content,"results/scale/；summary.json（五次观测中位数）")
    print("Generated selected evidence pages in .local/evidence-site")


if __name__ == "__main__":
    main()

"""Normalize Docker/K8s units and summarize measured evidence, without inventing data."""
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results"


def cpu_millicores(value):
    suffixes = {"n": 1e-6, "u": 1e-3, "m": 1}
    return float(value[:-1]) * suffixes[value[-1]] if value[-1] in suffixes else float(value) * 1000


def memory_bytes(value):
    match = re.fullmatch(r"([0-9.]+)\s*([A-Za-z]*)", value.strip())
    if not match:
        raise ValueError(f"Unknown memory quantity: {value}")
    number, unit = match.groups()
    binary = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
    decimal = {"": 1, "B": 1, "K": 1000, "M": 1000**2, "G": 1000**3, "T": 1000**4}
    normalized = unit[:-1] if unit.endswith("B") and unit != "B" else unit
    multiplier = binary.get(normalized, decimal.get(normalized))
    if multiplier is None:
        raise ValueError(f"Unknown memory suffix: {unit}")
    return float(number) * multiplier


def summarize_resources(sample):
    rows = []
    if "containers" in sample:
        for container in sample["containers"]:
            rows.append((container["Name"], float(container["CPUPerc"].rstrip("%")) * 10,
                         memory_bytes(container["MemUsage"].split("/")[0].strip())))
    else:
        for pod in sample["metrics"]["items"]:
            for container in pod["containers"]:
                rows.append((pod["metadata"]["name"], cpu_millicores(container["usage"]["cpu"]),
                             memory_bytes(container["usage"]["memory"])))
    api = [row for row in rows if row[0].startswith(("api-", "cloudlab-api-"))]
    return {"app_cpu_m": sum(row[1] for row in rows), "api_cpu_m": sum(row[1] for row in api),
            "app_memory_mib": sum(row[2] for row in rows) / 1024**2,
            "api_memory_mib": sum(row[2] for row in api) / 1024**2}


def read(path):
    return json.loads((OUT / path).read_text(encoding="utf-8"))


def build_summary():
    result = {"scope": "Measured on one Windows/WSL2/Docker Desktop host; application container usage excludes platform overhead."}
    if (OUT / "comparison/warm-start.json").exists():
        raw = read("comparison/warm-start.json")
        result["warm_start"] = []
        for scheme in ("compose", "k8s"):
            values = [row["ready_s"] for row in raw if row["scheme"] == scheme]
            result["warm_start"].append({"scheme": scheme, "runs": len(values), "mean_s": round(statistics.mean(values), 3),
                                         "median_s": statistics.median(values), "stdev_s": round(statistics.stdev(values), 3) if len(values) > 1 else 0,
                                         "min_s": min(values), "max_s": max(values)})
    if (OUT / "scale/summary.json").exists():
        result["scale"] = []
        for raw in read("scale/summary.json"):
            samples = [summarize_resources(sample) for sample in raw["resource_samples"]]
            result["scale"].append({"scheme": raw["scheme"], "step": raw["step"], "replicas": raw["replicas"],
                                    "ready_s": raw["scale_ready_s"], "observations": len(samples),
                                    **{key: round(statistics.median([s[key] for s in samples]), 3) for key in samples[0]},
                                    "requests": raw["traffic"]["requests"], "errors": raw["traffic"]["errors"],
                                    "p50_ms": raw["traffic"]["p50_ms"], "p95_ms": raw["traffic"]["p95_ms"]})
    for experiment in ("self-heal", "compose-delete", "node-failure"):
        if (OUT / experiment / "event.json").exists():
            result[experiment] = read(f"{experiment}/event.json")
    return result


def main():
    summary = build_summary()
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 实测数据摘要", "", "由 `python3 scripts/summary.py` 从原始 JSON/CSV 生成。应用用量不含 Docker Desktop、WSL2、控制面和系统组件的开销。", ""]
    if "warm_start" in summary:
        lines += ["## 无状态服务热启动（Redis 与平台保持运行）", "", "| 路径 | 次数 | 均值/s | 标准差/s | 中位数/s |", "| --- | ---: | ---: | ---: | ---: |"]
        lines += [f"| {s['scheme']} | {s['runs']} | {s['mean_s']} | {s['stdev_s']} | {s['median_s']} |" for s in summary["warm_start"]]
    if "scale" in summary:
        lines += ["", "## 扩缩容与固定负载资源（五次观测的中位数）", "", "| 路径 | 步骤 | 副本 | Ready/s | API CPU/m | API 内存/MiB | 全应用 CPU/m | 全应用内存/MiB | 请求/错误 | P95/ms |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        lines += [f"| {s['scheme']} | {s['step']} | {s['replicas']} | {s['ready_s']} | {s['api_cpu_m']} | {s['api_memory_mib']} | {s['app_cpu_m']} | {s['app_memory_mib']} | {s['requests']}/{s['errors']} | {s['p95_ms']} |" for s in summary["scale"]]
    for key in ("self-heal", "compose-delete", "node-failure"):
        if key in summary:
            traffic = summary[key]["traffic"]
            lines += ["", f"## {key}", "", f"连续请求 {traffic['requests']} 次，错误 {traffic['errors']} 次，成功率 {traffic['success_percent']}%。客户端重试次数：0。详情见 `{key}/event.json` 与请求 CSV。"]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Generated results/summary.json and results/summary.md")


if __name__ == "__main__":
    main()

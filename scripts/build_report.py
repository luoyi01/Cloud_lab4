"""Build the eight-part Chinese report from measured JSON, with editable Markdown."""
import argparse
import csv
import json
import re
from pathlib import Path
import statistics
import subprocess
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics import renderPDF

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "docs/figures"


def read(name):
    return json.loads((ROOT / "results" / name).read_text(encoding="utf-8"))


def render_figure(drawing, name):
    import pypdfium2 as pdfium
    temp = ROOT / ".local/figure-pdfs"
    temp.mkdir(parents=True, exist_ok=True)
    path = temp / f"{name}.pdf"
    renderPDF.drawToFile(drawing, str(path))
    pdf = pdfium.PdfDocument(path)
    pdf[0].render(scale=2.5).to_pil().save(FIGURES / f"{name}.png")
    pdf.close()


def architecture():
    drawing = Drawing(700, 420)
    ink = colors.HexColor("#17392e")
    muted = colors.HexColor("#66766e")
    drawing.add(Rect(0, 0, 700, 420, fillColor=colors.white, strokeColor=None))

    def label(x, y, text, size=12, color=ink):
        drawing.add(String(x, y, text, fontName="Chinese", fontSize=size, textAnchor="middle", fillColor=color))

    def box(x, y, w, h, title, sub="", fill="#f0f5ef"):
        drawing.add(Rect(x, y, w, h, rx=5, ry=5, fillColor=colors.HexColor(fill), strokeColor=colors.HexColor("#ccd8cd")))
        label(x+w/2, y+h/2+3, title, 13)
        if sub:
            label(x+w/2, y+12, sub, 9, muted)

    def arrow(x1, y1, x2, y2):
        drawing.add(Line(x1, y1, x2, y2, strokeColor=muted, strokeWidth=1.2))
        if y1 == y2:
            drawing.add(Polygon([x2,y2,x2-6,y2+3,x2-6,y2-3], fillColor=muted, strokeColor=None))
        else:
            drawing.add(Polygon([x2,y2,x2-3,y2+6,x2+3,y2+6], fillColor=muted, strokeColor=None))

    label(350, 391, "同一应用 · 两条本地部署路径", 18)
    label(350, 368, "Windows → WSL2 / Docker Desktop → Compose 或三节点 Kind", 10, muted)
    box(20, 285, 135, 58, "浏览器 / 采样脚本", "8090 / 8080 固定入口")
    box(190, 285, 135, 58, "Nginx Web", "页面 + API 反向代理")
    box(365, 285, 145, 58, "服务发现", "Compose DNS / K8s Service")
    box(545, 285, 135, 58, "API 多副本", "1 / 3 / 5 个无状态实例")
    arrow(155,314,190,314); arrow(325,314,365,314); arrow(510,314,545,314)
    box(545, 185, 135, 58, "Redis 共享数据", "Lua 原子写入 + AOF")
    arrow(612,285,612,243)
    box(545, 85, 135, 58, "持久化存储", "命名卷 / StatefulSet PVC")
    arrow(612,185,612,143)
    box(20, 170, 300, 72, "Compose：3 个 API + Web + Redis", "Docker DNS / 环境变量 / 命名卷")
    box(20, 65, 300, 72, "Kind：1 控制节点 + 2 工作节点", "Service / ConfigMap / Secret / 探针 / PDB")
    box(365, 65, 145, 177, "配置与故障边界", "同一宿主机 / 单实例 Redis", "#faf6ed")
    label(437, 136, "API 跨 worker 调度", 10, muted)
    label(437, 110, "Web / Redis 固定 stable", 10, muted)
    label(350, 28, "模拟 API worker 故障，不能外推为宿主机或存储节点高可用", 10, muted)
    return drawing


def resource_chart(summary):
    drawing = Drawing(700, 300)
    drawing.add(String(350, 278, "API aggregate memory · matched 20 requests/s", fontName="Helvetica", fontSize=14, textAnchor="middle"))
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 75, 55, 565, 190
    chart.data = [[next(r["api_memory_mib"] for r in summary["scale"] if r["scheme"] == scheme and r["step"] == step)
                   for step in (1, 2, 3)] for scheme in ("compose", "k8s")]
    chart.categoryAxis.categoryNames = ["1 replica", "3 replicas", "5 replicas"]
    chart.valueAxis.valueMin = 0
    maximum = max(max(group) for group in chart.data)
    chart.valueAxis.valueMax = (int(maximum / 50) + 1) * 50
    chart.valueAxis.valueStep = 50
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.gridStrokeColor = colors.HexColor("#e4e8e4")
    chart.bars[0].fillColor = colors.HexColor("#2f6c50")
    chart.bars[1].fillColor = colors.HexColor("#dc8851")
    chart.bars.strokeColor = None
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 11
    drawing.add(chart)
    drawing.add(String(28, 230, "MiB", fontName="Helvetica", fontSize=10))
    drawing.add(Rect(215, 16, 10, 10, fillColor=chart.bars[0].fillColor, strokeColor=None))
    drawing.add(String(232,16,"Compose",fontName="Helvetica",fontSize=10))
    drawing.add(Rect(360,16,10,10,fillColor=chart.bars[1].fillColor,strokeColor=None))
    drawing.add(String(377,16,"Kind / Kubernetes",fontName="Helvetica",fontSize=10))
    return drawing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", default="C:/Windows/Fonts/msyh.ttc")
    args = parser.parse_args()
    pdfmetrics.registerFont(TTFont("Chinese", args.font))
    FIGURES.mkdir(parents=True, exist_ok=True)
    summary = read("summary.json")
    assert len(summary.get("scale", [])) == 8, "Complete measured scaling evidence is required"
    assert all(row["runs"] == 5 for row in summary["warm_start"])
    heal, node = summary["self-heal"], summary["node-failure"]
    node_errors = node["traffic"]["errors"]
    for scheme in ("compose", "k8s"):
        assert read(f"persistence/{scheme}.json")["readback"] == "identical", "Persistence evidence must pass"
    pdb = read("pdb/eviction.json")
    assert pdb["same_pod_still_ready"] and pdb["status"]["disruptionsAllowed"] == 0 and pdb["exit_code"] != 0
    assert read("scale/compose-dataset.json") == read("scale/k8s-dataset.json"), "Datasets must match"
    test_log = (ROOT / "results/tests/green.log").read_text(encoding="utf-8")
    matched = re.search(r"(\d+) passed", test_log)
    assert matched and not re.search(r"\d+ failed|\d+ errors", test_log), "Passing test evidence is required"
    test_count = matched.group(1)
    starts = {row["scheme"]: row["mean_s"] for row in summary["warm_start"]}
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    render_figure(architecture(), "architecture")
    render_figure(resource_chart(summary), "api-memory")

    body = ParagraphStyle("Body", fontName="Chinese", fontSize=10.5, leading=18, spaceAfter=9, wordWrap="CJK")
    title = ParagraphStyle("Title", parent=body, fontSize=25, leading=34, spaceAfter=18)
    h1 = ParagraphStyle("H1", parent=body, fontSize=16, leading=24, spaceBefore=17, spaceAfter=11, keepWithNext=True)
    h2 = ParagraphStyle("H2", parent=body, fontSize=12, leading=19, spaceBefore=10, spaceAfter=8, keepWithNext=True)
    caption = ParagraphStyle("Caption", parent=body, fontSize=9, leading=14, textColor=colors.HexColor("#536055"), alignment=TA_CENTER)
    cell = ParagraphStyle("Cell", parent=body, fontSize=9, leading=14, spaceAfter=0)
    header = ParagraphStyle("Header", parent=cell, textColor=colors.white)
    story, md = [], []

    def p(text):
        story.append(Paragraph(escape(text), body)); md.extend([text, ""])

    def heading(text, level=1):
        story.append(Paragraph(escape(text), h1 if level == 1 else h2)); md.extend([("## " if level == 1 else "### ") + text, ""])

    def table(headers, rows, widths=None, label=None):
        if label:
            story.append(Paragraph(escape(label), caption)); md.extend([label, ""])
        formatted = [[Paragraph(escape(str(c)), header) for c in headers]] + [[Paragraph(escape(str(c)), cell) for c in row] for row in rows]
        item = Table(formatted, colWidths=widths or [483/len(headers)]*len(headers), repeatRows=1, hAlign="LEFT")
        item.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#254e3d")), ("GRID",(0,0),(-1,-1),.5,colors.HexColor("#d9d9d9")), ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f4f7f2")]), ("VALIGN",(0,0),(-1,-1),"MIDDLE"), ("LEFTPADDING",(0,0),(-1,-1),8), ("RIGHTPADDING",(0,0),(-1,-1),8), ("TOPPADDING",(0,0),(-1,-1),8), ("BOTTOMPADDING",(0,0),(-1,-1),8)]))
        story.extend([item, Spacer(1,12)])
        md.extend(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"]*len(headers)) + " |"])
        md.extend("| " + " | ".join(str(c).replace("|","/") for c in row) + " |" for row in rows); md.append("")

    def image(path, text, width=470, max_height=400):
        from PIL import Image as PILImage
        with PILImage.open(ROOT/path) as source:
            w,h = source.size
        ratio = min(width/w,max_height/h)
        story.append(KeepTogether([Image(str(ROOT/path),width=w*ratio,height=h*ratio),Paragraph(escape(text),caption),Spacer(1,10)]))
        md.extend([f"![{text}]({Path(path).relative_to('docs').as_posix() if path.startswith('docs/') else '../'+path})", ""])

    story.extend([Spacer(1,30), Paragraph("班级云留言板",title), Paragraph("云计算实验 4 · 容器化、编排与对比分析",h1),Spacer(1,16)])
    md.extend(["# 班级云留言板：云计算实验 4", ""])
    p("学号：________________    姓名：________________")
    p("实验平台：Windows 11 / Docker Desktop / WSL2 Ubuntu 24.04")
    p("交付版本：v1.0.0；代码及配置基线：" + revision[:12] + "。最终源码与报告以 Git 仓库的发布版本及压缩包 SUBMISSION.txt 为准。")
    p("仓库：https://github.com/luoyi01/Cloud_lab4")
    p("本报告依据实际运行数据编写。A 为 Docker Compose，B 为三节点 Kind；完整虚拟机仅列为可选方案，没有把本机未安装的 VMware 写成已实施环境。")
    image("docs/figures/architecture.png", "图 1  两条部署路径、共享存储与故障边界", max_height=285)
    story.append(PageBreak())

    heading("一、实验概述")
    p("实验目标是将一个有真实业务的多单元应用容器化，在本地 Kubernetes 上编排运行，再以相同应用比较容器运行与编排机制。应用选用班级留言板：Nginx 提供页面与固定入口，FastAPI 负责留言和访问计数，Redis 保存共享数据。三个运行单元职责独立，API 默认三个副本，并通过实例身份接口证明请求由不同实例处理。")
    p("必做验证包括 Dockerfile 构建、端口与环境配置、持久化卷、Deployment/Service/ConfigMap/Secret、Pod 自动重建、扩缩容及资源变化。进阶部分选用 StatefulSet/PVC、PDB 和两个 worker 的节点故障测试。实验保留连续请求 CSV、旧新 Pod UID、事件与指标原始数据，用于核对报告结论。")
    table(["课程评分项","分值","交付证据"], [["应用设计与实现",25,f"src/、{test_count} 项测试、共享数据与实例验证"],["容器化",10,"docker/、镜像构建、Compose 运行与卷"],["K8s 部署与编排",15,"k8s/、资源 Ready、配置与 Secret 注入"],["弹性伸缩与自愈",10,"1→3→5→3 指标、Pod UID 与连续请求"],["消融对比实验",15,"五次热启动、固定数据/负载资源、删除对照"],["报告结构与规范",10,"八部分正文、图表、分类截图、参考资料"],["心得与技能收获",15,"第七节结合真实问题和边界分析"]], [125,42,316], "表 1  百分制评分与证据映射（总计 100 分）")
    p("提交包含 src/、docker/、k8s/、分类 screenshots/、本报告与 README；scripts/、tests/、results/、docs/提供复现和核验。压缩包使用学号_姓名_云原生实验.zip；本次按要求先留空身份信息，需提交时补充或重命名。截止时间以课程群通知为准。")

    heading("二、环境与工具")
    table(["层次","实测环境与版本"], [["宿主机","Windows 11；Ryzen 7 7840H，8 核 / 16 线程；可见内存约 27.69 GiB"],["虚拟化基础","WSL2 Ubuntu 24.04；Docker Desktop 托管 Linux Engine，Ubuntu 使用 WSL 集成"],["容器工具","Docker Desktop 4.94.0；Engine 29.8.2；Compose 5.5.1"],["编排工具","Kind 0.33.0；Kubernetes 1.36.4；kubectl 1.36.1；1 控制节点 + 2 worker"],["业务组件","Python 3.12 / FastAPI 0.115.12 / Redis 7.4.5 / Nginx 1.28.0"],["指标组件","metrics-server 0.9.0，官方镜像固定摘要；本地 kubelet 自签证书采用实验参数"]], [96,387], "表 2  实测环境")
    p("A 使用现有 Docker Desktop 上的 Compose；B 使用同一 Engine 上的 Kind。两条路径均通过 WSL2 支撑，不是原生 Linux 与 Windows 的性能对照。C 可在额外安装的完整 Ubuntu 虚拟机上运行同一仓库，以比较独立 guest OS 的资源、启动与隔离，但本次没有安装或测量 C。虚拟机方案仅作为可行性分析，不能用估计数字替代实测。")
    p("API 上限固定为 500m CPU / 256Mi，Web 为 200m / 128Mi，Redis 为 500m / 512Mi。K8s request 分别是 API 100m/128Mi、Web 50m/64Mi、Redis 100m/128Mi。Compose 使用相同 CPU/内存上限及 memory reservation，但没有 K8s 调度器，二者语义不能简单视为相同。")

    heading("三、应用设计与实现")
    p("留言记录含 ID、作者、内容和 UTC 时间。作者最多 30 字符、内容最多 300 字符；拒绝空白、超长和错误类型。Redis Lua 将自增 ID、Hash 内容与 Sorted Set 索引写入合并为原子操作，避免并发写入时 ID 重复或索引不一致。访问计数使用 Redis INCR。所有副本只保存连接与配置，不保存业务数据。")
    p("查询采用 ID 倒序游标分页，而不是会被新留言挤动的页码偏移。返回 next_cursor，下一页使用 before 游标。前端以 textContent 显示留言，避免将用户输入解释为 HTML。页面有发布反馈、字符计数、空状态、刷新与继续加载，并展示本次处理的实例和节点。")
    table(["接口","功能与验证"], [["GET /api/whoami","实例、节点、版本、标题与时间；Compose 为容器 hostname，K8s 由 Downward API 注入"],["POST /api/messages","输入校验；成功 201；失败 422；原子写入"],["GET /api/messages","limit 1–50；before 游标；共享数据读取"],["POST /api/visits","多副本共享的原子计数"],["GET /health/live","进程存活；不会因为 Redis 暂时失败而直接重启 API"],["GET /health/ready","检查 Redis 连接；不可用时 503 并退出流量分发"]], [155,328], "表 3  接口契约")
    p(f"测试使用真实 Redis，而不是伪造存储：校验正常留言、错误输入、游标在插入后不重复、40 次并发创建 ID、40 次并发计数、进程重建后数据、健康探针以及存储失败时不泄漏内部信息。另以本地 HTTP 服务验证 503 逐条记入采样结果且没有隐藏重试，并测试 CPU/内存单位换算。另验证实验中断后的服务恢复。全套 {test_count} 项通过，证据见 results/tests/green.log；初始失败记录见 red.log。")
    image("screenshots/01-compose/message-board.png", "图 2  Compose 实际发布留言后的页面", max_height=340)

    heading("四、部署过程记录")
    heading("4.1 Compose 容器化", 2)
    p("API 与 Web 分别有 Dockerfile。Python 运行依赖连同传递依赖精确固定；Python、Nginx、Redis 基镜像固定摘要。API 使用非 root 用户及只读根文件系统。Compose 创建内部网络，以 redis/API 服务名发现组件，只将 Web 的 80 端口映射到 127.0.0.1:8090；API 与 Redis 没有宿主机端口。Redis 用随机密码、命名卷和 AOF everysec。")
    p("执行 bootstrap、build、test、compose-up 后，真实入口验证脚本连续采样身份，确认三个实例均可读到同一条新留言；再验证访问计数递增。restart: unless-stopped 可以作用于容器进程退出，但不会把已删除容器重新创建。该差异在第五节的删除对照中实际验证。")
    heading("4.2 Kind 编排与配置", 2)
    p("Kind 配置一控制节点与两个 worker。控制节点 30180 的 NodePort 映射到宿主机 127.0.0.1:8080，提供稳定外部入口。API Deployment 默认三个副本，Service 维持固定名字和地址；ConfigMap 配置标题、版本、Redis 主机与数据前缀；Secret 通过本地 env-file 生成密码。Pod 名及 Node 名由 Downward API 注入。")
    p("API 使用 startup、readiness、liveness 探针；readiness 依赖 Redis，liveness 只判断进程。终止前延迟五秒并预留 30 秒宽限，让 EndpointSlice 移除和服务端终止有缓冲。副本用拓扑分散约束部署到两个 worker，ScheduleAnyway 允许单 worker 故障后继续调度。未用 port-forward 做可用性证明，因为它绑定具体 Pod，会受 Pod 删除影响。")
    p("Redis 使用 StatefulSet，固定 redis-0 身份，headless Service 加客户端 Service，以及 1Gi PVC。Web 与 Redis 放在 stable worker，另一个 worker 只承载本轮故障测试的 API。local-path PV 与该 worker 关联，所以该设计只能观察 API 节点故障，不能证明 Redis 自动故障转移。")
    image("screenshots/02-k8s/message-board.png", "图 3  Kind 固定入口发布留言后的实际页面", max_height=330)
    heading("4.3 加分项完成状态", 2)
    table(["文档加分项","本次状态与边界"], [["StatefulSet / PDB / Ingress 等","已做 StatefulSet/PVC 和 PDB eviction；未做 Ingress"],["多节点节点级高可用验证",f"已停止一个 API worker，记录重新调度与 {node_errors} 次失败；单主机、单控制面不保证平台 HA"],["可复现 Git / README","仓库固定版本、自动生成配置、独立 clone 部署验证、打包脚本"],["架构图与深入问题分析","图 1 及第六、七节，结合失败日志和实测数据"],["Redis Sentinel / MySQL 故障转移","未实现；单实例持久化不等于该项"],["完整 CI/CD 自动部署","未实现；没有用单独测试脚本冒充完整流水线"]], [190,293], "表 4  加分项映射（累计最多 10 分，未自拟单项分值）")

    heading("五、消融对比实验")
    heading("5.1 实验控制与统计口径", 2)
    p("同一源码与镜像、相同 CPU/内存上限、相同端点与请求节奏。资源实验使用单独 cloudlab-benchmark 数据前缀的 100 条固定留言，两个数据集 SHA-256 必须一致；正常留言不删除。每轮只运行正在采样路径的 API/Web，另一条路径暂停；Kind、两条 Redis 仍存在。客户端四线程各每 0.2 秒发一个业务 GET，共目标 20 请求/秒，持续 65 秒，不重试，并使用新连接。超时或延迟使实际请求数偏离目标，按 CSV 实际统计。")
    p("在 20、30、40、50、60 秒采集五次用量，汇总中位数。Docker 用 docker stats，K8s 用 metrics.k8s.io/v1beta1；CPU 换算为 m，内存换算为 MiB。统计 API 合计与 API/Web/Redis 应用合计，不含平台及其他数据存储的开销。不同指标系统的 CPU 时间窗口和内存缓存口径并非完全相同，数值用于近似描述，不能严格证明某平台更省资源。五次采样是同一轮中的观测，不是五轮独立重复。")
    heading("5.2 五次热启动", 2)
    p("保留 Redis、镜像和平台，只重新启动三个 API 与一个 Web。计时从启动命令开始到全部期望服务就绪及公开业务端点返回 200。排除下载、构建、Docker Desktop/WSL2 启动及 Kind 建群；每条路径独立重复五次。这是在既定健康检查配置下的热启动对照。")
    table(["路径","次数","均值 / s","标准差 / s","最小 / s","最大 / s"], [[r["scheme"],r["runs"],r["mean_s"],r["stdev_s"],r["min_s"],r["max_s"] for r in summary["warm_start"]], [75,42,90,96,90,90], "表 5  无状态服务热启动")
    p(f"本轮热启动均值为 Compose {starts['compose']} 秒、Kind {starts['k8s']} 秒。差异可能受 readiness 的两秒周期、Compose 五秒健康检查及现有调度状态影响。该结果不能推导为普遍的启动性能排序，也不能当成完整虚拟机与 WSL2 启动成本的测量。")
    heading("5.3 1→3→5→3 扩缩容及资源", 2)
    table(["路径 / 步骤","副本","Ready / s","API CPU / m","API 内存 / MiB","P95 / ms"], [[f"{r['scheme']} / {r['step']}",r["replicas"],r["ready_s"],r["api_cpu_m"],r["api_memory_mib"],r["p95_ms"] for r in summary["scale"]], [100,40,74,92,100,77], "表 6  伸缩就绪时间与 API 用量（资源为五次观测中位数）")
    table(["路径 / 步骤","全应用 CPU / m","全应用内存 / MiB","请求数","错误数"], [[f"{r['scheme']} / {r['step']}",r["app_cpu_m"],r["app_memory_mib"],r["requests"],r["errors"]] for r in summary["scale"]], [105,115,130,68,65], "表 7  全应用资源与固定负载请求结果")
    image("docs/figures/api-memory.png", "图 4  固定负载下，API 副本数量与合计内存的关系", max_height=250)
    p("副本增加会重复 Python 进程和连接池的基础内存；在固定总请求量下，增加副本不会使总业务量同步增加。因此低负载时副本主要提高容错余量，不必然降低延迟或 CPU 合计。本实验没有施加饱和压力，也没有测吞吐上限，不能据此声称五副本带来线性性能提升。")
    heading("5.4 自愈、容器删除和持久化", 2)
    p(f"三副本中默认优雅删除一个 API Pod，旧 UID {heal['old_uid']}，替代 UID {heal['new_uid']}。新 Pod 在 {heal['replacement_ready_s']} 秒后 Ready。45 秒内共 {heal['traffic']['requests']} 次连续业务请求，错误 {heal['traffic']['errors']} 次；这只能证明本次采样窗口内成功，并不是所有故障情形下零中断的保证。")
    p("Compose 删除一个 API 容器后，15 秒后仍有两副本。Compose 没有常驻期望状态控制器，需要再次执行 compose up 才补回。Docker restart policy 与 Kubernetes Deployment 的重建职责不同：前者针对现存容器，后者不断维持期望的 Pod 副本数。")
    p("两条路径分别写入持久化标记，等待 AOF everysec，优雅重启 Redis / 重建 redis-0 后读取结果完全一致。StatefulSet 维持身份和 PVC 绑定，数据卷提供存储。这个测试不包含断电、PV 节点故障或 Redis 主从故障转移。")
    heading("5.5 PDB 与 API worker 故障", 2)
    p("API 降为两副本，PDB minAvailable=2 的 disruptionsAllowed 变为零。Eviction API 返回 TooManyRequests/429，原 Pod UID 与 Ready 状态保持不变，随后恢复三副本。这验证自愿驱逐预算；直接 delete pod、Deployment 缩容、节点突然失联并不由 PDB 阻止。")
    p(f"停止 cloudlab-worker2 前有 {len(node['affected_api_pods'])} 个 API 位于该节点，Web 与 Redis 在存活 stable worker。{node['node_not_ready_s']} 秒检测到 Node 非 Ready，{node['all_api_ready_on_survivor_s']} 秒后全部 API 在存活 worker 就绪。150 秒采样共 {node['traffic']['requests']} 请求、{node['traffic']['errors']} 错误，成功率 {node['traffic']['success_percent']}%。故障节点在 finally 中恢复，所有节点重新 Ready。")
    p("失败出现在失联检测、EndpointSlice 更新及重新调度窗口。Nginx 对符合条件的请求最多尝试三次上游，但在死节点后端仍存在时仍可能失败。API 的 20 秒 toleration 只缩短失联确认后的驱逐等待，不消除节点检测延迟。结果展示了恢复能力，也展示了本地 HA 的局限。")
    table(["比较维度","Compose","Kind / Kubernetes"], [["副本管理","up --scale，一次性执行","Deployment 持续维持期望副本"],["删除后恢复","被删除容器不会自动创建","新 UID Pod 自动调度与 Ready"],["配置","环境变量、挂载文件","ConfigMap/Secret，变更后 rollout"],["服务发现","Docker DNS + Nginx 动态 resolve","Service/EndpointSlice，固定入口"],["持久化","Redis 命名卷","StatefulSet + PVC，仍为 local-path"],["复杂度与隔离","配置较少，便于本地多单元启动","控制面、调度、探针、拓扑、预算；同主机节点仍共享物理故障域"]], [90,190,203], "表 8  同应用的编排机制对比")

    heading("六、问题与分析")
    heading("6.1 多架构镜像导入缺层", 2)
    p("现象：Kind 导入 Redis 时 ctr 报 content digest not found。Docker Desktop 保存的是多架构索引，而本机只下载 amd64 层；导入工具遍历全部平台时找不到其他平台内容。处理：docker image save --platform linux/amd64 后导入归档，并将 amd64 manifest digest 绑定为镜像引用。验证：redis-0 Ready，同一版本读写与持久化通过。只改架构导出，不替换为来源不明镜像。")
    heading("6.2 Service-link 环境变量冲突", 2)
    p("现象：Compose 正常，Kind API CrashLoopBackOff；日志显示 int(REDIS_PORT) 收到 tcp://ServiceIP:6379。原因是 Kubernetes 默认 Service-link 环境变量与应用的 REDIS_PORT 名字重合。处理：API Pod enableServiceLinks=false，保留 DNS 和 ConfigMap 的显式配置。验证：API 全部 Ready，三个身份及共享留言测试通过；原始失败日志保存在 results/issues/service-links-red.log。")
    heading("6.3 指标下载与 kubelet 证书", 2)
    p("官方指标镜像下载较慢且有暂时 TLS 连接错误。处理：WSL curl 从官方 registry 下载固定 OCI manifest 与各层，逐层验证 SHA-256，支持断点续传及排他锁，不修改用户代理。镜像就绪后，Kind 的 kubelet 自签证书缺少可验证的 IP SAN，metrics-server 抓取失败。仅对本实验集群添加 kubelet-insecure-tls，并保留失败日志；生产应正确配置受信任的 kubelet 证书。kubectl top 实际有数据后才进行资源采样。")
    heading("6.4 节点恢复与可用性不是同一指标", 2)
    p(f"Pod 优雅删除窗口出现 {heal['traffic']['errors']} 次错误，突然停止 worker 出现 {node_errors} 次错误。前者能提前移除就绪端点，后者需要控制面判断失联。两种故障必须独立报告，不能用一次成功自愈宣称全局高可用。进一步改进需考虑外部冗余入口、多控制面、跨物理主机 worker、真正的 Redis 故障转移与更严格的负载测试。")

    heading("七、心得体会与技能收获")
    p("这次实验让我更清楚地理解了虚拟化、容器化和编排之间的层次。WSL2 提供 Linux 虚拟化基础，Docker 解决应用封装与运行，Kubernetes 则提供期望状态、调度和流量管理。它们解决的问题不同，所以比较时必须先划定边界。把本机没有安装的虚拟机软件列为实测环境，会让后续资源和隔离结论失去依据；方案应从现有条件出发，扩展路径则明确标为待实施。")
    p("我最有收获的是看到同一应用在两种环境下表现不同：Compose 能一次性启动三副本，却不会补回已删除容器；Deployment 则会创建新的 Pod。这个现象比单纯记住命令更能说明控制器的作用。另一个例子是 REDIS_PORT 的环境变量冲突，它提醒我部署失败不一定是业务逻辑错误，也可能来自运行平台的隐式配置。排查时应先读取原始日志，再验证假设。")
    p("我也认识到，多副本与数据一致性不能依赖每个进程自己的内存。留言 ID 和访问计数都需要共享存储的原子操作；分页还要考虑新留言插入时是否重复。另一方面，把 Redis 放入 StatefulSet 并挂载 PVC，只能证明身份和数据的持久化管理，并没有自动得到主从切换或跨节点存储高可用。")
    p(f"节点故障时的 {node_errors} 次失败让我意识到，恢复耗时和用户可用性要分别衡量。保留失败数据比只展示恢复后的 Ready 更有价值。资源测量同样需要谨慎：固定总负载下，更多副本会增加基础内存，却不能凭低负载延迟推断性能上限；Docker 和 K8s 的指标窗口也有差异。之后我希望在跨物理主机环境中加入冗余入口和 Redis Sentinel，再用明确的业务成功判据测量不同故障的恢复时间。")
    p("最后，可复现性本身是实验的一部分。依赖固定、镜像摘要、独立 kubeconfig、随机凭证生成、原始 CSV 和全新 clone 验证，可以让其他人核对过程。仓库应只包含源代码与必要证据，把密码、缓存和本地工作记录排除，避免材料杂乱或暴露不应提交的信息。")

    heading("八、参考文献与资料")
    references = [("课程文档","作业4（改）.docx：技术要求、六提交要求、七评分标准及加分项"),
                  ("Docker WSL 2 backend","https://docs.docker.com/desktop/features/wsl/"),
                  ("Docker Compose up","https://docs.docker.com/reference/cli/docker/compose/up/"),
                  ("Kind configuration","https://kind.sigs.k8s.io/docs/user/configuration/"),
                  ("Kind v0.33.0","https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0"),
                  ("Kubernetes probes","https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/"),
                  ("StatefulSet","https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/"),
                  ("PDB","https://kubernetes.io/docs/tasks/run-application/configure-pdb/"),
                  ("metrics-server","https://github.com/kubernetes-sigs/metrics-server"),
                  ("Redis persistence","https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/"),
                  ("Nginx upstream","https://nginx.org/en/docs/http/ngx_http_upstream_module.html")]
    for i,(name,url) in enumerate(references,1):
        p(f"[{i}] {name}：{url}")
    p("证据导航：results/summary.md 为数据摘要；deployment/ 为节点和资源命令输出；self-heal/、scale/、persistence/、pdb/、node-failure/、comparison/ 为对应实验原始数据；reproduction/ 为全新 clone 验证；screenshots/README.md 标注截图来源。")

    def footer(canvas, doc):
        canvas.setFont("Chinese",8)
        canvas.setFillColor(colors.HexColor("#607064"))
        canvas.drawString(56,30,"云计算实验 4 · 班级云留言板")
        canvas.drawRightString(A4[0]-56,30,str(doc.page))
    document = SimpleDocTemplate(str(ROOT/"report.pdf"),pagesize=A4,leftMargin=56,rightMargin=56,topMargin=48,bottomMargin=48,
                                 title="班级云留言板：云计算实验4",author="",subject="容器化、Kubernetes 编排与实测对比")
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    (ROOT/"docs/report.md").write_text("\n".join(md),encoding="utf-8")
    print("Generated report.pdf and docs/report.md")


if __name__ == "__main__":
    main()

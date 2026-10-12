"""Local live command UI for genuine, repeatable operation screenshots.

Only fixed lab operations are exposed, on loopback. Logs are new supplemental
evidence; original experiment measurements are never replaced.
"""
import argparse
import html
import json
import os
from pathlib import Path
import shlex
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import experiments as ex

ROOT = ex.ROOT
OUT = ROOT / 'results/screenshot-validation'
OUT.mkdir(parents=True, exist_ok=True)
ex.OUT = OUT
os.environ['KUBECONFIG'] = ex.KUBE
STATE = dict(stage='', title='', output='', running=False, status='待执行', utc='')
CONTEXT = {}
LOCK = threading.Lock()
DC = ['docker', 'compose', '--env-file', '.env', '-f', 'docker/compose.yaml', '--progress', 'quiet']
K = [ex.KUBECTL, '-n', 'cloudlab']


def emit(value):
    with LOCK:
        STATE['output'] += str(value) + '\n'


def run(args, okay=(0,)):
    emit('$ ' + shlex.join(args))
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    emit((result.stdout + result.stderr).rstrip())
    if result.returncode not in okay:
        raise RuntimeError(f'command exit {result.returncode}')
    return result


def shell(command, okay=(0,)):
    checked_command = 'set -e -o pipefail; ' + command
    emit('$ ' + checked_command)
    result = subprocess.run(['bash', '-lc', checked_command], cwd=ROOT, text=True, capture_output=True, env=os.environ)
    emit((result.stdout + result.stderr).rstrip())
    if result.returncode not in okay:
        raise RuntimeError(f'command exit {result.returncode}')
    return result


def workload(wide=False):
    columns = ['-o', 'custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,PHASE:.status.phase,NODE:.spec.nodeName'] if wide else []
    run(K + ['get', 'pods', '-l', 'app=api'] + columns)


def endpoint(scheme):
    run(['curl', '--fail', '-sS', ex.URLS[scheme] + '/api/whoami'])


def wait_replicas(n):
    run(['python3', 'scripts/wait_api.py', '--replicas', str(n)])


def env():
    shell("cat /etc/os-release | head -n 4; uname -r; docker version --format 'Client {{.Client.Version}} / Server {{.Server.Version}}'; docker compose version; .local/bin/kind version; kubectl version --client")


def build():
    for component in ('api', 'web'):
        # Independent verification tags do not replace the baseline deployment.
        run(['docker', 'build', '-q', '-f', f'docker/{component}.Dockerfile', '-t', f'cloudlab-{component}:screenshot', '.'])
    shell("docker image ls --filter reference='cloudlab-*:screenshot' --format '{{.Repository}}:{{.Tag}} {{.ID}}'")
    try:
        run(['docker','run','-d','--name','cloudlab-screenshot-api','--network','cloudlab_default','--env-file','.env','-e','REDIS_HOST=redis','cloudlab-api:screenshot'])
        run(['docker','run','-d','--name','cloudlab-screenshot-web','--network','cloudlab_default','cloudlab-web:screenshot'])
        time.sleep(3)
        run(['docker','exec','cloudlab-screenshot-api','python','-c',"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready').read().decode())"])
        run(['docker','exec','cloudlab-screenshot-web','wget','-qO-','http://127.0.0.1/api/whoami'])
    finally:
        run(['docker','rm','-f','cloudlab-screenshot-api','cloudlab-screenshot-web'],okay=(0,1))


def compose_config():
    container = ex.dc('ps','-q','api').stdout.split()[0]
    name = ex.command('docker','inspect',container,'--format','{{.Name}}').stdout.strip().lstrip('/')
    run(['docker','inspect',name,'--format','image={{.Config.Image}} cpu={{.HostConfig.NanoCpus}} memory={{.HostConfig.Memory}} readonly={{.HostConfig.ReadonlyRootfs}}'])
    run(['docker','exec',name,'sh','-c','printenv APP_TITLE APP_VERSION REDIS_HOST'])
    run(['docker','port','cloudlab-web-1'])
    run(['docker','inspect','cloudlab-redis-1','--format','{{range .Mounts}}{{.Type}} {{.Name}} -> {{.Destination}}{{end}}'])
    run(['docker','exec',name,'python','-c',"import socket; print('redis DNS=',socket.gethostbyname('redis'))"])
    run(['curl','--fail','-sS','http://127.0.0.1:8090/api/messages?limit=1'])


def compose_before():
    shell("docker ps --filter label=com.docker.compose.project=cloudlab --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    run(['python3', 'scripts/check.py', '--url', ex.URLS['compose']])


def k8s_resources():
    run(['kubectl', 'get', 'nodes'])
    run(K + ['get', 'deploy,sts,svc,pvc,pdb'])


def k8s_config():
    run(K + ['get', 'configmap', 'cloudlab-config', '-o', 'jsonpath={.data}'])
    run(K + ['describe', 'secret', 'cloudlab-secret'])
    shell("kubectl -n cloudlab get deploy api -o jsonpath='ConfigMap={.spec.template.spec.containers[0].envFrom[0].configMapRef.name}{\"\\n\"}Secret={.spec.template.spec.containers[0].env[0].valueFrom.secretKeyRef.name}/{.spec.template.spec.containers[0].env[0].valueFrom.secretKeyRef.key}{\"\\n\"}'; kubectl -n cloudlab exec deployment/api -- printenv APP_TITLE APP_VERSION REDIS_HOST; curl --fail -sS http://127.0.0.1:8080/api/messages?limit=1")


def heal_before():
    wait_replicas(3)
    ready = [p for p in ex.pods() if ex.is_ready(p)]
    CONTEXT['heal_old'] = ready[0]
    CONTEXT['heal_uids'] = {p['metadata']['uid'] for p in ready}
    CONTEXT['heal_probe'] = ex.launch_probe('k8s', 45, 'self-heal/requests.csv')
    workload()
    endpoint('k8s')
    emit('Continuous business GET: 45 s, interval 0.2 s, retries 0; results/screenshot-validation/self-heal/requests.csv')


def heal_inject():
    old = CONTEXT['heal_old']['metadata']
    CONTEXT['heal_started'] = time.monotonic()
    emit('Old UID: ' + old['uid'])
    run(K + ['delete', 'pod', old['name'], '--wait=false'])
    workload()


def heal_after():
    wait_replicas(3)
    new = next(p for p in ex.pods() if ex.is_ready(p) and p['metadata']['uid'] not in CONTEXT['heal_uids'])
    workload()
    emit('Old UID: ' + CONTEXT['heal_old']['metadata']['uid'])
    emit('New UID: ' + new['metadata']['uid'])
    emit('New Pod: ' + new['metadata']['name'])
    thread, summary = CONTEXT['heal_probe']
    thread.join()
    emit(json.dumps(summary, ensure_ascii=False))
    endpoint('k8s')


def scale(n):
    run(DC + ['up', '-d', '--no-build', '--scale', f'api={n}', '--wait', '--wait-timeout', '120'])
    run(K + ['scale', 'deployment/api', f'--replicas={n}'])
    wait_replicas(n)
    emit(f'$ wait until kubectl top reports all {n} current Ready API Pods')
    deadline = time.monotonic() + 100
    wanted = {p['metadata']['name'] for p in ex.pods() if ex.is_ready(p)}
    while time.monotonic() < deadline:
        sample = ex.k('top','pods','-l','app=api','--no-headers',allow_failure=True)
        observed = {line.split()[0] for line in sample.stdout.splitlines() if line.strip()}
        if sample.returncode == 0 and observed == wanted:
            break
        time.sleep(2)
    else:
        raise TimeoutError('Metrics do not cover all Ready API Pods')
    shell("docker ps --filter label=com.docker.compose.service=api --filter label=com.docker.compose.project=cloudlab --format '{{.Names}}' | xargs docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'")
    run(K + ['get', 'pods', '-l', 'app=api'])
    run(K + ['top', 'pods', '-l', 'app=api'])
    emit('Supplemental instantaneous metrics; not the original five-observation medians.')


def persist_before():
    CONTEXT['markers'] = {}
    CONTEXT['redis_uid'] = json.loads(ex.k('get','pod','redis-0','-o','json').stdout)['metadata']['uid']
    emit('Before Redis Pod UID: ' + CONTEXT['redis_uid'])
    for scheme in ('compose', 'k8s'):
        emit(f'$ POST {ex.URLS[scheme]}/api/messages')
        status, msg = ex.http(ex.URLS[scheme], '/api/messages', {'author': '截图验证', 'content': '持久化补拍 ' + ex.now()})
        CONTEXT['markers'][scheme] = msg['message']
        emit(f'{scheme} status={status} ' + json.dumps(msg, ensure_ascii=False))
    shell("docker inspect cloudlab-redis-1 --format '{{range .Mounts}}{{.Type}} {{.Name}} -> {{.Destination}}{{end}}'; kubectl -n cloudlab get pvc")


def persist_inject():
    run(DC + ['restart', 'redis'])
    run(K + ['delete', 'pod', 'redis-0', '--wait=false'])
    run(K + ['get', 'pods', '-l', 'app=redis'])


def persist_after():
    emit('$ wait for redis-0 with a different UID, no deletionTimestamp, and Ready=True')
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        result = ex.k('get','pod','redis-0','-o','json',allow_failure=True)
        if result.returncode == 0:
            pod = json.loads(result.stdout)
            if pod['metadata']['uid'] != CONTEXT['redis_uid'] and ex.is_ready(pod):
                break
        time.sleep(.5)
    else:
        raise TimeoutError('New redis-0 Pod did not become Ready')
    run(K + ['wait', '--for=condition=Ready', 'pod/redis-0', '--timeout=120s'])
    emit('Old Redis UID: ' + CONTEXT['redis_uid'])
    emit('New Redis UID: ' + pod['metadata']['uid'])
    run(K + ['get','pods','-l','app=redis'])
    for scheme in ('compose', 'k8s'):
        ex.ready(ex.URLS[scheme])
        emit(f'$ GET {ex.URLS[scheme]}/api/messages?limit=50')
        _, data = ex.http(ex.URLS[scheme], '/api/messages?limit=50')
        old = CONTEXT['markers'][scheme]
        found = next(m for m in data['items'] if m['id'] == old['id'])
        assert found == old
        emit(f'{scheme} identical_readback=True ' + json.dumps(found, ensure_ascii=False))
    run(K + ['get', 'pvc'])


def compose_inject():
    CONTEXT['compose_probe'] = ex.launch_probe('compose', 35, 'compose-delete/requests.csv')
    name = ex.dc('ps', '-q', 'api').stdout.split()[0]
    run(['docker', 'rm', '-f', name])
    emit('Wait 15 s to observe whether a deleted container is recreated.')
    time.sleep(15)
    shell("docker ps --filter label=com.docker.compose.project=cloudlab --filter label=com.docker.compose.service=api --format 'table {{.Names}}\t{{.Status}}'")
    endpoint('compose')


def compose_after():
    run(DC + ['up', '-d', '--no-build', '--scale', 'api=3', '--wait'])
    shell("docker ps --filter label=com.docker.compose.project=cloudlab --filter label=com.docker.compose.service=api --format 'table {{.Names}}\t{{.Status}}'")
    thread, summary = CONTEXT['compose_probe']
    thread.join()
    emit(json.dumps(summary, ensure_ascii=False))


def pdb_before():
    workload()
    run(K + ['get', 'pdb'])


def pdb_inject():
    run(K + ['scale', 'deployment/api', '--replicas=2'])
    wait_replicas(2)
    time.sleep(3)
    run(K + ['get', 'pdb'])
    pod = next(p for p in ex.pods() if ex.is_ready(p))['metadata']['name']
    body = {'apiVersion': 'policy/v1', 'kind': 'Eviction', 'metadata': {'name': pod, 'namespace': 'cloudlab'}}
    target = OUT / 'eviction.json'
    target.write_text(json.dumps(body), encoding='utf-8')
    rejected = run(K + ['create', '--raw', f'/api/v1/namespaces/cloudlab/pods/{pod}/eviction', '-f', str(target.relative_to(ROOT))], okay=(1,))
    assert 'TooManyRequests' in rejected.stderr and "disruption budget" in rejected.stderr
    workload()


def pdb_after():
    run(K + ['scale', 'deployment/api', '--replicas=3'])
    wait_replicas(3)
    time.sleep(3)
    run(K + ['get', 'pdb'])
    workload()


def compare():
    # A fresh command reading existing measurements is labeled as review.
    emit('Original measurement review, not new startup timing.')
    run(['python3', '-c', "import json; d=json.load(open('results/comparison/warm-start.json')); print('scheme run ready_s original_UTC'); [print(r['scheme'],r['run'],r['ready_s'],r['utc']) for r in d]"])


def node_before():
    run(['kubectl', 'get', 'nodes'])
    workload(wide=True)
    affected = [p for p in ex.pods() if p['spec']['nodeName'] == 'cloudlab-worker2' and ex.is_ready(p)]
    assert affected, 'Need a real API Pod on the target worker before stopping it.'
    CONTEXT['node_old'] = [p['metadata']['uid'] for p in affected]
    CONTEXT['node_probe'] = ex.launch_probe('k8s', 140, 'node-failure/requests.csv')
    emit('Affected Pod UIDs: ' + ', '.join(CONTEXT['node_old']))
    emit('Continuous business GET: 140 s, interval 0.2 s, retries 0.')


def node_inject():
    run(['docker', 'stop', 'cloudlab-worker2'])
    emit('$ wait until cloudlab-worker2 becomes NotReady (poll kubectl get node)')
    deadline = time.monotonic() + 100
    while time.monotonic() < deadline:
        node = json.loads(ex.command('kubectl', 'get', 'node', 'cloudlab-worker2', '-o', 'json').stdout)
        if not any(c['type'] == 'Ready' and c['status'] == 'True' for c in node['status']['conditions']):
            break
        time.sleep(1)
    else:
        raise TimeoutError('Node did not become NotReady')
    run(['kubectl', 'get', 'nodes'])
    workload(wide=True)
    emit('Worker container is stopped; this is an API worker fault, not host or Redis failover.')


def node_after():
    try:
        emit('$ wait for 3 Ready API Pods on the surviving worker')
        deadline = time.monotonic() + 130
        while time.monotonic() < deadline:
            ready = [p for p in ex.pods() if ex.is_ready(p) and p['spec']['nodeName'] != 'cloudlab-worker2']
            if len(ready) == 3:
                break
            time.sleep(1)
        else:
            raise TimeoutError('API did not reschedule onto the surviving worker')
        workload(wide=True)
        emit('Replaced affected UIDs: ' + ', '.join(CONTEXT['node_old']))
        emit('All 3 ready replicas are on the surviving worker.')
    finally:
        run(['docker', 'start', 'cloudlab-worker2'])
        run(['kubectl', 'wait', '--for=condition=Ready', 'node/cloudlab-worker2', '--timeout=120s'])
    run(['kubectl', 'get', 'nodes'])
    thread, summary = CONTEXT['node_probe']
    thread.join()
    emit(json.dumps(summary, ensure_ascii=False))
    endpoint('k8s')


STAGES = {
    '01-env': ('V01 环境与工具 实际版本', env),
    '02-build': ('V02 Dockerfile 独立构建 API 与 Web 镜像', build),
    '03-compose-config': ('V03 Compose 端口 环境变量 卷与内部 DNS', compose_config),
    '04-compose-before': ('V04 V09 Compose 原始部署与业务共享', compose_before),
    '05-k8s-resources': ('V05 Kind 集群及 Deployment Service PVC', k8s_resources),
    '06-k8s-config': ('V06 ConfigMap Secret 注入与运行时验证', k8s_config),
    '07-heal-before': ('V07 Pod 自愈 原始部署与连续请求', heal_before),
    '08-heal-inject': ('V07 Pod 自愈 手动删除与重建过程', heal_inject),
    '09-heal-after': ('V07 Pod 自愈 恢复与连续请求统计', heal_after),
    '10-scale-one': ('V08 扩缩容 两条路径均为 1 副本', lambda: scale(1)),
    '11-scale-three': ('V08 扩缩容 两条路径扩至 3 副本', lambda: scale(3)),
    '12-scale-five': ('V08 扩缩容 两条路径扩至 5 副本', lambda: scale(5)),
    '13-scale-back': ('V08 扩缩容 两条路径缩回 3 副本', lambda: scale(3)),
    '14-persist-before': ('V10 持久化 重启前写入与卷', persist_before),
    '15-persist-inject': ('V10 持久化 Redis 重启与 Pod 重建', persist_inject),
    '16-persist-after': ('V10 持久化 恢复后相同记录读回', persist_after),
    '17-compose-inject': ('V09 Compose 删除容器 15 秒后仍为 2 副本', compose_inject),
    '18-compose-after': ('V09 Compose 显式恢复至 3 副本', compose_after),
    '19-pdb-before': ('B01 PDB 原始 3 副本与可驱逐预算', pdb_before),
    '20-pdb-inject': ('B01 PDB 2 副本时拒绝自愿驱逐', pdb_inject),
    '21-pdb-after': ('B01 PDB 恢复 3 副本与预算', pdb_after),
    '22-comparison': ('V09 B02 原始热启动与节点故障数据复核', compare),
    '23-node-before': ('B02 API worker 故障 原始节点与 Pod 分布', node_before),
    '24-node-inject': ('B02 API worker 故障 节点停止与 NotReady', node_inject),
    '25-node-after': ('B02 API worker 故障 重新调度与节点恢复', node_after),
}

PAGE = '''<!doctype html><meta charset="utf-8"><title>Cloud Lab 现场命令执行</title>
<style>body{margin:0;background:white;color:#111;font:18px/1.4 'SimSun',sans-serif}main{padding:24px 30px}h1{font-size:25px;margin:8px 0}p{margin:6px 0;font-size:16px}pre{font:17px/1.35 Consolas,'SimSun',monospace;white-space:pre-wrap;overflow-wrap:anywhere;border-top:1px solid #aaa;padding-top:14px;margin:12px 0}select,button{font-size:16px;padding:6px}header{border-bottom:1px solid #aaa;padding-bottom:12px}.tools{margin:12px 0}</style>
<main><header><p>Cloud Lab 04 本机现场操作截图</p><h1 id="title">本机实时命令执行界面</h1><p id="meta"></p><p>WSL2 Ubuntu 24.04 · 固定实验命令 · 原始 stdout / stderr · Secret 值不显示</p></header>
<div class="tools"><select id="stage">OPTIONS</select> <button onclick="start()">执行验证</button></div><pre id="output"></pre><p id="status"></p></main>
<script>async function start(){await fetch('/run',{method:'POST',body:document.querySelector('#stage').value});await update()}
async function update(){let s=await(await fetch('/state')).json();document.querySelector('#title').textContent=s.title;document.querySelector('#meta').textContent='验证 '+s.stage+' · UTC '+s.utc;document.querySelector('#output').textContent=s.output;document.querySelector('#status').textContent=s.status;document.querySelector('#stage').value=s.stage||Object.keys({})[0];}setInterval(update,300);update();</script>'''.replace('OPTIONS', ''.join(f'<option value="{k}">{html.escape(v[0])}</option>' for k,v in STAGES.items()))


def execute(stage):
    try:
        STAGES[stage][1]()
        STATE['status'] = '执行完成；输出来自本轮真实命令。'
    except Exception as error:
        emit(f'ERROR: {type(error).__name__}: {error}')
        STATE['status'] = '执行失败，请检查原始输出。'
    finally:
        STATE['running'] = False
        record = dict(STATE)
        history = OUT / 'history'
        history.mkdir(exist_ok=True)
        stamp = record['utc'].replace(':','-')
        (history / f'{stage}-{stamp}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (OUT / f'{stage}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (OUT / f'{stage}.txt').write_text(f"UTC {record['utc']}\n{record['title']}\n{record['output']}\n{record['status']}\n", encoding='utf-8')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if self.command == 'POST':
            print(fmt % args, flush=True)

    def reply(self, data, kind='application/json'):
        self.send_response(200)
        self.send_header('Content-Type', kind + '; charset=utf-8')
        self.end_headers()
        self.wfile.write(data.encode())

    def do_GET(self):
        if self.path == '/state':
            self.reply(json.dumps(STATE, ensure_ascii=False))
        else:
            self.reply(PAGE, 'text/html')

    def do_POST(self):
        origin = self.headers.get('Origin')
        allowed_origin = f'http://127.0.0.1:{self.server.server_port}'
        if self.path != '/run' or origin not in (None, allowed_origin):
            self.send_error(403)
            return
        if int(self.headers.get('Content-Length', 0)) > 128:
            self.send_error(413)
            return
        stage = self.rfile.read(int(self.headers.get('Content-Length', 0))).decode()
        if stage not in STAGES or STATE['running']:
            self.send_error(409)
            return
        STATE.update(stage=stage, title=STAGES[stage][0], output='', running=True, status='命令执行中', utc=ex.now())
        threading.Thread(target=execute, args=(stage,), daemon=True).start()
        self.reply('{"started":true}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8077)
    args = parser.parse_args()
    import fcntl
    lock_file = (ROOT / '.local/experiments.lock').open('a')
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    print(f'Live validation UI: http://127.0.0.1:{args.port}', flush=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    try:
        server.serve_forever()
    finally:
        ex.restore_all(lambda: ex.command('docker', 'start', 'cloudlab-worker2'), ex.restore_compose, ex.restore_k8s)

"""Read-only namespace/kernel observations; never collect environment secrets."""
import json
import os
from pathlib import Path
import platform
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
KUBECTL = str(ROOT / '.local/bin/kubectl') if (ROOT / '.local/bin/kubectl').is_file() else 'kubectl'
PAYLOAD = '''import json,os,platform
from pathlib import Path
print(json.dumps({'kernel':platform.release(),'hostname':platform.node(),
'namespaces':{name:os.readlink('/proc/1/ns/'+name) for name in ('pid','mnt','net')},
'pid1':Path('/proc/1/comm').read_text().strip(),'root_entries':sorted(os.listdir('/')),
'network_interfaces':[line.split(':')[0].strip() for line in Path('/proc/net/dev').read_text().splitlines()[2:]]}))'''


def main():
    compose = ['docker','compose','--env-file',str(ROOT/'.env'),'-f',str(ROOT/'docker/compose.yaml')]
    container = subprocess.check_output([*compose,'ps','-q','api'],cwd=ROOT,text=True).split()[0]
    commands = {'compose': ['docker','exec',container,'python','-c',PAYLOAD],
                'k8s': [KUBECTL,'--kubeconfig',str(ROOT/'.local/kubeconfig'),'-n','cloudlab','exec',
                        'deployment/api','--','python','-c',PAYLOAD]}
    result = {'utc':datetime.now(timezone.utc).isoformat(), 'host_scope':'Ubuntu WSL2',
              'host':{'kernel':platform.release(),'hostname':platform.node(),
                      'namespaces':{name:os.readlink('/proc/self/ns/'+name) for name in ('pid','mnt','net')}}}
    for scheme, command in commands.items():
        result[scheme] = json.loads(subprocess.check_output(command,cwd=ROOT,text=True))
    assert result['host']['kernel'] == result['compose']['kernel'] == result['k8s']['kernel']
    assert all(len({result[s]['namespaces'][name] for s in ('host','compose','k8s')}) == 3 for name in ('pid','mnt','net'))
    result['namespace_sources'] = {'host':'/proc/self/ns (current Ubuntu process)', 'containers':'/proc/1/ns'}
    result['interpretation'] = 'Both paths share the observed WSL2 kernel; PID/mount/network namespace IDs differ. This is a mechanism observation, not a security penetration test or a separate guest-kernel VM comparison.'
    out = ROOT/'results/comparison/isolation.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Kernel and namespace observations: passed; results/comparison/isolation.json')


if __name__ == '__main__':
    main()

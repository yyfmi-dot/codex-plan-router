"""Opt-in real exhausted-Plan failover. Never changes the user's native route.

Uses only CC Switch access leases, queries real quota, and runs at most three
short native Codex turns. No artificial upstream errors or mid-request mode
changes. All reports use aliases; no identifiers or raw upstream bodies.
"""
from pathlib import Path
from datetime import datetime, timezone
import concurrent.futures
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE / 'plugin/scripts'), str(BASE / 'plugin/scripts/vendor')]
from cpr import catalog, cc_switch, engine
from cpr.host import native_cli
from cpr.storage import Store, read, save


def run():
    if os.environ.get('CODEX_ROUTER_LIVE_PROBE') != '1':
        raise SystemExit('Set CODEX_ROUTER_LIVE_PROBE=1; real authorized Plan/API inference can incur charges.')
    native = Store()
    discovery = cc_switch.request(native, 'catalog')
    settings_file = Path(discovery['codex_home']) / 'config.toml'
    original_digest = hashlib.sha256(settings_file.read_bytes()).hexdigest()
    model = os.environ.get('CODEX_ROUTER_TEST_MODEL', 'gpt-6.2-sol')
    def eligible(item):
        try:
            lease = cc_switch.request(native, 'lease/plan', {'id': item['id']}, 35)
            request = urllib.request.Request('https://chatgpt.com/backend-api/wham/usage', headers={
                'Authorization': 'Bearer ' + lease['access_token'], 'ChatGPT-Account-Id': lease['account_id'],
                'User-Agent': 'codex-cli', 'Accept': 'application/json'})
            with urllib.request.urlopen(request, timeout=15) as response:
                usage = json.load(response)
            rate = usage.get('rate_limit') or {}
            return {'lease': lease, 'exhausted': rate.get('allowed') is False and rate.get('limit_reached') is True,
                    'available': rate.get('allowed') is True and rate.get('limit_reached') is False,
                    'used': [v.get('used_percent') for v in rate.values() if isinstance(v, dict)]}
        except Exception:
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        candidates = [x for x in pool.map(eligible, discovery['accounts']) if x]
    exhausted = [x for x in candidates if x['exhausted']]
    healthy = next((x for x in candidates if x['available']), None)
    if not exhausted or not healthy or not discovery['keys']:
        raise RuntimeError('Need a genuinely exhausted Plan, an available Plan, and an authorized official API source.')
    api = cc_switch.request(native, 'lease/key', {'id': discovery['keys'][0]['id']})
    cli = native_cli()
    report = {'schema': 1, 'model': model, 'method': 'real upstream quota and native client; isolated eligible sets',
              'exhausted_plans_available': len(exhausted), 'exhausted_plan_used_percent': exhausted[0]['used'],
              'quota_transition_observed': False, 'scope': 'pre-exhausted accounts; natural reset recovery not observed'}
    cli_path = str(cli)
    report['codex_cli'] = subprocess.check_output([cli_path, '--version'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='cpr-real-exhaustion-') as temporary:
        root = Path(temporary)
        client_home = root / 'client'
        client_home.mkdir()
        key = secrets.token_urlsafe(40)
        marker = 'CPR_ACCEPT_' + secrets.token_hex(8)
        native_catalog = catalog.prepare(native)
        def prepare(name, plans, with_api):
            store = Store(root / name)
            store.save({'codex_home': str(client_home), 'gateway_port': free_port(), 'credential_source': 'local',
                        'keys': [{'id': 'api-standby', 'label': 'api-standby', 'key': api['key']}] if with_api else [], 'mode': 'plan-first'})
            save(store.access_path, {'management': secrets.token_urlsafe(40), 'client': key})
            store.auths.mkdir(parents=True)
            state = catalog.stage(store, [Path(native_catalog[n]).read_bytes() for n in ('catalog', 'codex-catalog')], 'private-local-cache')
            save(store.data / 'catalog-state.json', state)
            target = engine.binary(store)
            target.parent.mkdir(parents=True)
            original = engine.binary(native)
            shutil.copy2(original, target)
            shutil.copy2(original.with_suffix('.sha256'), target.with_suffix('.sha256'))
            for i, (alias, plan) in enumerate(plans):
                lease = plan['lease']
                save(store.auths / (alias + '.json'), {'type': 'codex', 'email': alias, 'account_id': lease['account_id'],
                    'access_token': lease['access_token'], 'id_token': lease.get('id_token'),
                    'expired': datetime.fromtimestamp(lease['expires_at'], timezone.utc).isoformat(),
                    'last_refresh': lease['last_refresh'], 'priority': 200-i*10, 'disabled': False})
            process = engine.start(store)
            engine.management(store, "config/observability/usage/usage-statistics-enabled", True, "PUT")
            for _ in range(100):
                if model in catalog.model_ids(store):
                    break
                time.sleep(.1)
            assert model in catalog.model_ids(store), 'Selected model unavailable in the actual test engine.'
            save(client_home / 'models.json', catalog.client_payload(store))
            (client_home / 'config.toml').write_text('model='+json.dumps(model)+'\nmodel_provider="custom"\nmodel_reasoning_effort="low"\nservice_tier="default"\nmodel_catalog_json='+json.dumps(str(client_home/'models.json'))+'\n[features]\nmemories=false\n[model_providers.custom]\nname="Real exhausted-plan acceptance"\nbase_url="http://127.0.0.1:'+str(store.settings()['gateway_port'])+'/v1"\nwire_api="responses"\nrequires_openai_auth=true\nsupports_websockets=false\nexperimental_bearer_token='+json.dumps(key)+'\n')
            lease=healthy['lease']
            save(client_home/'auth.json', {'auth_mode':'chatgpt','OPENAI_API_KEY':None,'tokens':{
                'access_token':lease['access_token'],'id_token':lease.get('id_token'),'account_id':lease['account_id'],'refresh_token':''},'last_refresh':lease['last_refresh']})
            return store, process
        def client(arguments):
            env=dict(os.environ,CODEX_HOME=str(client_home))
            started=time.monotonic()
            result=subprocess.run([cli_path]+arguments, env=env,cwd=root,capture_output=True,text=True,timeout=150)
            rows=[]
            for line in result.stdout.splitlines():
                try: rows.append(json.loads(line))
                except ValueError: pass
            messages='\n'.join(x.get('item',{}).get('text','') for x in rows if x.get('item',{}).get('type')=='agent_message')
            return {'complete':result.returncode==0 and any(x.get('type')=='turn.completed' for x in rows),
                    'thread':next((x.get('thread_id') for x in rows if x.get('type')=='thread.started'),None),
                    'retained':marker in messages,'seconds':round(time.monotonic()-started,2),
                    'errors':[x.get('type') for x in rows if x.get('type') in ('error','turn.failed')]}
        def counters(store):
            result={}
            for x in engine.management(store,'credentials').get('files',[]):
                name=x.get('name','')
                if name not in ('exhausted-a.json','exhausted-b.json','available-plan.json'):
                    name='api-standby' if x.get('runtime_only') else 'other'
                message=x.get('status_message','')
                result[name]={'success':x.get('success',0),'failed':x.get('failed',0),'quota_rejected':('usage_limit_reached' in message or 'usage limit' in message.lower()),'unavailable':x.get('unavailable'),'quota':{k:v for k,v in (x.get('quota') or {}).items() if k in ('exceeded','reason','backoff_level')},'model_quota_count':len(x.get('model_quotas') or {})}
            return result
        def stop(process):
            process.terminate()
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired: process.kill();process.wait()
        # A short successful first turn establishes a native thread and context.
        store, process=prepare('initial', [('available-plan',healthy)], False)
        try:
            initial=client(['exec','--json','--skip-git-repo-check','Remember '+marker+'. Reply exactly OK. Do not use tools.'])
            report['initial_plan_turn']={'complete':initial['complete'],'seconds':initial['seconds']}
            assert initial['complete'] and initial['thread'], 'Initial native Plan turn failed.'
        finally: stop(process)
        for name,plans,with_api in [
            ('plan_to_plan',[('exhausted-a',exhausted[0]),('available-plan',healthy)],False),
            ('plan_to_api',[(('exhausted-a' if i==0 else 'exhausted-b'),p) for i,p in enumerate(exhausted[:2])],True)]:
            store,process=prepare(name,plans,with_api)
            try:
                result=client(['exec','resume',initial['thread'],'--json','--skip-git-repo-check','Repeat the marker from the first turn, and nothing else. Do not use tools.'])
                stats=counters(store)
                usage=[]
                for _ in range(30):
                    usage.extend(engine.management(store,'observability/usage/queue?count=20'))
                    if any(not x.get('failed') for x in usage): break
                    time.sleep(.1)
                evidence=[{k:x.get(k) for k in ('auth_type','model','failed','response_model')} for x in usage]
                api_success=any(not x.get('failed') and x.get('auth_type')=='apikey' for x in usage)
                failed=[v for k,v in stats.items() if k.startswith('exhausted-')]
                destination='api-standby' if with_api else 'available-plan.json'
                checks={'native_turn_completed':result['complete'],'same_thread_context_retained':result['retained'],
                        'real_exhausted_credentials_attempted':len(failed)==len(plans)-(0 if with_api else 1) and all(x['failed']>0 for x in failed),
                        'real_quota_error_observed':all(x['quota_rejected'] for x in failed),
                        'destination_succeeded':api_success if with_api else stats.get(destination,{}).get('success',0)>0,
                        'model_preserved':any(not x.get('failed') and x.get('model')==model for x in usage)}
                report[name]={'checks':checks,'seconds':result['seconds'],'credentials':stats,'client_errors':result['errors'],'usage':evidence}
                print(json.dumps({'case':name,'checks':checks,'seconds':result['seconds']}),flush=True)
            finally: stop(process)
    report['user_configuration_unchanged']=hashlib.sha256(settings_file.read_bytes()).hexdigest()==original_digest
    report['passed']=report['user_configuration_unchanged'] and all(all(report[n]['checks'].values()) for n in ('plan_to_plan','plan_to_api'))
    save(BASE/'dist/real-exhaustion-verification.json',report)
    print(json.dumps(report,indent=2))
    assert report['passed'],'See redacted report; real exhaustion acceptance has not passed.'


def free_port():
    import socket
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


if __name__=='__main__':
    run()

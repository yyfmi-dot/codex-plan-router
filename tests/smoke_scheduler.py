"""Black-box priority/failover/recovery checks against the installed gateway binary."""
import json
import pathlib
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'dist'
WORK = pathlib.Path((ROOT / 'smoke-path').read_text())
BIN = WORK / 'router/bin/8.0.76/cli-proxy-api'
state = {'plan-a': 'ok', 'plan-b': 'ok', 'api': 'ok'}
calls = []
context_calls = []

class Upstream(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        label = self.headers.get('Authorization', '').removeprefix('Bearer ')
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        context_calls.append({'credential': label, 'has_prior_marker': b'ROUTER_CONTEXT_3176' in body})
        calls.append(label)
        if state.get(label) == 'quota':
            payload = json.dumps({'error': {'type': 'usage_limit_reached', 'message': 'simulated exhausted plan', 'resets_in_seconds': 3}}).encode()
            self.send_response(429)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Retry-After', '3')
        else:
            message = {'id': 'msg_test', 'type': 'message', 'status': 'completed', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'OK', 'annotations': []}]}
            response = {'id': 'resp_test', 'object': 'response', 'created_at': int(time.time()), 'model': 'gpt-6.1-sol', 'status': 'completed', 'output': [message], 'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}}
            events = [{'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}}, {'type': 'response.output_text.delta', 'output_index': 0, 'content_index': 0, 'delta': 'OK'}, {'type': 'response.completed', 'response': response}]
            payload = ''.join('data: ' + json.dumps(event) + '\n\n' for event in events).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
threading.Thread(target=upstream.serve_forever, daemon=True).start()
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='codex-plan-scheduler-') as temp:
    work = pathlib.Path(temp)
    (work / 'auths').mkdir()
    model = {'name': 'gpt-6.1-sol', 'alias': 'gpt-6.1-sol', 'thinking': {'levels': ['low', 'medium', 'high', 'xhigh', 'max']}}
    groups = [{'name': label, 'priority': priority, 'base-url': f'http://127.0.0.1:{upstream.server_port}/v1', 'keys': [{'api-key': label, 'websockets': False, 'disable-codex-cloaking': True}], 'models': [model]} for label, priority in [('plan-a', 100), ('plan-b', 90), ('api', 0)]]
    cfg = {'config-version': 8, 'server': {'host': '127.0.0.1', 'port': port}, 'access': {'api-keys': ['local-scheduler-test']}, 'management': {'secret-key': 'local-scheduler-management', 'disable-control-panel': True}, 'oauth': {'auth-dir': str(work / 'auths')}, 'routing': {'strategy': 'fill-first', 'session-affinity': False, 'retry': {'request-retry': 0, 'max-retry-interval': 0}}, 'api-keys': {'codex': groups}}
    (work / 'config.yaml').write_text(json.dumps(cfg))
    with (work / 'gateway.log').open('w') as log:
        proc = subprocess.Popen([str(BIN), '-local-model', '-config', str(work / 'config.yaml')], cwd=work, stdout=log, stderr=log)
        try:
            base = f'http://127.0.0.1:{port}/v1'
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError('Gateway exited: ' + (work / 'gateway.log').read_text()[-2000:])
                try:
                    with urllib.request.urlopen(urllib.request.Request(base + '/models', headers={'Authorization': 'Bearer local-scheduler-test'}), timeout=1):
                        break
                except Exception:
                    time.sleep(0.1)
            else:
                raise RuntimeError('Gateway did not become ready')

            def request():
                start = len(calls)
                body = {'model': 'gpt-6.1-sol', 'input': 'Reply OK', 'reasoning': {'effort': 'low'}, 'stream': True, 'store': False}
                req = urllib.request.Request(base + '/responses', data=json.dumps(body).encode(), headers={'Authorization': 'Bearer local-scheduler-test', 'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = response.read().decode()
                assert 'response.completed' in data, data[:300]
                return calls[start:]

            checks = {}
            trace = request()
            if trace != ['plan-a']:
                with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}/v0/management/auth-files', headers={'Authorization': 'Bearer local-scheduler-management'})) as response:
                    print('DIAGNOSTIC', response.read().decode())
                print('GATEWAY LOG', (work / 'gateway.log').read_text()[-3000:])
                raise AssertionError(trace)
            checks['plan_preferred_over_api'] = trace
            state['plan-a'] = 'quota'
            trace = request()
            assert trace[-1] == 'plan-b' and 'api' not in trace, trace
            checks['next_plan_before_api'] = trace
            state['plan-b'] = 'quota'
            trace = request()
            assert trace[-1] == 'api', trace
            checks['api_only_after_plans_exhausted'] = trace
            state['plan-a'] = 'ok'
            # The gateway deliberately applies a 10-second minimum quota cooldown.
            time.sleep(10.3)
            trace = request()
            if trace != ['plan-a']:
                with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}/v0/management/auth-files', headers={'Authorization': 'Bearer local-scheduler-management'})) as response:
                    print('RECOVERY DIAGNOSTIC', response.read().decode())
                print('RECOVERY LOG', (work / 'gateway.log').read_text()[-3000:])
                raise AssertionError(trace)
            checks['recovered_plan_replaces_api'] = trace
            # Exercise the real Codex client across a simulated account/API switch.
            import os
            client_home = work / 'client-home'
            client_home.mkdir()
            (client_home / 'config.toml').write_text(
                'model="gpt-6.1-sol"\nmodel_provider="custom"\nmodel_reasoning_effort="low"\n'
                '[features]\nmemories=false\n'
                '[model_providers.custom]\nname="Plan Router"\n'
                + 'base_url="' + base + '"\nwire_api="responses"\n'
                + 'requires_openai_auth=false\nexperimental_bearer_token="local-scheduler-test"\n'
                + 'supports_websockets=false\n')
            candidates = list((pathlib.Path.home()/'.vscode/extensions').glob('openai.chatgpt-*/bin/macos-aarch64/codex'))
            cli = sorted(candidates)[-1]
            env = os.environ.copy()
            env['CODEX_HOME'] = str(client_home)
            def client(arguments):
                result = subprocess.run([str(cli)] + arguments, env=env, cwd=work,
                                        capture_output=True, text=True, timeout=80)
                events = []
                for line in result.stdout.splitlines():
                    try: events.append(json.loads(line))
                    except ValueError: pass
                assert result.returncode == 0, 'Native client failed: ' + str([e.get('type') for e in events])
                assert any(e.get('type') == 'turn.completed' for e in events), 'No completed native turn'
                return events
            first = client(['exec','--json','--skip-git-repo-check',
                            'Remember ROUTER_CONTEXT_3176. Reply OK. Do not use tools.'])
            thread_id = next(e['thread_id'] for e in first if e.get('type') == 'thread.started')
            state['plan-a'] = 'quota'
            state['plan-b'] = 'quota'
            start_context = len(context_calls)
            second = client(['exec','resume',thread_id,'--json','--skip-git-repo-check',
                             'Keep the marker from our previous turn. Reply OK. Do not use tools.'])
            continuation = context_calls[start_context:]
            assert any(e['credential']=='api' and e['has_prior_marker'] for e in continuation), continuation
            checks['real_codex_client_resumes_same_thread_after_simulated_failover'] = True
            checks['prior_user_context_reaches_fallback'] = True
            checks['test_upstream'] = 'local simulated quota responses; not real quota exhaustion'
            (ROOT / 'scheduler-verification.json').write_text(json.dumps(checks, indent=2) + '\n')
            print(json.dumps(checks))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            upstream.shutdown()

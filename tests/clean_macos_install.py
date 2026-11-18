"""Install the actual public release on a disposable, credential-free macOS runner.

No HOME replacement, auth fixtures, security bypass, or inference. This covers
an empty macOS VM user, not browser quarantine approval or interactive OAuth.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('--confirm-disposable-runner',action='store_true')
    args=parser.parse_args()
    if not args.confirm_disposable_runner or os.environ.get('GITHUB_ACTIONS')!='true' or platform.system()!='Darwin':
        raise SystemExit('Only run on an explicitly confirmed disposable GitHub macOS runner.')
    manifest=json.loads((ROOT/'tests/acceptance-release.json').read_text())
    out=ROOT/'dist';out.mkdir(exist_ok=True)
    report={'schema':1,'scope':'fresh GitHub-hosted Apple Silicon macOS VM; actual user home; no credentials',
            'release':manifest['router_version'],'macos':platform.mac_ver()[0], 'architecture':platform.machine(),
            'quarantine_approval_tested':False,'interactive_login_tested':False,'checks':{}}
    checks=report['checks']
    current_stage='preconditions'
    router=Path.home()/'.local/share/codex-plan-router/marketplace/plugins/codex-plan-router/scripts/router.py'
    app=Path.home()/'Applications/CC Switch Plan Router.app'
    def execute(command,timeout=180,env=None):
        result=subprocess.run([str(x) for x in command],capture_output=True,text=True,timeout=timeout,env=env)
        if result.returncode:
            raise RuntimeError('Command failed during '+current_stage+' (exit '+str(result.returncode)+')')
        return result.stdout
    def fetch(url,digest,path):
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'codex-plan-router-acceptance'}),timeout=90) as response,path.open('wb') as output:
            shutil.copyfileobj(response,output)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,'Release digest mismatch'
    try:
        absent=[Path.home()/'.cc-switch',Path.home()/'.local/share/codex-plan-router',Path.home()/'.codex/auth.json',Path.home()/'.codex/config.toml',app]
        checks['no_preexisting_router_cc_or_codex_configuration']=not any(p.exists() for p in absent)
        assert checks['no_preexisting_router_cc_or_codex_configuration'],'Runner has preexisting application data; refusing to reuse it.'
        assert platform.machine()=='arm64','Apple Silicon runner required'
        current_stage='download_and_verify_release'
        work=Path(os.environ['RUNNER_TEMP'])/'cpr-acceptance';work.mkdir()
        share=work/'share.zip';cli_archive=work/'codex.tar.gz'
        fetch(manifest['share_url'],manifest['share_sha256'],share)
        fetch(manifest['cli_url'],manifest['cli_sha256'],cli_archive)
        checks['public_release_sha256_verified']=True
        checks['native_cli_sha256_verified']=True
        cli_dir=work/'cli';cli_dir.mkdir()
        with tarfile.open(cli_archive) as archive:
            member=next(x for x in archive.getmembers() if x.isfile() and Path(x.name).name=='codex-aarch64-apple-darwin')
            cli=cli_dir/'codex';cli.write_bytes(archive.extractfile(member).read());cli.chmod(0o755)
        env=dict(os.environ,PATH=str(cli_dir)+os.pathsep+os.environ['PATH'],CODEX_ROUTER_TEST_CLI=str(cli))
        report['native_cli']=execute([cli,'--version'],env=env).strip()
        execute(['ditto','-x','-k',share,out])
        bundle=out/('Codex-Plan-Router-macOS-'+manifest['router_version'])
        checks['both_install_commands_executable']=all(os.access(bundle/name,os.X_OK) for name in ('Install.command','安装.command'))
        current_stage='full_colleague_installer'
        execute([sys.executable,bundle/'install.py','--codex-cli',cli],timeout=240,env=env)
        checks['full_installer_completed']=True
        checks['companion_installed']=app.is_dir()
        execute(['codesign','--verify','--deep','--strict',app])
        checks['companion_signature_valid']=True
        report['gatekeeper_status']=execute(['spctl','--status']).strip()
        assessment=subprocess.run(['spctl','--assess','--type','execute',str(app)],capture_output=True,text=True)
        report['gatekeeper_assessment_accepted']=assessment.returncode==0
        current_stage='fresh_service_and_bridge'
        status={}
        for _ in range(80):
            try:
                status=json.loads(execute([sys.executable,router,'status'],env=env))
                if status.get('running') and status.get('cc_switch',{}).get('connected'):break
            except RuntimeError:pass
            time.sleep(.25)
        checks['launchagent_and_engine_running']=status.get('running') is True
        checks['fresh_companion_bridge_connected']=status.get('cc_switch',{}).get('connected') is True
        checks['accounts_empty_without_user_login']=not status.get('cc_switch',{}).get('accounts')
        checks['api_sources_empty']=not status.get('api_keys')
        checks['routing_requires_explicit_activation']=status.get('active') is False
        checks['native_auth_not_created']=not (Path.home()/'.codex/auth.json').exists()
        state_dir=Path.home()/'.local/share/codex-plan-router/data'
        checks['runtime_private_permissions']=all((state_dir/name).stat().st_mode&0o777==0o600 for name in ('settings.json','access.json','engine.json'))
        current_stage='native_plugin_loader_and_writer_lease'
        execute([sys.executable,ROOT/'tests/smoke_install.py'],env=env)
        native=json.loads((out/'install-verification-desktop.json').read_text())
        checks['native_plugin_and_skills_loaded']=all(native.values())
        current_stage='idempotent_reinstallation'
        execute([sys.executable,bundle/'install.py','--codex-cli',cli],timeout=90,env=env)
        checks['repeat_installer_completed']=True
        current_stage='uninstall'
        execute([sys.executable,router,'uninstall'],env=env)
        for _ in range(80):
            status=json.loads(execute([sys.executable,router,'status'],env=env))
            if not status.get('running'):break
            time.sleep(.1)
        checks['uninstall_stops_engine']=not status.get('running')
        checks['uninstall_preserves_private_data']=state_dir.is_dir()
        report['passed']=all(checks.values())
        assert report['passed'],'A clean-install acceptance check failed.'
    except Exception as error:
        report.update(passed=False,failed_stage=current_stage,error_type=type(error).__name__,error=str(error)[:240])
        raise
    finally:
        if router.exists():
            subprocess.run([sys.executable,str(router),'stop'],capture_output=True,timeout=30)
        (out/'clean-macos-verification.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__=='__main__':
    run()

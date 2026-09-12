#!/usr/bin/env python3
"""Start, stop and reset only the iHear local development environment."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'


def run(command: list[str], *, env: dict | None = None, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, env=env, check=True, text=True, capture_output=capture)


def docker_env() -> dict[str, str]:
    env = dict(os.environ)
    config = LOCAL / 'docker'
    config.mkdir(parents=True, exist_ok=True)
    path = config / 'config.json'
    if not path.exists():
        path.write_text('{"auths":{}}\n')
    settings = json.loads(path.read_text())
    plugins = Path('/Applications/Docker.app/Contents/Resources/cli-plugins')
    if plugins.exists():
        settings['cliPluginsExtraDirs'] = [str(plugins)]
        path.write_text(json.dumps(settings) + '\n')
    env['DOCKER_CONFIG'] = str(config)
    socket = Path.home() / '.docker/run/docker.sock'
    if socket.exists():
        env.setdefault('DOCKER_HOST', f'unix://{socket}')
    return env


def read_env() -> dict[str, str]:
    path = ROOT / '.env.local'
    if not path.exists():
        return {}
    return dict(line.split('=', 1) for line in path.read_text().splitlines() if line and not line.startswith('#') and '=' in line)


def make_env(docker: dict[str, str], origin: str | None, *, force_offline: bool = False) -> dict[str, str]:
    result = run(['pnpm', 'exec', 'supabase', 'status', '-o', 'json'], env=docker, capture=True)
    local = json.loads(result.stdout)
    values = read_env()
    values.update({'DATABASE_URL': local['DB_URL'], 'SUPABASE_URL': local['API_URL'], 'SUPABASE_SERVICE_ROLE_KEY': local['SERVICE_ROLE_KEY']})
    defaults = {'APP_PUBLIC_ORIGIN': 'http://localhost:3000', 'DEV_ALLOWED_ORIGINS': 'http://localhost:3000,http://127.0.0.1:3000', 'IHEAR_RATE_LIMIT_SALT': secrets.token_hex(32), 'AUDIO_BUCKET': 'ihear-audio', 'REPORT_BUCKET': 'ihear-reports', 'QUEUE_NAME': 'ihear_jobs', 'PIPELINE_VERSION': '1', 'REPORT_VERSION': '3', 'OPENAI_API_KEY': '', 'ASTRA_MODEL': 'gpt-6-astra', 'ASTRA_REASONING_EFFORT': 'low', 'WORKER_CONCURRENCY': '1', 'CLINIC_TIMEZONE': 'Europe/Prague'}
    for key, value in defaults.items():
        values.setdefault(key, value)
    if force_offline:
        values['OPENAI_API_KEY'] = ''
    # Report template revisions must match the committed web/worker contract.
    values['REPORT_VERSION'] = '3'
    if origin:
        values['APP_PUBLIC_ORIGIN'] = origin.rstrip('/')
    path = ROOT / '.env.local'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as file:
        file.write(''.join(f'{key}={value}\n' for key, value in values.items()))
    path.chmod(0o600)
    return values


def web_running() -> bool:
    pidfile = LOCAL / 'web.pid'
    if not pidfile.exists():
        return False
    try:
        pid = int(pidfile.read_text())
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], text=True, capture_output=True)
        return str(ROOT) in result.stdout and 'pnpm' in result.stdout
    except (ValueError, OSError):
        return False


def start_web(production: bool = False) -> None:
    if web_running():
        print('iHear web process is already running.')
        return
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 3000)) == 0:
            raise RuntimeError('Port 3000 is already in use by an unmanaged process. Stop that specific process before starting iHear.')
    mode = 'start' if production else 'dev'
    if production:
        run(['pnpm', 'build'])
    log = LOCAL / 'web.log'
    with log.open('a') as file:
        process = subprocess.Popen(['pnpm', '--dir', str(ROOT), mode], cwd=ROOT, stdout=file, stderr=subprocess.STDOUT, start_new_session=True)
    log.chmod(0o600)
    (LOCAL / 'web.pid').write_text(str(process.pid))
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError('The web process exited. Inspect .local/web.log.')
        try:
            with urllib.request.urlopen('http://127.0.0.1:3000', timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError('Web readiness timed out. Inspect .local/web.log.')


def stop_web() -> None:
    if web_running():
        pid = int((LOCAL / 'web.pid').read_text())
        os.killpg(pid, signal.SIGTERM)
        for _ in range(100):
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1', 3000)) != 0:
                    break
            time.sleep(0.1)
        else:
            raise RuntimeError('The managed web process has not released port 3000. Inspect .local/web.log before restarting.')
    (LOCAL / 'web.pid').unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'reset', 'status'])
    parser.add_argument('--origin', help='Reachable HTTPS origin for phone testing; localhost is desktop-only.')
    parser.add_argument('--confirm-local-reset', action='store_true', help='Reset only the disposable iHear local database; verify Storage bytes separately.')
    parser.add_argument('--production', action='store_true', help='Build and run local production mode for stable offline/PWA verification.')
    args = parser.parse_args()
    LOCAL.mkdir(exist_ok=True)
    env = docker_env()
    compose = ['docker', 'compose', '-p', 'ihear', '-f', 'docker-compose.yml']
    if args.action == 'start':
        run(['docker', 'info', '--format', '{{.ServerVersion}}'], env=env)
        print('Starting isolated Supabase services. Initial public image downloads can take several minutes.', flush=True)
        log = LOCAL / 'supabase-start.log'
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as file:
            subprocess.run(['pnpm', 'exec', 'supabase', 'start'], cwd=ROOT, env=env, stdout=file, stderr=subprocess.STDOUT, check=True)
        values = make_env(env, args.origin)
        run(['pnpm', 'exec', 'supabase', 'migration', 'up', '--local'], env=env)
        run(compose + ['up', '--build', '-d'], env=env)
        start_web(args.production)
        origin_configured = bool(values.get('APP_PUBLIC_ORIGIN'))
        print(f"Web: http://localhost:3000\noriginConfigured: {str(origin_configured).lower()}\nStudio: http://127.0.0.1:54323\nLocal keys are stored only in ignored .env.local.")
    elif args.action == 'stop':
        stop_web()
        run(compose + ['down'], env=env)
        run(['pnpm', 'exec', 'supabase', 'stop'], env=env)
        print('iHear stopped. Local Supabase data is preserved. Disable an optional Tailscale Serve port separately.')
    elif args.action == 'reset':
        if not args.confirm_local_reset:
            parser.error('Reset deletes iHear local runtime data. Repeat with --confirm-local-reset.')
        run(compose + ['stop'], env=env)
        run(['pnpm', 'exec', 'supabase', 'db', 'reset', '--local'], env=env)
        run(compose + ['up', '-d'], env=env)
        print('iHear local database reset. Existing browser pairings are invalid; create new synthetic profiles and pair again.')
    else:
        result = run(['pnpm', 'exec', 'supabase', 'status', '-o', 'json'], env=env, capture=True)
        status = json.loads(result.stdout)
        print(json.dumps({'webManagedProcessRunning': web_running(), 'supabaseURL': status.get('API_URL'), 'studioURL': status.get('STUDIO_URL'), 'originConfigured': bool(read_env().get('APP_PUBLIC_ORIGIN'))}, indent=2))
        run(compose + ['ps'], env=env)

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Install the prepared dedicated-host units and read-only monitor as root.

Does not start services, expose ingress, modify data, or change the power policy.
"""
from pathlib import Path
import grp
import json
import os
import pwd
import re
import shutil
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def run(*argv):
    return subprocess.run(argv, check=True, text=True, capture_output=True).stdout


def install(source, destination, mode=0o644):
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    os.chown(destination, 0, 0)
    destination.chmod(mode)


def main():
    if os.geteuid() != 0 or socket.gethostname() != "openclaw-appliance" or ROOT != Path("/home/ondrej/iHear"):
        raise SystemExit("Use sudo on the verified dedicated host and canonical runtime checkout.")
    state = json.loads(run("tailscale", "status", "--json"))
    user_id = str(state["Self"]["UserID"])
    login = state["User"][user_id]["LoginName"]
    if not login or "\n" in login or "\r" in login:
        raise SystemExit("The current tailnet owner login is invalid.")
    container_names = run("docker", "ps", "-a", "--format", "{{.Names}}").splitlines()
    monitored = sorted({"ihear-worker-1", *(name for name in container_names if re.fullmatch(r"supabase_[a-z0-9_]+_iHear", name))})
    try:
        pwd.getpwnam("ihear-monitor")
    except KeyError:
        run("useradd", "--system", "--no-create-home", "--home-dir", "/nonexistent", "--shell", "/usr/sbin/nologin", "ihear-monitor")
    group_id = grp.getgrnam("ihear-monitor").gr_gid
    for directory, owner, mode in [("/var/lib/ihear-monitor", 0, 0o750), ("/var/log/ihear", pwd.getpwnam("www-data").pw_uid, 0o750)]:
        path = Path(directory)
        path.mkdir(exist_ok=True)
        os.chown(path, owner, group_id)
        path.chmod(mode)
    access_log = Path("/var/log/ihear/access.jsonl")
    access_fd = os.open(access_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o640)
    os.fchown(access_fd, pwd.getpwnam("www-data").pw_uid, group_id)
    os.fchmod(access_fd, 0o640)
    os.close(access_fd)
    for name in ("collector.py", "server.py", "store.py"):
        install(ROOT / "ops/monitor" / name, Path("/usr/local/lib/ihear-monitor") / name)
    for source in [*(ROOT / "ops/monitor/systemd").glob("*"), *(ROOT / "ops/linux").glob("*.service")]:
        install(source, Path("/etc/systemd/system") / source.name)
    install(ROOT / "ops/monitor/nginx/ihear.conf.template", "/etc/nginx/conf.d/ihear.conf")
    default = Path("/etc/nginx/sites-enabled/default")
    if default.is_symlink() and default.resolve() == Path("/etc/nginx/sites-available/default"):
        backup = Path("/etc/nginx/sites-disabled/ihear-distribution-default")
        backup.parent.mkdir(exist_ok=True)
        if backup.exists() or backup.is_symlink():
            raise SystemExit("A preserved nginx default already exists; reconcile the new enabled default manually.")
        default.rename(backup)
    install(ROOT / "ops/linux/logrotate-ihear", "/etc/logrotate.d/ihear")
    config = Path("/etc/ihear")
    config.mkdir(exist_ok=True)
    config.chmod(0o750)
    env = config / "monitor.env"
    fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(f"IHEAR_MONITOR_ALLOWED_LOGIN={login}\nIHEAR_MONITOR_DB=/var/lib/ihear-monitor/metrics.sqlite\nIHEAR_ACCESS_LOG=/var/log/ihear/access.jsonl\nIHEAR_DB_CONTAINER=supabase_db_iHear\nIHEAR_MONITOR_CONTAINERS={','.join(monitored)}\n")
    env.chmod(0o600)
    run("nginx", "-t")
    run("systemctl", "daemon-reload")
    print("Installed and validated iHear units, private proxy and monitor; activation is separate.")


if __name__ == "__main__":
    main()

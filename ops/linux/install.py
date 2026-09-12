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
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from runtime_identity import validate_runtime_identity

RUNTIME_IDENTITY = ROOT / ".local/sandbox/runtime.json"
PRIVATE_LOGIN_PLACEHOLDER = "__IHEAR_PRIVATE_LOGIN__"
WEB_NODE_PLACEHOLDER = "__IHEAR_NODE_BINARY__"
WEB_USER = "ihear-web"
WEB_NODE_LINK = Path("/home/ondrej/.local/bin/node")
WEB_SERVICE_SOURCE = ROOT / "ops/linux/ihear-web.service"


def run(*argv):
    return subprocess.run(argv, check=True, text=True, capture_output=True).stdout


def install(source, destination, mode=0o644):
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    os.chown(destination, 0, 0)
    destination.chmod(mode)


def validate_private_login(login):
    if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9_.+@-]+", login):
        raise RuntimeError("The current private-network owner login is invalid.")
    return login


def render_private_nginx(template, login):
    login = validate_private_login(login)
    quoted_placeholder = f'"{PRIVATE_LOGIN_PLACEHOLDER}"'
    if template.count(PRIVATE_LOGIN_PLACEHOLDER) != 1 or template.count(quoted_placeholder) != 1:
        raise RuntimeError("The private nginx template must contain one quoted login placeholder.")
    return template.replace(quoted_placeholder, f'"{login}"')


def canonical_node_binary(link=WEB_NODE_LINK):
    try:
        resolved = Path(link).resolve(strict=True)
        metadata = resolved.stat()
    except OSError as error:
        raise RuntimeError("The dedicated Node.js binary is missing or unreadable.") from error
    if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
        raise RuntimeError("The dedicated Node.js binary must resolve to an executable regular file.")
    return resolved


def render_web_service(template, node_binary):
    node_binary = str(Path(node_binary))
    if (
        not Path(node_binary).is_absolute()
        or not re.fullmatch(r"/[A-Za-z0-9_./+-]+", node_binary)
        or ".." in Path(node_binary).parts
    ):
        raise RuntimeError("The canonical Node.js binary path is invalid.")
    if template.count(WEB_NODE_PLACEHOLDER) != 1:
        raise RuntimeError("The web service template must contain one Node.js binary placeholder.")
    return template.replace(WEB_NODE_PLACEHOLDER, node_binary)


def validate_operator_secret(path, expected_uid):
    try:
        metadata = Path(path).lstat()
    except OSError as error:
        raise RuntimeError("The protected application environment file is missing or unreadable.") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("The protected application environment must be a regular non-symlink file.")
    if stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != expected_uid:
        raise RuntimeError("The protected application environment must be operator-owned with mode 0600.")


def ensure_web_account():
    try:
        account = pwd.getpwnam(WEB_USER)
    except KeyError:
        run(
            "useradd",
            "--system",
            "--user-group",
            "--no-create-home",
            "--home-dir",
            "/nonexistent",
            "--shell",
            "/usr/sbin/nologin",
            WEB_USER,
        )
        account = pwd.getpwnam(WEB_USER)
    try:
        primary_group = grp.getgrgid(account.pw_gid)
        group_ids = set(os.getgrouplist(WEB_USER, account.pw_gid))
    except (KeyError, OSError) as error:
        raise RuntimeError("The dedicated web account group configuration is invalid.") from error
    if (
        account.pw_name != WEB_USER
        or account.pw_uid <= 0
        or account.pw_uid >= 1000
        or account.pw_dir != "/nonexistent"
        or account.pw_shell != "/usr/sbin/nologin"
        or primary_group.gr_name != WEB_USER
        or group_ids != {account.pw_gid}
    ):
        raise RuntimeError("The dedicated web account must be non-login and have no supplementary groups.")
    password_state = run("passwd", "-S", WEB_USER).split()
    if len(password_state) < 2 or password_state[0] != WEB_USER or password_state[1] != "L":
        raise RuntimeError("The dedicated web account password must remain locked.")


def ensure_web_mount_targets():
    for raw in ("/srv/ihear-web", "/opt/ihear"):
        path = Path(raw)
        path.mkdir(parents=True, exist_ok=True)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError("A dedicated web mount target is not a safe directory.")
        os.chown(path, 0, 0)
        path.chmod(0o755)
    node_target = Path("/opt/ihear/node")
    descriptor = os.open(
        node_target,
        os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o755,
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RuntimeError("The dedicated Node.js mount target is not a regular file.")
        os.fchown(descriptor, 0, 0)
        os.fchmod(descriptor, 0o755)
    finally:
        os.close(descriptor)


def install_content(content, destination, mode=0o600):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(destination, flags, mode)
    with os.fdopen(descriptor, "w") as stream:
        os.fchown(stream.fileno(), 0, 0)
        os.fchmod(stream.fileno(), mode)
        stream.write(content)


def main():
    if os.geteuid() != 0 or ROOT != Path("/home/ondrej/iHear"):
        raise SystemExit("Use sudo on the verified dedicated host and canonical runtime checkout.")
    try:
        operator = pwd.getpwnam("ondrej")
        validate_runtime_identity(RUNTIME_IDENTITY, expected_uid=operator.pw_uid)
        validate_operator_secret(ROOT / ".env.local", operator.pw_uid)
        node_binary = canonical_node_binary()
        web_service = render_web_service(WEB_SERVICE_SOURCE.read_text(), node_binary)
    except (KeyError, OSError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
    state = json.loads(run("tailscale", "status", "--json"))
    user_id = str(state["Self"]["UserID"])
    try:
        login = validate_private_login(state["User"][user_id]["LoginName"])
        nginx_config = render_private_nginx(
            (ROOT / "ops/monitor/nginx/ihear.conf.template").read_text(),
            login,
        )
    except (KeyError, OSError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
    container_names = run("docker", "ps", "-a", "--format", "{{.Names}}").splitlines()
    monitored = sorted({"ihear-worker-1", *(name for name in container_names if re.fullmatch(r"supabase_[a-z0-9_]+_iHear", name))})
    interfaces = sorted(path.name for path in Path("/sys/class/net").iterdir() if (path / "device").exists() and re.fullmatch(r"[A-Za-z0-9_.:-]+", path.name))
    if not interfaces:
        raise SystemExit("No physical network interface found; configure an explicit reviewed interface list.")
    try:
        pwd.getpwnam("ihear-monitor")
    except KeyError:
        run("useradd", "--system", "--no-create-home", "--home-dir", "/nonexistent", "--shell", "/usr/sbin/nologin", "ihear-monitor")
    try:
        ensure_web_account()
        ensure_web_mount_targets()
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
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
    system_units = [
        *(ROOT / "ops/monitor/systemd").glob("*"),
        *(source for source in (ROOT / "ops/linux").glob("*.service") if source != WEB_SERVICE_SOURCE),
    ]
    for source in system_units:
        install(source, Path("/etc/systemd/system") / source.name)
    install_content(web_service, "/etc/systemd/system/ihear-web.service", 0o644)
    install_content(nginx_config, "/etc/nginx/conf.d/ihear.conf", 0o600)
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
        stream.write(f"IHEAR_MONITOR_ALLOWED_LOGIN={login}\nIHEAR_MONITOR_DB=/var/lib/ihear-monitor/metrics.sqlite\nIHEAR_ACCESS_LOG=/var/log/ihear/access.jsonl\nIHEAR_DB_CONTAINER=supabase_db_iHear\nIHEAR_MONITOR_CONTAINERS={','.join(monitored)}\nIHEAR_MONITOR_NETWORK_INTERFACES={','.join(interfaces)}\n")
    env.chmod(0o600)
    run("systemd-analyze", "verify", "/etc/systemd/system/ihear-web.service")
    run("nginx", "-t")
    run("systemctl", "daemon-reload")
    print("Installed and validated iHear units, private proxy and monitor; activation is separate.")


if __name__ == "__main__":
    main()

import os

from pyinfra.context import host
from pyinfra.facts.server import LinuxName
from pyinfra.operations import apt, files, server, systemd

EXPORTER_VERSION = "0.10.3"
EXPORTER_USER = "fail2ban-exporter"
EXPORTER_GROUP = "fail2ban-exporter"

URL = f"https://gitlab.com/hctrdev/fail2ban-prometheus-exporter/-/releases/v{EXPORTER_VERSION}/downloads/fail2ban_exporter_{EXPORTER_VERSION}_linux_amd64.tar.gz"

BASE_DIR = "/opt/fail2ban_exporter"
TARBALL = f"{BASE_DIR}/fail2ban_exporter_{EXPORTER_VERSION}_linux_amd64.tar.gz"
BIN_PATH = "/usr/local/bin/fail2ban_exporter"
UNIT_PATH = "/etc/systemd/system/fail2ban_exporter.service"
TMP_DIR = "/tmp/fail2ban_exporter"

MIMIR_URL = os.environ["MIMIR_URL"]
MIMIR_USERNAME = os.environ["MIMIR_USERNAME"]
MIMIR_PASSWORD = os.environ["MIMIR_PASSWORD"]

F2B_SOCKET_GROUP = "fail2ban-access"
F2B_DROPIN_DIR = "/etc/systemd/system/fail2ban.service.d"
F2BE_DROPIN_DIR = "/etc/systemd/system/fail2ban_exporter.service.d"
F2B_DROPIN_PATH = f"{F2B_DROPIN_DIR}/10-exporter-socket-access.conf"
F2BE_DROPIN_PATH = f"{F2BE_DROPIN_DIR}/override.conf"

if host.get_fact(LinuxName) in ["Ubuntu", "Debian"]:
    # 1) Packages
    _ = apt.packages(
        name="Install fail2ban + curl",
        packages=["fail2ban", "curl"],
        update=True,
        _sudo=True,
    )

# 2) Exporter system user/group
_ = server.group(
    name="Create fail2ban socket access group",
    group=F2B_SOCKET_GROUP,
    system=True,
    _sudo=True,
)

_ = server.group(
    name="Create fail2ban socket access group",
    group=EXPORTER_GROUP,
    system=True,
    _sudo=True,
)

_ = server.user(
    name="Create exporter user",
    user=EXPORTER_USER,
    group=EXPORTER_GROUP,
    groups=[F2B_SOCKET_GROUP],  # allow reading/writing the socket via group perms
    system=True,
    shell="/usr/sbin/nologin",
    create_home=False,
    _sudo=True,
)

_ = files.directory(
    name="Delete fail2ban drop-in dir",
    path=F2B_DROPIN_DIR,
    present=False,
    _sudo=True,
)

_ = files.directory(
    name="Create fail2ban systemd drop-in dir",
    path=F2B_DROPIN_DIR,
    present=True,
    mode="0755",
    _sudo=True,
)

_ = files.file(
    name="Delete fail2ban override",
    path=F2B_DROPIN_PATH,
    present=False,
    _sudo=True,
)

dropin_op = files.put(
    name="Install fail2ban drop-in (socket permissions)",
    src="files/10-exporter-socket-access.conf",
    dest=F2BE_DROPIN_PATH,
    mode="0644",
    user="root",
    group="root",
    _sudo=True,
)

_ = systemd.daemon_reload(
    name="systemd daemon-reload (fail2ban drop-in)",
    _sudo=True,
)

_ = systemd.service(
    name="Restart fail2ban when drop-in changes",
    service="fail2ban",
    running=True,
    restarted=True,
    _if=dropin_op.did_change,
    _sudo=True,
)

# 3) Directories
_ = files.directory(
    name="Create exporter working dir",
    path=BASE_DIR,
    present=True,
    user="root",
    group="root",
    mode="0755",
    _sudo=True,
)  # files.directory manages directory state [page:0]

# 4) Download tarball (idempotent via cache_time unless force=True)
download_op = files.download(
    name="Download fail2ban_exporter tarball",
    src=URL,
    dest=TARBALL,
    mode="0644",
    _sudo=True,
)

# 5) Install/upgrade binary only when the tarball changed
_ = server.shell(
    name="Extract & install fail2ban_exporter binary",
    commands=[
        f'mkdir -p "{TMP_DIR}"',
        f'tar -C "{TMP_DIR}" -xzf {TARBALL}',
        # Handles either archive layouts: binary at root or under a top-level folder
        f'install -m 0755 "{TMP_DIR}/fail2ban_exporter" {BIN_PATH}',
        f'rm -rf "{TMP_DIR}"',
    ],
    _sudo=True,
    _if=download_op.did_change,
)

# 6) Install/refresh systemd unit
unit_create = files.put(
    name="Install fail2ban_exporter systemd unit",
    src="files/fail2ban_exporter.service",
    dest=UNIT_PATH,
    mode="0644",
    user="root",
    group="root",
    _sudo=True,
)  # files.put uploads unit content [page:0]

_ = systemd.service(
    name="Restart exporter when drop-in changes",
    service="fail2ban_exporter",
    running=True,
    restarted=True,
    _if=dropin_op.did_change or unit_create.did_change,
    _sudo=True,
)

# 7) systemd reload + enable/start (+ restart when new binary downloaded)
_ = systemd.daemon_reload(
    name="systemd daemon-reload",
    _if=unit_create.did_change,
    _sudo=True,
)  # daemon_reload reads updated unit files [page:1]

_ = systemd.service(
    name="Enable & start fail2ban_exporter",
    service="fail2ban_exporter",
    enabled=True,
    running=True,
    restarted=download_op.changed,  # restart only when a new tarball was downloaded
    _sudo=True,
)  # systemd.service manages enable/start/restart [page:1]

ALLOY_CONFIG = "/etc/alloy/config.alloy"

template_op = files.template(
    name="Render Alloy config",
    src="templates/config.alloy.j2",
    dest=ALLOY_CONFIG,
    mimir_username=MIMIR_USERNAME,
    mimir_password=MIMIR_PASSWORD,
    mimir_url=MIMIR_URL,
    _sudo=True,
)

_ = systemd.service(
    name="Restart alloy only if config changed",
    service="alloy",
    running=True,
    restarted=True,
    _if=template_op.did_change,  # preferred conditional style in pyinfra docs
    _sudo=True,
)

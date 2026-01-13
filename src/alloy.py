from dataclasses import dataclass, field
from io import StringIO
import os
from typing import Any, Callable, List, Optional

from pyinfra import logger
from pyinfra.context import host
from pyinfra.facts.server import LinuxName
from pyinfra.operations import apt, files, server, systemd

F2B_EXPORTER_VERSION = "0.10.3"
F2B_EXPORTER_USER = "fail2ban-exporter"
F2B_EXPORTER_GROUP = "fail2ban-exporter"

SMARTCTL_EXPORTER_VERSION = "0.14.0"

FAIL2BAN_EXPORTER_URL = f"https://gitlab.com/hctrdev/fail2ban-prometheus-exporter/-/releases/v{F2B_EXPORTER_VERSION}/downloads/fail2ban_exporter_{F2B_EXPORTER_VERSION}_linux_amd64.tar.gz"
SMARTCTL_EXPORTER_URL = f"https://github.com/prometheus-community/smartctl_exporter/releases/download/v{SMARTCTL_EXPORTER_VERSION}/smartctl_exporter-{SMARTCTL_EXPORTER_VERSION}.linux-amd64.tar.gz"

BASE_DIR = "/opt/fail2ban_exporter"
UNIT_PATH = "/etc/systemd/system/fail2ban_exporter.service"

MIMIR_URL = os.environ["MIMIR_URL"]
MIMIR_USERNAME = os.environ["MIMIR_USERNAME"]
MIMIR_PASSWORD = os.environ["MIMIR_PASSWORD"]

F2B_SOCKET_GROUP = "fail2ban-access"
F2B_DROPIN_DIR = "/etc/systemd/system/fail2ban.service.d"
F2BE_DROPIN_DIR = "/etc/systemd/system/fail2ban_exporter.service.d"
F2B_DROPIN_PATH = f"{F2B_DROPIN_DIR}/10-exporter-socket-access.conf"
F2BE_DROPIN_PATH = f"{F2BE_DROPIN_DIR}/override.conf"

@dataclass(frozen=True)
class JobSpec:
    address: str
    job_name: str

@dataclass(frozen=True)
class ExporterSpec:
    url: str
    name: str
    version:str
    ubuntu_prerequisites: list[str] = field(default_factory=list)
    template_args: dict[str, str] = field(default_factory=dict)
    func_dependencies: list[Callable] = field(default_factory=list)
    job_spec: Optional[JobSpec] = None


def fail2ban():
    if host.get_fact(LinuxName) in ["Ubuntu", "Debian"]:
        # 1) Packages
        _ = apt.packages(
            name="Install fail2ban",
            packages=["fail2ban"],
            present=True,
            _sudo=True,
        )

    # 2) Exporter system user/group
    _ = server.group(
        name="Create fail2ban socket access group",
        group=F2B_SOCKET_GROUP,
        system=True,
        _sudo=True,
    )

    _ = server.user(
        name="Create exporter user",
        user=F2B_EXPORTER_USER,
        group=F2B_EXPORTER_GROUP,
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

def alloy_override():
    unit = "alloy.service"
    dropin_file = f"/etc/systemd/system/{unit}.d/override.conf"

    tpl = StringIO("[Service]\nUser=root\n")

    override_op = files.template(
        src=tpl, dest=dropin_file, group="root", mode="644", user="root"
    )

    _ = systemd.daemon_reload(_if=override_op.did_change)
    _ = systemd.service(
        service=unit, running=True, restarted=True, _if=override_op.did_change, enabled=True
    )


def install_exporter(
    url: str,
    bin_name: str,
    ubuntu_prerequisites: List[str],
    func_dependencies: list[Callable],
    version:str
):

    for dep in func_dependencies:
        dep()

    if host.get_fact(LinuxName) in ["Ubuntu", "Debian"]:
        # 1) Packages
        _ = apt.packages(
            name=f"Install {bin_name} prerequisites if Ubuntu/Debian Machine",
            packages=ubuntu_prerequisites,
            present=True,
            _sudo=True,
        )

    # 3) Directories
    _ = files.directory(
        name="Create exporter working dir",
        path=f"/opt/{bin_name}",
        present=True,
        user="root",
        group="root",
        mode="0755",
        _sudo=True,
    )  # files.directory manages directory state [page:0]
    tarball = f'/opt/{bin_name}/{bin_name}_{version}_linux_amd64.tar.gz'
    # 4) Download tarball (idempotent via cache_time unless force=True)
    download_op = files.download(
        name=f"Download {bin_name} tarball",
        src=url,
        dest=tarball,
        mode="0644",
        _sudo=True,
    )

    # 5) Install/upgrade binary only when the tarball changed
    tmp_dir = f"/tmp/{bin_name}"
    _ = server.shell(
        name=f"Extract & install {bin_name} binary",
        commands=[
            f'rm -rf "{tmp_dir}"',
            f'rm -rf "/usr/local/bin/{bin_name}"',
            f'mkdir -p "{tmp_dir}"',
            f'tar -C "{tmp_dir}" -xzf "{tarball}"',
            f'find /tmp/{bin_name} -executable -iname "{bin_name}" -type f -exec mv {{}} /usr/local/bin/{bin_name} \\;',
            f'rm -rf "{tmp_dir}"',
        ],
        _sudo=True,
        _if=download_op.did_change
    )

    # 6) Install/refresh systemd unit
    unit_create = files.put(
        name=f"Install {bin_name} systemd unit",
        src=f"files/{bin_name}.service",
        dest=f"/etc/systemd/system/{bin_name}.service",
        mode="0644",
        user="root",
        group="root",
        _sudo=True,
    )  # files.put uploads unit content [page:0]

    _ = systemd.service(
        name="Restart exporter when drop-in changes",
        service=bin_name,
        running=True,
        restarted=True,
        _if=unit_create.did_change,
        _sudo=True,
    )

    _ = systemd.daemon_reload(
        name="systemd daemon-reload",
        _if=unit_create.did_change,
        _sudo=True,
    )  # daemon_reload reads updated unit files [page:1]

    _ = systemd.service(
        name=f"Enable & start {bin_name}",
        service=bin_name,
        enabled=True,
        running=True,
        restarted=download_op.changed,  # restart only when a new tarball was downloaded
        _sudo=True,
    )  # systemd.service manages enable/start/restart [page:1]

    return (unit_create, download_op)


exporters = [
    ExporterSpec(
        url=FAIL2BAN_EXPORTER_URL,
        name="fail2ban_exporter",
        template_args={
            "mimir_username": MIMIR_USERNAME,
            "mimir_password": MIMIR_PASSWORD,
            "mimir_url": MIMIR_URL,
        },
        func_dependencies=[fail2ban],
        job_spec=JobSpec("127.0.0.1:9191", "fail2ban"),
        version=F2B_EXPORTER_VERSION
    ),
    ExporterSpec(
        url=SMARTCTL_EXPORTER_URL,
        name="smartctl_exporter",
        ubuntu_prerequisites=["smartmontools"],
        job_spec=JobSpec("127.0.0.1:9633", "smartmontools"),
        version=SMARTCTL_EXPORTER_VERSION,
        func_dependencies=[alloy_override]
  ),
]

for exporter in exporters:
    install_exporter(
        url=exporter.url,
        bin_name=exporter.name,
        ubuntu_prerequisites=exporter.ubuntu_prerequisites,
        func_dependencies=exporter.func_dependencies,
        version=exporter.version
    )

# 7) systemd reload + enable/start (+ restart when new binary downloaded)

ALLOY_CONFIG = "/etc/alloy/config.alloy"

merged_args: dict[str, Any] = {}
job_specs: List[JobSpec] = []
for obj in exporters:
    merged_args |= obj.template_args
    if not obj.job_spec is None:
        job_specs.append(obj.job_spec)
merged_args["job_specs"] = job_specs

logger.debug(f"merged args: {merged_args}")

template_op = files.template(
    name="Render Alloy config",
    src="templates/config.alloy.j2",
    dest=ALLOY_CONFIG,
    _sudo=True,
    **merged_args,
)

_ = systemd.service(
    name="Restart alloy only if config changed",
    service="alloy",
    running=True,
    restarted=True,
    _if=template_op.did_change,  # preferred conditional style in pyinfra docs
    _sudo=True,
)

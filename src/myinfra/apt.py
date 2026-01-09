from pyinfra import logger
from pyinfra.context import config, host
from pyinfra.facts.server import LinuxName, RebootRequired, Which
from pyinfra.operations import apt, docker, files, pacman

config.SUDO = True
config.PARALLEL = 3

if host.get_fact(LinuxName) in ["Ubuntu", "Debian"]:
    _ = apt.update(name="Update apt repos", _sudo=True)
    _ = apt.dist_upgrade(_sudo=True)
    _ = apt.packages(
        name="Install unattended-upgrades",
        packages=["unattended-upgrades"],
        update=True,
        present=True,
        _sudo=True,
    )
    for origin in ("updates", "proposed", "backports"):
        _ = files.line(
            path="/etc/apt/apt.conf.d/50unattended-upgrades",
            line=r'^\s*//\s*"${distro_id}:${distro_codename}-' + origin + '";',
            replace='"${distro_id}:${distro_codename}-' + origin + '";',
            name="Enable unattended upgrades",
            _sudo=True,
        )

if host.get_fact(LinuxName) in ["Arch", "Manjaro Linux", "EndeavourOS", "CachyOS"]:
    _ = pacman.update()
    _ = pacman.upgrade()
    _ = pacman.packages(packages=["docker"], present=True)

if host.get_fact(Which, "docker"):
    _ = docker.prune(_sudo=True)

if host.get_fact(RebootRequired):
    logger.info("Reboot required")

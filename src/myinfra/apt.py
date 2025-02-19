from pyinfra import logger
from pyinfra.context import config, host
from pyinfra.facts.files import File
from pyinfra.facts.server import LinuxName
from pyinfra.operations import apt, pacman, server

config.SUDO = True
config.PARALLEL = 3

if host.get_fact(LinuxName) in ["Ubuntu", "Debian"]:
    apt.update(
        name="Update apt repos",
    )
    apt.dist_upgrade()
    if host.get_fact(File, "/var/run/reboot-required") is not None:
        logger.info("Reboot required!")

if host.get_fact(LinuxName) in ["Arch", "Manjaro Linux", "EndeavourOS"]:
    pacman.update()
    pacman.upgrade()
    pacman.packages(packages=["docker"], present=True)

docker_installed, _ = host.run_shell_command("which docker")

if docker_installed:
    server.shell(name="Docker container prune", commands=["docker container prune -f"])
    server.shell(name="Docker image prune", commands=["docker image prune -af"])

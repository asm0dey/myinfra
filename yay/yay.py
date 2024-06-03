"""
Manage yay packages. (Arch Linux package manager)
"""

from pyinfra import host
from pyinfra.api import operation
from pyinfra.operations.util.packaging import ensure_packages

from .facts import YayPackages, YayUnpackGroup


@operation(is_idempotent=False)
def upgrade():
    """
    Upgrades all yay packages.
    """

    yield "yay --noconfirm -Su"


_upgrade = upgrade  # noqa: E305


@operation(is_idempotent=False)
def update():
    """
    Updates yay repositories.
    """

    yield "yay -Sy"


_update = update  # noqa: E305


@operation
def packages(
    packages=None,
    present=True,
    update=False,
    upgrade=False,
):
    """
    Add/remove yay packages.

    + packages: list of packages to ensure
    + present: whether the packages should be installed
    + update: run ``yay -Sy`` before installing packages
    + upgrade: run ``yay -Su`` before installing packages

    Versions:
        Package versions can be pinned like yay: ``<pkg>=<version>``.

    **Example:**

    .. code:: python

        yay.packages(
            name="Install Vim and a plugin",
            packages=["vim-fugitive", "vim"],
            update=True,
        )
    """

    if update:
        yield from _update()

    if upgrade:
        yield from _upgrade()

    yield from ensure_packages(
        host,
        packages,
        host.get_fact(YayPackages),
        present,
        install_command="yay --noconfirm -S",
        uninstall_command="yay --noconfirm -R",
        expand_package_fact=lambda package: host.get_fact(
            YayUnpackGroup,
            name=package,
        ),
    )

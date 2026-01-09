from io import StringIO

from pyinfra.context import config
from pyinfra.operations import files, systemd

config.SUDO = True
config.PARALLEL = 3

unit = "alloy.service"
dropin_file = f"/etc/systemd/system/{unit}.d/override.conf"

tpl = StringIO("[Service]\nUser={{ needed_user }}\n")

override_op = files.template(
    src=tpl, dest=dropin_file, group="root", mode="644", user="root", needed_user="root"
)

_ = systemd.daemon_reload(_if=override_op.did_change)
_ = systemd.service(
    service=unit, running=True, restarted=True, _if=override_op.did_change, enabled=True
)

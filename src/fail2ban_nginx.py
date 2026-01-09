from io import StringIO

from pyinfra import host
from pyinfra.facts.server import Which
from pyinfra.operations import apt, files, server

# —————————————————————————
# Ensure fail2ban is installed (optional)
# —————————————————————————

_ = apt.packages(
    name="Install fail2ban only (nginx conditional later)",
    packages=["fail2ban"],
    update=True,
    present=True,
    _sudo=True,
)

# —————————————————————————
# Only proceed if nginx is installed
# —————————————————————————
nginx_path = host.get_fact(Which, command="nginx")
if nginx_path:
    # nginx is installed

    # (Optional) ensure nginx service is running/enabled
    _ = server.service(
        name="Ensure nginx is running & enabled",
        service="nginx",
        running=True,
        enabled=True,
        restarted=True,
        _sudo=True,
    )

    # Deploy the basic fail2ban jail for nginx
    fail2ban_jail_local = StringIO("""
[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 3
    """)

    _ = files.put(
        name="Deploy Fail2ban nginx jail.local",
        src=fail2ban_jail_local,
        dest="/etc/fail2ban/jail.d/nginx.local",
        _sudo=True,
        mode="644",
    )

    # Ensure fail2ban is running
    _ = server.service(
        name="Ensure fail2ban is running & enabled",
        service="fail2ban",
        running=True,
        enabled=True,
        restarted=True,
        _sudo=True,
    )

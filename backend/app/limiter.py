import ipaddress

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    """Rate-limit key: the real viewer's IP.

    In production the API sits behind CloudFront -> Caddy, so the TCP peer is a proxy.
    CloudFront is configured (infra/bootstrap.sh) to forward CloudFront-Viewer-Address
    ("ip:port"), a header CloudFront sets itself — viewer-supplied CloudFront-* headers
    are discarded — so it's the trustworthy source. Locally the header is absent and we
    fall back to the socket address.
    """
    addr = request.headers.get("cloudfront-viewer-address")
    if addr:
        host = addr.rsplit(":", 1)[0].strip("[]")  # IPv6 arrives as "[::1]:port"
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            # A single IPv6 allocation hands out /64s (or more) for free, so keying
            # on the full address would let one machine mint unlimited limit keys.
            # IPv4 is scarce enough to key exactly.
            if ip.version == 6:
                return str(ipaddress.ip_network(f"{ip}/64", strict=False))
            return str(ip)
    return get_remote_address(request)


# key_style="endpoint" is load-bearing, not a style choice. slowapi's default is
# "url", which builds each limit bucket from the CONCRETE request path — so
# /claude/analyze/aspas/lev and /claude/analyze/tenz/na1 get separate quotas and
# the per-IP limit never aggregates. Every expensive route takes the player name
# in the path, so the default let anyone bypass the limits (and spend our
# Anthropic credits and Riot quota) just by varying the Riot ID. Keying on the
# view function instead makes the limit per-person-per-route as intended.
# Verified: with "url", 17 requests across varied paths all returned 200.
limiter = Limiter(key_func=client_ip, key_style="endpoint")

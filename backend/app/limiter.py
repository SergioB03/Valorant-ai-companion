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
            return str(ipaddress.ip_address(host))
        except ValueError:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip)

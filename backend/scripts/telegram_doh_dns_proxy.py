"""Tiny UDP DNS stub that answers via Cloudflare DoH (for TG-3 cloudflared).

Needed when local/VPN resolvers NXDOMAIN SRV for argotunnel.com while DoH works.
Listens on 127.0.0.1:5353 by default. No secrets.
"""

from __future__ import annotations

import argparse
import socket
import struct
import threading

import dns.message
import dns.query
import dns.rdatatype
import httpx

DOH = "https://cloudflare-dns.com/dns-query"


def _doh_resolve(request: dns.message.Message) -> dns.message.Message:
    wire = request.to_wire()
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(
            DOH,
            content=wire,
            headers={
                "accept": "application/dns-message",
                "content-type": "application/dns-message",
            },
        )
        resp.raise_for_status()
        return dns.message.from_wire(resp.content)


def handle(data: bytes, addr, sock: socket.socket) -> None:
    try:
        req = dns.message.from_wire(data)
        ans = _doh_resolve(req)
        sock.sendto(ans.to_wire(), addr)
    except Exception as exc:  # noqa: BLE001
        # Best-effort SERVFAIL
        try:
            req = dns.message.from_wire(data)
            resp = dns.message.make_response(req)
            resp.set_rcode(dns.rcode.SERVFAIL)
            sock.sendto(resp.to_wire(), addr)
        except Exception:  # noqa: BLE001
            pass
        print(f"dns_proxy_error from={addr[0]} err={type(exc).__name__}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5353)
    args = parser.parse_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    print(f"doh_dns_proxy listening={args.host}:{args.port}")
    while True:
        data, addr = sock.recvfrom(4096)
        threading.Thread(target=handle, args=(data, addr, sock), daemon=True).start()


if __name__ == "__main__":
    raise SystemExit(main())

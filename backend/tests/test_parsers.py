from __future__ import annotations

import base64
import json

import pytest

from app.services.rules import validate_rule_payload_lines
from app.services.subscriptions import _parse_remote_subscription_payload


def test_subscription_parser_accepts_proxies() -> None:
    data = _parse_remote_subscription_payload("proxies:\n  - name: a\n    type: socks5\n")
    assert isinstance(data, list)
    assert data[0]["name"] == "a"


def test_subscription_parser_rejects_missing_proxies() -> None:
    with pytest.raises(Exception):
        _parse_remote_subscription_payload("proxy-providers:\n  a: {}\n")


def test_subscription_parser_accepts_base64_uri_subscription() -> None:
    vmess_json = {
        "v": "2",
        "ps": "vmess node",
        "add": "vmess.example.com",
        "port": "443",
        "id": "11111111-1111-1111-1111-111111111111",
        "aid": "0",
        "scy": "auto",
        "net": "ws",
        "type": "none",
        "host": "cdn.example.com",
        "path": "/ws?ed=2048",
        "tls": "tls",
        "sni": "sni.example.com",
    }
    links = "\n".join(
        [
            "ss://YWVzLTI1Ni1nY206cGFzcw@example.com:8388#ss node",
            f"vmess://{_b64(json.dumps(vmess_json))}",
        ]
    )

    proxies = _parse_remote_subscription_payload(_b64(links))

    assert [proxy["type"] for proxy in proxies] == ["ss", "vmess"]
    assert proxies[0]["cipher"] == "aes-256-gcm"
    assert proxies[0]["password"] == "pass"
    assert proxies[1]["name"] == "vmess node"
    assert proxies[1]["network"] == "ws"
    assert proxies[1]["ws-opts"]["max-early-data"] == 2048


def test_subscription_parser_accepts_supported_uri_schemes() -> None:
    links = "\n".join(
        [
            "ss://YWVzLTI1Ni1nY206cGFzcw@example.com:8388#ss",
            f"ssr://{_b64('ssr.example.com:8388:auth_sha1_v4:aes-128-gcm:tls1.2_ticket_auth:' + _b64('pass') + '/?remarks=' + _b64('ssr'))}",
            "vmess://11111111-1111-1111-1111-111111111111@vmess.example.com:443?security=tls&type=grpc&serviceName=svc#vmess",
            "vless://11111111-1111-1111-1111-111111111111@vless.example.com:443?security=reality&sni=site.example.com&pbk=pub&sid=short&type=xhttp&path=%2Fx#vless",
            "trojan://secret@trojan.example.com:443?sni=site.example.com&type=ws&path=%2Fws&host=cdn.example.com#trojan",
            "hysteria://hy.example.com:443?auth=token&peer=site.example.com&upmbps=10&downmbps=50#hy",
            "hy2://pass@hy2.example.com:443?sni=site.example.com&obfs=salamander&obfs-password=obfs#hy2",
            "tuic://11111111-1111-1111-1111-111111111111:pass@tuic.example.com:443?congestion_control=bbr&sni=site.example.com#tuic",
            "anytls://pass@anytls.example.com:443?sni=site.example.com#anytls",
        ]
    )

    proxies = _parse_remote_subscription_payload(links)

    assert [proxy["type"] for proxy in proxies] == [
        "ss",
        "ssr",
        "vmess",
        "vless",
        "trojan",
        "hysteria",
        "hysteria2",
        "tuic",
        "anytls",
    ]
    assert proxies[3]["reality-opts"] == {"public-key": "pub", "short-id": "short"}
    assert proxies[7]["congestion-controller"] == "bbr"


def test_rule_ipcidr_validator() -> None:
    out = validate_rule_payload_lines("ipcidr", ["10.0.0.0/8", "192.168.1.0/24"])
    assert len(out) == 2


def test_rule_ipcidr_validator_rejects_invalid() -> None:
    with pytest.raises(Exception):
        validate_rule_payload_lines("ipcidr", ["bad-cidr"])


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode().rstrip("=")

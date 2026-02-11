from __future__ import annotations

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


def test_rule_ipcidr_validator() -> None:
    out = validate_rule_payload_lines("ipcidr", ["10.0.0.0/8", "192.168.1.0/24"])
    assert len(out) == 2


def test_rule_ipcidr_validator_rejects_invalid() -> None:
    with pytest.raises(Exception):
        validate_rule_payload_lines("ipcidr", ["bad-cidr"])

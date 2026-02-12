from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_filtered_group_preview_endpoint_uses_backend_logic(client, admin_headers):
    sub1 = await client.post(
        "/api/admin/subscriptions",
        headers=admin_headers,
        json={
            "name": "sub-1",
            "mode": "manual",
            "proxy_yaml_object_text": (
                "name: hk-node\ntype: socks5\nserver: 1.1.1.1\nport: 1080\n"
            ),
        },
    )
    assert sub1.status_code == 200, sub1.text
    sub1_id = sub1.json()["id"]

    sub2 = await client.post(
        "/api/admin/subscriptions",
        headers=admin_headers,
        json={
            "name": "Sub 2",
            "mode": "manual",
            "proxy_yaml_object_text": (
                "name: hk-node\ntype: socks5\nserver: 2.2.2.2\nport: 1081\n"
            ),
        },
    )
    assert sub2.status_code == 200, sub2.text
    sub2_id = sub2.json()["id"]

    preview = await client.post(
        "/api/admin/main-configs/filtered-groups/preview",
        headers=admin_headers,
        json={
            "filtered_groups": [
                {
                    "name": "HK",
                    "rules": [
                        {
                            "subscription_source_id": sub1_id,
                            "regex_pattern": "hk-node",
                            "regex_flags": "",
                            "position": 1,
                        },
                        {
                            "subscription_source_id": sub2_id,
                            "regex_pattern": "hk-node",
                            "regex_flags": "",
                            "position": 2,
                        },
                    ],
                }
            ],
        },
    )
    assert preview.status_code == 200, preview.text
    data = preview.json()

    groups = data["groups"]
    assert len(groups) == 1
    assert groups[0]["name"] == "HK"
    assert groups[0]["issues"] == []
    assert groups[0]["matched_proxy_names"] == ["hk-node", "hk-node@sub-2"]


@pytest.mark.asyncio
async def test_generation_flow_manual_sources(client, admin_headers):
    sub_response = await client.post(
        "/api/admin/subscriptions",
        headers=admin_headers,
        json={
            "name": "sub-1",
            "mode": "manual",
            "proxy_yaml_object_text": "name: node-a\ntype: socks5\nserver: 1.1.1.1\nport: 1080\n",
        },
    )
    assert sub_response.status_code == 200, sub_response.text
    subscription_id = sub_response.json()["id"]

    rule_response = await client.post(
        "/api/admin/rules",
        headers=admin_headers,
        json={
            "name": "rule-1",
            "mode": "manual",
            "behavior": "domain",
            "payload_lines": [".example.com", ".example.org"],
        },
    )
    assert rule_response.status_code == 200, rule_response.text
    rule_id = rule_response.json()["id"]

    config_response = await client.post(
        "/api/admin/main-configs",
        headers=admin_headers,
        json={
            "name": "cfg-1",
            "password_plain": "pw1",
            "base_config_yaml": "mixed-port: 7890\nmode: rule\n",
            "final_target_type": "DIRECT",
        },
    )
    assert config_response.status_code == 200, config_response.text
    config_id = config_response.json()["id"]

    builder_payload = {
        "filtered_groups": [
            {
                "name": "FG-A",
                "position": 1,
                "group_mode": "select",
                "rules": [
                    {
                        "subscription_source_id": subscription_id,
                        "regex_pattern": ".*",
                        "regex_flags": "",
                        "position": 1,
                    }
                ],
            }
        ],
        "manual_groups": [
            {
                "name": "MG-A",
                "position": 1,
                "group_mode": "select",
                "members": [
                    {
                        "member_type": "filtered_group",
                        "member_ref": "FG-A",
                        "position": 1,
                    }
                ],
            }
        ],
        "dialer_override_rules": [],
        "shunt_bindings": [
            {
                "position": 1,
                "binding_name": "SHUNT-1",
                "rule_source_id": rule_id,
                "default_group_name": "FG-A",
                "no_resolve": False,
            }
        ],
    }

    put_builder_response = await client.put(
        f"/api/admin/main-configs/{config_id}/builder",
        headers=admin_headers,
        json=builder_payload,
    )
    assert put_builder_response.status_code == 200, put_builder_response.text

    artifact_response = await client.get(
        f"/api/public/configs/{config_id}/artifact",
        params={"password": "pw1"},
    )
    assert artifact_response.status_code == 200, artifact_response.text
    artifact = artifact_response.text

    assert "proxy-groups:" in artifact
    assert "rule-providers:" in artifact
    assert "MATCH,DIRECT" in artifact

    rule_payload_response = await client.get(
        f"/api/public/configs/{config_id}/rules/{rule_id}.yaml",
        params={"password": "pw1"},
    )
    assert rule_payload_response.status_code == 200, rule_payload_response.text
    assert "payload:" in rule_payload_response.text

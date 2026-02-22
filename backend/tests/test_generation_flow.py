from __future__ import annotations

import pytest

from app.yaml import yaml_load


@pytest.mark.asyncio
async def test_filtered_group_preview_endpoint_uses_backend_logic(client, admin_headers):
    sub1 = await client.post(
        "/api/admin/subscriptions",
        headers=admin_headers,
        json={
            "name": "sub-1",
            "mode": "manual",
            "proxy_yaml_object_text": (
                "- name: hk-node\n  type: socks5\n  server: 1.1.1.1\n  port: 1080\n"
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
                "- name: hk-node\n  type: socks5\n  server: 2.2.2.2\n  port: 1081\n"
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
    assert len(groups[0]["rule_results"]) == 2
    assert groups[0]["rule_results"][0]["matched_proxy_names"] == ["hk-node"]
    assert groups[0]["rule_results"][0]["issue"] is None
    assert groups[0]["rule_results"][1]["matched_proxy_names"] == ["hk-node@sub-2"]
    assert groups[0]["rule_results"][1]["issue"] is None


@pytest.mark.asyncio
async def test_generation_flow_manual_sources(client, admin_headers):
    sub_response = await client.post(
        "/api/admin/subscriptions",
        headers=admin_headers,
        json={
            "name": "sub-1",
            "mode": "manual",
            "proxy_yaml_object_text": "- name: node-a\n  type: socks5\n  server: 1.1.1.1\n  port: 1080\n",
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
            "base_config_yaml": "mixed-port: 7890\nmode: rule\n",
            "final_target_type": "DIRECT",
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
        },
    )
    assert config_response.status_code == 200, config_response.text
    config_data = config_response.json()
    config_id = config_data["id"]

    assert len(config_data["filtered_groups"]) == 1
    assert config_data["route_template_id"] is None

    # create route template and assign it
    template_response = await client.post(
        "/api/admin/route-templates",
        headers=admin_headers,
        json={
            "name": "tmpl-1",
            "slots": [{"name": "FG-A", "position": 1}],
            "bindings": [
                {
                    "position": 1,
                    "binding_name": "ROUTE-1",
                    "rule_source_id": rule_id,
                    "default_target": "FG-A",
                    "no_resolve": False,
                }
            ],
        },
    )
    assert template_response.status_code == 200, template_response.text
    template_id = template_response.json()["id"]

    update_response = await client.put(
        f"/api/admin/main-configs/{config_id}",
        headers=admin_headers,
        json={
            "route_template_id": template_id,
            "slot_mappings": [{"slot_name": "FG-A", "group_name": "FG-A"}],
        },
    )
    assert update_response.status_code == 200, update_response.text

    artifact_response = await client.get(
        f"/api/public/configs/{config_id}/artifact",
    )
    assert artifact_response.status_code == 200, artifact_response.text
    artifact = artifact_response.text

    assert "proxy-groups:" in artifact
    assert "rule-providers:" in artifact
    assert "MATCH,Final" in artifact

    rule_payload_response = await client.get(
        f"/api/public/rules/{rule_id}.yaml",
    )
    assert rule_payload_response.status_code == 200, rule_payload_response.text
    assert "payload:" in rule_payload_response.text


@pytest.mark.asyncio
async def test_copy_nodes_isolates_dialer_override(client, admin_headers):
    sub = await client.post(
        "/api/admin/subscriptions",
        headers=admin_headers,
        json={
            "name": "shared-sub",
            "mode": "manual",
            "proxy_yaml_object_text": (
                "- name: shared-node\n  type: socks5\n  server: 1.1.1.1\n  port: 1080\n"
            ),
        },
    )
    assert sub.status_code == 200, sub.text
    sub_id = sub.json()["id"]

    rule = await client.post(
        "/api/admin/rules",
        headers=admin_headers,
        json={
            "name": "dummy-rule",
            "mode": "manual",
            "behavior": "domain",
            "payload_lines": [".example.com"],
        },
    )
    assert rule.status_code == 200, rule.text
    rule_id = rule.json()["id"]

    template = await client.post(
        "/api/admin/route-templates",
        headers=admin_headers,
        json={
            "name": "copy-nodes-tmpl",
            "slots": [{"name": "Direct", "position": 1}],
            "bindings": [
                {
                    "position": 1,
                    "binding_name": "Test",
                    "rule_source_id": rule_id,
                    "default_target": "Direct",
                    "no_resolve": False,
                }
            ],
        },
    )
    assert template.status_code == 200, template.text
    template_id = template.json()["id"]

    config = await client.post(
        "/api/admin/main-configs",
        headers=admin_headers,
        json={
            "name": "copy-nodes-test",
            "base_config_yaml": "mixed-port: 7890\nmode: rule\n",
            "final_target_type": "DIRECT",
            "filtered_groups": [
                {
                    "name": "Direct",
                    "position": 1,
                    "group_mode": "select",
                    "copy_nodes": False,
                    "rules": [
                        {
                            "subscription_source_id": sub_id,
                            "regex_pattern": ".*",
                            "regex_flags": "",
                            "position": 1,
                        }
                    ],
                },
                {
                    "name": "Relay",
                    "position": 2,
                    "group_mode": "select",
                    "copy_nodes": True,
                    "rules": [
                        {
                            "subscription_source_id": sub_id,
                            "regex_pattern": ".*",
                            "regex_flags": "",
                            "position": 1,
                        }
                    ],
                },
            ],
            "manual_groups": [],
            "dialer_override_rules": [
                {
                    "filtered_group_name": "Relay",
                    "dialer_group_name": "Direct",
                }
            ],
            "route_template_id": template_id,
            "slot_mappings": [{"slot_name": "Direct", "group_name": "Direct"}],
        },
    )
    assert config.status_code == 200, config.text
    config_id = config.json()["id"]

    artifact = await client.get(
        f"/api/public/configs/{config_id}/artifact",
    )
    assert artifact.status_code == 200, artifact.text

    parsed = yaml_load(artifact.text)
    proxy_names = [p["name"] for p in parsed["proxies"]]
    assert "shared-node" in proxy_names
    assert "shared-node [Relay]" in proxy_names

    proxy_map = {p["name"]: p for p in parsed["proxies"]}
    assert "dialer-proxy" not in proxy_map["shared-node"]
    assert proxy_map["shared-node [Relay]"]["dialer-proxy"] == "Direct"

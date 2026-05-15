from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlsplit


Parser = Callable[[str, dict[str, int]], dict[str, Any]]


def parse_uri_subscription_payload(content: str) -> list[dict[str, Any]]:
    text = _decode_subscription_text(content)
    names: dict[str, int] = {}
    proxies: list[dict[str, Any]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        scheme, separator, _ = line.partition("://")
        if not separator:
            continue
        parser = _PARSERS.get(scheme.lower())
        if parser is None:
            continue
        try:
            proxies.append(parser(line, names))
        except (
            ValueError,
            TypeError,
            KeyError,
            binascii.Error,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ):
            continue

    if not proxies:
        raise ValueError("subscription has no supported URI proxy links")
    return proxies


def _decode_subscription_text(content: str) -> str:
    text = content.strip("\ufeff \t\r\n")
    if "://" in text:
        return text

    compact = "".join(text.split())
    decoded = _try_decode_base64_text(compact)
    if decoded and "://" in decoded:
        return decoded
    return text


def _try_decode_base64_text(value: str) -> str | None:
    if not value:
        return None
    try:
        return _decode_base64(value).decode()
    except (binascii.Error, UnicodeDecodeError):
        return None


def _decode_base64(value: str) -> bytes:
    normalized = value.strip().replace("-", "+").replace("_", "/")
    normalized += "=" * (-len(normalized) % 4)
    return base64.b64decode(normalized)


def _decode_urlsafe_base64(value: str) -> str:
    return _decode_base64(value).decode()


def _split_query(query: str) -> dict[str, list[str]]:
    return parse_qs(query, keep_blank_values=True)


def _q(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key)
    return values[0] if values else ""


def _q_any(query: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        value = _q(query, key)
        if value != "":
            return value
    return ""


def _bool(value: str) -> bool:
    return value.lower() in {"1", "t", "true", "y", "yes"}


def _port(value: Any) -> int | str:
    if isinstance(value, int):
        return value
    text = str(value)
    if not text:
        raise ValueError("port is required")
    return int(text) if text.isdigit() else text


def _url_port(parts: Any, default: int | None = None) -> int | str:
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("invalid port") from exc
    if port is None:
        if default is None:
            raise ValueError("port is required")
        return default
    return port


def _hostname(parts: Any) -> str:
    host = parts.hostname
    if not host:
        raise ValueError("hostname is required")
    return host


def _username(parts: Any) -> str:
    return unquote(parts.username or "")


def _password(parts: Any) -> str:
    return unquote(parts.password or "")


def _raw_userinfo(parts: Any) -> str:
    if "@" not in parts.netloc:
        return ""
    return unquote(parts.netloc.rsplit("@", 1)[0])


def _name(names: dict[str, int], raw: str, fallback: str) -> str:
    base = unquote(raw).strip() or fallback
    index = names.get(base)
    if index is None:
        names[base] = 0
        return base
    index += 1
    names[base] = index
    return f"{base}-{index:02d}"


def _fallback(scheme: str, server: str, port: Any) -> str:
    return f"{scheme}-{server}:{port}"


def _set(proxy: dict[str, Any], key: str, value: Any) -> None:
    if value not in (None, ""):
        proxy[key] = value


def _set_int(proxy: dict[str, Any], key: str, value: str) -> None:
    if value:
        proxy[key] = _port(value)


def _alpn(value: str) -> list[str]:
    return [item for item in value.split(",") if item]


def _parse_hysteria(line: str, names: dict[str, int]) -> dict[str, Any]:
    parts = urlsplit(line)
    query = _split_query(parts.query)
    server = _hostname(parts)
    port = _url_port(parts)
    proxy: dict[str, Any] = {
        "name": _name(names, parts.fragment, _fallback("hysteria", server, port)),
        "type": "hysteria",
        "server": server,
        "port": port,
        "skip-cert-verify": _bool(_q(query, "insecure")),
    }
    _set(proxy, "sni", _q(query, "peer"))
    _set(proxy, "obfs", _q(query, "obfs"))
    _set(proxy, "auth-str", _q(query, "auth"))
    _set(proxy, "protocol", _q(query, "protocol"))
    _set(proxy, "up", _q_any(query, "up", "upmbps"))
    _set(proxy, "down", _q_any(query, "down", "downmbps"))
    if alpn := _q(query, "alpn"):
        proxy["alpn"] = _alpn(alpn)
    return proxy


def _parse_hysteria2(line: str, names: dict[str, int]) -> dict[str, Any]:
    parts = urlsplit(line)
    query = _split_query(parts.query)
    server = _hostname(parts)
    port = _url_port(parts, default=443)
    proxy: dict[str, Any] = {
        "name": _name(names, parts.fragment, _fallback("hysteria2", server, port)),
        "type": "hysteria2",
        "server": server,
        "port": port,
        "skip-cert-verify": _bool(_q(query, "insecure")),
    }
    _set(proxy, "password", _raw_userinfo(parts))
    _set(proxy, "obfs", _q(query, "obfs"))
    _set(proxy, "obfs-password", _q(query, "obfs-password"))
    _set(proxy, "sni", _q(query, "sni"))
    _set(proxy, "fingerprint", _q(query, "pinSHA256"))
    _set(proxy, "up", _q(query, "up"))
    _set(proxy, "down", _q(query, "down"))
    _set(proxy, "ports", _q(query, "mport"))
    _set_int(proxy, "hop-interval", _q(query, "hop-interval"))
    if alpn := _q(query, "alpn"):
        proxy["alpn"] = _alpn(alpn)
    return proxy


def _parse_tuic(line: str, names: dict[str, int]) -> dict[str, Any]:
    parts = urlsplit(line)
    query = _split_query(parts.query)
    server = _hostname(parts)
    port = _url_port(parts)
    proxy: dict[str, Any] = {
        "name": _name(names, parts.fragment, _fallback("tuic", server, port)),
        "type": "tuic",
        "server": server,
        "port": port,
        "udp": True,
    }

    userinfo = _raw_userinfo(parts)
    if ":" in userinfo:
        uuid, password = userinfo.split(":", 1)
        _set(proxy, "uuid", uuid)
        _set(proxy, "password", password)
    else:
        _set(proxy, "token", userinfo)

    _set(proxy, "congestion-controller", _q_any(query, "congestion_control", "congestion-controller"))
    _set(proxy, "sni", _q(query, "sni"))
    _set(proxy, "udp-relay-mode", _q_any(query, "udp_relay_mode", "udp-relay-mode"))
    _set(proxy, "ip", _q(query, "ip"))
    _set_int(proxy, "heartbeat-interval", _q(query, "heartbeat-interval"))
    _set_int(proxy, "request-timeout", _q(query, "request-timeout"))
    _set_int(proxy, "max-udp-relay-packet-size", _q(query, "max-udp-relay-packet-size"))
    _set_int(proxy, "max-open-streams", _q(query, "max-open-streams"))
    if alpn := _q(query, "alpn"):
        proxy["alpn"] = _alpn(alpn)
    if _q(query, "disable_sni") == "1" or _bool(_q(query, "disable-sni")):
        proxy["disable-sni"] = True
    if _bool(_q(query, "reduce-rtt")):
        proxy["reduce-rtt"] = True
    if _bool(_q(query, "skip-cert-verify")):
        proxy["skip-cert-verify"] = True
    return proxy


def _parse_trojan(line: str, names: dict[str, int]) -> dict[str, Any]:
    parts = urlsplit(line)
    query = _split_query(parts.query)
    server = _hostname(parts)
    port = _url_port(parts)
    proxy: dict[str, Any] = {
        "name": _name(names, parts.fragment, _fallback("trojan", server, port)),
        "type": "trojan",
        "server": server,
        "port": port,
        "password": _username(parts),
        "udp": True,
        "skip-cert-verify": _bool(_q_any(query, "allowInsecure", "insecure")),
        "client-fingerprint": _q(query, "fp") or "chrome",
    }
    _set(proxy, "sni", _q(query, "sni"))
    if alpn := _q(query, "alpn"):
        proxy["alpn"] = _alpn(alpn)

    network = _q(query, "type").lower()
    if network:
        proxy["network"] = network
    if network == "ws":
        ws_opts: dict[str, Any] = {"path": _q(query, "path") or "/"}
        if host := _q(query, "host"):
            ws_opts["headers"] = {"Host": host}
        proxy["ws-opts"] = ws_opts
    elif network == "grpc":
        proxy["grpc-opts"] = {"grpc-service-name": _q(query, "serviceName")}
    return proxy


def _parse_vless(line: str, names: dict[str, int]) -> dict[str, Any]:
    parts = urlsplit(line)
    query = _split_query(parts.query)
    proxy = _parse_v_share_link(parts, query, "vless", names)
    if flow := _q(query, "flow"):
        proxy["flow"] = flow.lower()
    proxy["encryption"] = _q(query, "encryption")
    return proxy


def _parse_vmess(line: str, names: dict[str, int]) -> dict[str, Any]:
    body = line.split("://", 1)[1].split("#", 1)[0]
    try:
        values = json.loads(_decode_base64(body).decode())
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        parts = urlsplit(line)
        query = _split_query(parts.query)
        proxy = _parse_v_share_link(parts, query, "vmess", names)
        proxy["alterId"] = 0
        proxy["cipher"] = _q(query, "encryption") or "auto"
        return proxy

    if not isinstance(values, dict):
        raise ValueError("vmess JSON must be an object")
    temp_name = str(values.get("ps") or "")
    server = str(values.get("add") or "")
    if not server:
        raise ValueError("vmess server is required")
    port = _port(values.get("port"))
    proxy: dict[str, Any] = {
        "name": _name(names, temp_name, _fallback("vmess", server, port)),
        "type": "vmess",
        "server": server,
        "port": port,
        "uuid": values.get("id"),
        "alterId": _port(values.get("aid") or 0),
        "udp": True,
        "packet-encoding": "xudp",
        "tls": False,
        "skip-cert-verify": False,
        "cipher": values.get("scy") or "auto",
    }
    _set(proxy, "servername", str(values.get("sni") or ""))
    _set(proxy, "client-fingerprint", str(values.get("fp") or ""))

    network = str(values.get("net") or "").lower()
    if values.get("type") == "http":
        network = "http"
    elif network == "http":
        network = "h2"
    http_upgrade = network == "httpupgrade"
    if http_upgrade:
        network = "ws"
    if network:
        proxy["network"] = network

    tls = str(values.get("tls") or "").lower()
    if tls.endswith("tls") or tls == "reality":
        proxy["tls"] = True
    if alpn := str(values.get("alpn") or ""):
        proxy["alpn"] = _alpn(alpn)

    _apply_vmess_json_transport(proxy, values, network, http_upgrade=http_upgrade)
    return proxy


def _parse_v_share_link(
    parts: Any,
    query: dict[str, list[str]],
    scheme: str,
    names: dict[str, int],
) -> dict[str, Any]:
    server = _hostname(parts)
    port = _url_port(parts)
    proxy: dict[str, Any] = {
        "name": _name(names, parts.fragment, _fallback(scheme, server, port)),
        "type": scheme,
        "server": server,
        "port": port,
        "uuid": _username(parts),
        "udp": True,
    }

    security = _q(query, "security").lower()
    if security.endswith("tls") or security == "reality":
        proxy["tls"] = True
        proxy["client-fingerprint"] = _q(query, "fp") or "chrome"
        if alpn := _q(query, "alpn"):
            proxy["alpn"] = _alpn(alpn)
        _set(proxy, "fingerprint", _q(query, "pcs"))
    if sni := _q(query, "sni"):
        proxy["servername"] = sni
    if public_key := _q(query, "pbk"):
        proxy["reality-opts"] = {
            "public-key": public_key,
            "short-id": _q(query, "sid"),
        }
    if _bool(_q_any(query, "allowInsecure", "insecure")):
        proxy["skip-cert-verify"] = True

    packet_encoding = _q(query, "packetEncoding")
    if packet_encoding == "packet":
        proxy["packet-encoding"] = "packetaddr"
    elif packet_encoding != "none":
        proxy["packet-encoding"] = packet_encoding or "xudp"

    network = _q(query, "type").lower() or "tcp"
    fake_type = _q(query, "headerType").lower()
    http_upgrade = network == "httpupgrade"
    if network == "tcp" and fake_type == "http":
        network = "http"
    elif network == "http":
        network = "h2"
    elif http_upgrade:
        network = "ws"
    proxy["network"] = network
    _apply_v_transport(proxy, query, network, http_upgrade=http_upgrade)
    return proxy


def _apply_v_transport(
    proxy: dict[str, Any],
    query: dict[str, list[str]],
    network: str,
    *,
    http_upgrade: bool = False,
) -> None:
    if network == "http":
        http_opts: dict[str, Any] = {"path": [_q(query, "path") or "/"]}
        if method := _q(query, "method"):
            http_opts["method"] = method
        headers: dict[str, Any] = {}
        if host := _q(query, "host"):
            headers["Host"] = [host]
        http_opts["headers"] = headers
        proxy["http-opts"] = http_opts
    elif network == "h2":
        h2_opts: dict[str, Any] = {"path": _q(query, "path") or "/"}
        if host := _q(query, "host"):
            h2_opts["host"] = [host]
        proxy["h2-opts"] = h2_opts
    elif network in {"ws", "httpupgrade"}:
        ws_opts: dict[str, Any] = {"path": _q(query, "path")}
        headers: dict[str, Any] = {}
        if host := _q(query, "host"):
            headers["Host"] = host
        if headers:
            ws_opts["headers"] = headers
        if http_upgrade:
            ws_opts["v2ray-http-upgrade"] = True
        if early_data := _q(query, "ed"):
            early_data_size = int(early_data)
            if http_upgrade:
                ws_opts["v2ray-http-upgrade-fast-open"] = True
            else:
                ws_opts["max-early-data"] = early_data_size
                ws_opts["early-data-header-name"] = "Sec-WebSocket-Protocol"
        if early_data_header := _q(query, "eh"):
            ws_opts["early-data-header-name"] = early_data_header
        proxy["ws-opts"] = ws_opts
    elif network == "grpc":
        proxy["grpc-opts"] = {"grpc-service-name": _q(query, "serviceName")}
    elif network == "xhttp":
        opts: dict[str, Any] = {}
        _set(opts, "path", _q(query, "path"))
        _set(opts, "host", _q(query, "host"))
        _set(opts, "mode", _q(query, "mode"))
        if extra := _q(query, "extra"):
            try:
                _parse_xhttp_extra(json.loads(extra), opts)
            except json.JSONDecodeError:
                pass
        proxy["xhttp-opts"] = opts


def _apply_vmess_json_transport(
    proxy: dict[str, Any],
    values: dict[str, Any],
    network: str,
    *,
    http_upgrade: bool = False,
) -> None:
    host = str(values.get("host") or "")
    path = str(values.get("path") or "")
    if network == "http":
        proxy["http-opts"] = {
            "path": [path or "/"],
            "headers": {"Host": [host]} if host else {},
        }
    elif network == "h2":
        proxy["h2-opts"] = {
            "path": path,
            "host": [host] if host else [],
        }
    elif network in {"ws", "httpupgrade"}:
        ws_opts: dict[str, Any] = {"path": path or "/"}
        if host:
            ws_opts["headers"] = {"Host": host}
        if http_upgrade:
            ws_opts["v2ray-http-upgrade"] = True
        if "?" in ws_opts["path"]:
            path_part, query_part = ws_opts["path"].split("?", 1)
            path_query = _split_query(query_part)
            if early_data := _q(path_query, "ed"):
                early_data_size = int(early_data)
                if http_upgrade:
                    ws_opts["v2ray-http-upgrade-fast-open"] = True
                else:
                    ws_opts["max-early-data"] = early_data_size
                    ws_opts["early-data-header-name"] = "Sec-WebSocket-Protocol"
                ws_opts["path"] = path_part
            if early_data_header := _q(path_query, "eh"):
                ws_opts["early-data-header-name"] = early_data_header
        proxy["ws-opts"] = ws_opts
    elif network == "grpc":
        proxy["grpc-opts"] = {"grpc-service-name": path}


def _parse_xhttp_extra(extra: Any, opts: dict[str, Any]) -> None:
    if not isinstance(extra, dict):
        return
    bool_fields = {"noGRPCHeader": "no-grpc-header", "xPaddingObfsMode": "x-padding-obfs-mode"}
    str_fields = {
        "xPaddingBytes": "x-padding-bytes",
        "xPaddingKey": "x-padding-key",
        "xPaddingHeader": "x-padding-header",
        "xPaddingPlacement": "x-padding-placement",
        "xPaddingMethod": "x-padding-method",
        "uplinkHttpMethod": "uplink-http-method",
        "sessionPlacement": "session-placement",
        "sessionKey": "session-key",
        "seqPlacement": "seq-placement",
        "seqKey": "seq-key",
        "uplinkDataPlacement": "uplink-data-placement",
        "uplinkDataKey": "uplink-data-key",
    }
    int_fields = {
        "uplinkChunkSize": "uplink-chunk-size",
        "scMaxEachPostBytes": "sc-max-each-post-bytes",
        "scMinPostsIntervalMs": "sc-min-posts-interval-ms",
    }
    for src, dst in bool_fields.items():
        if extra.get(src) is True:
            opts[dst] = True
    for src, dst in str_fields.items():
        value = extra.get(src)
        if isinstance(value, str) and value:
            opts[dst] = value
    for src, dst in int_fields.items():
        value = extra.get(src)
        if isinstance(value, int | float):
            opts[dst] = int(value)
    if reuse := _parse_xmux(extra.get("xmux")):
        opts["reuse-settings"] = reuse
    if download_settings := _parse_download_settings(extra.get("downloadSettings")):
        opts["download-settings"] = download_settings


def _parse_xmux(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    mappings = {
        "maxConnections": "max-connections",
        "maxConcurrency": "max-concurrency",
        "cMaxReuseTimes": "c-max-reuse-times",
        "hMaxRequestTimes": "h-max-request-times",
        "hMaxReusableSecs": "h-max-reusable-secs",
    }
    out: dict[str, Any] = {}
    for src, dst in mappings.items():
        field = value.get(src)
        if field not in (None, ""):
            out[dst] = str(int(field)) if isinstance(field, float) else str(field)
    if isinstance(value.get("hKeepAlivePeriod"), int | float):
        out["h-keep-alive-period"] = int(value["hKeepAlivePeriod"])
    return out


def _parse_download_settings(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    _set(out, "server", value.get("address"))
    if "port" in value:
        out["port"] = _port(value["port"])

    security = str(value.get("security") or "").lower()
    if security in {"tls", "reality"}:
        out["tls"] = True
        tls_settings = value.get("tlsSettings")
        if isinstance(tls_settings, dict):
            _set(out, "servername", tls_settings.get("serverName"))
            _set(out, "client-fingerprint", tls_settings.get("fingerprint"))
            alpn = tls_settings.get("alpn")
            if isinstance(alpn, list):
                out["alpn"] = [item for item in alpn if isinstance(item, str)]
            if tls_settings.get("allowInsecure") is True:
                out["skip-cert-verify"] = True
        if security == "reality":
            reality_settings = value.get("realitySettings")
            if isinstance(reality_settings, dict):
                reality_opts: dict[str, Any] = {}
                _set(reality_opts, "public-key", reality_settings.get("publicKey"))
                _set(reality_opts, "short-id", reality_settings.get("shortId"))
                if reality_opts:
                    out["reality-opts"] = reality_opts

    xhttp_settings = value.get("xhttpSettings")
    if isinstance(xhttp_settings, dict):
        _set(out, "path", xhttp_settings.get("path"))
        _set(out, "host", xhttp_settings.get("host"))
        headers = xhttp_settings.get("headers")
        if isinstance(headers, dict) and headers:
            out["headers"] = headers
        extra = xhttp_settings.get("extra")
        if isinstance(extra, dict) and (reuse := _parse_xmux(extra.get("xmux"))):
            out["reuse-settings"] = reuse
    return out


def _parse_ss(line: str, names: dict[str, int]) -> dict[str, Any]:
    parts = urlsplit(line)
    fragment = parts.fragment
    query_text = parts.query
    try:
        parsed_port = parts.port
    except ValueError as exc:
        raise ValueError("invalid ss port") from exc
    if parts.hostname is None or parsed_port is None:
        decoded = _decode_base64(parts.netloc).decode()
        parts = urlsplit(f"ss://{decoded}")
    query = _split_query(query_text)
    server = _hostname(parts)
    port = _url_port(parts)

    cipher = _username(parts)
    password = _password(parts)
    if not password:
        decoded_user = _decode_base64(cipher).decode()
        cipher, separator, password = decoded_user.partition(":")
        if not separator:
            raise ValueError("ss userinfo is invalid")

    proxy: dict[str, Any] = {
        "name": _name(names, fragment, _fallback("ss", server, port)),
        "type": "ss",
        "server": server,
        "port": port,
        "cipher": cipher,
        "password": password,
        "udp": True,
    }
    if _q(query, "udp-over-tcp") == "true" or _q(query, "uot") == "1":
        proxy["udp-over-tcp"] = True
    _apply_ss_plugin(proxy, _q(query, "plugin"))
    return proxy


def _apply_ss_plugin(proxy: dict[str, Any], plugin: str) -> None:
    if ";" not in plugin:
        return
    parts = plugin.split(";")
    plugin_name = parts[0]
    values: dict[str, str] = {}
    for part in parts[1:]:
        key, separator, value = part.partition("=")
        values[key] = value if separator else "true"
    if "obfs" in plugin_name:
        proxy["plugin"] = "obfs"
        proxy["plugin-opts"] = {
            "mode": values.get("obfs", ""),
            "host": values.get("obfs-host", ""),
        }
    elif "v2ray-plugin" in plugin_name:
        proxy["plugin"] = "v2ray-plugin"
        proxy["plugin-opts"] = {
            "mode": values.get("mode", ""),
            "host": values.get("host", ""),
            "path": values.get("path", ""),
            "tls": "tls" in values or "tls" in plugin,
        }


def _parse_ssr(line: str, names: dict[str, int]) -> dict[str, Any]:
    body = line.split("://", 1)[1]
    decoded = _decode_urlsafe_base64(body)
    before, separator, after = decoded.partition("/?")
    if not separator:
        raise ValueError("ssr query is required")
    parts = before.split(":")
    if len(parts) != 6:
        raise ValueError("ssr body is invalid")
    host, port, protocol, method, obfs, encoded_password = parts
    query = _split_query(after)
    remarks = _decode_urlsafe_base64(_q(query, "remarks")) if _q(query, "remarks") else ""
    proxy: dict[str, Any] = {
        "name": _name(names, remarks, _fallback("ssr", host, port)),
        "type": "ssr",
        "server": host,
        "port": _port(port),
        "cipher": method,
        "password": _decode_urlsafe_base64(encoded_password),
        "obfs": obfs,
        "protocol": protocol,
        "udp": True,
    }
    if obfs_param := _q(query, "obfsparam"):
        proxy["obfs-param"] = _decode_urlsafe_base64(obfs_param)
    if protocol_param := _q(query, "protoparam"):
        proxy["protocol-param"] = _decode_urlsafe_base64(protocol_param)
    return proxy


def _parse_anytls(line: str, names: dict[str, int]) -> dict[str, Any]:
    parts = urlsplit(line)
    query = _split_query(parts.query)
    server = _hostname(parts)
    port = _url_port(parts, default=443)
    proxy: dict[str, Any] = {
        "name": _name(names, parts.fragment, _fallback("anytls", server, port)),
        "type": "anytls",
        "server": server,
        "port": port,
        "password": _raw_userinfo(parts),
        "udp": True,
        "skip-cert-verify": _bool(_q_any(query, "insecure", "allowInsecure")),
    }
    _set(proxy, "sni", _q_any(query, "sni", "peer"))
    _set(proxy, "client-fingerprint", _q(query, "fp"))
    _set_int(proxy, "idle-session-check-interval", _q(query, "idle-session-check-interval"))
    _set_int(proxy, "idle-session-timeout", _q(query, "idle-session-timeout"))
    _set_int(proxy, "min-idle-session", _q(query, "min-idle-session"))
    if alpn := _q(query, "alpn"):
        proxy["alpn"] = _alpn(alpn)
    return proxy


_PARSERS: dict[str, Parser] = {
    "hy": _parse_hysteria,
    "hysteria": _parse_hysteria,
    "hysteria2": _parse_hysteria2,
    "hy2": _parse_hysteria2,
    "tuic": _parse_tuic,
    "trojan": _parse_trojan,
    "vless": _parse_vless,
    "vmess": _parse_vmess,
    "ss": _parse_ss,
    "ssr": _parse_ssr,
    "anytls": _parse_anytls,
}

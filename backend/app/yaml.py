from __future__ import annotations

from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO

_load_yaml = YAML(typ="safe", pure=True)


class _DumpYAML(YAML):
    """YAML dumper that returns a string (ruamel.yaml requires a stream)."""

    def dump(self, data, stream=None, **kw):
        if stream is None:
            stream = StringIO()
            YAML.dump(self, data, stream, **kw)
            return stream.getvalue()
        return YAML.dump(self, data, stream, **kw)


_dump_yaml = _DumpYAML(typ="safe", pure=True)
_dump_yaml.default_flow_style = False
_dump_yaml.allow_unicode = True


class YAMLError(Exception):
    """Re-export so callers don't need to import ruamel.yaml directly."""

    pass


def yaml_load(text: str) -> Any:
    from ruamel.yaml import YAMLError as _RuamelError

    try:
        return _load_yaml.load(text)
    except _RuamelError as exc:
        raise YAMLError(str(exc)) from exc


def yaml_dump(data: Any) -> str:
    return _dump_yaml.dump(data)

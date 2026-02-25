from __future__ import annotations

from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml import YAMLError as _RuamelError
from ruamel.yaml.compat import StringIO

_yaml = YAML(typ="rt", pure=True)


class YAMLError(Exception):
    """Re-export so callers don't need to import ruamel.yaml directly."""

    pass


def yaml_load(text: str) -> Any:
    try:
        return _yaml.load(text)
    except _RuamelError as exc:
        raise YAMLError(str(exc)) from exc


def yaml_dump(data: Any) -> str:
    stream = StringIO()
    _yaml.dump(data, stream)
    return stream.getvalue()

from __future__ import annotations

"""Small YAML compatibility layer for release/audit scripts.

The production path should use PyYAML when it is installed.  The fallback is a
strict parser for the repository's generated/simple YAML subset so provenance and
final-audit gates remain executable in a clean Python environment.  It supports
nested mappings, sequences, scalar booleans/null/numbers/strings, empty flow
collections, and simple one-line flow maps/lists.  It intentionally rejects YAML
features that are not used by this repository's release artifacts, such as
anchors, tags, and block scalars, instead of silently mis-parsing them.
"""

import ast
import re
from typing import Any

try:  # pragma: no cover - exercised only when PyYAML is installed.
    import yaml as _pyyaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback covered by stdlib runs.
    _pyyaml = None


class YAMLError(Exception):
    """Raised when the fallback parser cannot safely parse the input."""


_TOKEN_RE = re.compile(r"^[A-Za-z_.$/][A-Za-z0-9_.$/\-]*$")


def safe_load(text: str | bytes | None) -> Any:
    """Parse YAML using PyYAML, or the repository-local strict fallback.

    Args:
        text: YAML document content. ``None`` and blank content resolve to ``None``.

    Returns:
        Parsed Python data.

    Raises:
        YAMLError: If the fallback parser sees unsupported YAML syntax.
    """
    if _pyyaml is not None:
        return _pyyaml.safe_load(text)
    if text is None:
        return None
    if isinstance(text, bytes):
        text = text.decode('utf-8')
    parser = _FallbackYamlParser(str(text))
    return parser.parse()


def safe_dump(payload: Any, *, sort_keys: bool = True, allow_unicode: bool = True, **_: Any) -> str:
    """Render a deterministic YAML subset.

    Args:
        payload: Python data to render.
        sort_keys: Whether mapping keys are sorted.
        allow_unicode: Kept for PyYAML API compatibility.

    Returns:
        YAML text ending with a newline.
    """
    if _pyyaml is not None:
        return _pyyaml.safe_dump(payload, sort_keys=sort_keys, allow_unicode=allow_unicode)
    return _dump_node(payload, indent=0, sort_keys=sort_keys) + '\n'


class _FallbackYamlParser:
    def __init__(self, text: str) -> None:
        self.lines: list[tuple[int, str]] = []
        for raw in text.splitlines():
            cleaned = self._strip_comment(raw.rstrip('\n\r'))
            if not cleaned.strip():
                continue
            if '\t' in cleaned[: len(cleaned) - len(cleaned.lstrip(' \t'))]:
                raise YAMLError('tab indentation is not supported')
            indent = len(cleaned) - len(cleaned.lstrip(' '))
            content = cleaned.strip()
            if content in {'|', '>'} or content.endswith(': |') or content.endswith(': >'):
                raise YAMLError('block scalars are not supported by the fallback YAML parser')
            if content.startswith(('---', '...')):
                continue
            if self.lines and indent > self.lines[-1][0] and not content.startswith('-') and ':' not in content:
                previous_indent, previous_content = self.lines[-1]
                self.lines[-1] = (previous_indent, f'{previous_content} {content}')
                continue
            self.lines.append((indent, content))

    @staticmethod
    def _strip_comment(raw: str) -> str:
        quote: str | None = None
        escaped = False
        for index, char in enumerate(raw):
            if quote:
                if quote == '"' and char == '\\' and not escaped:
                    escaped = True
                    continue
                if char == quote and not escaped:
                    quote = None
                escaped = False
                continue
            if char in {'"', "'"}:
                quote = char
                continue
            if char == '#' and (index == 0 or raw[index - 1].isspace()):
                return raw[:index].rstrip()
        return raw.rstrip()

    def parse(self) -> Any:
        if not self.lines:
            return None
        value, index = self._parse_block(0, self.lines[0][0])
        if index != len(self.lines):
            raise YAMLError(f'unparsed YAML content at line {index + 1}')
        return value

    def _parse_block(self, index: int, indent: int) -> tuple[Any, int]:
        if index >= len(self.lines):
            return None, index
        line_indent, content = self.lines[index]
        if line_indent < indent:
            return None, index
        if line_indent != indent:
            raise YAMLError(f'unexpected indentation at line {index + 1}')
        if content.startswith('-'):
            return self._parse_list(index, indent)
        return self._parse_map(index, indent)

    def _parse_map(self, index: int, indent: int) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while index < len(self.lines):
            line_indent, content = self.lines[index]
            if line_indent < indent:
                break
            if line_indent > indent:
                raise YAMLError(f'unexpected nested mapping at line {index + 1}')
            if content.startswith('-'):
                break
            key, rest = self._split_key_value(content, index)
            if rest == '':
                next_index = index + 1
                if next_index < len(self.lines) and (
                    self.lines[next_index][0] > indent
                    or (self.lines[next_index][0] == indent and self.lines[next_index][1].startswith('-'))
                ):
                    value, index = self._parse_block(next_index, self.lines[next_index][0])
                else:
                    value, index = {}, next_index
            else:
                value = self._parse_scalar(rest)
                index += 1
            result[key] = value
        return result, index

    def _parse_list(self, index: int, indent: int) -> tuple[list[Any], int]:
        result: list[Any] = []
        while index < len(self.lines):
            line_indent, content = self.lines[index]
            if line_indent < indent:
                break
            if line_indent != indent or not content.startswith('-'):
                break
            rest = content[1:].strip()
            next_index = index + 1
            if rest == '':
                if next_index < len(self.lines) and self.lines[next_index][0] > indent:
                    value, index = self._parse_block(next_index, self.lines[next_index][0])
                else:
                    value, index = None, next_index
                result.append(value)
                continue
            if self._looks_like_inline_mapping(rest):
                key, value_text = self._split_key_value(rest, index)
                item: dict[str, Any] = {key: self._parse_scalar(value_text) if value_text else {}}
                index = next_index
                if index < len(self.lines) and self.lines[index][0] > indent:
                    extra, index = self._parse_block(index, self.lines[index][0])
                    if not isinstance(extra, dict):
                        raise YAMLError(f'list item continuation must be a mapping at line {index + 1}')
                    item.update(extra)
                result.append(item)
                continue
            result.append(self._parse_scalar(rest))
            index = next_index
        return result, index

    def _split_key_value(self, content: str, index: int) -> tuple[str, str]:
        quote: str | None = None
        escaped = False
        for pos, char in enumerate(content):
            if quote:
                if quote == '"' and char == '\\' and not escaped:
                    escaped = True
                    continue
                if char == quote and not escaped:
                    quote = None
                escaped = False
                continue
            if char in {'"', "'"}:
                quote = char
                continue
            if char == ':':
                key = content[:pos].strip()
                rest = content[pos + 1 :].strip()
                if not key:
                    raise YAMLError(f'empty YAML key at line {index + 1}')
                return self._parse_key(key), rest
        raise YAMLError(f'mapping entry missing colon at line {index + 1}: {content}')

    @staticmethod
    def _parse_key(key: str) -> str:
        if (key.startswith("'") and key.endswith("'")) or (key.startswith('"') and key.endswith('"')):
            parsed = ast.literal_eval(key)
            return str(parsed)
        return key

    @staticmethod
    def _looks_like_inline_mapping(text: str) -> bool:
        """Return true only for YAML list items of the form ``key: value``.

        YAML treats an unquoted colon as a mapping separator only when the colon
        is followed by whitespace or the end of the scalar.  Values such as
        ``color:red``, ``http://example.test`` and ``topic:/arm/state`` are plain
        scalars and must not be rewritten into dictionaries by the fallback
        parser.  This function mirrors that repository-required subset instead
        of treating every colon as a mapping separator.
        """
        if text.startswith(('{', '[')):
            return False
        quote: str | None = None
        escaped = False
        for pos, char in enumerate(text):
            if quote:
                if quote == '"' and char == '\\' and not escaped:
                    escaped = True
                    continue
                if char == quote and not escaped:
                    quote = None
                escaped = False
                continue
            if char in {'"', "'"}:
                quote = char
                continue
            if char == ':':
                key = text[:pos].strip()
                if not key:
                    return False
                return pos == len(text) - 1 or text[pos + 1].isspace()
        return False

    def _parse_scalar(self, text: str) -> Any:
        if text == '':
            return ''
        lower = text.lower()
        if lower in {'null', 'none', '~'}:
            return None
        if lower == 'true':
            return True
        if lower == 'false':
            return False
        if text == '[]':
            return []
        if text == '{}':
            return {}
        if text.startswith('[') and text.endswith(']'):
            return [self._parse_scalar(part.strip()) for part in self._split_flow_items(text[1:-1]) if part.strip()]
        if text.startswith('{') and text.endswith('}'):
            result: dict[str, Any] = {}
            body = text[1:-1].strip()
            if not body:
                return result
            for item in self._split_flow_items(body):
                key, value = self._split_flow_pair(item)
                result[self._parse_key(key.strip())] = self._parse_scalar(value.strip())
            return result
        if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
            try:
                return ast.literal_eval(text)
            except Exception as exc:  # pragma: no cover
                raise YAMLError(f'invalid quoted scalar: {text}') from exc
        if re.fullmatch(r'[-+]?\d+', text):
            try:
                return int(text)
            except ValueError:
                pass
        if re.fullmatch(r'[-+]?(\d+\.\d*|\d*\.\d+)([eE][-+]?\d+)?', text) or re.fullmatch(r'[-+]?\d+[eE][-+]?\d+', text):
            try:
                return float(text)
            except ValueError:
                pass
        return text

    @staticmethod
    def _split_flow_items(body: str) -> list[str]:
        items: list[str] = []
        start = 0
        depth = 0
        quote: str | None = None
        escaped = False
        for index, char in enumerate(body):
            if quote:
                if quote == '"' and char == '\\' and not escaped:
                    escaped = True
                    continue
                if char == quote and not escaped:
                    quote = None
                escaped = False
                continue
            if char in {'"', "'"}:
                quote = char
                continue
            if char in '[{':
                depth += 1
            elif char in ']}':
                depth -= 1
            elif char == ',' and depth == 0:
                items.append(body[start:index])
                start = index + 1
        items.append(body[start:])
        return items

    @staticmethod
    def _split_flow_pair(item: str) -> tuple[str, str]:
        quote: str | None = None
        depth = 0
        for index, char in enumerate(item):
            if quote:
                if char == quote:
                    quote = None
                continue
            if char in {'"', "'"}:
                quote = char
                continue
            if char in '[{':
                depth += 1
            elif char in ']}':
                depth -= 1
            elif char == ':' and depth == 0:
                return item[:index], item[index + 1 :]
        raise YAMLError(f'invalid flow mapping item: {item}')


def _dump_node(value: Any, *, indent: int, sort_keys: bool) -> str:
    prefix = ' ' * indent
    if isinstance(value, dict):
        keys = sorted(value) if sort_keys else list(value.keys())
        lines: list[str] = []
        for key in keys:
            item = value[key]
            rendered_key = str(key)
            if isinstance(item, (dict, list)) and item:
                lines.append(f'{prefix}{rendered_key}:')
                lines.append(_dump_node(item, indent=indent + 2, sort_keys=sort_keys))
            else:
                lines.append(f'{prefix}{rendered_key}: {_dump_scalar(item)}')
        return '\n'.join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)) and item:
                lines.append(f'{prefix}-')
                lines.append(_dump_node(item, indent=indent + 2, sort_keys=sort_keys))
            else:
                lines.append(f'{prefix}- {_dump_scalar(item)}')
        return '\n'.join(lines)
    return f'{prefix}{_dump_scalar(value)}'


def _dump_scalar(value: Any) -> str:
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == '':
        return "''"
    if _TOKEN_RE.match(text):
        return text
    return repr(text)

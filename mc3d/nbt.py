"""Minimal NBT (Named Binary Tag) writer, enough for Sponge schematics.

Python values are mapped to NBT tags as follows unless wrapped explicitly:
    bool/int -> TAG_Int, float -> TAG_Double, str -> TAG_String,
    dict -> TAG_Compound, list -> TAG_List, bytes -> TAG_Byte_Array
Use the wrapper classes (Byte, Short, Int, Long, ...) to force a tag type.
"""

from __future__ import annotations

import gzip
import struct
from dataclasses import dataclass
from typing import Any

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12


@dataclass(frozen=True)
class Byte:
    value: int


@dataclass(frozen=True)
class Short:
    value: int


@dataclass(frozen=True)
class Int:
    value: int


@dataclass(frozen=True)
class Long:
    value: int


@dataclass(frozen=True)
class Float:
    value: float


@dataclass(frozen=True)
class Double:
    value: float


@dataclass(frozen=True)
class ByteArray:
    value: bytes


@dataclass(frozen=True)
class IntArray:
    value: list[int]


@dataclass(frozen=True)
class List:
    """A TAG_List with an explicit element type (needed for empty lists)."""

    tag_type: int
    items: list[Any]


def _tag_type(value: Any) -> int:
    if isinstance(value, Byte):
        return TAG_BYTE
    if isinstance(value, Short):
        return TAG_SHORT
    if isinstance(value, (Int, bool, int)):
        return TAG_INT
    if isinstance(value, Long):
        return TAG_LONG
    if isinstance(value, Float):
        return TAG_FLOAT
    if isinstance(value, (Double, float)):
        return TAG_DOUBLE
    if isinstance(value, (ByteArray, bytes, bytearray)):
        return TAG_BYTE_ARRAY
    if isinstance(value, str):
        return TAG_STRING
    if isinstance(value, (List, list)):
        return TAG_LIST
    if isinstance(value, dict):
        return TAG_COMPOUND
    if isinstance(value, IntArray):
        return TAG_INT_ARRAY
    raise TypeError(f"Cannot encode {type(value).__name__} as NBT")


def _unwrap(value: Any) -> Any:
    return value.value if hasattr(value, "value") and not isinstance(value, List) else value


def _write_string(out: bytearray, s: str) -> None:
    data = s.encode("utf-8")
    out += struct.pack(">H", len(data))
    out += data


def _write_payload(out: bytearray, tag: int, value: Any) -> None:
    v = _unwrap(value)
    if tag == TAG_BYTE:
        out += struct.pack(">b", v)
    elif tag == TAG_SHORT:
        out += struct.pack(">h", v)
    elif tag == TAG_INT:
        out += struct.pack(">i", int(v))
    elif tag == TAG_LONG:
        out += struct.pack(">q", v)
    elif tag == TAG_FLOAT:
        out += struct.pack(">f", v)
    elif tag == TAG_DOUBLE:
        out += struct.pack(">d", v)
    elif tag == TAG_BYTE_ARRAY:
        out += struct.pack(">i", len(v))
        out += bytes(v)
    elif tag == TAG_STRING:
        _write_string(out, v)
    elif tag == TAG_LIST:
        if isinstance(value, List):
            elem_type, items = value.tag_type, value.items
        else:
            items = v
            elem_type = _tag_type(items[0]) if items else TAG_END
        out += struct.pack(">bi", elem_type, len(items))
        for item in items:
            _write_payload(out, elem_type, item)
    elif tag == TAG_COMPOUND:
        for key, item in v.items():
            _write_named(out, key, item)
        out += bytes([TAG_END])
    elif tag == TAG_INT_ARRAY:
        out += struct.pack(">i", len(v))
        out += struct.pack(f">{len(v)}i", *v)
    else:
        raise ValueError(f"Unsupported tag type {tag}")


def _write_named(out: bytearray, name: str, value: Any) -> None:
    tag = _tag_type(value)
    out.append(tag)
    _write_string(out, name)
    _write_payload(out, tag, value)


def encode(root_name: str, root: dict) -> bytes:
    """Encode a root compound to uncompressed NBT bytes."""
    out = bytearray()
    _write_named(out, root_name, root)
    return bytes(out)


def write_gzip(path: str, root_name: str, root: dict) -> None:
    with gzip.open(path, "wb") as f:
        f.write(encode(root_name, root))

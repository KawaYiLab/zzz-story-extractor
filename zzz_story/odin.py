"""Bounded reader for Odin binary entries used by offline Perform assets.

Format reference: TeamSirenix/odin-serializer, BinaryEntryType.cs and
BinaryDataReader.cs (Apache-2.0). This reads data, never instantiates types.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


class OdinError(ValueError):
    pass


@dataclass
class Entry:
    name: str | None
    value: object


@dataclass
class Node:
    type_name: str | None
    reference_id: int | None
    entries: list[Entry] = field(default_factory=list)

    def get(self, name: str, default=None):
        values = [entry.value for entry in self.entries if entry.name == name]
        if len(values) > 1:
            raise OdinError(f"duplicate field: {name}")
        return values[0] if values else default


@dataclass(frozen=True)
class Reference:
    kind: str
    value: object


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0
        self.types: dict[int, str] = {}

    def take(self, size: int) -> bytes:
        if size < 0 or size > len(self.data) - self.offset:
            raise OdinError(f"truncated entry at {self.offset}, size {size}")
        start = self.offset
        self.offset += size
        return self.data[start:self.offset]

    def number(self, fmt: str):
        return struct.unpack("<" + fmt, self.take(struct.calcsize("<" + fmt)))[0]

    def string(self) -> str:
        encoding = self.number("B")
        if encoding not in (0, 1):
            raise OdinError(f"unknown string encoding: {encoding}")
        length = self.number("i")
        try:
            return self.take(length * (encoding + 1)).decode("latin1" if encoding == 0 else "utf-16le")
        except UnicodeDecodeError as exc:
            raise OdinError("invalid UTF-16 string") from exc

    def type_name(self) -> str | None:
        tag = self.number("B")
        if tag == 0x2E:
            return None
        if tag == 0x2F:
            key = self.number("i")
            if key in self.types:
                raise OdinError(f"duplicate type id: {key}")
            self.types[key] = self.string()
            return self.types[key]
        if tag == 0x30:
            key = self.number("i")
            if key not in self.types:
                raise OdinError(f"missing type id: {key}")
            return self.types[key]
        raise OdinError(f"invalid type entry: {tag:#x}")

    def entry(self, depth: int = 0) -> Entry:
        if depth > 128:
            raise OdinError("entry nesting exceeds limit")
        tag = self.number("B")
        named = tag in (1, 3, 9, 11, 13, 0x32) or 0x0F <= tag <= 0x2D and tag % 2 == 1
        name = self.string() if named else None
        if tag in (1, 2, 3, 4):
            type_name = self.type_name()
            node = Node(type_name, self.number("i") if tag in (1, 2) else None)
            while self.offset < len(self.data) and self.data[self.offset] != 5:
                node.entries.append(self.entry(depth + 1))
            if self.number("B") != 5:
                raise OdinError("missing node end")
            value = node
        elif tag == 6:
            count = self.number("q")
            if count < 0 or count > len(self.data):
                raise OdinError(f"invalid array length: {count}")
            value = [self.entry(depth + 1).value for _ in range(count)]
            if self.number("B") != 7:
                raise OdinError("array count/end mismatch")
        elif tag == 8:
            count, size = self.number("i"), self.number("i")
            if count < 0 or size <= 0:
                raise OdinError("invalid primitive array length")
            value = self.take(count * size)
        elif tag in (9, 10, 11, 12):
            value = Reference("internal" if tag < 11 else "external_index", self.number("i"))
        elif tag in (13, 14):
            value = Reference("external_guid", self.take(16))
        elif 0x0F <= tag <= 0x22:
            fmt = {0x0F: "b", 0x11: "B", 0x13: "h", 0x15: "H", 0x17: "i",
                   0x19: "I", 0x1B: "q", 0x1D: "Q", 0x1F: "f", 0x21: "d"}[tag if tag % 2 else tag - 1]
            value = self.number(fmt)
        elif tag in (0x23, 0x24, 0x29, 0x2A):
            value = self.take(16)
        elif tag in (0x25, 0x26):
            value = chr(self.number("H"))
        elif tag in (0x27, 0x28):
            value = self.string()
        elif tag in (0x2B, 0x2C):
            boolean = self.number("B")
            if boolean not in (0, 1):
                raise OdinError("invalid boolean")
            value = bool(boolean)
        elif tag in (0x2D, 0x2E):
            value = None
        elif tag in (0x32, 0x33):
            value = Reference("external_string", self.string())
        else:
            raise OdinError(f"unexpected entry {tag:#x} at {self.offset - 1}")
        return Entry(name, value)


def read_entries(data: bytes) -> list[Entry]:
    reader = Reader(data)
    result = []
    while reader.offset < len(data):
        if reader.data[reader.offset] == 0x31:
            reader.offset += 1
            if reader.offset != len(data):
                raise OdinError("bytes after end of stream")
            break
        result.append(reader.entry())
    return result


def perform_entries(raw: bytes) -> tuple[str, list[Entry]]:
    """Read MonoBehaviour name and binary serializationData, with size checks."""
    if len(raw) < 40:
        raise OdinError("truncated MonoBehaviour")
    length = struct.unpack_from("<I", raw, 28)[0]
    end = 32 + length
    offset = (end + 3) & ~3
    if offset + 8 > len(raw):
        raise OdinError("truncated serializationData")
    try:
        name = raw[32:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OdinError("invalid object name") from exc
    format_id, size = struct.unpack_from("<ii", raw, offset)
    if format_id != 0 or size <= 0 or offset + 8 + size > len(raw):
        raise OdinError("not a binary serializationData payload")
    return name, read_entries(raw[offset + 8:offset + 8 + size])


def walk_nodes(value):
    if isinstance(value, Node):
        yield value
        for entry in value.entries:
            yield from walk_nodes(entry.value)
    elif isinstance(value, list):
        for item in value:
            yield from walk_nodes(item)

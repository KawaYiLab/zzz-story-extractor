"""Port of the mhy1 container decoder used by Zenless Zone Zero.

The descrambling/AES/RC4 layout is ported from simon300000/zenless-voice's
``galgame-perform.ts`` (MIT), which in turn documents the format used by the
game's Perform resource blocks.
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .constants import MHY_KEY, MHY_MUL, MHY_SBOX, MHY_SHIFT_ROW, RC4_STATE


class MhyError(RuntimeError):
    pass


def _gf_mul(left: int, right: int) -> int:
    a, b, result = left, right, 0
    while b:
        if b & 1:
            result ^= a
        a = (a << 1) ^ 0x11B if a & 0x80 else a << 1
        b >>= 1
    return result & 0xFF


def descramble_chunk(data: bytearray) -> None:
    if len(data) != 16:
        raise MhyError(f"descramble chunk must be 16 bytes, got {len(data)}")
    vector = bytearray(16)
    for round_no in range(3):
        for index in range(16):
            source = MHY_SHIFT_ROW[(2 - round_no) * 16 + index] % len(data)
            key_index = index % 8
            vector[index] = MHY_KEY[key_index] ^ MHY_SBOX[
                (index % 4 * 0x100) | _gf_mul(MHY_MUL[key_index], data[source])
            ]
        data[:] = vector


def rc4(data: bytearray, key: bytes, operation: bytes) -> None:
    state = bytearray(RC4_STATE)
    repeated = bytes(key[index % len(key)] for index in range(256))
    j = 0
    for index in range(256):
        j = (j + state[index] + repeated[index]) & 0xFF
        state[index], state[j] = state[j], state[index]

    i = 0
    j = 0
    for index in range(len(data)):
        i = (i + 1) & 0xFF
        j = (j + state[i]) & 0xFF
        state[i], state[j] = state[j], state[i]
        value = state[(state[j] + state[i]) & 0xFF]
        if not operation:
            continue
        mode = operation[i % len(operation)] % 3
        if mode == 0:
            data[index] ^= value
        elif mode == 1:
            data[index] = (data[index] - value) & 0xFF
        else:
            data[index] = (data[index] + value) & 0xFF


def descramble(data: bytearray, entry_size: int) -> None:
    block_size = min(len(data), 128)
    if len(data) < 36:
        raise MhyError("encrypted entry is too short")
    chunk = bytearray(data[4:20])
    descramble_chunk(chunk)
    data[4:20] = chunk
    if bytes(data[4:12]) != b"mhynewec":
        raise MhyError("invalid mhy1 encrypted signature")
    if block_size <= 35:
        return
    chunk = bytearray(data[20:36])
    descramble_chunk(chunk)
    data[20:36] = chunk
    seed = bytes(data[0:16])
    encryptor = Cipher(algorithms.AES(seed), modes.ECB()).encryptor()
    encrypted = encryptor.update(bytes(data[20:36])) + encryptor.finalize()
    data[20:36] = encrypted
    for index in range(4):
        data[index] ^= encrypted[index]
    rounded_entry_size = (entry_size + 15) // 16 * 16
    tail = bytearray(data[20 + rounded_entry_size:block_size])
    rc4(tail, bytes(data[20:28]), bytes(data[28:36]))
    data[20 + rounded_entry_size:block_size] = tail


class MhyReader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def bytes(self, length: int) -> bytes:
        if self.offset + length > len(self.data):
            raise MhyError("truncated mhy1 metadata")
        value = self.data[self.offset:self.offset + length]
        self.offset += length
        return value

    def int(self) -> int:
        value = self.bytes(6)
        raw = value[2] | value[4] << 8 | value[0] << 16 | value[5] << 24
        return raw - 0x100000000 if raw & 0x80000000 else raw

    def uint(self) -> int:
        value = self.bytes(7)
        return (value[1] | value[6] << 8 | value[3] << 16 | value[2] << 24) & 0xFFFFFFFF

    def string(self) -> str:
        value = self.bytes(0x105)
        end = value.find(b"\x00")
        return value[:end if end >= 0 else len(value)].decode("utf-8", errors="replace")


@dataclass
class MhyNode:
    path: str
    offset: int
    size: int


def oodle_decompress(data: bytes, raw_size: int) -> bytes:
    try:
        import ooz
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise MhyError("pyooz is not installed; run: pip install pyooz") from exc
    return ooz.decompress(data, raw_size)


def unpack_mhy_named_file(file: bytes, start: int) -> tuple[list[tuple[str, bytes]], int]:
    if file[start:start + 4] != b"mhy1":
        raise MhyError(f"invalid mhy1 signature at {start}")
    if start + 8 > len(file):
        raise MhyError("truncated mhy1 header")
    info_size = int.from_bytes(file[start + 4:start + 8], "little")
    info_end = start + 8 + info_size
    if info_end > len(file):
        raise MhyError("truncated mhy1 info block")

    encrypted_info = bytearray(file[start + 8:info_end])
    descramble(encrypted_info, 28)
    info = MhyReader(bytes(encrypted_info[48:]))
    raw_info_size = info.uint()
    compressed_info = info.bytes(len(info.data) - info.offset)
    if not compressed_info or compressed_info[0] != 0x8C:
        raise MhyError("mhy1 metadata is not Oodle-compressed")
    raw_info = MhyReader(oodle_decompress(compressed_info, raw_info_size))

    node_count = raw_info.int()
    nodes: list[MhyNode] = []
    for _ in range(node_count):
        path = raw_info.string()
        raw_info.bytes(1)
        nodes.append(MhyNode(path, raw_info.int(), raw_info.uint()))

    block_count = raw_info.int()
    blocks: list[tuple[int, int]] = []
    for _ in range(block_count):
        blocks.append((raw_info.int(), raw_info.uint()))

    raw_size = sum(raw for _, raw in blocks)
    contents = bytearray(raw_size)
    source_offset = info_end
    target_offset = 0
    for compressed, raw in blocks:
        if source_offset + compressed > len(file):
            raise MhyError("truncated mhy1 content block")
        encrypted = bytearray(file[source_offset:source_offset + compressed])
        descramble(encrypted, 8)
        raw_data = oodle_decompress(bytes(encrypted[28:]), raw)
        contents[target_offset:target_offset + raw] = raw_data
        source_offset += compressed
        target_offset += raw

    files = [
        (node.path, bytes(contents[node.offset:node.offset + node.size]))
        for node in nodes
        if not node.path.lower().endswith(".ress")
    ]
    return files, source_offset


def unpack_mhy_file(file: bytes, start: int) -> tuple[list[bytes], int]:
    named, end = unpack_mhy_named_file(file, start)
    return [data for _, data in named], end


def extract_mhy_named_files(block: bytes) -> list[tuple[str, bytes]]:
    """Keep serialized CAB names for exact external Unity PPtr resolution."""
    result: list[tuple[str, bytes]] = []
    offset = 0
    length = len(block)
    while offset + 8 <= length:
        while offset < length and block[offset] == 0:
            offset += 1
        if offset + 8 > length:
            break
        if block[offset:offset + 4] != b"mhy1":
            next_offset = block.find(b"mhy1", offset + 1)
            if next_offset < 0:
                break
            offset = next_offset
        try:
            files, end = unpack_mhy_named_file(block, offset)
            result.extend(files)
            offset = end if end > offset else offset + 4
        except MhyError:
            offset += 4
    return result


def extract_mhy_files(block: bytes) -> list[bytes]:
    """Extract every concatenated mhy1 container in a .blk file."""
    return [data for _, data in extract_mhy_named_files(block)]

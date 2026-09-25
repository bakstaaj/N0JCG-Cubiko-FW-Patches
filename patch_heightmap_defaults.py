#!/usr/bin/env python3
"""Patch Cubiko Control Panel height-map defaults and About marker.

The override runs at the shared settings-dispatch continuation, after a
setting value is received. It changes only actual IEEE-754 fields still equal
to their stock defaults:

    length  80 -> 132 mm
    width   60 -> 80 mm
    X       9 -> 11 points
    Y       7 -> 10 points

Values already changed by the user are preserved. Length and width are
32-bit floats at 0x200002A8/0x200002AC; X and Y counts are bytes at
0x200002B0/0x200002B1. The English and German About screens receive an H45.5
marker. The input image is checked
against its known SHA-256, hook bytes and version strings are checked, and
the entire code cave must still be erased (0xFF) before output is written.

Usage:
    python patch_heightmap_defaults.py [input.bin] [output.bin]
"""

from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path


FLASH_BASE = 0x08008000
KNOWN_SHA256 = "fa36f34e2a92c61a36b2d14d4c96fccde8fc5d0d91e6884d1e00950a7f7980bd"

# Common settings-dispatch tail, after the System Board value is stored.
HOOK_ADDRESS = 0x0801C19A
HOOK_BYTES = bytes.fromhex("00 bf 4e e0")

# 125 erased bytes at this address; the patch uses 84 bytes.
CAVE_ADDRESS = 0x0803EA16
CAVE_SIZE = 84
CAVE_RESERVED_SIZE = 125

EN_VERSION = b"Version:4AXIS_V45.2"
EN_VERSION_PATCHED = b"Version:4AXIS_H45.5"
DE_VERSION = b"4axis_v45.2"
DE_VERSION_PATCHED = b"4axis_h45.5"
FLOAT_CHANGES = (
    (0, 0x42A00000, 0x43040000, "length 80 -> 132"),
    (4, 0x42700000, 0x42A00000, "width 60 -> 80"),
)
BYTE_CHANGES = ((8, 9, 11, "X points 9 -> 11"), (9, 7, 10, "Y points 7 -> 10"))
RETURN_ADDRESS = 0x0801C23C


def thumb_bw(source: int, target: int) -> bytes:
    """Encode a Thumb-2 unconditional B.W instruction."""
    displacement = target - (source + 4)
    if displacement & 1 or not -(1 << 24) <= displacement < (1 << 24):
        raise ValueError("B.W target is out of range or not halfword-aligned")
    imm = displacement & 0x01FFFFFF
    s = (imm >> 24) & 1
    i1 = (imm >> 23) & 1
    i2 = (imm >> 22) & 1
    j1 = (~(i1 ^ s)) & 1
    j2 = (~(i2 ^ s)) & 1
    first = 0xF000 | (s << 10) | ((imm >> 12) & 0x03FF)
    second = 0x9000 | (j1 << 13) | (j2 << 11) | ((imm >> 1) & 0x07FF)
    return struct.pack("<HH", first, second)


def movw(rd: int, immediate: int) -> list[int]:
    """Encode Thumb-2 MOVW for a low register and 16-bit immediate."""
    first = 0xF240 | (((immediate >> 11) & 1) << 10) | ((immediate >> 12) & 0xF)
    second = (((immediate >> 8) & 7) << 12) | (rd << 8) | (immediate & 0xFF)
    return [first, second]


def movt(rd: int, immediate: int) -> list[int]:
    """Encode Thumb-2 MOVT for a low register and 16-bit immediate."""
    first = 0xF2C0 | (((immediate >> 11) & 1) << 10) | ((immediate >> 12) & 0xF)
    second = (((immediate >> 8) & 7) << 12) | (rd << 8) | (immediate & 0xFF)
    return [first, second]


def cave_code() -> bytes:
    """Build guarded float and byte substitutions; preserve volatile registers."""
    halfwords = [0xB40F]  # push {r0-r3}
    halfwords += movw(0, 0x02A8)
    halfwords += movt(0, 0x2000)
    for offset, stock, replacement, _label in FLOAT_CHANGES:
        halfwords.append(0x6800 | ((offset // 4) << 6) | 1)  # ldr r1,[r0,#offset]
        halfwords += movw(2, stock & 0xFFFF)
        halfwords += movt(2, stock >> 16)
        halfwords.append(0x4291)  # cmp r1,r2
        halfwords.append(0xD104)  # bne over replacement MOVW/MOVT/STR
        halfwords += movw(2, replacement & 0xFFFF)
        halfwords += movt(2, replacement >> 16)
        halfwords.append(0x6000 | ((offset // 4) << 6) | 2)  # str r2,[r0,#offset]
    for offset, stock, replacement, _label in BYTE_CHANGES:
        halfwords.append(0x7800 | (offset << 6) | 1)  # ldrb r1,[r0,#offset]
        halfwords.append(0x2900 | stock)  # cmp r1,#stock
        halfwords.append(0xD101)  # bne over the following MOVS/STRB pair
        halfwords.append(0x2100 | replacement)  # movs r1,#replacement
        halfwords.append(0x7000 | (offset << 6) | 1)  # strb r1,[r0,#offset]
    halfwords.append(0xBC0F)  # pop {r0-r3}
    code = b"".join(struct.pack("<H", word) for word in halfwords)
    if len(code) + 4 != CAVE_SIZE:
        raise AssertionError(f"unexpected stub size: {len(code) + 4}")
    return code + thumb_bw(CAVE_ADDRESS + len(code), RETURN_ADDRESS)


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Control Panel/firmware.bin")
    destination = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("out/control-panel-heightmap-H45.5.bin")
    if len(sys.argv) > 3:
        print(__doc__)
        return 2

    original = source.read_bytes()
    before_hash = sha256(original)
    if before_hash != KNOWN_SHA256:
        raise SystemExit(
            "error: unexpected input firmware SHA-256\n"
            f"  expected {KNOWN_SHA256}\n  found    {before_hash}"
        )

    hook_offset = HOOK_ADDRESS - FLASH_BASE
    cave_offset = CAVE_ADDRESS - FLASH_BASE
    if original[hook_offset : hook_offset + len(HOOK_BYTES)] != HOOK_BYTES:
        raise SystemExit(
            f"error: expected hook bytes not found at {HOOK_ADDRESS:#010x}: "
            f"{original[hook_offset:hook_offset + len(HOOK_BYTES)].hex(' ')}"
        )
    if original[cave_offset : cave_offset + CAVE_RESERVED_SIZE] != b"\xff" * CAVE_RESERVED_SIZE:
        raise SystemExit(f"error: code cave at {CAVE_ADDRESS:#010x} is not erased")

    for original_text in (EN_VERSION, DE_VERSION):
        if original.count(original_text) != 1:
            raise SystemExit(f"error: expected exactly one About version string {original_text!r}")

    patched = bytearray(original)
    stub = cave_code()
    patched[hook_offset : hook_offset + 4] = thumb_bw(HOOK_ADDRESS, CAVE_ADDRESS)
    patched[cave_offset : cave_offset + len(stub)] = stub
    for original_text, patched_text in (
        (EN_VERSION, EN_VERSION_PATCHED),
        (DE_VERSION, DE_VERSION_PATCHED),
    ):
        if len(original_text) != len(patched_text):
            raise AssertionError("About marker must preserve the original string length")
        string_offset = original.index(original_text)
        patched[string_offset : string_offset + len(original_text)] = patched_text
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(patched)

    print("Height-map default patch applied")
    print(f"  hook   {HOOK_ADDRESS:#010x}: {HOOK_BYTES.hex(' ')} -> {thumb_bw(HOOK_ADDRESS, CAVE_ADDRESS).hex(' ')}")
    print(f"  cave   {CAVE_ADDRESS:#010x}: wrote {len(stub)} bytes; {CAVE_RESERVED_SIZE - len(stub)} erased bytes remain")
    print("  about  English/German version marker V45.2 -> H45.5")
    for offset, stock, replacement, label in FLOAT_CHANGES:
        print(f"  RAM    {0x200002A8 + offset:#010x}: {label}; only if stock float bits match")
    for offset, stock, replacement, label in BYTE_CHANGES:
        print(f"  RAM    {0x200002A8 + offset:#010x}: {label}; only if stock byte matches")
    print(f"  input  sha256 {before_hash}")
    print(f"  output sha256 {sha256(patched)}")
    print(f"  output {destination} ({len(patched)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

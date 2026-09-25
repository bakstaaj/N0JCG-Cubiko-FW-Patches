#!/usr/bin/env python3
"""Build and deploy paired Cubiko Control Panel and System Board V45.3 images.

PATCH THE FACTORY FIRMWARE
==========================
1. Keep the factory V45.2 files in these locations:
       Control Panel/firmware.bin
       System Board/firmware.bin
   Do not use already-patched images as inputs. The script checks both factory
   SHA-256 checksums and stops if either image is not the expected V45.2 build.
2. Edit the user-configurable values in the section immediately below this
   docstring, if desired. The default patch sets a 132 x 80 mm height map,
   11 x 10 sample points, a 20000 RPM Manual_Spindle_RPM ceiling, and displays
   V45.3 on the Control Panel About screen.
3. From this project directory, run:
       python patch_cubiko_v45_3.py
   The script writes two files under out/ and prints both output SHA-256 values.
   Record those checksums if you want to verify the files after copying them.

FLASH THE TWO BOARDS (ONE IMAGE AT A TIME)
==========================================
The two boards use different SD slots. Do not put both images on one card under
the name firmware.bin, and do not put an image in the other board's slot.

1. For the Control Panel, copy out/control-panel-V45.3.bin to the root of an
   SD card and rename the copy to firmware.bin. Insert it in the SD slot on the
   right side of the controller. Power on and wait for the panel's firmware
   update process to finish. Confirm that About shows V45.3.
2. Power the machine off. Replace the card contents with a copy of
   out/system-board-V45.3.bin named firmware.bin. Insert this card in the SD
   slot at the top right of the CNC cabinet (the System Board slot). Power on
   and wait for the firmware update process to finish.
3. After updating, verify the height-map dimensions and sample counts, test the
   bed Z probe, and confirm Manual_Spindle_RPM accepts and retains the desired
   value after saving and rebooting. Keep the factory images and a recovery
   copy of each generated image.

PROBE BEHAVIOR
==============
The System Board change makes G38.2 read the PB14 bed sensor. It disables the
PB7 external probe-jack path, including panel probing actions that use PB7.
Understand this limitation before flashing and keep clear access to the stop
control while testing.

Only the factory V45.2 input images with the SHA-256 values below are accepted.
Output checksums are displayed for recording; they are not compared to fixed
values, so edits to the configurable settings are supported.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path


# ---------------------------------------------------------------------------
# User-editable patch settings
# ---------------------------------------------------------------------------
HEIGHT_MAP_LENGTH_MM = 132.0
HEIGHT_MAP_WIDTH_MM = 80.0
HEIGHT_MAP_X_POINTS = 11
HEIGHT_MAP_Y_POINTS = 10
MANUAL_SPINDLE_RPM_LIMIT = 20000
ABOUT_VERSION = "V45.3"

CONTROL_PANEL_INPUT = Path("Control Panel/firmware.bin")
SYSTEM_BOARD_INPUT = Path("System Board/firmware.bin")
CONTROL_PANEL_OUTPUT = Path("out/control-panel-V45.3.bin")
SYSTEM_BOARD_OUTPUT = Path("out/system-board-V45.3.bin")


# Factory V45.2 input image identities. These are the only checksum gates.
CONTROL_PANEL_SHA256 = "fa36f34e2a92c61a36b2d14d4c96fccde8fc5d0d91e6884d1e00950a7f7980bd"
SYSTEM_BOARD_SHA256 = "8a054bbc7471a08c94fa1ed72551e39ae4b6a22ab9949b9e563a563cb8025d2e"


# ---------------------------------------------------------------------------
# Verified patch locations and expected stock bytes
# ---------------------------------------------------------------------------
FLASH_BASE = 0x08008000

# Control Panel height-map hook and erased code cave.
HM_HOOK_ADDRESS = 0x0801C19A
HM_HOOK_BYTES = bytes.fromhex("00 bf 4e e0")
HM_CAVE_ADDRESS = 0x0803EA16
HM_CAVE_SIZE = 84
HM_CAVE_RESERVED_SIZE = 125
HM_RETURN_ADDRESS = 0x0801C23C
HM_RAM_BASE = 0x200002A8
HM_FLOAT_STOCK = ((0, 80.0, "length"), (4, 60.0, "width"))
HM_BYTE_STOCK = ((8, 9, "X points"), (9, 7, "Y points"))

# About text in the factory Control Panel image (English and German strings).
ABOUT_EN_STOCK = b"Version:4AXIS_V45.2"
ABOUT_DE_STOCK = b"4axis_v45.2"

# System Board G38.2 probe selector: force PB14 bed sensor (movs r0,#0).
PROBE_OFFSET = 0x1544C
PROBE_EXPECTED = bytes.fromhex("01 20")
PROBE_PATCHED = bytes.fromhex("00 20")
PROBE_CONTEXT_OFFSET = 0x1543C
PROBE_CONTEXT = bytes.fromhex(
    "2a 48 00 78 0c 28 03 d1 00 20 29 49 08 70 02 e0 01 20 27 49 08 70"
)

# System Board Manual_Spindle_RPM ceiling in two mirrored settings records.
RPM_RECORD_STARTS = (0x0803DB48, 0x0803DB70)
RPM_JOG_FEED_EXPECTED = 2000
RPM_LIMIT_STOCK = 10000


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


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
    first = 0xF240 | (((immediate >> 11) & 1) << 10) | ((immediate >> 12) & 0xF)
    second = (((immediate >> 8) & 7) << 12) | (rd << 8) | (immediate & 0xFF)
    return [first, second]


def movt(rd: int, immediate: int) -> list[int]:
    first = 0xF2C0 | (((immediate >> 11) & 1) << 10) | ((immediate >> 12) & 0xF)
    second = (((immediate >> 8) & 7) << 12) | (rd << 8) | (immediate & 0xFF)
    return [first, second]


def checked_point_count(value: int, name: str) -> int:
    if not isinstance(value, int) or not 1 <= value <= 255:
        raise ValueError(f"{name} must be an integer from 1 through 255")
    return value


def make_heightmap_stub() -> bytes:
    """Override only stock defaults when settings are loaded from the board."""
    x_points = checked_point_count(HEIGHT_MAP_X_POINTS, "HEIGHT_MAP_X_POINTS")
    y_points = checked_point_count(HEIGHT_MAP_Y_POINTS, "HEIGHT_MAP_Y_POINTS")
    floats = (
        (0, struct.unpack("<I", struct.pack("<f", HM_FLOAT_STOCK[0][1]))[0],
         struct.unpack("<I", struct.pack("<f", HEIGHT_MAP_LENGTH_MM))[0]),
        (4, struct.unpack("<I", struct.pack("<f", HM_FLOAT_STOCK[1][1]))[0],
         struct.unpack("<I", struct.pack("<f", HEIGHT_MAP_WIDTH_MM))[0]),
    )
    bytes_to_change = ((8, 9, x_points), (9, 7, y_points))

    halfwords = [0xB40F]  # push {r0-r3}
    halfwords += movw(0, HM_RAM_BASE & 0xFFFF)
    halfwords += movt(0, HM_RAM_BASE >> 16)
    for offset, stock_bits, replacement_bits in floats:
        halfwords.append(0x6800 | ((offset // 4) << 6) | 1)  # ldr r1,[r0,#offset]
        halfwords += movw(2, stock_bits & 0xFFFF)
        halfwords += movt(2, stock_bits >> 16)
        halfwords.append(0x4291)  # cmp r1,r2
        halfwords.append(0xD104)  # bne over replacement MOVW/MOVT/STR
        halfwords += movw(2, replacement_bits & 0xFFFF)
        halfwords += movt(2, replacement_bits >> 16)
        halfwords.append(0x6000 | ((offset // 4) << 6) | 2)  # str r2,[r0,#offset]
    for offset, stock, replacement in bytes_to_change:
        if not 0 <= replacement <= 255:
            raise ValueError("height-map point counts must fit in one byte")
        halfwords.append(0x7800 | (offset << 6) | 1)  # ldrb r1,[r0,#offset]
        halfwords.append(0x2900 | stock)  # cmp r1,#stock
        halfwords.append(0xD101)  # bne over MOVS/STRB
        halfwords.append(0x2100 | replacement)  # movs r1,#replacement
        halfwords.append(0x7000 | (offset << 6) | 1)  # strb r1,[r0,#offset]
    halfwords.append(0xBC0F)  # pop {r0-r3}
    body = b"".join(struct.pack("<H", word) for word in halfwords)
    stub = body + thumb_bw(HM_CAVE_ADDRESS + len(body), HM_RETURN_ADDRESS)
    if len(stub) != HM_CAVE_SIZE:
        raise AssertionError(f"unexpected height-map stub size: {len(stub)}")
    return stub


def make_about_string(stock: bytes, german: bool) -> bytes:
    version = ABOUT_VERSION.encode("ascii")
    if german:
        replacement = b"4axis_" + version.lower()
    else:
        replacement = b"Version:4AXIS_" + version
    if len(replacement) != len(stock):
        raise ValueError(
            f"ABOUT_VERSION must keep the stock version string length ({len(stock)} bytes)"
        )
    return replacement


def patch_control_panel(original: bytes) -> bytes:
    hook_offset = HM_HOOK_ADDRESS - FLASH_BASE
    cave_offset = HM_CAVE_ADDRESS - FLASH_BASE
    if original[hook_offset : hook_offset + len(HM_HOOK_BYTES)] != HM_HOOK_BYTES:
        raise SystemExit(f"Control Panel: expected height-map hook missing at {HM_HOOK_ADDRESS:#x}")
    if original[cave_offset : cave_offset + HM_CAVE_RESERVED_SIZE] != b"\xff" * HM_CAVE_RESERVED_SIZE:
        raise SystemExit(f"Control Panel: reserved code cave is not erased at {HM_CAVE_ADDRESS:#x}")
    for text in (ABOUT_EN_STOCK, ABOUT_DE_STOCK):
        if original.count(text) != 1:
            raise SystemExit(f"Control Panel: expected one stock About string {text!r}")

    patched = bytearray(original)
    stub = make_heightmap_stub()
    hook = thumb_bw(HM_HOOK_ADDRESS, HM_CAVE_ADDRESS)
    patched[hook_offset : hook_offset + len(hook)] = hook
    patched[cave_offset : cave_offset + len(stub)] = stub
    for stock, replacement in (
        (ABOUT_EN_STOCK, make_about_string(ABOUT_EN_STOCK, german=False)),
        (ABOUT_DE_STOCK, make_about_string(ABOUT_DE_STOCK, german=True)),
    ):
        at = original.index(stock)
        patched[at : at + len(stock)] = replacement
    return bytes(patched)


def patch_system_board(original: bytes) -> bytes:
    context_end = PROBE_CONTEXT_OFFSET + len(PROBE_CONTEXT)
    if original[PROBE_CONTEXT_OFFSET:context_end] != PROBE_CONTEXT:
        raise SystemExit("System Board: expected G38.2 PB14/PB7 selector context not found")
    if original[PROBE_OFFSET : PROBE_OFFSET + 2] != PROBE_EXPECTED:
        raise SystemExit("System Board: unexpected instruction at G38.2 probe selector")
    if not 1 <= MANUAL_SPINDLE_RPM_LIMIT <= 0xFFFF:
        raise ValueError("MANUAL_SPINDLE_RPM_LIMIT must fit an unsigned 16-bit value")

    rpm_offsets: list[int] = []
    for address in RPM_RECORD_STARTS:
        record_offset = address - FLASH_BASE
        if record_offset < 0 or record_offset + 6 > len(original):
            raise SystemExit(f"System Board: RPM settings record out of range at {address:#x}")
        jog_feed, rpm = struct.unpack_from("<HH", original, record_offset + 2)
        if (jog_feed, rpm) != (RPM_JOG_FEED_EXPECTED, RPM_LIMIT_STOCK):
            raise SystemExit(
                f"System Board: unexpected RPM record at {address:#x}: "
                f"Jog_Feed={jog_feed}, Manual_Spindle_RPM limit={rpm}"
            )
        rpm_offsets.append(record_offset + 4)

    patched = bytearray(original)
    patched[PROBE_OFFSET : PROBE_OFFSET + 2] = PROBE_PATCHED
    for offset in rpm_offsets:
        struct.pack_into("<H", patched, offset, MANUAL_SPINDLE_RPM_LIMIT)
    return bytes(patched)


def read_checked_input(path: Path, expected_sha256: str, label: str) -> bytes:
    data = path.read_bytes()
    actual = sha256(data)
    if actual != expected_sha256:
        raise SystemExit(
            f"{label}: factory V45.2 input checksum mismatch\n"
            f"  expected {expected_sha256}\n  found    {actual}"
        )
    print(f"{label} factory input SHA-256: {actual}")
    return data


def main() -> int:
    cp_source = read_checked_input(CONTROL_PANEL_INPUT, CONTROL_PANEL_SHA256, "Control Panel")
    sb_source = read_checked_input(SYSTEM_BOARD_INPUT, SYSTEM_BOARD_SHA256, "System Board")

    cp_patched = patch_control_panel(cp_source)
    sb_patched = patch_system_board(sb_source)

    CONTROL_PANEL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    SYSTEM_BOARD_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    CONTROL_PANEL_OUTPUT.write_bytes(cp_patched)
    SYSTEM_BOARD_OUTPUT.write_bytes(sb_patched)

    print("\nCombined Cubiko patch generated")
    print(
        f"  Height Map: {HEIGHT_MAP_LENGTH_MM:g} x {HEIGHT_MAP_WIDTH_MM:g} mm; "
        f"{HEIGHT_MAP_X_POINTS} x {HEIGHT_MAP_Y_POINTS} samples"
    )
    print(f"  Manual_Spindle_RPM maximum: {MANUAL_SPINDLE_RPM_LIMIT}")
    print(f"  About version: {ABOUT_VERSION}")
    print("  Z probe input: G38.2 uses PB14 bed sensor")
    print(f"  Control Panel output SHA-256: {sha256(cp_patched)}")
    print(f"  System Board output SHA-256:  {sha256(sb_patched)}")
    print(f"  Control Panel: {CONTROL_PANEL_OUTPUT} ({len(cp_patched)} bytes)")
    print(f"  System Board:  {SYSTEM_BOARD_OUTPUT} ({len(sb_patched)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

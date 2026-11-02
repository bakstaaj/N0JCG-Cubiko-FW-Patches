# N0JCG Cubiko Firmware Patches

This repository contains reproducible patches for the Genmitsu Cubiko V45.2 Control Panel and System Board firmware. The V45.3 patcher generates a matched pair of images and checks that both input files are the expected factory V45.2 binaries before modifying them.

## V45.3 combined patch

The V45.3 release includes these changes:

- Control Panel Height Map defaults: length **132 mm**, width **80 mm**, **11 X** sample points, and **10 Y** sample points. The override runs when firmware settings are loaded and changes only values that still match the stock defaults, preserving values that have already been customized.
- Control Panel About screen: displays **V45.3**.
- System Board probe input: G38.2 selects the **PB14 bed sensor**.
- System Board `Manual_Spindle_RPM`: raises the accepted maximum from **10000** to **20000 RPM**. It does not change the startup value; the user can set and save that value in firmware settings.

### Important probe behavior

The System Board probe patch forces G38.2 to use PB14. This disables the PB7 external probe-jack path, including panel probing actions that use PB7. Do not install this patch if you need that external probe input.

## Build from factory firmware

Place the unmodified factory V45.2 binaries at these paths in the project directory:

```text
Control Panel/firmware.bin
System Board/firmware.bin
```

Edit the configuration constants near the top of `patch_cubiko_v45_3.py` if different Height Map or RPM values are desired. The About version must remain the same character length as the stock version string.

Run from the repository root:

```powershell
python patch_cubiko_v45_3.py
```

The script verifies the initial input SHA-256 checksums and the expected patch locations. It writes:

```text
out/control-panel-V45.3.bin
out/system-board-V45.3.bin
```

It prints the resulting SHA-256 checksums for both patched images. Output hashes are informational and are not fixed in the script, so configurable values can be changed.

Factory input SHA-256 values:

| Image | SHA-256 |
| --- | --- |
| Control Panel | `fa36f34e2a92c61a36b2d14d4c96fccde8fc5d0d91e6884d1e00950a7f7980bd` |
| System Board | `8a054bbc7471a08c94fa1ed72551e39ae4b6a22ab9949b9e563a563cb8025d2e` |

Default V45.3 output SHA-256 values:

| Image | SHA-256 |
| --- | --- |
| Control Panel | `7a0bac0b00cee38c4514e9f432bb2d1d9ee3284420bfa788bc5a2ac656ac92aa` |
| System Board | `edf78d73401d1e8623785462126c0825bfa4e0b8a2e1fd9ad65551b8f5bce0f0` |

## Install the firmware

Update one board at a time. Both update files must be named `firmware.bin` at the root of the SD card, so remove the first image before copying the second. Use the correct SD slot for each board:

1. **Control Panel:** copy `out/control-panel-V45.3.bin` to an SD card and rename the copy to `firmware.bin`. Insert it into the SD slot on the **right side of the controller**. Power on and wait for the Control Panel update to complete. Confirm that the About screen displays V45.3.
2. Power the machine off. Replace the card contents with `out/system-board-V45.3.bin`, named `firmware.bin`. Insert it into the SD slot at the **top right of the CNC cabinet** (System Board slot). Power on and wait for the System Board update to complete.
3. After both updates, check the Height Map defaults, test the bed probe with the tool clear, and verify that `Manual_Spindle_RPM` accepts the desired value and retains it after saving and rebooting.

Keep the factory images and a recovery copy of each patched image. The patched firmware has been checked for input identity and binary read-back, and the Height Map and RPM behavior has been confirmed on the machine. Test probe behavior carefully after installation.

## Cubiko 4th-axis connector pinout

The following pinout was identified from the Cubiko controller-board silkscreen and confirmed on the machine. This is a six-position connector:

| Pin | Signal | Confirmed voltage / label |
| --- | --- | --- |
| 1 | V+ | 24 V DC |
| 2 | GND | Ground |
| 3 | COM | Board label `COM` |
| 4 | DIR | Direction signal |
| 5 | STP | Step signal |
| 6 | EN | Enable signal |

**Orientation:** Pin 1 (`V+`) is the top contact in the two connector-face photos. In the photo of the labeled controller-board connector, Pin 1 is the rightmost contact. Count the remaining pins in order from Pin 1: `V+`, `GND`, `COM`, `DIR`, `STP`, `EN`.

**Power warning:** `V+` is confirmed as **24 V DC**. Do not mistake it for the 5 V signal logic level specified for the rotary module, and do not connect it to a 5 V input. Verify connector orientation and wiring before plugging in or powering the rotary module.

## Cubiko laser connector pinout

From the orientation shown in the supplied connector photo, the three-pin laser connector is read **from top to bottom** as follows:

| Position | Signal | Voltage / function |
| --- | --- | --- |
| Top | PWM | Laser power control signal |
| Middle | GRND | Ground |
| Bottom | 12V | 12 V DC supply |

Keep the connector orientation as shown when identifying the pins. The laser connector's 12 V supply is separate from the 4th-axis connector's 24 V V+ pin. Confirm the laser module's voltage and wiring before connecting it.

## Cubiko leveling connector pinout

The two-pin leveling connector is read **from top to bottom** in the stated orientation:

| Position | Signal |
| --- | --- |
| Top | GND |
| Bottom | Probe |

The probe contact is the leveling/probe signal; the upper contact is ground. Confirm the connector orientation before wiring or connecting external equipment.

## Release package

The GitHub release contains a ZIP with both patched binaries, the patch script, this README, and the SHA-256 manifest. The factory firmware binaries are not included in this source repository.

# Cubiko Control Panel firmware patches

This repository contains reproducible patch scripts for the Genmitsu Cubiko Control Panel firmware. Original and patched vendor firmware images are not committed; the script validates the exact input image and prints checksums for the generated output.

## Height Map defaults (H45.5)

The patch changes the stock Height Map setup defaults to:

- Length: 132 mm (stock 80 mm)
- Width: 80 mm (stock 60 mm)
- X sample points: 11 (stock 9)
- Y sample points: 10 (stock 7)

It updates only fields still equal to the stock values, preserving other user settings. Length and width are IEEE-754 values at RAM addresses `0x200002A8` and `0x200002AC`; sample counts are byte values at `0x200002B0` and `0x200002B1`. The Control Panel About screen is tagged `H45.5` so the patched image is identifiable.

The H45.5 image was loaded on a Cubiko and the requested Height Map defaults were confirmed on the display.

### Build

Obtain the vendor firmware package from the [SainSmart Cubiko resource page](https://docs.sainsmart.com/article/8f6ypseduj-cubiko) and place its original `Control Panel/firmware.bin` at that path. Then run:

```powershell
python patch_heightmap_defaults.py
```

The script writes `out/control-panel-heightmap-H45.5.bin`. It refuses inputs whose SHA-256 or expected hook, code cave, or About strings differ from the analyzed image.

- Expected input SHA-256: `fa36f34e2a92c61a36b2d14d4c96fccde8fc5d0d91e6884d1e00950a7f7980bd`
- Verified H45.5 output SHA-256: `8759db23c0088dcc3b04f64f6ec6032d4ff5c692cf971e41a33fdb082dfaf57d`

Install the generated image only as a Control Panel/offline-module update using the controller-side SD slot. Do not use the cabinet slot, which is for the System Board firmware.

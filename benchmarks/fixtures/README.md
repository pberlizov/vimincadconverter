# Real-part style fixtures (pack v1)

Small on-disk meshes and point clouds used by the **benchmark catalog** (`benchmarks/cases.json`) so CI exercises **noisy / non-ideal** inputs without large binaries or LFS.

| File | Description |
|------|-------------|
| `noisy_plate.stl` | 10×6×2 mm-class plate with light Gaussian vertex jitter (simulates scan noise). |

Add new fixtures here (prefer under **100 KiB** STL or xyz) and reference them from catalog cases with `"generator": "fixture_file", "fixture": "<filename>"`.

# np21w-local

Personal patches for [Neko Project 21/W](https://github.com/Aile2017/np21w) and the script that builds it with them.
The upstream source is kept in `Aile2017/np21w` (`main` = the latest published source, one commit per release).
This repository holds only the patches and the build procedure.

## Layout

| Path | Content |
|---|---|
| `base.conf` | The upstream repository and the commit the patches are applied to |
| `patches/` | The patches, applied in file-name order (`git format-patch` format) |
| `build.ps1` | Extracts the base commit, applies the patches, builds, collects the binaries in `out\` |

### Patches

1. `0001-build-vs2026.patch` — build with Visual Studio 2026 (v145 toolset, `winres.h`).
2. `0002-key101.patch` — US 101 keyboard support: symbol keys follow the key tops, an AX keyboard is treated like 101,
   and the Application key no longer leaves the CAPS lock pressed (the subject line of this commit only mentions the AX part).
3. `0003-prefetch.patch` — 386/486 prefetch queue emulation (Wizardry 7 `DS.EXE` anti-debug).
   Use a 486-class CPU setting in the ini (`cpu_fami=4`, `cpu_mode=1`, `cpu_step=3`, `cpu_feat=1`, `cpu_brid=0`);
   with a Pentium-class setting it reboots in a loop, as it does on real hardware.

`SUPPORT_NPDISP_W2K` is also switched off, but as a step of `build.ps1` and not as a patch
(the `PreprocessorDefinitions` lines change between releases and the patch used to conflict).
The Windows 2000 NPDISP is not needed for DOS use, and with the prefetch patch it caused tempo and UMB problems.

## Build

Requirements: Visual Studio 2026 (v145 toolset), Git, PowerShell.

```
git clone https://github.com/Aile2017/np21w-local
cd np21w-local
.\build.ps1            # all executables and language DLLs  -> out\
.\build.ps1 -ExeOnlyX64   # np21x64w.exe only (quick)
```

`build.ps1` uses `BASE_REPO` (a local clone of the upstream repository) if it exists, otherwise it clones `BASE_URL` into `build\`.
Nothing outside this repository is modified. Copy `out\` into the emulator directory yourself,
and keep the language DLLs (`out\language\*.dll`) in step with the executables.

## Updating to a new upstream release

1. Import the release into `Aile2017/np21w` (`main`).
2. Set `BASE_REF` in `base.conf` to the new commit.
3. Run `.\build.ps1`. If a patch no longer applies, fix it in `build\src` (a git work tree with the base commit checked out),
   then re-create it with `git format-patch`.

## Notes

- `build\src` is a clone of the upstream repository because `git apply` only patches paths inside the repository it runs in.
  `build.ps1` applies the patches with `core.autocrlf=false` so the line endings of the sources are not rewritten.
- The `.rc` files are CRLF, so `patch` fails on them; use `git apply --ignore-whitespace`.

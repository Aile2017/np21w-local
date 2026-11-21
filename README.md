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
| `NOTES.md` | Operation notes (in Japanese): procedures, pitfalls, the keyboard investigation |
| `tools/` | `update_np21w.py` imports a new release into the upstream repository; `import_np21w.py` and the logs record the initial bulk import |

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

## パッチの詳細

1. **`0001-build-vs2026.patch`**
   Visual Studio 2026 でビルドできるようにします。プロジェクトの `PlatformToolset` を `v145` にし、
   リソースファイル(`.rc`)の `afxres.h` を `winres.h` に置き換え、`wab/npdisp_d3d.cpp` に BOM を付けます。
2. **`0002-key101.patch`**(101 キーボード対応)
   元のソースは、101 キーボードと認識しても、PC-98 のキー配列に位置を対応させるだけで、
   US 配列の刻印どおりには入力できません。このパッチは、101 キーボードのモードで
   US 配列の記号キー(`2 @`、`6 ^`、`7 &`、`8 *`、`9 (`、`0 )`、`- _`、`= +`、`[ {`、`] }`、
   `; :`、`' "`、`` ` ~ ``、`\ |`、`, <`、`. >`、`/ ?`)を、Windows のキーボードレイアウトに
   依存しないようスキャンコードで判定し、刻印どおりの文字になる PC-98 のキーとシフト状態に
   変換して送ります(`win9x/winkbd.cpp`)。カナロック中は JIS 配列の位置どおりに送り、
   CTRL / GRPH を併用しているときはシフト状態を操作しません。
   あわせて、キーボードの種類の自動判定で AX キーボード(`GetKeyboardType(0) == 7`)も
   英語キーボード(101)と判定されるようにしています(`win9x/np2.cpp`)。
   さらに、アプリケーションキーを押すと CAPS が押されたままになり、解除できなくなる問題を直しています。
   元のソースは、押すときだけアプリケーションキー(0x79)を CAPS(0x71)に変換し、離すときは変換しないため、
   CAPS の「離した」が送られませんでした。押すときの条件を、離すときと同じ `!= KEY_PC98` に揃えました。
3. **`0003-prefetch.patch`**(プリフェッチキュー)
   386/486 の命令プリフェッチキュー(16 バイト)をエミュレートします
   (`i386c/ia32/cpu.c`、`cpu_mem.c`、`interface.h`)。CPU ファミリが 4 以下で、
   ページングが無効のときだけ働きます。プリフェッチ済みのコードを書き換えて動作を判定する
   アンチデバッグ(Wizardry 7 PC-98 の `DS.EXE` など)が、再起動を繰り返す問題を避けるためのものです。

ビルド手順の `SUPPORT_NPDISP_W2K` の無効化は、DOS 専用の用途では Windows 2000 用 NPDISP が不要で、
有効のままだと `prefetch` との組み合わせで動作が不安定になる場合があったためです。

運用の詳しい手順と落とし穴は、[NOTES.md](NOTES.md) にあります。

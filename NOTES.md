# np21w ソース管理・ビルドの手順メモ

作成: 2026-11-15。2026-11-21 に、公開元のソースと個人パッチのリポジトリを分けた構成に書き直した。

## 1. 構成

| 場所 | 内容 |
|---|---|
| `C:\usr\games\np21w\git\np21w` | 公開元のソースだけを持つ Git リポジトリ。リモートは https://github.com/Aile2017/np21w(公開) |
| `C:\usr\games\np21w\git\np21w-local` | 個人パッチとビルド手順のリポジトリ(このリポジトリ)。リモートは https://github.com/Aile2017/np21w-local(公開) |
| `C:\usr\games\np21w\_arcs` | 公開元のアーカイブ(zip)。rev100 以降だけ残してある |
| `C:\usr\games\np21w\bin` | 実際に使っている実行ファイルと ini |
| `C:\usr\games\np21w\np21w-rev107-*.diff`、`np21w-rev107beta10-*.diff` | 旧運用のパッチの diff。もう使わない(いまは `patches\`) |

公開元: https://simk98.github.io/np21w/ (更新履歴: https://simk98.github.io/np21w/version.html)

### このリポジトリ(`np21w-local`)の中身

| パス | 内容 |
|---|---|
| `base.conf` | パッチを当てる公開元のリポジトリとコミット(`BASE_REF`) |
| `patches\` | 個人パッチ 3 つ(`git format-patch` 形式。ファイル名の順に適用) |
| `build.ps1` | ソースの取り出し、パッチ適用、W2K 無効化、ビルド、`out\` への収集 |
| `tools\update_np21w.py` | 新版のアーカイブを `np21w`(公開元のソース)に取り込むスクリプト(§4) |
| `tools\import_np21w.py`、`tools\import-log.md`、`tools\import-run.out` | 過去の全アーカイブを一括で取り込んだスクリプトとそのログ(記録用。§6) |
| `.gitattributes` | `* -text`。パッチに CRLF の行(`.rc` ファイル)が入っているので、改行変換を止めてある |
| `build\`、`out\` | ビルドの作業ディレクトリと成果物(`.gitignore` で除外) |

### `np21w`(公開元のソース)のブランチ

- `main`: 0.85 から最新版までの公開ソース。1 版 1 コミット。`README.md` だけが公開元のファイルではない。
- `bsd`、`haxm`、`variant/*`: 派生版・試験版。対応する rev の `main` のコミットから分岐。
- タグ: `0.85`、`rev1`〜`rev106`(beta でない版だけ。0.86 は更新履歴の rev1)。
- 個人パッチのブランチ(`local-patches`、`patched/*`)は、2026-11-21 に origin から削除した。
  パッチは `np21w-local` の `patches\` にある(ローカルの `np21w` リポジトリには、古いブランチが残っている)。

## 2. 個人パッチ

1. `0001-build-vs2026.patch`: Visual Studio 2026(v145)でビルドできるようにする。
2. `0002-key101.patch`: 101 キーボード(US 配列)で刻印どおりに入力できるようにする。
   AX キーボードも 101 と判定する付加機能つき(コミットの件名には、この付加機能のほうだけが書いてある)。
   アプリケーションキーで CAPS が固定される問題の修正も含む(§7)。
3. `0003-prefetch.patch`: 386/486 のプリフェッチキューのエミュレーション。Wizardry 7 の再起動ループ対策。
   `wiz67.ini` で 486 相当(`cpu_fami=4`、`cpu_mode=1`、`cpu_step=3`、`cpu_feat=1`、`cpu_brid=0`)にしておくこと。
   Pentium 相当では、実機と同じく再起動ループする。

パッチではなく、`build.ps1` の手順として、`SUPPORT_NPDISP_W2K` を無効にする
(`np21vs2019.vcxproj` の `PreprocessorDefinitions` から `SUPPORT_NPDISP_W2K;` を取り除く)。

- 以前はこれもパッチ(コミット)にしていたが、β9・β10 で `PreprocessorDefinitions` の行が変わり、衝突した。
  版が変わっても壊れないよう、スクリプトの手順にした。
- `np2vs2019.vcxproj` のほうは `UndefinePreprocessorDefinitions` に入っているだけで、触らない。

### なぜ W2K を無効にするのか

- rev107β3・β4 のプロジェクトには `UndefinePreprocessorDefinitions: SUPPORT_NPDISP_W2K` があり、W2K は無効だった。
  β5 以降はこの指定が消えて、W2K(Windows 2000 用 NPDISP)が有効になっている。配布版の exe も有効。
- この環境(DOS 専用)で `prefetch` を当てたビルドに W2K を有効のまま使うと、次の症状が出た。
  - `SuperDepth.cmd`: テンポがおかしくなり、音切れが出る。
  - `msdos5.cmd`: UMB を確保するデバイスドライバ(`UMB領域 : A5-A7 D0-D7 DE-DF E8-F3` の表示)で止まる。
- `prefetch` なしの W2K 有効ビルド(配布版も同じ)では、これらは出なかった。
  W2K 無効 + `prefetch` ではどれも出ず、`wiz7.cmd` も再起動しなかった。
  W2K と `prefetch` の組み合わせで何が起きているかの原因は、特定していない。
- W2K を無効にすると、ゲストの Windows 2000 で NPDISP を使えない。DOS だけなら影響はない。

## 3. ビルド手順(Visual Studio 2026)

前提: Visual Studio 2026(`C:\Program Files\Microsoft Visual Studio\18\Community`)。toolset は v145。Git、PowerShell。

```
cd C:\usr\games\np21w\git\np21w-local
.\build.ps1                # exe 4 つと言語 DLL 8 つ  -> out\
.\build.ps1 -ExeOnlyX64    # np21x64w.exe だけ(速い)
```

`build.ps1` がやること:

1. `base.conf` を読む。`BASE_REPO`(ローカルの `np21w`)があればそれを、なければ `BASE_URL` を `build\` に clone して使う。
2. `BASE_REF` のコミットを、`build\src` にローカル clone + checkout で取り出す。
3. `patches\*.patch` を、`git -c core.autocrlf=false apply --ignore-whitespace --unsafe-paths -p1` で順に当てる。
4. `SUPPORT_NPDISP_W2K` を無効にする(§2)。
5. MSBuild で、次の構成と言語 DLL をビルドする。
6. `out\` に集める。**`bin` には何も触らない。** 差し替えは手でコピーする。

| 構成 | プロジェクト | Platform | 出力(`out\`) |
|---|---|---|---|
| np21 x64 | `np21vs2019.vcxproj` | x64 | `np21x64w.exe` |
| np21 Win32 | `np21vs2019.vcxproj` | Win32 | `np21w.exe` |
| np2 x64 | `np2vs2019.vcxproj` | x64 | `np2x64w.exe` |
| np2 Win32 | `np2vs2019.vcxproj` | Win32 | `np2w.exe` |
| 言語 DLL | `win9x\resources\<932,1252,936,950>\np2vs2008_<cp>.vcxproj`(`-p:PlatformToolset=v145`) | x64 / Win32 | `language\np2x64_<cp>.dll`、`language\np2_<cp>.dll` |

- WHPX 版(`ReleaseWHPX`)、HAXM 版(`ReleaseHAXM`)は、`build.ps1` に入れていない。必要なら手で MSBuild を実行する。
- 警告は 1000 件以上出るが、エラー 0 件でビルドできる。画面には警告を出さない。
- 全構成のビルドで、10 分弱かかる。`-ExeOnlyX64` なら数分。

### ビルドの落とし穴(`build.ps1` で対策済み)

- システムの Git 設定が `core.autocrlf=true` のため、そのままだと `git apply` やコミットで改行が書き換わる。
  パッチ適用では `-c core.autocrlf=false` を指定し、リポジトリには `.gitattributes`(`* -text`)を置いてある。
  これがないと、`.rc` の CR が落ちて、パッチが当たらなくなる。
- `patch` は使わない。`.rc` が CRLF のため、失敗する。
- `build\src` は、`np21w-local` リポジトリの中にある。`git apply` は、いるリポジトリの中のパスしか直さないので、
  `build\src` の `.git` を消さずに残してある(clone した公開元の `.git`)。
- `git archive | tar` は使わない。bsdtar が、日本語のファイル名(`LICENSES\全体説明.txt`)を展開できない。
- 前回のビルドで残る `mspdbsrv.exe` が `build\src` を掴んで、削除に失敗する。スクリプトの先頭で終了させている。
- ソース zip の中のフォルダ名は版によって違う(β9 は `np21w-src-rev108`、他は `np21w-src-rev107`)。
  `update_np21w.py` は気にしないが、手で展開するときは決め打ちしない。

## 4. 新版が公開されたとき

1. 公開元(Drive のフォルダ、または更新履歴ページのリンク)から、アーカイブを手動でダウンロードして `_arcs` に置く。
   - Drive のファイルは、`curl` や Chrome の自動操作ではダウンロードできなかった(サインインや 403)。**手動で取得する。**
2. 公開元のソースを取り込む:

```
python -I C:\usr\games\np21w\git\np21w-local\tools\update_np21w.py --push --update-base C:\usr\games\np21w\_arcs\np21w-0.86-rev107beta11.zip
```

   - 更新履歴ページを読み、タイトルと変更点でコミットを作る(`np21w` の `main`)。正式版にはタグも付ける。
   - `--push`: `np21w` の `main` と、新しいタグをプッシュする。
   - `--update-base`: `np21w-local\base.conf` の `BASE_REF` を、新しいコミットにする。
   - `--dry-run` で、何をするかだけ確認できる。
   - 作業ツリーが汚れている、すでに取り込み済み、`main` の先頭より新しくない、のいずれかでは止まる。
   - `README.md` は残し、それ以外は新しいソースに入れ替える。
3. `np21w-local` で `.\build.ps1` を実行する。パッチが当たらなければ、§4.1 の手順で直す。
4. 動作確認(§5)をして、`out\` から `bin` に差し替える。差し替え前に、元の exe を別の場所に残しておくこと
   (たとえば `C:\usr\games\np21w\_bak\`。`C:\tmp` は消えやすい)。
5. `np21w-local` で、`base.conf`(と、直したパッチ)をコミットしてプッシュする。

### 4.1 パッチが当たらなくなったとき

1. `build\src` は、`BASE_REF` を checkout した作業ツリー(`.git` つき)なので、そこで手作業でパッチの内容を当てる
   (当たったところまでの変更は残っている。`git apply --reject` で、当たらない部分を `.rej` にできる)。
2. 当たらないものを手で直して、`git diff` で差分を確認する。
3. 公開元のソースの上で、パッチ 3 つを順にコミットし直して、`git format-patch <BASE_REF>..HEAD` で作り直す。
   (`np21w` リポジトリに一時ブランチを作ってもよいが、コミットは公開元に push しないこと。)
4. 作り直したパッチで `build.ps1` を実行して、通るのを確認してから、`patches\` を置き換える。

## 5. 動作確認

差し替えた exe で、次の 3 つを起動する。

| 起動 | 見ること |
|---|---|
| `SuperDepth.cmd` | 音楽のテンポと音切れ |
| `msdos5.cmd` | UMB のドライバで止まらず、DOS が起動する |
| `wiz7.cmd` | 再起動を繰り返さずに起動する |

`bin` の更新後は、`バージョン更新時の注意.txt` にあるとおり、`language\` の言語リソース DLL
(`np2_*.dll`、`np2x64_*.dll`)も同じ版に更新する(`out\language\` にできている)。

## 6. 過去のアーカイブの一括取り込み(記録)

- 公開元の Google Drive のフォルダにある、全 np21w アーカイブ(460 件)を取り込んだ。
  そのうちメイン系列(0.85、0.86、rev2〜、beta を含む)が 369 件。
- アーカイブ内のソースの置き方が 2 通りあった。
  - 新しい版(rev100 前後〜): `np21w-src-*.zip` が入っている。
  - 古い版: `<版>/src/np21w-0.86/...` のツリーが直接入っている。
  - ソースのルートディレクトリが 1 つだけなら、それを取り除いてコミットした。
  - zip の中のファイル名は、UTF-8 フラグがなければ CP932 として読み直した。
- ソースがない 31 件と、`.ish` の 24 件は取り込まなかった(`tools\import-log.md`)。
- コミット日時は、更新履歴にある日付(正午)。ない版は、アーカイブ内のソースの更新日時。
- 作者は `np21w release import`(`noreply@example.invalid`)。個人情報は入れていない。
- 再実行の方法(同じ構成でゼロから作り直す場合):
  `python -I tools\import_np21w.py <アーカイブのディレクトリ> <version.html> <リポジトリ> <ログ.md>`
  (`version.html` は更新履歴ページを保存したもの。リポジトリのディレクトリは空であること)
- 検証: `main` の rev107β6 と β3 のツリーが、公開元のソース zip と全ファイル一致することを確認した。
- β7〜β10(2026-11-21)は、`update_np21w.py` を使わず、手作業で取り込んだ。
  β9 のソース zip だけ、中のフォルダ名が `np21w-src-rev108` だった。

## 7. 注意・落とし穴

- Drive 上のファイルの一覧は、フォルダ ページを最後までスクロールしないと全件が出ない(最初は 50 件)。
- 古い `bash` 環境の `grep` は、`-E` などのオプションを解釈しない場合がある(`rtk` / `rg` のため)。
  Python(`python -I`)で処理した方が確実。
- Claude Code のツールを経由すると、コマンド中のバックスラッシュが減ることがある。
  Python のスクリプトでパスや正規表現を書き換えるときは、`chr(92)` で組み立てるか、ファイルに書いてから実行する。
- 公開済みのブランチやタグの履歴を書き換えると強制プッシュが必要になる。コミットメッセージの誤りは、
  可能なら README の記述で補う方針にしている。
- `C:\tmp` は、消えることがある(2026-11-21 に消えた)。ビルドの出力や元の exe の退避先にしないこと。

### 101 キーボードでのカナ・CAPS(2026-11-21 の調査)

- このキーボードは、Windows のレジストリで、CAPS Lock を左 Ctrl に変更してある。
  Windows が報告するキーボードは type=7、subtype=1(AX 扱い)で、`np2.cpp` の自動判定で 101 モードになる。
- カナは、**右 Shift + 右 Ctrl** で入る。日本語配列のドライバが、Shift つきの右 Ctrl を `vk=0xF2`(ひらがなキー)に
  変え、これがエミュレータのカナキー(0x72)に対応する。押すたびにロックと解除が切り替わる(ロック式)。
- 右 Alt は、`VK_MENU` ではなく `VK_KANJI`(0x19)で Windows から届くため、エミュレータの「右 Alt → カナ」の処理
  (`winkbd.cpp` の `KEY_KEY101` の分岐)は働かない。直すこともできるが、右 Shift + 右 Ctrl で足りるので、直していない。
- アプリケーションキー(0x79)は、押すときだけ CAPS(0x71)に変換され、離すときは変換されないという、
  公開元(rev91 から)の不整合があり、CAPS が押されたままになって解除できなかった。`key101` パッチで直してある
  (押すときの条件を、離すときと同じ `!= KEY_PC98` に揃えた)。
- CAPS ロックキーは、キー表のうえではロック式(押すたびに ON/OFF)のはずだが、実機のキーでは確かめていない。
- 調べるときの道具: Windows の `GetKeyboardType`、キー入力を記録する小さな Windows Forms のツール
  (`IMessageFilter` で `WM_KEYDOWN` 等の `vk`、スキャンコード、拡張フラグを記録する)。

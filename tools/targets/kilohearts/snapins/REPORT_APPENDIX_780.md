# REPORT APPENDIX 780 — KH-17 (#780): Ladder Filter (ksla) の process 閉包を x64c で測る

> 本付録は #780 (親 #61 KH-6) の Ladder の**閉包測定**。lift・wasm・native との bit-exact 比較は未実施 (§4。子 #3721 [KH-60] で実施)。
> 本体の導線は `snapins/REPORT.md`・`REPORT.md` §4 (難度表 36-41)。

## 0. 結論 (先出し)

- **Ladder の process は `LadderDsp` の vtable slot 14 = `0x1804d9930` (624 B)**。slot 14 が process であることは、既存 13 本 (`snapins.json` の `proc`、Gain〜Limiter) すべてで同じ index と一致することを確認して決めた。
- process は `this` の vtable を**間接 call** で呼ぶ: `call [rax+0xa0]` (slot 20 = `0x1804d9ba0`) と `call [rax+0x78]` (slot 15 = `0x1804d9820`)。`LadderDsp` が独自に override する slot は `0, 7, 14, 15, 20` の 5 本 (slot 20 は base `SnapinDsp<LadderDspModel>` に無い独自 slot)。
- flelift `x64c` で **5 root** の閉包 = **98 関数 / 7,766 命令** (`--closure 1000`)。unsup は測定 commit `9f02a5b69` では **4 種 38 site** (`rcpps` 34・`addsubpd` 2・`vpmovsxdq` 1・`vshufps` 1)、`f9da4f150` では **0** (§3c)。IAT import 17 種。trap 0。
- **ネガコン**: root を process 1 本にすると閉包は **2 関数 / 178 命令** で unsup 0。間接 call の先 (slot 15・20) を根に入れないと Ladder の DSP 本体は閉包に入らない。
- 残り (lift の unsup 38 site・scenario・native 比較) は子 #3721 [KH-60] に移した。Slice EQ → Filter Table は子 #3722 [KH-61]。

## 1. 数え方の定義

| 項目 | 定義 |
|---|---|
| process VA | `LadderDsp` (`.?AVLadderDsp@ladder@@`) の vtable の slot 14。既存 13 本の `snapins.json` の `proc` が `GainDsp`〜`LimiterDsp` の slot 14 と一致 (`idx [14]`)。既存の harness の先頭コメントにも同じ対応がある (`tools/targets/kilohearts/license/harness/scen_{gain,clipper,gate,haas,matrix,quickeq}.h`) |
| roots | `LadderDsp` vtable の slot のうち `SnapinDsp<LadderDspModel>` (`0x1818589f8`) と値が異なるもの (= 独自 override + slot 20)。no-op `0x1800128a0` は除外。計 5 本: `0x1804d9820 0x1804d98b0 0x1804d9930 0x1804d9ba0 0x1804db990` |
| 閉包 | `x64c.py --closure 1000`。roots から直接 call/jmp (即値先) を辿った関数集合。**間接 call は辿らない** (= root として明示したものだけが閉包に入る) |
| functions | `lift_meta.json` の `functions` 件数 (IAT thunk・tail 吸収は x64c の仕様どおり関数に数えない) |
| insns | `lift_meta.json` の `ninsn` |
| unsup sites | `lift_meta.json` の `unsup_sites` 件数 (`unsup` の値の合計と一致: 38) |

## 2. 測定 (再現: `KH_CORE=<HeartCore.core_64> OUT=<work 配下> bash scripts/ladder_x64c_closure.sh`)

| 条件 | functions | insns | unsup (種: site) | imports | traps |
|---|--:|--:|---|--:|--:|
| 閉包 (roots 5) | **98** | **7,766** | rcpps 34・addsubpd 2・vpmovsxdq 1・vshufps 1 (計 38) | 17 | 0 |
| ネガコン (root = process のみ) | 2 | 178 | 0 | 0 | 0 |

- 入力: `HeartCore.core_64` 76,642,304 B (sha256 先頭 16 hex `d55ce8b4c0ad7ebe`)。素材 `plugins-kilohearts` の `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/*` → `HeartCore.core_64` (`scripts/extract_installer.sh` の Windows 部分と同じ手順)。
- `--img 0x180000000`・`--img-size 0x625c000` は上の入力に合わせて `scripts/ladder_x64c_closure.sh` に固定した値。別 build の `KH_CORE` で使う前に、その PE の ImageBase・SizeOfImage を確かめること (スクリプトは検査しない。§5)。
- 再現実行: 同一 HeartCore で 2 回実行し、閉包 98 / 7,766 / unsup 38 が一致 (1 回目は commit 前の同内容のスクリプト、2 回目は測定 commit `9f02a5b69` の HEAD `4213316bb`)。
- 所要: x64c 閉包 1 回 約 14 s。スクリプト全体 (rtti_walk + 2 閉包) 約 29 s (load 4 vCPU)。
- unsup の内訳 (`rcpps` 34 site): 既存 snap-in の rcpps 実機近似 (`snapins/REPORT.md` §13・`scripts/rcpps_probe.c`・`approx_tables.b64`) と同じ型。x64c 側には未実装 = 次の作業の最初の項目。

## 3. 測定 commit と差分

- 測定 commit: `9f02a5b69` (`scripts/ladder_x64c_closure.sh` を追加した commit)。この commit の HEAD で再実行し、§2 と同じ値 (98 / 7,766 / unsup 38 / ネガコン 2 関数 / 178 命令) を得た。
- 測定 commit から `f9da4f150` までのコード差分: `git diff --stat 9f02a5b69 f9da4f150 -- tools/targets/kilohearts/scripts tools/targets/kilohearts/snapins/lift tools/targets/kilohearts/snapins/harness tools/targets/kilohearts/snapins/scripts tools/targets/kilohearts/snapins/run_all.sh tools/targets/kilohearts/snapins/snapins.json` は **12 files / 623 insertions / 6 deletions** (`build.py`・`kh_passes.py`・`x64c.py` 系が main 取り込みで入った)。前版はこの範囲を 0 行と書いたが誤りだった。
- `f9da4f150` から HEAD までのコード差分は 0 (本付録の追記のみ)。

## 3c. f9da4f150 時点の実測 (本 PR の head)

- 測定 commit: `f9da4f150` (コードは `9f02a5b69` から 12 files 変更。§3 の diff 参照)。測定は `f9da4f150` の worktree で実施。日付 2026-10-15 (UTC 10:57〜10:58)。
- 入力: `plugins-kilohearts` (`Kilohearts Offline Installer.zip`) → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B (sha256 先頭 16 hex `d55ce8b4c0ad7ebe`。§2 と同一)。抽出は `extract_installer.sh` の Windows 部分と同じ手順を `$RUNNER_TEMP/kh/` で行った (repo に生成物は置かない)。
- ツール: 既存の [RETDEC] (RetDec)・[EMSDK] (emsdk) を使用。`toolchain-retdec`・`toolchain-emsdk` の素材は展開していない (両者が同一版かは未確認)。

| 実行 | 結果 |
|---|---|
| `KH_CORE=$RUNNER_TEMP/kh/winpkg/HeartCore.core_64 OUT=$RUNNER_TEMP/kh_closure bash scripts/ladder_x64c_closure.sh` | 閉包 **functions 98 / insns 7,766 / unsup 0 (kinds 0・sites 0) / unlifted_callees 0 / traps 0 / imports 17**。ネガコン **functions 2 / insns 178 / unsup 0**。所要 30.1 s (load 0.9) |
| `python3 build.py ladder --path s0 --no-compare --tag s0` (`snapins/lift/`) | **exit 0**。wasm **574,270 B** / `undefined_imports []` / `shims` は memset・memmove。RetDec 10.5 s・emcc 2.7 s。全体 15.7 s |
| `python3 build.py ladder --no-compare` (既定 `--path a`) | **exit 1**。`final.ll:4918:36: error: use of undefined value '%arg3'` → emcc 失敗。全体 42.5 s。追跡: #4689 [KH-111] |

- §2 の 98 / 7,766 / 178 命令は再現した。§0 の「unsup 38」は `9f02a5b69` の値で、`f9da4f150` では unsup 0 (`x64c.py` の `addsubpd`・`vshufps`・`vpmovsxdq`・`rcpps` の対応が main 取り込みで入ったため)。
- `--no-compare` を外した run (`native_ref` の `ladder` scenario) は本付録では実行していない。scenario は未実装 (§4)。
- `build.py` の wasm 成果物は `tools/targets/kilohearts/snapins/work/` (gitignore) に置いた。`HeartCore.core_64` は `tools/targets/kilohearts/work/winpkg/` (gitignore) に置いた。どちらも commit しない。

## 3d. self / ctx のレイアウト (機械語からの集計・#5326 / KH-150)

- 測定 commit: `858dc0e1c` (§3d の表を書いた commit。script の process 末端は `0x1804d9b9c`)。修正 commit `67b2a3a8c` で末端を `0x1804d9ba0` に直した。`git diff 858dc0e1c 67b2a3a8c -- tools/targets/kilohearts/scripts` の差分は range end の 1 行のみ。
- 再測定 commit: `67b2a3a8c` (census を実行した commit。以降の修正 commit は REPORT のみで script は変えない)。`git diff 67b2a3a8c HEAD -- tools/targets/kilohearts/scripts` は空。
- 再現: `python3 scripts/ladder_layout_census.py <HeartCore.core_64> [out.json]` (入力は §2 と同一の HeartCore。sha256 先頭 16 hex `d55ce8b4c0ad7ebe`)。逆アセンブラは capstone 5.0.7。
- 素材: 再測定 commit で `plugins-kilohearts` (`oc_artifacts`) を展開し、`HeartCore.core_64` 76,642,304 B・sha256 先頭 16 hex `d55ce8b4c0ad7ebe` (§2 と同一) を確認してから実行した。標準出力は §3d-4。§3d の表はこの出力と照合済み。
- 範囲: process `[0x1804d9930, 0x1804d9ba0)` (624 B)・slot 15 `[0x1804d9820, 0x1804d98b0)` (144 B)・slot 20 `[0x1804d9ba0, 0x1804db990)` (7,664 B。x64c の関数境界 = 次の関数 `0x1804db990` まで)。
- 方法: メモリオペランドを直線走査し、`rcx` (this)・`rdx` (ctx) 由来のレジスタを追う。分岐は無視する簡易集計。**`[rdx+0x3188]` は ctx の model 参照として扱う**。
- 型は命令の幅からの推定 (`movss`=f32・`movd`/`mov dword`=i32・`movzx byte`/`mov byte`=u8・`movaps`/`movups`=v128)。**enum 名・フラグ意味は未確定**。

### 3d-1. process `0x1804d9930` (slot 14)

| 参照元 | オフセット | 幅 | 型 (推定) | 読み/書き | 根拠 (VA) |
|---|--:|--:|---|---|---|
| this | `+0x0` | 8 | ptr | 読み (vtable) | `1804d9a3a` `mov rax,[rdi]` |
| this | `+0x528` | 4 | i32 | 読み・書き | `1804d9951` 読み・`1804d9975` 書き (値 `ebp`) |
| this | `+0x52c` | 4 | i32 | 読み・書き | `1804d9958` 読み・`1804d9985` 書き (値は ctx 由来) |
| this | `+0x5d8` | 8 | ptr | 読み | `1804d9b79` `mov rcx,[rdi+0x5d8]` → 最後の `call 0x1802ff250` の引数 |
| ctx | `+0x3188` → `+0x10` | 4 | i32 | 読み | `1804d9982` `mov eax,[rax+0x10]` (→ `this+0x52c`)・`1804d9a34` `cmp eax,[r8+0x10]` |
| ctx | `+0x3188` → `+0x14` | 1 | u8 | 読み | `1804d994a` `movzx ebp,[rax+0x14]` (`&1` して `this+0x528` へ) |
| vtable | `[this]+0x78` (slot 15) | 8 | fn ptr | 呼び出し | `1804d9a86` `mov rax,[rdi]`・`call [rax+0x78]` |
| vtable | `[this]+0xa0` (slot 20) | 8 | fn ptr | 呼び出し | `1804d9a4c`・`1804d9a77`・`1804d9ab5` `call [rax+0xa0]` (`rax`=`[rdi]`) |

> 注: 間接 call の `rax` は `[rdi]` (this の vtable) 由来。ctx の model ではない (最終版の集計でも `ctx.model` の行には出ない)。

### 3d-2. slot 15 `0x1804d9820`

| 参照元 | オフセット | 幅 | 型 (推定) | 読み/書き | 根拠 (VA) |
|---|--:|--:|---|---|---|
| self (`rsi`=this) | `+0x4c4`・`+0x4dc`・`+0x4f4`・`+0x50c`・`+0x524` | 1 | u8 | 書き (値 1) | `1804d9842`・`1804d9849`・`1804d9857`・`1804d9850`・`1804d985e` |
| self | `+0x528` | 8 | i64 | 書き (値 `0x200000002`) | `1804d9899` |
| self | `+0x530`・`+0x540`・`+0x550`・`+0x560`・`+0x570`・`+0x580`・`+0x590`・`+0x5a0` | 16 | v128 | 書き (0 初期化) | `1804d9834`〜`1804d9888` |
| self | `+0x70` | — | サブオブジェクト | `this+0x70` を `rcx` にして `call 0x180b824d0` | `1804d982c` |

### 3d-3. slot 20 `0x1804d9ba0`

| 参照元 | オフセット | 幅 | 型 (推定) | 読み/書き | 根拠 (VA) |
|---|--:|--:|---|---|---|
| self (`rbx`=this) | `+0x60` | 4 | f32 | 読み | `1804d9c17` `movss xmm7,[rcx+0x60]` (rcx=this) |
| self | `+0x70` | 8 | ptr (サブオブジェクト) | 読み (アドレス) | `1804d9e02` `lea r14,[rbx+0x70]` → `call 0x18065f6d0` |
| self | `+0x4b0`〜`+0x5a0` | 8〜16 | f32/i32/v128 混在 | 読み・書き | 上の集計 (`1804d9cdc` 以降の多数) |
| self | `+0x528` | 4 | i32 | 読み | `1804d9c23` `mov eax,[rbx+0x528]`・`cmp eax,1` で分岐 (slot 14 が書いた値) |
| self | `+0x52c` | 4 | i32 | 読み | `1804d9c5a` `mov r14d,[rbx+0x52c]`・`cmp r14d,1` (`1804d9c5e` 付近)・`test r14d,r14d` で分岐 |
| self | `+0x5b0`〜`+0x5d0` | 8 | i64 (`movddup`) | 読み | `1804da7d1`〜`1804db1f9` |
| ctx (`r15`=ctx) | `+0x3188` → `+0x0`・`+0x4`・`+0x8`・`+0xc` | 4 | f32 | 読み | `1804d9cb7` `minss [rcx]`・`1804d9c55` `movss [rcx+4]`・`1804d9c3a` `movss [rcx+8]`・`1804d9e19` `movss [rax+0xc]` |

### 3d-4. 集計の生データ

- 出力: 再測定 commit `67b2a3a8c` で `scripts/ladder_layout_census.py` を実行 (exit 0・所要 0.1 s)。全 71 行 (process slot14 6 行・slot15 14 行・slot20 51 行)。3d-1〜3d-3 の表は、この出力のうち上表に写した行だけ。
- role 別の行数・先頭オフセット: process slot14 = self 4 行 (先頭 `+0x0`)・ctx.model 2 行 (先頭 `+0x10`)。slot15 = self 14 行 (先頭 `+0x4c4`)。slot20 = self 47 行 (先頭 `+0x60`)・ctx.model 4 行 (先頭 `+0x0`)。
- register の対応: script は `rcx`=self・`rdx`=ctx だけを seed する。script は `mov reg,reg` の複写を追跡する。slot 15 の `rsi`=this は `1804d9825 mov rsi,rcx`、slot 20 の `rbx`=this・`r15`=ctx は `1804d9c14 mov rbx,rcx`・`1804d9c11 mov r15,rdx` で、census 出力で確認済み。process の `rdi`=this は `1804d9940 mov rdi,rcx`、ctx.model は `1804d9943 mov rax,[rdx+0x3188]` 由来。
- `self`・`ctx.model` の列は、関数の入口の `rcx`/`rdx` 由来で追った結果。分岐は見ない。

## 4. 未実施・未達 (受入条件との対応)

| 受入 | 状態 |
|---|---|
| 段階順に 1 本ずつ bit-exact (Ladder → Slice EQ → Filter Table) | **未達** (Ladder は閉包と `--path s0` の wasm 生成まで。native 比較は未実施)。子 #3721 [KH-60] (Ladder)・#3722 [KH-61] (Slice EQ → Filter Table) に移した |
| ネガコン・数え方の定義・再計算スクリプトを REPORT に書く | 数え方 = §1、ネガコン = §0・§2 (process 1 本の閉包)、再計算 = `scripts/ladder_x64c_closure.sh`。f9da4f150 で再現 (§3c)。bit-exact 用のネガコン (1 bit 改変の検出) は未実施 |
| 既存 14 本の `run_all.sh` が不変 | `snapins.json` の既存 14 エントリは main と同値 (`ladder` 行の追加のみ)。`lift/gen_simd.py` に addsubpd を 4 行追加。`run_all.sh` 本体は未実行 (既存 14 本の bit-exact 実測は本 PR では行っていない) |

## 5. 次の作業 (未解決)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `build.py ladder` の既定 `--path a` が emcc で失敗 (`final.ll:4918` の `%arg3` 未定義) | 既定経路の lift が通らない。`--path s0` は通る (§3c) | #4689 [KH-111] |
| Ladder scenario の実装・`native_ref` 比較 (`--no-compare` を外した run) | 受入の bit-exact 本体。scenario 未実装のため `--no-compare` 無しは失敗する | #3721 [KH-60] |
| 間接 call (`[rax+0xa0]` slot 20 / `[rax+0x78]` slot 15) の wasm 側の dispatch 方式 | `this` 依存の vtable 呼び出し。native 比較の scenario で `this` の vtable を実物で組む必要がある (snapins の `scenarios` と同じ型) | #3721 [KH-60] |
| Ladder scenario・bit-exact 比較・ネガコン (1 bit 改変) | 受入の本体 | #3721 [KH-60] |
| `ladder_x64c_closure.sh` の `--img`・`--img-size` を PE から読む (または一致を検査する) | 別 build の `KH_CORE` で閉包が黙って狂う。本 PR では見送り: スクリプトを変えると §3 の commit 以降のコード差分が 0 でなくなり、再測定が要る | #3721 [KH-60] (閉包を次に測るときに入れる) |
| Slice EQ (kpeq) → Filter Table (ksft) の bit-exact 化 | 親 #780 の受入の残り | #3722 [KH-61] |

## 6. 付録の位置づけ

- `docs/DOC_MAP.md` に本付録の行を登録 (pr-lint の DOC_MAP 未登録チェック用)。
- 数値の正本は本付録。`snapins/REPORT.md` には書かない (行数上限 250 のため。本付録へのリンクだけを後で足す)。

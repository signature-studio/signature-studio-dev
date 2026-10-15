# REPORT APPENDIX 780 — KH-17 (#780): Ladder Filter (ksla) の process 閉包を x64c で測る

> 本付録は #780 (親 #61 KH-6) の Ladder の**閉包測定**。lift・wasm・native との bit-exact 比較は未実施 (§4。子 #3721 [KH-60] で実施)。
> 本体の導線は `snapins/REPORT.md`・`REPORT.md` §4 (難度表 36-41)。

## 0. 結論 (先出し)

- **Ladder の process は `LadderDsp` の vtable slot 14 = `0x1804d9930` (620 B)**。slot 14 が process であることは、既存 13 本 (`snapins.json` の `proc`、Gain〜Limiter) すべてで同じ index と一致することを確認して決めた。
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
- ツール: 既存の `/opt/retdec` (RetDec)・`/opt/emsdk` (emsdk) を使用。`toolchain-retdec`・`toolchain-emsdk` の素材は展開していない (両者が同一版かは未確認)。

| 実行 | 結果 |
|---|---|
| `KH_CORE=$RUNNER_TEMP/kh/winpkg/HeartCore.core_64 OUT=$RUNNER_TEMP/kh_closure bash scripts/ladder_x64c_closure.sh` | 閉包 **functions 98 / insns 7,766 / unsup 0 (kinds 0・sites 0) / unlifted_callees 0 / traps 0 / imports 17**。ネガコン **functions 2 / insns 178 / unsup 0**。所要 30.1 s (load 0.9) |
| `python3 build.py ladder --path s0 --no-compare --tag s0` (`snapins/lift/`) | **exit 0**。wasm **574,270 B** / `undefined_imports []` / `shims` は memset・memmove。RetDec 10.5 s・emcc 2.7 s。全体 15.7 s |
| `python3 build.py ladder --no-compare` (既定 `--path a`) | **exit 1**。`final.ll:4918:36: error: use of undefined value '%arg3'` → emcc 失敗。全体 42.5 s。追跡: #4689 [KH-111] |

- §2 の 98 / 7,766 / 178 命令は再現した。§0 の「unsup 38」は `9f02a5b69` の値で、`f9da4f150` では unsup 0 (`x64c.py` の `addsubpd`・`vshufps`・`vpmovsxdq`・`rcpps` の対応が main 取り込みで入ったため)。
- `--no-compare` を外した run (`native_ref` の `ladder` scenario) は本付録では実行していない。scenario は未実装 (§4)。
- `build.py` の wasm 成果物は `tools/targets/kilohearts/snapins/work/` (gitignore) に置いた。`HeartCore.core_64` は `tools/targets/kilohearts/work/winpkg/` (gitignore) に置いた。どちらも commit しない。

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

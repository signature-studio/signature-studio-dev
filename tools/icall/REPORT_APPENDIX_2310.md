# 付録: icall #2310 (ICALL-72) — BLK+0 (0x36319008) 書込み store の wasm オフセット対応

> 親: #1998 (ICALL-54) の付録 `REPORT_APPENDIX_1998.md` §1 の未達 (IR 行 19132 → wasm オフセット)。本付録は子 issue #2310 の測定結果を記録する。

## 1. 結論

- **受入条件 1 (wasm オフセットまで特定): 達成** (586c8b0c 時点の値。1998 付録の再実行 HEAD `1fff0e4f` でも行 19132)。`0x36319008` に "emsc" (`0x63736d65`) を書く store (IR 行 19132) は、wasm の関数 `function_181057d20` 内の **`i64.store offset=909217800` (wasm ファイル内オフセット `0x427be`)** に対応する。検証 HEAD `6f7e941a` でも `52ad0ce1` (#1664) の影響で IR 行 19056・オフセット `0x427bd` に移動している (§6-4・§6-6)。
- **受入条件 2 (route 側 / lift 側の分類): 達成 (lift 側に分類)**。store 命令は lift が生成した `function_181057d20` の中にあり、route 側 (data 敷設) は 1998 付録 §3 で否定済み。値 "emsc" を作る `0x400000004` は、RetDec の RDA 段で脱落する frame store 2 本の欠落から生じる (元の機械語は 4B store 2 本)。根拠と HEAD 再測定は §6。
- **既知類型との関係**: D24 候補 (`REPORT_APPENDIX_2394.md` §6・新規、DEFECTS.md 未編集)。
- **受入条件 3 (`fa_sweep.sh 8 60` の wasm のみ err 件数): 達成**。wasm のみ err は 9 件で、現状の件数と一致 (実測は §3)。

## 2. 対応の詳細 (実測)

測定: `fa_wc_build.sh` で監視付き wasm (`work/fa_wc/fa_wc.cjs`) を作り、`fa_wc_drv.cjs` で `181057b38` を 8 入力で実行。

> 注 (HEAD 再確認): 本節の IR 行 19132 と wasm オフセット `0x427be` は 586c8b0c 時点 (`52ad0ce1` より前) の値で、1998 付録の再実行 HEAD `1fff0e4f` でも行 19132。検証 HEAD `6f7e941a` でも IR 行 19056・`0x427bd` に移動している (§6-4・§6-6)。値 `0x63736d65` の BLK+0 への書込み 8 件は検証 HEAD でも変わらない。

| 段階 | 観測 |
|---|---|
| 監視付き IR の挿入 | `fa_wc.py instr`: `store total=5526 instrumented=5526 unhandled=0` |
| 実行 (8 入力) | 全入力で `memory access out of bounds`。`WC line=` 168 行 (1998 §2 と一致)。`WC line=19132 addr=36319008 sz=8 val=63736d65` が 8 件 |
| `__wchk` の第 4 引数 | IN 側 (`work/fa_route/oi.flat.ll`) の行番号。OUT 側 (`oi.wc.ll`) の行番号ではない。`oi.flat.ll` 19132 行 = `store i64 %1, ptr %ce31n11_function_181057d20` |
| wasm 側の位置 | `wasm-dis` で `$function_181057d20` (wat 140562 行〜)。wat 141476 行の `i64.const 19132` → `i64.store offset=909217800` (wat 141490 行) |
| バイナリオフセット | `llvm-objdump -d fa_wc.wasm`: `i64.const 19132` が `0x4279a`、直後の `i64.store offset=909217800` が **`0x427be`** |

対応の読み方: wasm 内の `i64.const 19132` は `__wchk` に渡す IR 行番号 (計装用の定数)。その直後に、同じ IR 行の本体 store (`909217800` = `0x36319008`) が続く。

DWARF の行表 (`llvm-dwarfdump --debug-line`) には `.ll` の行情報が無い (`-g` を付けても lift IR は `!dbg` を持たない)。そのため、対応は `__wchk` の定数を介して取った。

## 3. 測定 (`tools/icall/diff/fa_sweep.sh 8 60`)

| 項目 | 値 |
|---|---|
| 測定 commit (コードを変えた最後の commit) | `586c8b0c` (origin/main 取り込み時点の HEAD。本 PR はコード変更なし) |
| 素材 | `fl-win64`・`plugins-freshair` (`fetch.sh`: win 17 files, factory .epf 8)・`toolchain-emsdk` ([EMSDK])・`toolchain-retdec` ([RETDEC])・`work-icall`・`work-liftlib` |
| `tools/ott/native/build.sh` | OK |
| `tools/icall/fa_route_build.sh` | OK、11.5 s |
| `tools/icall/diff/fa_wc_build.sh` | OK、3.2 s (`store total=5526 instrumented=5526 unhandled=0`) |
| `tools/icall/diff/fa_sweep.sh 8 60` | 131 関数、73.1 s (real 1m13.145s)、開始 load 0.58・終了 0.95 (4 vCPU) |
| 区分 | **bit 一致 46 / native crash・timeout 66 / wasm のみ err 9 / 値の不一致 10** (合計 131) |

- wasm のみ err は 9 件で、1998 §4 と一致。
- bit 一致 / 値の不一致 は 1998 §4 (47 / 9) と 1 件ずれた。**`REPORT_APPENDIX_1998.md` §4 の 47 / 9 が正本**で、本 run の 46 / 10 は `fa_sweep` の ±1 揺れと判断し、#2302 (ICALL-71) で追跡する。本付録では再現判定を行わず、この実測値をそのまま記録する。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| §6 で分類済み (#2310 の受入条件 2)。脱落 store を戻す pass は #2427 (ICALL-77・CLOSED) の修復 #2514 で merge 済み。残件は #2508 (ICALL-78) | 受入条件 2 | #2514 (merge 済み) / #2508 (ICALL-78) |
| `fa_sweep` の bit 一致の ±1 揺れ (本 run 46、1998 は 47) | sweep 件数の判定精度 | #2302 (ICALL-71) |

## 5. 再現 (IR 行 19132 は 586c8b0c 時点の値)

以下の `19132`・`0x427be` は 586c8b0c (1fff0e4f も同値) の値。検証 HEAD `6f7e941a` でも IR 行 19056・オフセット `0x427bd` になるため、この grep では得られない。検証 HEAD の手順は §6-7。

```
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 FA_DL=$RUNNER_TEMP/plugins-freshair TMPDIR=$RUNNER_TEMP
export RETDEC_ROOT=<[RETDEC] の展開先>   # 環境変数の規約は WORKFLOW §11。[EMSDK] の所在は emsdk_env.sh が設定する $EMSDK
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .
mkdir -p "$FL_WIN64_DIR" "$FA_DL" && tar --zstd -xf "$ARTIFACTS_DIR/fl-win64.tar.zst" -C "$FL_WIN64_DIR"
tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$FA_DL"
bash tools/targets/freshair/fetch.sh
bash tools/ott/native/build.sh
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_wc_build.sh
node tools/icall/diff/fa_wc_drv.cjs $PWD/tools/icall/work/fa_wc/fa_wc.cjs 181057b38 2>err.txt
grep -c '^WC line=' err.txt                       # 168
grep '^WC line=19132' err.txt | head -1           # addr=36319008 val=63736d65
"$EMSDK/upstream/bin/llvm-objdump" -d tools/icall/work/fa_wc/fa_wc.wasm | grep -A1 'i64.const.*19132' # 直後の store (0x427be)
bash tools/icall/diff/fa_sweep.sh 8 60
```

## 6. 受入条件 2: 書込み元の分類 (route / lift)

**結論: BLK+0 (`0x36319008`) への "emsc" 書込みの書込み元は lift 側に分類する。** route 側 (data 敷設) は否定済み。値を作る frame store 2 本が RetDec の RDA 段 (と後続の Combine 段) で脱落することが原因で、これは lift 側の欠陥。脱落 store を戻し alloca を統合すると結果が変わることを §6-2 で実測した。因果の範囲は下の真因の項。

根拠 (引用元):

- 書込み命令: lift が生成した `function_181057d20` 内の `store i64 %1, ptr %ce31n11_function_181057d20` (§2・`REPORT_APPENDIX_1998.md` §2)。
- route 側の否定: `ott_data_install` が書くのは `0x310c4000`・`0x3125c000`・`0x31354000` のみで BLK を含まない。DLL の bytes に "emsc" は無い (`REPORT_APPENDIX_1998.md` §3。本 HEAD の `rw.dll` でも `emsc` の出現 0 件を確認)。route 側 = data 敷設の意味で、memory shift・heap 配置 (route 内部の配置) は個別には測っていない。
- 元の機械語: `0x181057b38` の 2 本の 4B store (`mov [rbp-0x30],eax`・`mov [rbp-0x2c],eax`)。8B で読む命令は無い (`REPORT_APPENDIX_2394.md` §2)。
- 真因: RetDec の `LLVM instruction optimization using RDA` 段で `[rbp-8]` (`0x181057b71`)・`[rbp-0x20]` (`0x181057b87`) の 2 本の frame store が IR から脱落する (`REPORT_APPENDIX_2394.md` §3 の段別表)。2 store を戻し 16B 1 alloca にすると BLK+0 への "emsc" 書込みは 8 → 0 (`REPORT_APPENDIX_2394.md` §4)。因果の範囲: この 8 → 0 は『2 store を戻す + alloca を 16B 1 本に統合』の結果。alloca を別のまま store だけ戻す negative (sep) は TRAP 8・BLK+0 emsc 8 のまま (`fs2394.log` の sep 行、HEAD でも同じ)。よって真因は『脱落 store』と『callee の +8 読みが alloca の範囲外 (UB) になる配置』の組合せ (`REPORT_APPENDIX_2394.md` §1(b)・§3)。
- 既知類型との関係: D24 候補 (`REPORT_APPENDIX_2394.md` §6・新規、DEFECTS.md 未編集。D23 は DEFECTS.md 既存項目 (M11 / #1630) のため不可)。
- 脱落 store を戻す pass は #2427 (ICALL-77・CLOSED) で実装され、#2514 で merge 済み (`REPORT_APPENDIX_2427.md`)。残件 (180da6e60 候補 10 件の分類・fixed 後の 8/8 不一致・SlateCore bytes 照合) は #2508 (ICALL-78・OPEN)。merge 規則の一般化 (他関数での妥当性) は 2427 §5 の限界に記載されており、#2508 の受入条件 4 に追記した (起票先は #2508)。

### 6-1. HEAD 再測定 (WORKFLOW §6)

| 項目 | 値 |
|---|---|
| 測定 commit (測定した HEAD) | `6f7e941a` (PR head を本 run で再測定した commit) |
| 経路のコードを変えた最後の commit | `111c1411` (#2427 の `FA_FRAME_SLOT` 組込み・既定 OFF。main 取り込みで `6f7e941a` に入った)。`52ad0ce1` (#1664) の `tools/m5/ir5_patch.py` +3 行も経路に入る |
| 比較範囲 (`fa_route_build.sh` が実際に呼ぶ経路) | `tools/icall/fa_route_build.sh`・`tools/icall/{ir_fix_mask,ir_fix_vstore,ir_fix_cookie,frame_slot_restore,ir_flatten,ir_override,vex_gen,simd_merge,frame_slot_2394,frame_slot_probe}.py`・`tools/icall/{rt,diff}`・`tools/m2` (`ir_normalize.py`)・`tools/m5` (`ir5_patch.py`)・`tools/m11/m11_simd2.py`・`tools/m11/msimd11_core.h`・`tools/ott/lift/data_gen.py`・`tools/ott/native`・`tools/targets/freshair` |
| `git diff 54bacdc0 6f7e941a -- <上の経路>` | `fa_route_build.sh` +6 行 (`FA_FRAME_SLOT` hook・既定 OFF) と `frame_slot_restore.py` 新規 219 行 (既定 OFF の経路では呼ばれない)。`--stat` の合計 225 insertions |
| `git diff 2c8088f4 6f7e941a -- <上の経路>` (`--stat`) | 5 ファイル 342 insertions・2 deletions。内訳: 上の 225 行に、`tools/m5/ir5_patch.py` +3 (`52ad0ce1`)、`tools/icall/diff/dispatcher_ids.py` +112 と `ott_apiset_cmp.py` ±4 (`5f6547c2`・#2225。測定経路からの参照は 0 件) |
| 測定 commit から HEAD までの経路差分 | `git diff 6f7e941a HEAD -- <上の経路>` は 0 行 (本 PR の後続 commit は REPORT・docs のみ。commit 後に `git diff --stat` で確認) |
| 実行 | `bash tools/ott/native/build.sh` (rc 0)、`SWEEP=1 bash tools/icall/frame_slot_2394.sh` (rc 0・§1〜§6 全部と base/fixed/sep の sweep)、`FA_CORE=<rw.dll> bash tools/icall/diff/fa_sweep.sh 8 60` (rc 0) |
| 所要 | `frame_slot_2394.sh` 193.6 s (15:18:31 → 15:21:45)、`fa_sweep.sh 8 60` 71.4 s (15:22:30 → 15:23:41) |
| load (`uptime` の 1 分平均) | `frame_slot_2394.sh` 開始 1.37 → 終了 1.12、`fa_sweep.sh` 開始 0.68 → 終了 0.99 (4 vCPU・逐次) |
| 素材 | `work-icall` (`tools/icall/work/rt_freshair-core`・`rw.dll`)、RetDec は runner 既設の [RETDEC] (`RETDEC_ROOT` 既定)。emsdk: 本 run の素材 (`$ARTIFACTS_DIR`) に `toolchain-emsdk` は無かったため、上流 `emscripten-core/emsdk` を pin 版 `6.0.12` (`tools/m1/flags.sh` の `EMCC_VERSION_PIN`) で [EMSDK] に導入した (`emsdk install 6.0.12`・`emcc` の sanity 通過)。`plugins-freshair`・`fl-win64` は未使用 |

> 注: 旧版の検証 HEAD `54bacdc0` の値 (`fa_sweep.sh 8 60` の 47 / 66 / 9 / 9) は、本節の `6f7e941a` の実測と同じ値だった。§6-2・§6-4・§6-5 は `6f7e941a` の実測で置き換えた。

### 6-2. 実測結果 (`6f7e941a`・`frame_slot_2394.sh` §4 の 8 入力と §1〜§3)

| 条件 | 8 入力 | WC 行 | emsc を含む行 (WC+WCV) | BLK+0 への "emsc" | `REPORT_APPENDIX_2394.md` §4 と |
|---|---|---|---|---|---|
| base (現 IR) | OK 0 / TRAP 8 | 168 | 32 (WC 24 + WCV 8) | 8 | 一致 |
| fixed (2 store 戻し・16B 1 alloca) | OK 8 / TRAP 0 | 168 | 0 | 0 | 一致 |
| sep (負の対照) | OK 0 / TRAP 8 | 168 | 32 (WC 24 + WCV 8) | 8 | 一致 |

- §1 (元の機械語): `before.0.drc.dsm` の再 decode と `rw.dll` の同 VA が 205 B 一致。
- §2 (RDA 段の表): `REPORT_APPENDIX_2394.md` §3 の段別表と全セル一致。
- §3 (census): F 131・dsm に命令あり 130・frame pointer 型 4・rbp 相対 mov store 29・脱落 21・候補 12 件 / 2 関数 (`181057b38` が 2 件、`180da6e60` が 10 件)。`REPORT_APPENDIX_2394.md` §5 と一致。

### 6-3. IR 行番号の差 (検証 HEAD `6f7e941a` で確認)

- 検証 HEAD の `work/fa_route/oi.flat.ll` は 25694 行。`REPORT_APPENDIX_1998.md` §2 の 25805 行 (586c8b0c・1fff0e4f 時点) とは一致しない。
- BLK+0 への "emsc" 書込みの WC 行は検証 HEAD では `line=19056` (8 件)。§2 と `REPORT_APPENDIX_1998.md` §2 の行 19132 は旧 IR の番号で、検証 HEAD の WC 行には 19132 が現れない。
- wasm 側: 検証 HEAD の `i64.const 19056` は `fa_wc.wasm` の 0x42799、直後の `i64.store offset=909217800` は 0x427bd (§6-4)。
- 行番号の差の原因: `52ad0ce1` (#1664) の `tools/m5/ir5_patch.py` の変更 (`; uselistorder directives` 直前の空行の除去)。旧版を当てると 25805 行・行 19132 に戻る (§6-6)。行番号を引くときは測定 commit を併記すること。

### 6-4. 受入条件 1 の HEAD 再確認

| 項目 | §2 (586c8b0c 時点・旧 IR) | HEAD 6f7e941a (本再確認) |
|---|---|---|
| BLK+0 (`0x36319008`) へ `0x63736d65` を書く WC 行 (`fa_wc_drv.cjs`・base) | 行 19132 | **行 19056** (8 件) |
| 行 19132 の WC 行 | 8 件 | 0 件 |
| `fa_wc_drv.cjs <fa_wc.cjs> 181057b38` の 8 入力 | OK 0 / TRAP 8 | OK 0 / TRAP 8 |
| 監視対象の IR 行 (`oi.flat.ll`) | `store i64 %1, ptr %ce31n11_function_181057d20` | 行 19056 が同じ store |
| `i64.const` (IR 行) の wasm 位置 (`llvm-objdump -d`) | 0x4279a | **0x42799** |
| `i64.store offset=909217800` の wasm 位置 | 0x427be | **0x427bd** |

- HEAD の WC 行は 168 行、`0x63736d65` を含む行は 32 件 (WC 24 + WCV 8。`frame_slot_2394.sh` は err 全体を grep する)、BLK+0 への書込みは 8 件 (`WC line=19056 addr=36319008 sz=8 val=63736d65`)。`fa_wc.cjs` は HEAD の `fa_route` から `fa_wc_build.sh` で作り直した。
- wasm の確認: `llvm-objdump -d fa_wc.wasm` で `42799: i64.const 19056`。`427bd: i64.store 909217800` は、その間に 12 命令 (`__wchk` の呼出し 1 件を含む) を挟んで続く (base は `i32.const 0` のアドレス + offset `0x36319008`)。

### 6-5. 受入条件 3 の HEAD 再測定 (`fa_sweep.sh 8 60`)

| 項目 | 値 |
|---|---|
| 測定 HEAD | `6f7e941a`。route・wc は `frame_slot_2394.sh` の §6 後始末で base に戻した状態を使う |
| 素材 | `work-icall` (`rt_freshair-core`)。`FA_CORE` = `rw.dll` (plugins-freshair は未展開。`REPORT_APPENDIX_2394.md` §7 と同じ条件) |
| 実行 | `FA_CORE=<rw.dll> timeout 600 bash tools/icall/diff/fa_sweep.sh 8 60` (foreground、rc 0)。`FA_CORE` 未指定だと既定の plugins-freshair の SlateCore を探して `ott_load failed` となり、全 131 件が `crash_or_timeout` になる |
| 所要 | 71.4 s (15:22:30 → 15:23:41) |
| load (1 分平均) | 0.68 (開始) → 0.99 (終了) |
| 区分 (131 関数) | **bit一致 47 / native crash・timeout 66 / wasm のみ err 9 / 値の不一致 9** (合計 131) |

- wasm のみ err の 9 件は `0x1803b5500`・`0x1803fb6f0`・`0x18040c950`・`0x180c8b280`・`0x180ca1480`・`0x180da5f20`・`0x181057b38`・`0x181057d20`・`0x18106632c` で、期待の 9 件と完全に一致。
- 指定 3 関数の判定 (`sweep.jsonl`): `181057b38` は n 8・match 0・mismatch 8・wasm_err 8 (wasm のみ err)。`180c8b280` は n 8・match 6・mismatch 2・wasm_err 2。`181057d20` は n 8・match 0・mismatch 8・wasm_err 8。
- 区分は `REPORT_APPENDIX_2394.md` §7 の rw.dll の base (47 / 66 / 9 / 9) と一致。§3 (46 / 66 / 9 / 10) は plugins-freshair を使った別条件のため直接比べない。§3 は変更しない。

### 6-6. 行番号移動の原因 (`52ad0ce1`)

| 項目 | 値 |
|---|---|
| 差分 | `git diff 586c8b0c 54bacdc0 -- tools/m5/ir5_patch.py` の変更は `52ad0ce1` (#1664) の 1 件。`normalize` に「`; uselistorder directives` の見出しと直前の空行を消す」正規表現を 3 行追加 |
| 他の経路 | `586c8b0c`..HEAD で `tools/m2`・`tools/icall/ir_flatten.py` に変更なし (`git log` で確認)。`fa_route_build.sh` の変更は `FA_SRC` の既定値を変えないフック (`4831c686`) と、`FA_FRAME_SLOT` の既定 OFF フック (`111c1411`)。`52ad0ce1` は `tools/liftlib/liftlib/passes/base.py` (+3) と `tools/m11/test_a7_uselistorder.py` (+51) も変更するが、fa_route 経路 (`fa_route_build.sh`・`ir_flatten.py`・`ir5_patch.py`・`m2/ir_normalize.py` 等) は liftlib を参照しない (grep 0 件) ため結論に影響しない |
| 旧版の再現 | `git show 52ad0ce1^:tools/m5/ir5_patch.py` を `$RUNNER_TEMP` に書き出し、HEAD の `work/fa_route/oi.norm0.ll` に当てる。続けて HEAD の `tools/icall/ir_flatten.py` (`--limit 0x10000000`) を通す |
| 結果 | 旧版: lift 段 26014 行、flat 段 **25805 行・store 行 19132**。HEAD: lift 段 25903 行、flat 段 25694 行・store 行 19056 |
| 整合 | 旧版の flat 段は `REPORT_APPENDIX_1998.md` §2 の 25805 行・行 19132 と一致。差 111 行は HEAD の `oi.norm0.ll` の `; uselistorder directives` 見出し件数 (111) と一致 |
| 結論 | 行番号と wasm オフセットの移動は、`52ad0ce1` の IR 正規化による行数の変化で説明できる (再現で確認)。旧版の WC・sweep は未測定で、挙動の差は確認していない |

### 6-7. 再現

```
export TMPDIR=$RUNNER_TEMP RETDEC_ROOT=<[RETDEC] の展開先>
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .      # tools/icall/work/ へ (§5 と同じ)
bash tools/ott/native/build.sh
bash tools/icall/frame_slot_2394.sh                          # §4 の 8 入力は SWEEP 無しで出る
```

6-4・6-5 (HEAD 再確認。`FA_CORE` は素材の `rw.dll`):

```
export FA_CORE=<work-icall の展開先>/tools/icall/work/rt_freshair-core/rw.dll TMPDIR=$RUNNER_TEMP  # FA_CORE 未指定だと全件 crash になる
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_wc_build.sh
node tools/icall/diff/fa_wc_drv.cjs $PWD/tools/icall/work/fa_wc/fa_wc.cjs 181057b38 2>err.txt
grep -c 'WC line=19056 addr=36319008 sz=8 val=63736d65' err.txt   # 8
"$EMSDK/upstream/bin/llvm-objdump" -d tools/icall/work/fa_wc/fa_wc.wasm | grep -E '^ *(42799|427bd):'
timeout 600 bash tools/icall/diff/fa_sweep.sh 8 60
```

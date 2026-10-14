# tools/shimx REPORT 付録 — SHX-T39 (#3149) unit 23 の baseline が 0xf960 の後に入る分岐条件

> 親: #1607 (SHX-T9e) の受入 2 の残件 (#1607 本文の子 issue 移送分)。本体: `tools/shimx/REPORT_SHX-T9.md` §3.3.4。
> 前段: `REPORT_SHX-T9h.md` §3.3.7 (現行 `m11_ov.c` からの baseline 再生成)・`REPORT_SHX-T9j.md` (GetLastError)。
> 証跡: `tools/shimx/evidence_3149/` (`repro.sh` で IR 行を再抽出。`ir_branch_excerpt.txt` は出力の保存。`probe_*_head.txt` は HEAD の実行時 trace)。
> 測定 commit: `5e8ce9ba` (PR #3163 の head。コード差分は無く、本付録と証跡のみ)。HEAD で再測定した (2026-10-14)。
> 素材: `oc_artifacts: fl-win64 work-m11 work-liftdiff toolchain-emsdk`。emsdk は上流の pin 版 6.0.12 を runner 上に導入し、[EMSDK] (`docs/REFERENCES.md` §4) へ symlink した (repo 外)。

## 1. 結論

- HEAD で再生成した baseline (`m11_boot.cjs`) の unit 23 は、`0xf960` (`function_40f960` = TObject.NewInstance) の後、`function_467c40` の **slot ゲート** で「非 0」側に入る。shimx 版 (`m11_sx_trace_soft_fix.cjs`) も同じ分岐・同じ値に入る。
  - 分岐点: IR `function_467c40` の `icmp eq (Q(Q(0x15E3AF0)), 0)` (`boot_final3.ll` L174340–174342)。`0x15E3AF0` は VA (LVA `0x11E3AF0`) の `.data` 関数ポインタ変数。
  - 値 (HEAD 実測): `P = Q(0x11E3AF0) = 0x11F10E0` (`.bss` slot)、`Q(P) = 0x457860` (fallback)。`≠ 0` なので `dec_label_pc_467cac` (L174344) へ進む。
  - 非 0 側の中身: VarBstrFromBool 呼出し (`ICALL 0x467cc9`・`0x467d5d`)。この indirect call は IR に無い (lift で落ちた D15 型)。`m11_ov.c:1408-1410` の C 転記が呼ぶ。target `0x457860` は dispatch 表に無く icall-miss (ret 0)。
- unit 23 の結果は shimx 版と baseline で `lasterr` が異なる: baseline 0・shimx 126 (HEAD 実測。0bdd046d の実測でも同じ差)。分岐条件の差ではない。
- 0xf960 までの呼出し列 (IR と C 転記の対応):
  1. `icall 0x67f00` = `function_467f00`。初期化フラグ `0x11F1114` (VA) の分岐 (L174466–174468) で、値 0 → init 経路 (`dec_label_pc_467f1d`)。
  2. init 経路の L174500: `function_40f9e0(…, (arg2 & ~0xff) | 1)`。`%17 = or (and arg2, -256), 1` (L174496–174498) なので low8 = 1。L115590–115591 の `icmp eq low8, 0` は偽 → `dec_label_pc_40fa13` → L115594 `function_410320` 呼出し。
  3. `function_410320` の IR は `ret arg1` (L116093–116095)。実体は C 転記 `m11_ov.c:556-558` (`ICALL 0x41032e`, `Q(self-0x30)` = vmtNewInstance) → `icall 0xf960`。
  4. 戻った後、L174502 で `function_467c40()` を呼ぶ → 上記の slot ゲート。

## 2. 実測・根拠

### 2.1 IR (HEAD 再生成・本 run)

- `m11_gen_ir2.sh` (`FL_WIN64_DIR` は `fl-win64` の `extracted/block00031_PE.bin` だけを展開) → `boot_final.ll` 490735 行、sha256 `7c653b0f…` (51 秒)。`REPORT_SHX-T9h.md` §3.3.7 の regen 記録と一致。
- `m11_build.sh` (emcc 6.0.12 まで実行・23 秒。rc 0) → `boot_final3.ll` 529579 行、sha256 `8d0fe6ce…`。`m11_boot.cjs` 5,772,457 B、`m11_sx_trace_soft_fix.cjs` (`shimx_link/build.sh --trace --soft --fix`) は signature mismatch 0・undefined 0・duplicate 0。
- `m11_image.bin`: HEAD の `m11_image_gen.py` で作り直し、素材由来の版と sha256 `2d10d692…` で一致 (入力の PE と `lb_base.py` が不変)。
- 抽出: `bash tools/shimx/evidence_3149/repro.sh` (assert 全通過)。出力は `evidence_3149/ir_branch_excerpt.txt` と一致 (HEAD の IR 行)。
- 行番号の注意: レビューで示された旧 snapshot の `boot_final3.ll` (529468 行・sha256 `010451…`) では、同じ分岐が 174291 付近にずれる。本付録の行番号は HEAD 生成の IR のもの。

| 項目 | IR 行 (`boot_final3.ll`, HEAD) | 内容 |
|---|---|---|
| 467c40 slot 読み | L174337–174340 | `inttoptr i64 22952688` (VA 0x15E3AF0) → `Q` → `Q` |
| 467c40 ゲート | L174341–174342 | `icmp eq %2, 0` → 真で `467e07` (skip)・偽で `467cac` |
| 467cac (非 0 側) | L174344– | `function_412e00`・`function_45a640`・… (indirect call は無し) |
| 467f00 フラグ | L174463–174468 | `Q32(inttoptr i64 18813204)`: 0 → `467f1d` (init) |
| 467f00 init 呼出し | L174500・L174502 | `function_40f9e0(…, %17)` → `function_467c40()` |
| 40f9e0 分岐 | L115590–115594 | low8 == 0 で `40fa50` (skip)・非 0 で `410320` |
| 410320 (IR) | L116093–116095 | `ret arg1` のみ。C 転記 (`m11_ov.c:556-558`) が強定義で上書き |

- 定数の表記: IR の `inttoptr` 定数は VA の 10 進。`18813204` = `0x11F1114`、`22952688` = `0x15E3AF0` (`python3 -c 'print(hex(18813204), hex(22952688))'` で確認)。本付録の VA 表記はこの変換による。
- `m11_post.py` は `function_*` を weak 化する (`m11_post.py` 冒頭の注記)。IR 側の weak 定義より C 側の強定義が優先される (`m11_build.sh` の `cc m11_ov.c work/obj/ov.o`)。

### 2.2 実行時 (HEAD 実測)

probe: `tools/m11/shimx_link/probe_unit23.mjs` と `probe_lasterr_1985.mjs` (引数 `<cjs> 22`)。同一条件で 3 回実行し、値は全て同じ。

| 版 (HEAD `5e8ce9ba`) | gate (unit 23 の直前) | unit 23 ret / lasterr | icall の並び |
|---|---|---|---|
| baseline `m11_boot.cjs` | P=0x11f10e0 slot=0x457860 flag=0 | 2 / 0 | `0x67f00` → `0xf960` → icall-miss `0x457860` |
| shimx `m11_sx_trace_soft_fix.cjs` | P=0x11f10e0 slot=0x457860 flag=0 | 2 / 126 | 同上 |

- baseline の trace (`[m11]` 行。PRE 行を除く) は `evidence_2533/probe_lasterr_baseline_regen.txt` (0bdd046d の実測) と**全行一致**。
- shimx の trace は 0bdd046d と同じ gate・icall・lasterr=126。`UStrAsg` の `src` の heap アドレスだけが 0x1000 ずれる (`0x1141aa30` → `0x1142aa30`。heap の配置の違い)。
- 証跡: `evidence_3149/probe_lasterr_baseline_head.txt`・`evidence_3149/probe_lasterr_shimx_trace_soft_fix_head.txt`。
- 注記: 本 probe は icall・UStrAsg・slot を出力する。`CoCreateInstance` と `GetProcAddress` の呼出しは出力に現れない (`SHBrowseForFolder` も 0 件)。

### 2.3 0bdd046d から HEAD までの差分 (WORKFLOW §6)

- `git diff --name-only 0bdd046d HEAD -- tools/m11 tools/shimx/src tools/plugins/lift` = 156 files (`git diff --stat` は +14215/−1098)。
- 既定で動く変更を、ファイル別に確認した:

| ファイル | 変更 | unit 23 への影響 (確認方法) |
|---|---|---|
| `tools/m11/m11_build.sh` (+41 行) | `guard4fa210` (#2773) は既定 on。`function_4fa210` の入口ガードだけを書き換える。`M11_XMM_ARGS`・`M11_PROBE_134`・`M11_PROBE_2780`・`M11_FIX_50A830` は既定 0 | gate の IR 行・slot・icall 列は 0bdd046d と一致 (上の表)。ガードの有無による観測差は無い |
| `tools/m11/m11_post.py` (+1/−1) | `_conv` の trunc 化 (#2715・既定の経路)。i8/i1/i16 への変換だけ変わる | gate の IR 行 (L174341) は不変。trace 不変 |
| `tools/m11/m11_ov.c` (+134/−1) | 10 hunk。追加は関数の追加・override で、`#if` ガードは 16 行に付く (`M11_FIX_50A830` 既定 0、`M11_PRINT_DEST_2118` 既定 0 など)。`#ifndef M11_OV_NO_450560` の override は既定で有効。ガードの被覆は hunk ごとには確認していない。削除は `function_413060` の debug `fprintf` 1 行 | 追加行に `function_410320`・`function_40f960`・`function_467c40`・`function_467f00` の名前は無い (grep 0 件)。ICALL の行 (`:556-558`・`:1408-1410`) は HEAD でも本文どおり (レビュー確認)。trace 不変 |
| `tools/shimx/src/handles.c` (+3) | `shimx_set_file_close_hook`。hook 未設定 (既定 NULL) なら何もしない | hook を設定する経路は本 probe に無い。影響なし |
| `tools/shimx/src/module.c` (+2) | `GetProcAddress` で名前が `SHBrowseForFolderA/W` の時だけ `shim_unimplemented` | trace に `SHBrowseForFolder` は 0 件 (観測された範囲で不変) |
| `tools/shimx/src/ole.c` (+7/−1) | `CoCreateInstance` で FileOpenDialog / FileSaveDialog の CLSID の時だけ `shim_unimplemented` (既定 on) | **未観測**。本 probe は `CoCreateInstance` を出力しないため、unit 23 の経路に入るかは分からない (§4) |

- 結論: 既定で動く変更のうち、unit 23 の経路で観測できたもの (guard4fa210・`_conv`・m11_ov.c の追加) は、gate と icall 列に影響しない (HEAD の実測)。`ole.c` の CoCreateInstance だけは未観測として残す。
- 差分 0 の証跡: 測定 commit `5e8ce9ba` 以降のコード差分は、本 commit (`tools/shimx/REPORT_SHX-T39.md`・`evidence_3149/`・`docs/DOC_MAP.md` のみ) で、`git diff 5e8ce9ba HEAD -- tools/m11 tools/shimx/src tools/plugins/lift` は空。

## 3. 位置づけ

- #3149 の受入 (「unit 23 で baseline が `0xf960` 以降どの分岐に入るかを特定する (分岐条件の関数名・値)」) は、HEAD の IR 行と実行時の slot 値で満たした。
- slot が fallback `0x457860` になる経路 (`function_457c40` の `+40` 残存値 `0x56670`・`REPORT_SHX-T9k.md` §4) は未解決のまま。本付録の範囲外。#1607 は closed のため、起票先は PM 判断 (§4)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `slot` が fallback `0x457860` になる経路 (`REPORT_SHX-T9k.md` §4) | unit 23 の icall-miss の根本原因 | 既存の open issue なし (#1607 は closed)。PM が起票先を決める |
| shimx 版の `lasterr=126` (baseline は 0) の原因 | unit 23 の error 状態の差 (分岐は同じ)。0bdd046d でも同じ差 | 同上 (PM 判断) |
| `ole.c` (CoCreateInstance) の変更が unit 23 の経路に入るか | 本 probe は未観測 | 同上 (PM 判断。観測を足す場合は probe の出力に `CoCreateInstance` を追加する) |

## 5. 検証範囲

- 検証した範囲: HEAD (`5e8ce9ba`) の `m11_gen_ir2.sh`・`m11_build.sh`・`shimx_link/build.sh --trace --soft --fix` と、unit 23 の probe (baseline・shimx 版)。
- 範囲外: 他の unit の挙動・`--full` (RetDec 再生成)・`ole.c` の CoCreateInstance 経路・起動 KPI (本付録はコードを変えない)。

# tools/shimx REPORT 付録 — SHX-T39 (#3149) unit 23 の baseline が 0xf960 の後に入る分岐条件

> 親: #1607 (SHX-T9e) の受入 2 の残件 (#1607 本文の子 issue 移送分)。本体: `tools/shimx/REPORT_SHX-T9.md` §3.3.4。
> 前段: `REPORT_SHX-T9h.md` §3.3.7 (現行 `m11_ov.c` からの baseline 再生成)・`REPORT_SHX-T9j.md` (GetLastError)。
> 証跡: `tools/shimx/evidence_3149/` (`repro.sh` で IR 行を再抽出する。`ir_branch_excerpt.txt` は出力の保存)。
> 素材: `oc_artifacts: fl-win64 work-m11 work-liftdiff`。emsdk は素材に無く、emcc 段は実行していない (§4)。

## 1. 結論

- baseline (現行 `m11_ov.c` から再生成) の unit 23 は、`0xf960` (`function_40f960` = TObject.NewInstance) の後、`function_467c40` の **slot ゲート** で「非 0」側に入る。
  - 分岐点: IR `function_467c40` の `icmp eq (Q(Q(0x15E3AF0)), 0)` (`boot_final3.ll` L174340–174342)。VA `0x15E3AF0` は LVA `0x11E3AF0` (`.data` の関数ポインタ変数)。
  - 値: `P = Q(0x11E3AF0) = 0x11F10E0` (`.bss` slot)、`Q(P) = 0x457860` (fallback)。`≠ 0` なので `dec_label_pc_467cac` (L174344) へ進む。
  - 非 0 側の中身: VarBstrFromBool 呼出し (`ICALL 0x467cc9`・`0x467d5d`)。この indirect call は IR に無い (lift で落ちた D15 型)。`m11_ov.c:1408-1410` の C 転記が呼ぶ。target `0x457860` は dispatch 表に無く icall-miss (ret 0)。
- 0xf960 までの呼出し列 (IR と C 転記の対応):
  1. `icall 0x67f00` = `function_467f00`。初期化フラグ `0x11F1114` (VA) の分岐 (L174466–174468) で、値 0 → init 経路 (`dec_label_pc_467f1d`)。
  2. init 経路の L174500: `function_40f9e0(…, (arg2 & ~0xff) | 1)`。`%17 = or (and arg2, -256), 1` (L174496–174498) なので low8 = 1。L115590–115591 の `icmp eq low8, 0` は偽 → `dec_label_pc_40fa13` → L115594 `function_410320` 呼出し。
  3. `function_410320` の IR は `ret arg1` (L116093–116095)。実体は C 転記 `m11_ov.c:556-558` (`ICALL 0x41032e`, `Q(self-0x30)` = vmtNewInstance) → `icall 0xf960`。
  4. 戻った後、L174502 で `function_467c40()` を呼ぶ → 上記の slot ゲート。
- shimx 版と baseline は、この分岐で同じ経路 (同じ slot 値 `0x457860`・同じ icall-miss) に入る。よって unit 23 の差は、この分岐条件の差ではない。

## 2. 実測・根拠

### 2.1 IR (HEAD 上で再生成。本 run)

- `m11_gen_ir2.sh` (`FL_WIN64_DIR` は `fl-win64` の `extracted/block00031_PE.bin` だけを展開) → `boot_final.ll` 490735 行、sha256 `7c653b0f…` (`REPORT_SHX-T9h.md` §3.3.7 の regen と一致)。
- `m11_build.sh` の emcc 直前まで (guard・post。emsdk 行だけ外した一時コピーで実行) → `boot_final3.ll` sha256 `8d0fe6ce…`。行番号は本ファイルの値 (`boot_final.ll` の行番号とは違う)。
- 抽出: `bash tools/shimx/evidence_3149/repro.sh` (assert 付き)。出力は `evidence_3149/ir_branch_excerpt.txt`。

| 項目 | IR 行 (`boot_final3.ll`) | 内容 |
|---|---|---|
| 467c40 slot 読み | L174337–174340 | `inttoptr 22952688` (VA 0x15E3AF0) → `Q` → `Q` |
| 467c40 ゲート | L174341–174342 | `icmp eq %2, 0` → 真で `467e07` (skip)・偽で `467cac` |
| 467cac (非 0 側) | L174344– | `function_412e00`・`function_45a640`・… (indirect call は無し) |
| 467f00 フラグ | L174463–174468 | `Q32(0x11F1114)`: 0 → `467f1d` (init) |
| 467f00 init 呼出し | L174500・L174502 | `function_40f9e0(…, %17)` → `function_467c40()` |
| 40f9e0 分岐 | L115590–115594 | low8 == 0 で `40fa50` (skip)・非 0 で `410320` |
| 410320 (IR) | L116093–116095 | `ret arg1` のみ。C 転記 (`m11_ov.c:556-558`) が強定義で上書き |

- `m11_post.py` は `function_*` を weak 化する (`m11_post.py` 冒頭の注記)。IR 側の weak 定義より C 側の強定義が優先される (`m11_build.sh` の `cc m11_ov.c work/obj/ov.o`)。

### 2.2 実行時 (再生成 baseline の trace・過去の実測)

- 出典: `tools/shimx/evidence_2533/probe_lasterr_baseline_regen.txt` (SHX-T9j #2533。現行 `m11_ov.c` から `m11_build.sh` で再生成した `m11_boot.cjs`、cjs sha256 `49e6cce2…`)。
  - `before unit 23: gate P=0x11f10e0 slot=0x457860 flag=0`
  - `unit 23 (trace) ret=2 lasterr=0`
  - `[m11][icall] 0x67f00` → `[m11][icall] 0xf960` → `[m11][icall-miss] target=0x457860` → `[m11][UStrAsg] dest=0x11f1120` (IR L174356 の `ce1n11` = `0x11F1120` と一致)
- 測定 commit: `0bdd046d` (#2533 の測定に使ったコード)。

### 2.3 0bdd046d から HEAD までの差分 (WORKFLOW §6)

- 対象の関数定義は不変。`git diff 0bdd046d HEAD -- tools/m11/m11_ov.c`: hunk は `function_50a830` 系・`450560`・`47b260`・`412770`・`413060` 周辺の追加と `#if`/`#ifndef` の既定 OFF ガード (`M11_FIX_50A830=0` 等)。`function_410320`・`function_40f960`・`function_467c40` の hunk は無い。
- `git diff 0bdd046d HEAD -- tools/m11/m11_build.sh`: `guard4fa210` (#2773) の追加は `function_4fa210` だけを変える (`work/guard4fa210_report.json` の `fn`)。probe 系 (`M11_PROBE_*`) は既定 0。
- 残る差: `function_4fa210` の guard が unit 23 の経路に入るかは、HEAD の cjs を作って trace を取り直すまで未確認 (§4)。

## 3. 位置づけ

- 残件 (#1607 の受入 2・#3149 の受入) のうち「0xf960 の後の分岐条件」は、IR 行と実行時の slot 値で特定できた。
- 残る問い (`function_457c70` 側): slot が fallback `0x457860` で埋まる経路 (`GetProcAddress` の失敗・`function_457c40` の `+40` 残存値 `0x56670`) は、`REPORT_SHX-T9k.md` §4 の未解決のまま。本付録の範囲外。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| HEAD で `m11_boot.cjs` を作り直し、`probe_unit23.mjs` で unit 23 の trace を取り直す (emsdk が要る。`oc_artifacts` に `toolchain-emsdk` を足す必要がある) | 2.2 の実行時の値は 0bdd046d での実測。HEAD の `guard4fa210` (#2773) の差が unit 23 の経路に無いことは未実測 | 本 PR の未解決 (再測定だけの子 issue は立てない) |
| `slot` が fallback `0x457860` になる経路 (`REPORT_SHX-T9k.md` §4) | unit 23 の icall-miss の根本原因 | #1607 (open) |

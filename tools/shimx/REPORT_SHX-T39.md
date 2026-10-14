# tools/shimx REPORT 付録 — SHX-T39 (#3149) unit 23 の baseline が 0xf960 の後に入る分岐条件

> 親: #1607 (SHX-T9e) の受入 2 の残件 (#1607 本文の子 issue 移送分)。本体: `tools/shimx/REPORT_SHX-T9.md` §3.3.4。
> 前段: `REPORT_SHX-T9h.md` §3.3.7 (現行 `m11_ov.c` からの baseline 再生成)・`REPORT_SHX-T9j.md` (GetLastError)。
> 証跡: `tools/shimx/evidence_3149/` (`repro.sh` で IR 行を再抽出。`probe_run{1,2,3}_{baseline,shimx}.txt` は HEAD の実行時 trace の 3 回分。`cjs_sha256_head.txt`・`numstat_0bdd046d_HEAD.txt`・`boot_final3_diff_0bdd046d_HEAD.txt`・`heap_swap_probe.txt` は §2.3 の根拠)。
> 測定 commit (コード): `5e8ce9ba`。round 2 の修正 run で、コードが同一の `8e6cb10e` (本 commit の親) を worktree で展開して再測定した。本 commit はコード差分 0 (文書と証跡のみ)。
> 素材: `oc_artifacts: fl-win64 work-m11`。emcc は runner 同梱の [EMSDK] (6.0.12) を使った (§2.1)。

## 1. 結論

- HEAD で再生成した baseline (`m11_boot.cjs`) の unit 23 は、`0xf960` (`function_40f960` = TObject.NewInstance) の後、`function_467c40` の **slot ゲート** で「非 0」側に入る。shimx 版 (`m11_sx_trace_soft_fix.cjs`) も同じ分岐・同じ値に入る。
  - 分岐点: IR `function_467c40` の `icmp eq (Q(Q(0x15E3AF0)), 0)` (`boot_final3.ll` L174340–174342)。`0x15E3AF0` は VA (LVA `0x11E3AF0`) の `.data` 関数ポインタ変数。
  - 値 (HEAD 実測): `P = Q(0x11E3AF0) = 0x11F10E0` (`.bss` slot)、`Q(P) = 0x457860` (fallback)。`≠ 0` なので `dec_label_pc_467cac` (L174344) へ進む。
  - 非 0 側の中身: VarBstrFromBool 呼出し (`ICALL 0x467cc9`・`0x467d5d`)。この indirect call は IR に無い (lift で落ちた D15 型)。`m11_ov.c:1408-1410` の C 転記が呼ぶ。target `0x457860` は dispatch 表に無く icall-miss (ret 0)。
- unit 23 の結果は shimx 版と baseline で `lasterr` が異なる: baseline 0・shimx 126 (HEAD 実測。0bdd046d の記録でも同じ差)。分岐条件の差ではない。
- **ビルド成果物は 0bdd046d と一致しない** (`m11_boot.cjs`・`m11_sx_trace_soft_fix.cjs` の sha が違う。§2.1・§2.3)。ただし unit 23 の gate・icall 列と baseline の trace は 0bdd046d の記録と全行一致 (§2.2)。shimx 版は `UStrAsg` の heap アドレス (0x1141aa30 → 0x1142aa30) だけがずれるが、原因は未特定 (§2.2)。
- 0xf960 までの呼出し列 (IR と C 転記の対応):
  1. `icall 0x67f00` = `function_467f00`。初期化フラグ `0x11F1114` (VA) の分岐 (L174466–174468) で、値 0 → init 経路 (`dec_label_pc_467f1d`)。`0x11F1114` は IR の定数 `18813204` を `inttoptr` で直接使ったもの (VA の 10 進。`python3 -c 'print(hex(18813204))'` = `0x11f1114`)。
  2. init 経路の L174500: `function_40f9e0(…, (arg2 & ~0xff) | 1)`。`%17 = or (and arg2, -256), 1` (L174496–174498) なので low8 = 1。L115590–115591 の `icmp eq low8, 0` は偽 → `dec_label_pc_40fa13` → L115594 `function_410320` 呼出し。
  3. `function_410320` の IR は `ret arg1` (L116093–116095)。実体は C 転記 `m11_ov.c:556-558` (`ICALL 0x41032e`, `Q(self-0x30)` = vmtNewInstance) → `icall 0xf960`。
  4. 戻った後、L174502 で `function_467c40()` を呼ぶ → 上記の slot ゲート。

## 2. 実測・根拠

### 2.1 IR とビルド (HEAD 再生成・本 run)

- emsdk: [EMSDK] (`/opt/emsdk`。runner イメージ同梱)。`emcc --version` = `emcc (Emscripten gcc/clang-like replacement + linker emulating GNU ld) 6.0.12 (5488e0871d46d19a3209988190fa6a653126256f)`。この install の出所 (URL・tag) は本 run で未確認。`$ARTIFACTS_DIR` の `toolchain-emsdk` 素材 (532 MB) は展開していない (`oc_artifacts` に入れない)。
- `m11_gen_ir2.sh` (`FL_WIN64_DIR` は `fl-win64` の `extracted/block00031_PE.bin` だけを展開) → `boot_final.ll` 490735 行、sha256 `7c653b0f…` (50 秒)。0bdd046d も同じ sha (同一環境で再生成)。`REPORT_SHX-T9h.md` §3.3.7 の記録とも一致。
- `m11_build.sh` (23 秒・rc 0) → HEAD の `boot_final3.ll` 529579 行 sha `8d0fe6ce…`。0bdd046d の再生成は 529576 行 sha `d24dddd8…`。差は §2.3 の 1 hunk (5 行)。
- `m11_boot.cjs` (HEAD): 5,772,457 B、sha `0d3bb64f…`。0bdd046d の再ビルド: 5,766,813 B、sha `49e6cce2…`。記録 (`evidence_2533/cjs_sha256.txt` の `49e6cce219f84655`) と一致した。
- `shimx_link/build.sh --trace --soft --fix` (HEAD): `m11_sx_trace_soft_fix.cjs` 6,174,446 B、sha `7f4c3708…`、signature mismatch 0・undefined 0・duplicate 0。0bdd046d の再ビルド: 6,168,545 B、sha `66181f8f…` (記録と一致)、signature mismatch **1**。
- sha の全文は `evidence_3149/cjs_sha256_head.txt`。
- 同一環境で同じ入力を 2 回ビルドすると `m11_boot.cjs` は同一 (`cmp` 一致)。よって sha の差はビルドの揺らぎではなく、入力 (コード) の差による。
- `m11_image.bin` の sha `2d10d692…` (前回 run の記録。本 run では未再確認)。
- `repro.sh` (rc 0) の出力は `evidence_3149/ir_branch_excerpt.txt` と一致 (本 run で確認)。

### 2.2 実行時 (HEAD 実測・3 回)

probe: `tools/m11/shimx_link/probe_lasterr_1985.mjs <cjs> 22`。同一条件で 3 回実行し、3 回とも同一 (`evidence_3149/probe_run{1,2,3}_{baseline,shimx}.txt`)。

| 版 (HEAD `8e6cb10e`) | gate (unit 23 の直前) | unit 23 ret / lasterr | icall の並び |
|---|---|---|---|
| baseline `m11_boot.cjs` | P=0x11f10e0 slot=0x457860 flag=0 | 2 / 0 | `0x67f00` → `0xf960` → icall-miss `0x457860` |
| shimx `m11_sx_trace_soft_fix.cjs` | P=0x11f10e0 slot=0x457860 flag=0 | 2 / 126 | 同上 |

- baseline の trace は 0bdd046d の記録 (`evidence_2533/probe_lasterr_baseline_regen.txt`) と**全行一致**。
- shimx の trace は 0bdd046d の記録と、`UStrAsg` の `src` の 4 行 (`dest=0x11f1148`〜`0x11f1160` の heap 領域) だけが異なる: `0x1141aa30` → `0x1142aa30` (+0x1000)。gate・icall・`lasterr=126` は同じ。
- **原因は未特定**。切り分け: 0bdd046d の shimx ビルドに HEAD の `tools/shimx/src/heap.c` だけを入れて再ビルドすると、`src` は `0x1141aa30` のまま (ずれない。`evidence_3149/heap_swap_probe.txt`)。よって `heap.c` 単独の差は原因ではない。残る候補は、他の shimx 変更 (`module.c`・`ole.c`・`handles.c`・`shimx.h`)・m11 側の IR 差 (§2.3 の `function_4fa210` のガード)・shimx ビルドの signature mismatch (0bdd046d 1 → HEAD 0)。未切り分け。
- 注記: 本 probe の出力に shimx 版の `unit 18 exc=halt0 lasterr=0` (baseline は `ret=1 lasterr=0`) が出る。0bdd046d の記録 (`evidence_2533`) も同じ出力。`REPORT_SHX-T9h.md` 46 行目の未確認事項と同じ件。本付録は unit 18 の分岐を見ていない。
- 注記: 本 probe は icall・UStrAsg・slot を出力する。`CoCreateInstance` と `GetProcAddress` の呼出しは出力に現れない (`SHBrowseForFolder` も 0 件)。

### 2.3 0bdd046d から HEAD までの差分 (WORKFLOW §6)

- 範囲: `git diff --numstat 0bdd046d HEAD -- tools/m11 tools/shimx/src tools/plugins/lift` = **156 files、+14215/−1098** (`evidence_3149/numstat_0bdd046d_HEAD.txt`)。カテゴリ別の内訳は下表 (数値は同じ numstat の集計)。
- 「IR 段」は 0bdd046d と HEAD で同一環境に再生成した成果物の比較。`boot_final.ll` (`m11_gen_ir2.sh`) は sha 同一。`boot_final3.ll` (`m11_build.sh` / `m11_post.py` の出力) は 1 hunk (下記) のみ差がある。

| カテゴリ | files | 変更 (+/−) | 成果物への影響 (実測) | unit 23 の trace への影響 |
|---|---|---|---|---|
| `tools/m11/m11_build.sh` | 1 | +34/−7 | `boot_final3.ll` の差 (1 hunk) の源。`guard4fa210` (#2773・既定 on) の入口ガード | gate・icall 不変 (下記) |
| `tools/m11/m11_post.py` | 1 | +2/−1 | `_conv` の変更は `boot_final3.ll` に文字列の差を出さない (差は 1 hunk のみ) | 不変 |
| `tools/m11/m11_ov.c` | 1 | +133/−1 | C 側。cjs・wasm に入る (寄与は未分離) | baseline の trace 全行一致 |
| `tools/m11/ldfix/` | 72 | +8459/−192 | `boot_final.ll` (gen_ir2 出力) sha 同一。gen_ir2 の経路の変更は IR に影響しない | 不変 (経路の網羅は未確認) |
| `tools/m11/trap_triage/` | 32 | +1664/−14 | 未分離 (経路未確認。cjs の差に寄与するかは不明) | 未観測 |
| `tools/m11/shimx_link/` | 13 | +726/−10 | shimx 版の cjs の差に寄与し得る (寄与は未分離) | shimx の UStrAsg のみずれる (原因未特定) |
| `tools/m11/` (上記以外) | 29 | +3059/−863 | `boot_final.ll` sha 同一の範囲は IR に影響しない。他は未分離 | 不変 (経路の網羅は未確認) |
| `tools/shimx/src/heap.c` | 1 | +6/−2 | 単独では UStrAsg のずれを出さない (§2.2 の切り分け) | 単独では不変 |
| `tools/shimx/src/ole.c` | 1 | +6/−1 | 未分離 | **未観測** (本 probe は `CoCreateInstance` を出力しない) |
| `tools/shimx/src/module.c` | 1 | +2/−0 | 未分離 | `SHBrowseForFolder` は 0 件 (観測の範囲で不変) |
| `tools/shimx/src/handles.c` | 1 | +3/−0 | 未分離。hook 未設定 (既定 NULL) なら何もしない | 影響なし (hook の経路は本 probe に無い) |
| `tools/shimx/src/shimx.h` | 1 | +1/−0 | 未分離 | 未分離 |
| `tools/plugins/lift/` | 2 | +120/−7 | 未確認 (経路未確認) | 未観測 |
| 合計 | 156 | +14215/−1098 | | |

- `boot_final3.ll` の差 (`evidence_3149/boot_final3_diff_0bdd046d_HEAD.txt`): 1 hunk、180816 行付近。`br label %dec_label_pc_4fa248` の 1 行を、`%g4fa = icmp eq i32 %9, 0` ・条件分岐・`dec_label_pc_4fa210_g4fa:` ・`ret i64 0` の 4 行に置き換える (純増 +3 行: 529576 → 529579)。`function_4fa210` の入口ガード (guard4fa210) で、条件が真なら `ret i64 0` する。hunk より前は両版で行の位置も内容も同じ。よって slot ゲート (L174340–174342) は 0bdd046d と同じ行・同じ内容。
- `function_4fa210` が unit 23 の経路に入るかは、本 probe の trace (icall・UStrAsg のみ) では見えない。観測範囲では gate・icall 列は不変。
- 結論 (実測の範囲に限る): (a) gen_ir2 の出力は同一、(b) boot_final3 の差は `function_4fa210` の入口ガード 1 hunk、(c) unit 23 の gate・icall・baseline の trace は 0bdd046d と一致、(d) shimx 版の UStrAsg の heap アドレスのみずれ、原因は未特定。ビルド成果物 (cjs) の同一性は**確認されていない** (sha が違う)。

## 3. 位置づけ

- #3149 の受入 (「unit 23 で baseline が `0xf960` 以降どの分岐に入るかを特定する (分岐条件の関数名・値)」) は、HEAD の IR 行と実行時の slot 値で満たした。
- slot が fallback `0x457860` になる経路 (`function_457c40` の `+40` 残存値 `0x56670`・`REPORT_SHX-T9k.md` §4) は未解決のまま。本付録の範囲外。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `slot` が fallback `0x457860` になる経路 (`REPORT_SHX-T9k.md` §4) | unit 23 の icall-miss の根本原因 | 本 PR 本文の未解決表 (追跡のみ・子 issue なし)。#1607 は closed |
| shimx 版の `lasterr=126` (baseline は 0) の原因 | unit 23 の error 状態の差 (分岐は同じ。0bdd046d でも同じ差) | 本 PR 本文の未解決表 (追跡のみ・子 issue なし) |
| shimx 版の UStrAsg の heap アドレス `+0x1000` のずれ (原因未特定。`heap.c` 単独では無い) | unit 23 の trace の差 (分岐は同じ) | 本 PR 本文の未解決表 (追跡のみ・子 issue なし) |
| 0bdd046d → HEAD のビルド成果物 (cjs) の sha の差 (寄与の分離は未実施) | 測定値の帰属 (trace は一致・成果物の同一性は未確認) | 本 PR 本文の未解決表 (追跡のみ・子 issue なし) |
| `tools/shimx/src/ole.c` (CoCreateInstance) の変更が unit 23 の経路に入るか | 本 probe は未観測 | 本 PR 本文の未解決表 (追跡のみ・子 issue なし。観測を足す場合は probe の出力に `CoCreateInstance` を追加する) |
| unit 18 の `exc=halt0` (baseline `ret=1`。`REPORT_SHX-T9h.md` 46 行目と同件) | 本付録の分岐は見ていない | 本 PR 本文の未解決表 (追跡のみ・子 issue なし) |

## 5. 検証範囲

- 検証した範囲: HEAD (`8e6cb10e`、コードは `5e8ce9ba` と同一) の `m11_gen_ir2.sh`・`m11_build.sh`・`shimx_link/build.sh --trace --soft --fix`・`probe_lasterr_1985.mjs` (3 回)。同じ手順の 0bdd046d の再ビルド。0bdd046d の shimx に HEAD の `heap.c` を入れた再ビルド。`repro.sh`。
- 検証 HEAD と測定 commit の差分: `git diff 5e8ce9ba HEAD -- tools/m11 tools/shimx/src tools/plugins/lift` の出力は 0 行 (本 commit の親 `8e6cb10e` で確認。本 commit は `tools/shimx/REPORT_SHX-T39.md`・`evidence_3149/`・`docs/DOC_MAP.md` のみ変更)。
- 再現の 1 行: `cd tools/m11 && bash m11_gen_ir2.sh && bash m11_build.sh && (cd shimx_link && bash build.sh --trace --soft --fix)` のあと `node tools/m11/shimx_link/probe_lasterr_1985.mjs tools/m11/work/m11_boot.cjs 22`。IR の行だけなら `bash tools/shimx/evidence_3149/repro.sh` (`tools/m11/work/boot_final3.ll` が必要)。
- 範囲外: 他の unit の挙動・`--full` (RetDec 再生成)・`ole.c` の CoCreateInstance 経路・起動 KPI (本付録はコードを変えない)。

# tools/icall → tools/liftlib 統合手順 (CAB-89)

**状態 (#229): `liftlib` への統合は完了済み** (`liftlib/passes/icall.py` + `pipeline.py`)。以降の liftlib 側変更は `tools/liftlib` を直接編集する。
`liftlib_icall.patch` / `liftlib_passes_icall.py` は**再適用不可の履歴スナップショット** (patch は stub 長 `stub+78` 固定の旧版で、現行の `stub_len` (map.json 由来) と合わない)。適用コマンドは載せない。cfg 例は `tools/liftlib/targets/ott_route.json`。

## 1. 統合の構成
- `liftlib/passes/icall.py`: `prelift()` / `restore()` の 2 関数 (tools/icall の CLI を subprocess 呼出し)。**`passes.icall.funcs` は functions ファイルのパス必須** (inline range 文字列は不可。`closure.py` で作る)。
- `liftlib/pipeline.py`: `cfg.passes.icall` があれば ① lift 前に PE を書換え ② RetDec の ranges と image を書換え版に差し替え ③ raw ll を復元してから既存の
  `repair_ll` (P1/F7/F2) へ渡す。`img` (修復 pass が機械語を参照する正本) は元 PE のまま。`image` / `funcs` は repo 相対・絶対・`${PLUGINS_DIR}` 等 (tools/shared の変数) が使える。
- cfg 例 (`targets/ott_route.json`): `{"name":"ott_route","image":"${PLUGINS_DIR}/ott/binaries/OTT_vst2_win64.dll","passes":{"icall":{"funcs":"tools/icall/work/route/F.txt"},"p1":false,"f7":false,"f2":false,"gdata":null}, …}`
  icall の書換えは P1 (comis flag) / F7 (load 脱落 = D7) / F2 (xmm 引数脱落) の対象を**生成前に**除去するので、icall 有効時は p1/f7/f2 を off にできる (残すと二重修復なので off 推奨)。
- emcc の sources に `tools/icall/rt/icall_rt.c` と `rt/icall_simd_extra.c` を追加し、`ir_flatten.py --table` の出力 (`icall_tbl_*`, `icall_cfg_va`) をリンクする。

## 2. API / 入出力フォーマット

| ツール | 入力 | 出力 |
|---|---|---|
| `closure.py --pe PE --roots roots --out F.txt` | roots: VA または `A-B` の CSV/改行 | F.txt: `0xA-0xB,…` (直接 call / 末尾 jmp / 条件 jmp の推移閉包, 範囲は .pdata→次関数境界, 退化 range (start==end) は無視) |
| `icall_rewrite.py --pe PE --funcs F.txt --out PE' --map map.json` | PE, 関数集合 | PE' (+`.icall` section), `map.json` (func_map new↔orig, `insn_ranges` [new,len,orig], sites, blk/stub/comis_stub VA, cfg_thunks, 件数), `map.json.ranges` (RetDec `--select-ranges` 用) |
| RetDec | PE' + `map.json.ranges` (+ stub 2 本の range) | raw ll (`!insn.addr` は新 VA) |
| `ir_icall_restore.py --ir raw.ll --map map.json --out r.ll` | 上記 | 元 VA 体系の ll: `@function_<orig>`, `!insn.addr`=orig, stub 呼出し→`call void @__icall_dispatch(i64 <site VA>)` / `__icall_comis()` |
| `ir_flatten.py in out --table t.c --cfg <cfg thunk VA>` | normalize/ir5 後 ll | `@global_var_*` を絶対アドレス定数へ (データは image 敷設で供給 → D2 根絶), VA shift, dispatch 表 C |
| `audit_icall.py --pe PE --ir a.ll [--ir b.ll …] [--funcs F] [--dsm x.dsm] --json out --sites s.json` | 任意 IR (`!insn.addr` 付き raw が望ましい) | site 別 {kind, 元命令, IR status: kept_indirect / resolved_direct / other_insn / dropped} と集計 JSON |

**ABI 規約 (rewrite/runtime 共通)**: closure 内の関数は全て `i64 f(void)` 形。引数/戻り値は固定 BLK (VA は map.json `blk`) 経由 —
`+0 target / +8 rcx / +0x10 rdx / +0x18 r8 / +0x20 r9 / +0x28.. xmm0-3(low64) / +0x80 rax / +0x88 xmm0 / +0x90 rax-in / +0xA0.. comis`。
呼出側が spill→`call`→reload、被呼側 prologue が reload・`ret` 前に rax/xmm0 を store。戻り型が i128 の関数 (RetDec が xmm0 戻りと推定) は `ir_flatten --table` が wrapper で揃える。
closure 外 (CRT 等) の direct call は従来どおり RetDec の推定 signature のまま (adapter は rt 側で BLK→C 関数)。

## 3. 回帰試験

| テスト | コマンド | 期待 |
|---|---|---|
| unit + rewriter 固定値 | `python3 tools/icall/tests/test_icall.py` | PASS 全件 (derefix 符号/復元 lea, modrm 長, capstone `disp_size` 誤りの検知, OTT F: site 96 / errors {} / jt-chain ≥5) |
| 監査 + route + native 比較 | `bash tools/icall/icall_e2e.sh` (約 1 分; `--small` / `--full` で target 追加) | OTT F の非 IAT 間接 call 落ち ≥60 → ≤8, tail-jmp 落ち 0, **matrix 89 scenario・全 cell が native と bit 一致 (max_ulp 0, state diff 0・正本 `tools/ott/REPORT.md`)** |
| liftlib 側 | `bash tools/liftlib/liftlib_e2e.sh` に `python3 -m liftlib ott --icall` 相当 (ott_route.sh を呼ぶ) を追加 | 上と同一基準 |

## 4. 既知の制約 (統合時の注意)
- **stack 渡し引数 (5 個目以降)**: #229 で対応。BLK `+0x48` = `ICALL_BLK+0x100` (STKBUF) のアドレス、STKBUF[k] = 呼出し点の `[rsp+0x20+8k]` (最大 12 語)。
  「rsp+0x20 のアドレス」を渡す方式は RetDec が rsp を stack_var 別 alloca に分割するため不採用 → 呼出し直前に実際に store されたスロットだけを値コピー (`stk_slots_stored`)。実測と経緯は [`../REPORT.md` §9](../REPORT.md)。
  検出は site 直前 48 命令内 (直前の call/ret/jmp まで) の `[rsp+0x20+8k]` **書込み** (cmp/test 等の読み取りは除外)。**限界**: 他の基本ブロックで store された引数・`rep movs` 等の一括 store・13 語以上は検出外。tail `jmp` 経由は引数が呼出し元スロットのまま (コピーしない)。
- jump table: `jmp reg` 形のみ cmp/je 列へ展開。`jmp [idx*8+tbl]` (メモリ直接) 形は表パッチのみ (RetDec 任せ)。Delphi の in-code 表 (`lea B,[rip+x]; jmp [B+i*8+d]`) は解決器が対応するが cmp/je 展開は未実装。
- CFG unreachable code (Delphi unwind landing pad = try/finally の dtor 呼出し, FLEngine で 879 site) は RetDec が decode しない → 別 pass (unwind info → 到達エッジ追加) が必要。
- FPU(x87)/MMX/AVX/`lock` 命令は RetDec の translator 依存 (本 pass の対象外)。`rep movs/stos` は RetDec 任せ。
- `[reg]` 補償 (derefix) は base 以外の同名 reg を read する命令 (`add rcx,[rcx]` 等) と string 命令を除外 (除外件数は map.json に出していない → 子チケット)。

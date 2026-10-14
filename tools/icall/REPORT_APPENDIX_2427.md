# 付録: icall #2427 (ICALL-77) — 脱落 frame slot store を IR に戻す pass と route への組込み

> 親: #2394 (ICALL-75)。残件: ICALL-78 (#2508)。
> **既知類型との関係**: DEFECTS.md の D22 に近縁。REPORT_APPENDIX_2394 §6 の D24 候補 (脱落 store) の**修復側**を実装した。DEFECTS.md 本体への行追加は PM 判断 (`docs/WORKFLOW.md` §5)。

## 1. 結論

- pass `tools/icall/frame_slot_restore.py` を追加した。`fa_route_build.sh` に `FA_FRAME_SLOT=1` で組み込む (**既定 OFF**)。既定 OFF の理由: 本 pass は 181057b38 の IR だけを変え、closure の bit 一致数は動かないため、既定化は PM 判断とした。
- `function_181057b38`: 8 入力の結果が TRAP 8 → **TRAP 0** (例外なし。値は一致しない、§4)。BLK+0 (`0x36319008`) への "emsc" 書込み 8 → **0**。
- `fa_sweep.sh 8 60` (131 関数): 判定が変わる関数は `0x181057b38` の **1 件** (`wasm_err` 8 → 0、`mismatch` 8 のまま)。他 130 関数の `n/match/mismatch/wasm_err/native_err` は不変。
- 未達 (子 ICALL-78 #2508 へ移した): (a) `0x180da6e60` 候補 10 件の分類、(b) fixed IR でも残る 8/8 不一致の原因、(c) 元 `SlateCore.core_64` の bytes との照合 (`plugins-freshair` 素材が本 run に無い)。

## 2. 検出と復元 (`frame_slot_restore.py`)

- **検出** (`frame_slot_probe.py census` と同じ定義): rbp 相対の 8B store `d` のうち、before IR (`before.0.drc.ll`) に同じ `insn.addr` の store が無く、lea で address を取られた slot `e` に対し `0 < d - e <= 0x40` を満たすもの (候補)。
- **値の解決**: 候補 store の source reg を、同一基本ブロック内で最後に書いた命令から解決する。`lea reg,[rbp+e]` なら frame slot の address、`lea reg,[rip+x]` なら global の VA。分岐先 (jump target) を跨ぐ場合と、call・ret・jcc を跨ぐ場合は未解決にして戻さない。
- **命名**: RetDec の `stack_var_X` は `X = disp - 8` (`[rbp+0x20]`→`stack_var_24`、`[rbp-8]`→`stack_var_-16`、`[rbp-0x20]`→`stack_var_-40` で確認)。
- **復元**: 戻す store の target slot `X` の alloca が無く、`X-8` が lea で取られた i64 alloca なら、両者を 1 つの `alloca i128` (16B) にまとめる (`X-8` が下位、`X` が上位)。そうでなければ `alloca i64` を足す。値の store は、`insn.addr` が元 VA より大きい最初の IR 命令の直前に挿入する。
- **181057b38 での適用** (`work/fa_exp/frame_slot.json` の実測):
  - 候補 2 件: `0x181057b71` (`mov [rbp-8],rax`、値 = frame `-0x20`)、`0x181057b87` (`mov [rbp-0x20],rax`、値 = global `0x181306ce0`)。
  - merge 2 件: `[-24,-16]` と `[-48,-40]`。`-40` は `-48` (lea 済み、機械語上 `[rbp-0x28]` と `[rbp-0x20]` は隣接) に隣接するため、規則どおり merge した。REPORT_APPENDIX_2394 §4 の手作業実験では `-40` を単独 alloca にしていた。この違いによる結果の差は、8 入力 (TRAP 0・emsc 0) と sweep (他 130 関数不変) では出なかった。
- **180da6e60**: 候補 10 件 (`mov [rbp-0x29],rcx` 等) は全て `value: null` (局所の lea で値が出ない)。戻していない。この関数は native crash/timeout のため sweep でも比較できない。分類は ICALL-78 (#2508)。
- **census との一致**: F 131 関数の候補は 12 件 / 2 関数 (`181057b38` 2 件・`180da6e60` 10 件)。REPORT_APPENDIX_2394 §5 と一致。

## 3. 実測 (測定 commit `111c1411`)

測定 commit は、コードを変えた最後の commit (`feat(icall): restore dropped frame slot stores (ICALL-77 #2427)`、`frame_slot_restore.py` と `fa_route_build.sh`)。本付録の commit は docs のみ。測定は `111c1411` の内容を worktree (`../ws-2427`) で展開して行った。素材は `work-icall` (`rt_freshair-core`・`rw.dll`)、`toolchain-emsdk`、`toolchain-retdec`。`FA_CORE=rw.dll`。`plugins-freshair` は不使用。

### 3.1 8 入力 (`fa_wc_drv.cjs <fa_wc.cjs> 181057b38`)

| 条件 | 8 入力の結果 | WC 行 | "emsc" (`63736d65`) の WC 行 | BLK+0 (`0x36319008`) への "emsc" |
|---|---|---|---|---|
| base (`FA_FRAME_SLOT` 未設定) | OK 0 / TRAP 8 | 168 | 32 | 8 |
| fixed (`FA_FRAME_SLOT=1`) | OK 8 / TRAP 0 | 168 | 0 | 0 |

base の数値は REPORT_APPENDIX_2394 §4 の base と一致 (同じ 168 / 32 / 8)。`fa_wc_drv.cjs` は OK/TRAP だけを出すので、8 入力の値は本 run では取っていない。値は fa_sweep の先頭 2 入力 (§3.2) で見ている。

### 3.2 fa_sweep (`fa_sweep.sh 8 60`、131 関数)

| 条件 | bit 一致 | native crash/timeout | wasm のみ err | 値の不一致 | 所要 | load (1 分) 実行前→後 |
|---|---|---|---|---|---|---|
| base (`111c1411`) | 46 | 66 | 9 | 10 | 73 s | 0.84 → 1.04 |
| fixed (`FA_FRAME_SLOT=1`、`111c1411`) | 46 | 66 | 8 | 11 | 73 s | 0.14 → 0.84 |

- 逐次実行 (1 並列)。load は `uptime` の 1 分平均 (実行前 → 実行後)。
- **行が異なる関数は 1 件**: `0x181057b38`。`wasm_err` 8 → 0。base の先頭 2 入力は `ERR:RuntimeError: memory access out of bounds`、fixed は `0000000000000000`。`n=8`・`mismatch=8` は両方同じ。
- base の 46/66/9/10 は、REPORT_APPENDIX_2394 §4 の 47/66/9/9 と ±1 異なる (#2302 で追跡中の揺れ。本 HEAD でも再現)。

### 3.3 ネガティブコントロール

- 負の対照: 本 run では再実行していない。REPORT_APPENDIX_2394 §4 の `frame_slot_probe.py restore --separate` (store は戻し alloca を分けたまま) は TRAP 8・emsc 8 のまま。本 pass の結果 (TRAP 0) との差は、alloca の結合 (16B 化) による。
- 値の検出: 候補の数 12 は census (REPORT_APPENDIX_2394 §5) の数と一致する。

## 4. 残件 (ICALL-78 #2508 へ移した)

- **fixed IR でも 8/8 不一致**: sweep の先頭 2 入力で wasm の結果は `0x0000000000000000` (REPORT_APPENDIX_2394 §4 でも wasm の xmm0 は 0 と記載)。native の値とは一致しない。harness 由来か lift 由来かは未切り分け。TRAP だけは消えた。
- **180da6e60 候補 10 件**: 値が局所で解決できず分類していない。`[rbp-0x29]` の store が `lea rdx,[rbp-0x31]` → `call r10` の先で読まれるかの確認が必要。
- **SlateCore.core_64 の bytes 照合**: 元ファイルは本 run に無い (`plugins-freshair` を `oc_artifacts` に指定していない)。REPORT_APPENDIX_2394 §2 の「rw.dll の同 VA と 205 B 一致」は元 PE の decode 結果との比較で、元ファイル本体の sha256 との照合は未実施。

## 5. 範囲と限界

- 検証範囲: `181057b38` (8 入力と fa_sweep 131 関数)、`FA_FRAME_SLOT=1` の route・wc の build、検出件数 (F 131 関数)。
- 範囲外: 180da6e60 の wasm 実行 (native crash/timeout)、元 `SlateCore.core_64` との照合、8/8 不一致の原因、RDA 段が store を消す条件 (REPORT_APPENDIX_2394 §8)、他 PE (FLEngine 等) への適用。
- merge 規則 (`X-8` が lea で取られた i64 なら 16B にまとめる) は 181057b38 の 2 件で確認したのみ。一般化の妥当性は他関数で未確認。

## 6. 再現

```sh
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" -C .                      # tools/icall/work/ へ
bash tools/ott/native/build.sh                                               # fa_sweep に必要 (libottnative.so)
export FA_CORE="$PWD/tools/icall/work/rt_freshair-core/rw.dll"
bash tools/icall/fa_route_build.sh                                           # base
bash tools/icall/diff/fa_wc_build.sh
node tools/icall/diff/fa_wc_drv.cjs "$PWD/tools/icall/work/fa_wc/fa_wc.cjs" 181057b38
FA_FRAME_SLOT=1 bash tools/icall/fa_route_build.sh                          # fixed (既定 OFF を env で ON)
bash tools/icall/diff/fa_wc_build.sh && node tools/icall/diff/fa_wc_drv.cjs "$PWD/tools/icall/work/fa_wc/fa_wc.cjs" 181057b38
bash tools/icall/diff/fa_sweep.sh 8 60                                       # 131 関数 (約 73 秒)
```

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x181057b38` fixed 後も 8/8 不一致 (wasm の xmm0 戻り値 0) の原因 | TRAP は消えたが bit 一致は 0/8 | ICALL-78 (#2508) |
| `0x180da6e60` 候補 10 件の miscompile か無害かの分類 | closure 全体の判定は native crash/timeout のため比較不能 | ICALL-78 (#2508) |
| 元 `SlateCore.core_64` の bytes と `rw.dll` の同 VA の sha256 照合 | (a) の根拠は PE decode 結果の比較のみ | ICALL-78 (#2508) (`plugins-freshair` 必要) |
| `FA_FRAME_SLOT` の既定 ON 化 | 既定 OFF のため closure の route は従来どおり | PM 判断 (本 PR では既定 OFF) |
| `docs/DEFECTS.md` への D24 行の追加 | 横断正本への反映 | PM 判断 (`docs/WORKFLOW.md` §5) |
| `fa_sweep.sh` の ±1 の揺れ (base 46/66/9/10 と 47/66/9/9) | 数値の正本の取り方 | #2302 (既存) |

## 8. 測定 commit と差分

- 測定 commit: `111c1411` (コードを変えた最後の commit)。
- `git diff --name-only 111c1411 HEAD -- tools/icall/*.py tools/icall/*.sh tools/icall/diff tools/icall/rt` の出力: 0 行 (本付録の commit は md の追加のみ。コード差分 0)。
- 同じ範囲の `git diff --stat 111c1411 HEAD -- tools/icall` は本付録 1 件 (`tools/icall/REPORT_APPENDIX_2427.md`) のみ。

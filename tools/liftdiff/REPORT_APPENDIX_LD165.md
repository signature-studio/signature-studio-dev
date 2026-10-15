# 付録: liftdiff LD-165 (#3585) — units / hybrid の case 単位の揺れの起点と候補

> **正本**: `tools/liftdiff/REPORT.md`。前段は `REPORT_APPENDIX_LD154.md` (#3350・受入 1 の未達を #3585 へ移管) と `REPORT_APPENDIX_LD157.md` (#3423)。本書は LD-165 の実測と切り分けを置く。

## 結論

- **本 run の 4 回 (units 2 回・hybrid 2 回) では判定は揺れなかった**: units 360 / 234 / 206 (2 回とも)、hybrid 352 / 271 / 177 (2 回とも)。判定の変化は 0 関数。LD-154 の判定変化 (units `0x959a40`、hybrid `0x10348b0`・`0x959a40`) は再現しなかった。
- **case 単位では揺れた**: units 10 case / 6 関数、hybrid 6 case / 4 関数。全件が **wasm 側の status の変化** (trap ↔ timeout、crash ↔ hang) で、native 側は全件 `segv` のまま。timing 付き native の差は無い。
- **起点**: shard ごと (chunk 内 `vas[i::12]`) に最初に違った関数は、units 4 shard・hybrid 3 shard の全てで wasm 側の 1 case だった。起点より前に同じ shard で違った関数は無い。
- **原因の候補 (未確定)**:
  - (A) **wasm 1.0 s 上限の内外**。同じ case の trap は、同じ関数の先の case の後で 0.20 s (§4)。batch r2 では同じ経路が 1.296 s の timeout になった。負荷 (12 shard・4 vCPU) で 6 倍超に延びたと見られる。
  - (B) **wasm runner の履歴依存**。同じ case の経路が、同じ runner で先に走った case で変わる (`0x1060950 s` は前段なしで timeout 1.05 s、同じ関数の z の後で trap 0.20 s)。(B) は batch の r1/r2 の差 (前段が同じ) は説明しない。r1/r2 の差は (A) による。
  - (C) V8 の wasm 階層化 (Liftoff → TurboFan) の完了時刻が負荷で変わる。**未検証** (次の子 issue で確かめる)。
- **受入 1・2 (同一入力の再現性) は本付録では未達** (4 回の一致は偶然の一致かもしれず、LD-154 の揺れは再現していない)。受入 3 (揺れた case の候補と証拠) は case 単位について満たした。判定が変わった関数は本 run では 0 件のため、LD-154 の判定変化の原因は未確定のまま。残りは子 issue へ (§7)。

## 1. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit | `d5681415e` (本 branch の base)。`git diff --stat d5681415e HEAD -- tools/liftdiff/ldlib tools/liftdiff/liftdiff.py tools/liftdiff/rt` = 出力なし (0 行)。本 PR は解析スクリプトと本付録だけを足し、batch の実行経路は変えていない |
| 最新 main | `origin/main` は `251d55a1b` へ進んだ (`rt/ld_core.h` 37 行・`rt/ld_native.c` 24 行 ほか計 59 行追加)。**本測定は `d5681415e` のコードで行った**。最新 main での揺れは未測定 (§7) |
| 入力 | `targets/m11.json --set sample:800 --shards 12 --nobuild` |
| units state | `--state auto` = `work/m11/boot_state.json` (`bootstate targets/m11.json --nobuild`・`units_run=22/942`・`precondition ok=False`。LD-42 の既存状態) |
| hybrid state | `--state work/m11/boot_state_hybrid.json` (`bootstate --mode hybrid --nobuild`・`units_run=928/942`・`first_fail=830`・`precondition ok=True`) |
| 素材 | `fl-win64` を `$RUNNER_TEMP/fl-win64` へ展開 (`FL_WIN64_DIR`)。`work-m11`・`work-liftdiff` を `tools/m11/work`・`tools/liftdiff/work` へ展開。`[EMSDK]` (`docs/REFERENCES.md` §4) |
| build | `gcc ... rt/ld_native.c` と `liftdiff.py build targets/m11.json` (`[build] OK`・`wasm_size` 4460359) |
| 機 | 4 vCPU・15 GiB。run は直列 (並列にしない) |
| 所要 (実測) | units r1 04:24:43→04:26:28 (1 分精度)、r2 04:26:28→04:28:11。hybrid h1 `[batch] done 219s`、h2 `done 209s` |
| load (1 分) | units r1 開始 0.90 → 終了 5.49、r2 終了 6.02。hybrid h1 終了 8.93 |

## 2. 判定と case 単位の突合

`tests/ld165_flip_origin.py` の出力 (判定変化・case 単位の揺れ・shard の起点)。timing の表記は `n=<cause>/<秒> w=<cause>/<秒>` (cause は `runner_timeout`・`eof` など)。

units (r1 = A、r2 = B):

| 関数 | case | A (outcome/native/wasm) | A timing | B (outcome/native/wasm) | B timing |
|---|---|---|---|---|---|
| `0x1060950` | s | both_fault/segv/trap | - | hang/segv/timeout | w 1.296 s |
| `0x1266e70` | p0 | hang/segv/timeout | w 1.016 s | native_fault/segv/ok | - |
| `0x67e2b0` | p1 | both_fault/segv/trap | - | hang/segv/timeout | w 1.037 s |
| `0x67e2b0` | s | both_fault/segv/trap | - | hang/segv/timeout | w 1.030 s |
| `0x4630d0` | z | both_fault/segv/trap | - | hang/segv/timeout | w 1.011 s |
| `0x5c5500` | fvm#0 | both_fault/segv/trap | - | hang/segv/timeout | w 1.037 s |
| `0x5c5500` | p1 | hang/segv/timeout | w 1.028 s | both_fault/segv/trap | - |
| `0x5c5500` | pall | both_fault/segv/trap | - | hang/segv/timeout | w 1.030 s |
| `0x5c5500` | u16 | both_fault/segv/trap | - | hang/segv/timeout | w 1.032 s |
| `0xde10c0` | z | both_fault/segv/trap | - | hang/segv/timeout | w 1.023 s |

hybrid (h1 = A、h2 = B):

| 関数 | case | A | A timing | B | B timing |
|---|---|---|---|---|---|
| `0x620cd0` | q0 | wasm_timeout_native_long/ok/timeout | w 1.384 s | wasm_trap/ok/timeout | w 1.231 s |
| `0x67e2b0` | p1 | both_fault/segv/trap | - | hang/segv/timeout | w 1.093 s |
| `0x67e2b0` | s | both_fault/segv/trap | - | hang/segv/timeout | w 1.072 s |
| `0xa9ece0` | pall | hang/segv/crash | w eof 1.097 s | hang/segv/hang | w eof 1.099 s |
| `0xa9ece0` | pall2 | hang/segv/crash | w eof 2.865 s | hang/segv/hang | w eof 2.748 s |
| `0x4630d0` | z | both_fault/segv/trap | - | hang/segv/timeout | w 1.095 s |

- 負の対照 (同じ JSONL 同士): 揺れ 0 件 (`ld165_flip_origin.py` の出力)。
- 別アルゴリズムの検算 `tests/ld154_repeat.py` (units r1/r2): 判定 360/234/206 で 2 回一致、判定変化 0 関数。timing 付き case は 285 (A) と 291 (B) で、LD-154 の手順の出力と一致する形式。

## 3. shard ごとの起点

`ld165_flip_origin.py` は、chunk 内で `vas[i::12]` に割られた shard の順に、最初に A と B が違った関数を出す。

- units: chunk 400・shard 0 `0x1060950` (s) / shard 1 `0x67e2b0` (p1・s) / shard 6 `0x5c5500` (fvm#0・p1・pall・u16) / shard 8 `0x1266e70` (p0)
- hybrid: chunk 0・shard 5 `0x620cd0` (q0) / chunk 400・shard 1 `0x67e2b0` (p1・s) / chunk 400・shard 2 `0xa9ece0` (pall・pall2)

起点はすべて wasm 側の 1 case で、起点より前の同 shard の関数は両 run で一致している。

## 4. 単独照合と前段の再現

`tests/ld165_replay.py` は、対象の関数を同じ shard の前段の関数の後に、新しい runner で走らせる (`run_functions` と同じ経路)。wasm の経過秒 (`_w._elapsed_s`) を出す。units state (`work/m11/boot_state.json`)。

| 条件 | `0x1060950` の `s` | wasm 経過秒 |
|---|---|---|
| 新規 runner で `s` を最初の case として単独 (`--solo`) | timeout | 1.077・1.075・1.075 s (3 回) |
| 同じ関数の全 pattern を z から順に (前段の関数なし・`--patterns s`) | trap | 0.203・0.204 s (2 回) |
| 前段 `0x9773f0` の後 (shard 0 の 1 つ前) | trap | 0.202・0.198 s (2 回) |
| batch r1 (shard 0 の chunk 2) | trap | - |
| batch r2 (同じ前段) | timeout | 1.296 s |

| 条件 | `0x1266e70` の `p0` | wasm 経過秒 |
|---|---|---|
| 同じ関数の全 pattern を z から順に (新規 runner・前段なし) | trap | 0.261・0.262 s (2 回) |
| shard 8 の前段 9 関数の後 (`tests/ld165_replay.py --prefix`) | ok | 0.181・0.181 s (2 回) |
| batch r1 | timeout | 1.016 s |
| batch r2 | ok | - |

- 前段が同じでも、同じ case の経過秒は 0.2 s (replay) と 1.3 s (batch r2) に分かれた。負荷による 6 倍超の延びで説明できる (A)。
- 同じ case が、同じ runner で先に走った case の有無で 0.2 s の trap と 1.05 s の timeout に分かれた。wasm runner の履歴 (前に走った case) が経路を変える (B)。
- replay (前段あり・3 回) の trap は、batch r1 の trap と一致し、r2 の timeout とは一致しない。r2 は (A) による。
- (B) の機構は未確定。wasm の状態が case 間で完全には戻らないのか、wasm 側の実行の経路 (V8 の階層化を含む) が履歴で変わるのかは区別していない (子 issue で確かめる)。

## 5. LD-154 の判定変化は再現せず

LD-154 (`38e057dce`) の判定変化 (units `0x959a40`、hybrid `0x10348b0`・`0x959a40`) は、測定 commit `d5681415e` の 4 回では出なかった。LD-157 の起点候補 (`0x10348b0` の chain) も、本 run の起点には現れない。判定変化の再現条件は未確定で、子 issue で扱う。

## 6. 検証

- `python3 tests/ld165_flip_origin.py work/m11/ld165_units_r1.jsonl work/m11/ld165_units_r1.jsonl` → 揺れ 0 件 (負の対照)。
- `python3 tests/ld154_repeat.py work/m11/ld165_units_r1.jsonl work/m11/ld165_units_r2.jsonl` → 判定変化 0 関数 (検算)。
- `python3 tests/ld165_flip_origin.py` の入力は `work/m11/ld165_{units,hybrid}_{r1,r2,h1,h2}.jsonl` (gitignore・commit しない)。
- 再現: `cd tools/liftdiff && FL_WIN64_DIR=<fl-win64 展開先> TMPDIR=<tmp> python3 liftdiff.py batch targets/m11.json --set sample:800 --shards 12 --nobuild --state auto --out work/m11/ld165_units_r1.jsonl` (r2 も同じ・hybrid は `--state work/m11/boot_state_hybrid.json`)。
- §4 の再現 (`tools/liftdiff` で実行): `python3 tests/ld165_replay.py --state work/m11/boot_state.json --target 0x1060950 --patterns s --solo --reps 3` (単独)、`... --target 0x1060950 --patterns s --reps 2` (同じ関数の全 pattern を z から)、`... --target 0x1060950 --prefix 0x9773f0 --patterns s --reps 2` (前段あり)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1・2 (units / hybrid を同一 commit で 2 回連続して一致させる) | 基準値の再現性 (`liftdiff_e2e.sh` [4/4]) | 子 issue LD-182 (本 PR で起票) |
| 揺れの原因の確定: (A) 負荷による 1.0 s 上限の内外、(B) wasm runner の履歴依存、(C) V8 の wasm 階層化の完了時刻 (未検証) | 修正方針 (判定ロジック・timeout 既定値は変えない制約の下で、何を決定的にするか) | 子 issue LD-182 |
| LD-154 の判定変化 (`0x959a40`・`0x10348b0`) の原因 (本 run では再現せず) | 受入 3 の判定変化の部分 | 子 issue LD-182 |
| 最新 main (`251d55a1b`・`rt/ld_core.h`・`rt/ld_native.c` の変更) での揺れは未測定 | 測定の前提 | 子 issue LD-182 |

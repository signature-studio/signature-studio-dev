# REPORT_APPENDIX_2152 — unit 158 の後続経路と ON 書換えの 2 区間計装 (#2152, 親 #2118)

REPORT_944.md の #2152 追記 (旧 §11) の付録。測定 commit: **`870f7ecd`** (コードを変えた最後の commit。実測はこの commit の状態で行った)。

## 1. 結論 (受入条件 1〜4)

- **受入 1 (後続経路の IR 突合・部分)**: unit 158 は IR 上 `function_66d1a0` (VA `0x26d1a0`・IR 行 231236)。直接 call の到達は 303 関数。
  2 区間を直接読む関数は §3 の一覧のとおり (`function_412c20` は `0x11e6a2c` を読む 1 経路)。j=12 の dest (k=148) は ON で `0x10a9e0b8` (len 1) で、2 区間の外。
  **未確定**: 2 区間を読む `412c20` の結果が j=12 の後続の ok/trap を変えるかは、この run では測っていない。
- **受入 2 (ON の 2 区間への書込み)**: **達成**。OFF と ON の `[rw]` 書込み集合 (site・addr・val・width) は 738 件で完全一致。
  ON の再実行でも一致 (決定性)。
- **受入 3 (結論の反映)**: 意味的差 / ビルド差 / 観測副作用の**結論は未決**のまま。REPORT_944 (main 版 250 行上限のため #2152 の要旨は本付録のみに置く) に本付録の要旨だけを書く。
- **受入 4 (決定性・所要・load)**: §4 に実測値。

## 2. 2 区間の書込み (受入 2・実測)

計装: `trap_triage/watch_2118.sh` (`watch_store_682.py` の全 54,041 store 計装 + `watch_range_2118.c` の 2 区間版 `m11_sw`)。
clean 判定は計装なし build。watch build は計装で unit 158 が trap する (既知の計装副作用)。

| 構成 | unit 0 | unit 1 | unit 158 (clean) | unit 158 (watch) | `[rw]` 件数 |
|---|---|---|---|---|--:|
| OFF (`M11_OV_413060=0`) | ok | ok | ok | trap (計装副作用) | 738 |
| ON (`M11_OV_413060=1`・`M11_DEST_READ=1`) | ok | ok | ok | trap (計装副作用) | 738 |

単位ごとの書込み (区間 A = `0xfa5108`〜、区間 B = `0x11e69b0`〜・OFF と ON で同一):

| unit | 区間 | 件数 | 書込み関数 |
|---|---|--:|---|
| 1 | A | 321 | `function_4090e0` |
| 1 | B | 347 | `function_409070` 326・`function_40f4b0` 15・`function_41ce10` 3・`function_4090e0` 2・`function_41ca50` 1 |
| 158 | A | 68 | `function_407a50__lifted` 43・`function_407e20__lifted` 25 |
| 158 | B | 2 | `function_407680` (`0x11e6b88`/`0x11e6b90`) |

- unit 0 は両区間に書かない (§10.3 と一致)。
- unit 158 は計装版で 2 区間に書く。clean 版の値は計装で変わり得るため、書込み元の特定だけに使う。
- `function_407a50__lifted` / `function_407e20__lifted` は lift 名の suffix 付き (sites.json の fn 名)。直接 IR 名は `function_407a50` / `function_407e20`。

## 3. unit 158 の後続経路 (受入 1・静的)

- 根: `function_66d1a0` (= unit 158)。直接 call の到達 303 関数。
- 書込み (reach 内): `function_407680` が `0x11e6b90` に書く (単一)。
- 読出し (reach 内・2 区間): `function_407a50` (`0xfa5108`・`0x11e6a35`・`0x11e6a3c`)・`function_412c20` (`0x11e6a2c`)・`function_412c90`/`413230`/`413340`/`414aa0` (`0x11e6a28`)・`function_407680` (`0x11e6b88`/`0x11e6b90`)・`function_4074d0`/`407720`/`407e20` (`0x11e6a35`)。
- 限界: 直接 call のみ。indirect call と base+offset の書込みは含まない。

### j=12 の dest (k=148) の値 (ON 計装・`M11_PRINT_DEST_2118=1`・probe 無し)

unit 158 の `function_413060` 呼出し 28 件の dest はすべて `0x10a9xxxx` (heap)。2 区間の外。
j=12 (0 始まりで 13 行目) は `dest=0x10a9e0b8 len=1`。`n>0` 経路で `function_412c20` を呼ぶ。
この dest 値は OFF の実行記録が無いため、OFF との直接比較は REPORT_944 §8 (`dest=... len 0→1`) に頼る。

## 4. 決定性・所要・load (受入 4)

測定 commit `ed20d891` の状態での実測。

| 測定 | 内容 | 結果 | elapsed | load (開始) |
|---|---|---|--:|--:|
| 既定 survey | `env -u M11_INSTR_413060 node m11_survey.mjs` | ok 870 / trap 24 / miss 47 / noproc 1 / units 942 | 16.3 s | 0.92 |
| watch OFF | `watch_2118.sh off` (clean・dest・watch の 3 build と実行を含む) | 0,1,158 = ok/ok/ok (clean)・`[rw]` 738 | 87 s | 0.93 |
| watch ON | `watch_2118.sh on` (同上) | 0,1,158 = ok/ok/ok (clean)・`[rw]` 738 | 87 s | 0.91 |
| watch ON 再実行 | 同上 | `[rw]` 集合は前回と一致 (OFF/ON の集合も一致) | 86 s | 0.76 |

dest 段 (`M11_PRINT_DEST_2118=1`) は `watch_2118.sh` の中で実行される。ON は `[d413060]` 28 件・0,1,158 = ok/ok/ok、OFF は `[d413060]` 0 件・0,1,158 = ok/ok/ok。dest 段の所要は個別には計っておらず、watch 行の elapsed に含まれる。

dest 段で確認したのは `[d413060]` の dest 値 (ON のみ) と ok/trap だけ。dest 段の build は `[rw]` を出さないので、rw 集合の一致はこの段からは言えない (rw 集合の根拠は watch build の表 §2 のみ)。

既定 survey の 870/24 は REPORT_944 §6.1 (870/24) と一致。既定 build の `boot_final3.ll` md5 は `baa100ff37a790dc1103c26a2e648d12` (§10 と一致)。
watch 系の 2 回の ON で `[rw]` 集合が一致 (決定的)。

## 5. 実行環境

- 素材: `fl-win64`・`work-m11`・`toolchain-emsdk` (`$HOME/artifacts` から展開)。`m11_gen_ir2.sh` で `ir_conditions.json` 生成 (ldfix F1=902 F3c=36 errors=0)。
- `m11_gen_ir2.sh` 所要 57 s (測定 commit で再生成し、ldfix F1=902 F3c=36 errors=0 を確認)。
- `work-m11` 付属の `work/m11_boot.cjs` のままでは survey が `_m11_set_va_unit_budget` 未定義で落ちたため、`m11_gen_ir2.sh` → `m11_build.sh` で作り直してから測定した。
- IR の unit 名は `function_<VA>` で、VA `0x26d1a0` は `function_66d1a0` (base `0x400000`)。REPORT_944 §10 の `function_41ce10` (VA `0x1ce10`) と同じ規則。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `412c20` の結果 (2 区間の読出し) が j=12 の後続の ok/trap を変えるかの確定 (ON で 2 区間を読む経路の値差) | 意味的差か観測副作用かの判定 (REPORT_944 §4 (a)) | #2203 |
| OFF 側の dest 値の直接記録 (`m11_ov.c` の print は C 版 413060 のみ) | OFF/ON の dest 値の 1 対 1 比較 | #2203 |

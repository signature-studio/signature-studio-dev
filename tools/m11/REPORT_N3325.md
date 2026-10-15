# M11 LB 依存 unit 差 8 件の切り分け (#3325・親 #3296・祖父 #3229)

測定主体: 本 PR の作業 runner (2026-10-15 UTC)。素材は `fl-win64` (`extracted/block00031_PE.bin` 22,227,016 B のみ展開)・`tools/m11/work/` (work-m11 展開済み・lift 成果物あり)・`[EMSDK]` (toolchain-emsdk 既存・`docs/REFERENCES.md`)。
測定 commit: `d6b7b27c` (コードを変えた最後の commit。計測 env の既定は 0)。`git diff d6b7b27c HEAD -- tools/m11 ':(exclude)tools/m11/REPORT*'` の出力は空。
既知類型との関係: 該当なし (類型の新規候補は §5)。

## 1. 結論

- **#3296 の源修正の前提が build に効いていない。** `function_412770` の実行体は IR 本体ではなく、`tools/m11/m11_ov.c` の手書き C 版 (`function_412770(void* ctx)`・longjmp 相当で `m11_throw_dllmain_done` を投げる) である。IR 本体 (`ptr null` の rep movsq を含む) は両 LB とも一度も実行されない (§2)。
- したがって `REPORT_N403.md` §7 の推定「arg1 先が 0 のため address 0 を読む」は、この実行経路では成立しない (棄却)。#3296 の源修正が結果を 1 件も変えないのは、この構造で説明できる。
- kind 差 8 件は HEAD (`d6b7b27c`・既定フラグ) でも再現した (§3)。原因の分岐は未特定。`function_4128b0` の Halt 分岐の入口まで絞れた (§4)。
- 未達の受入条件 (分岐値の呼出し時点の実測・kind 差 0・新類型の行案) は子 issue `[M11-N182]` へ移した (§6)。

## 2. function_412770 の arg1 観測 (受入 1)

計測: `M11_INSTR_412770=1 M11_TOLERANT_ERR=1` で build し、寛容起動 (942 unit) を LB=0 / LB=0x10000 で各 1 回。`m11_post.py` が IR 本体を `function_412770__lifted` に改名し、観測 wrapper `function_412770` (weak) を置く。

| LB | 観測行 `[m11][412770]` | unit 40 の結果 (C 版を通る経路か) |
|---|---|---|
| 0 | 0 件 | ok (trap なし) |
| 0x10000 | 0 件 | halt0 (C 版の `m11_throw_dllmain_done` まで到達) |

- 観測 wrapper が 0 回。IR 本体の arg1 (`ptr %arg1`) と `[arg1+0]` は実行時に存在しない。
- LB=0x10000 の unit 40 の trap スタック (wasm 関数名は同一 build で付与): `m11_throw_dllmain_done` ← `function_412770` (C 版・`m11_ov.c` の `EM_JS` 呼出し元) ← `function_4128b0__lifted`。IR の本体は `m11_throw` を直接呼ばないので、この frame は C 版である。
- 推定の棄却: REPORT_N403 §7 の「寛容起動の arg1 先が 0 のため、`[arg1+0]` が address 0」は、この経路 (C 版が arg1 を読まない) では起きない。

## 3. kind 差 8 件 (受入 3 の現状)

`python3 tools/m11/m11_lb_unit_diff.py tools/m11/work/head_lb0/tolerant_units.json tools/m11/work/head_lb10000/tolerant_units.json` → `kind_diff 8` (HEAD `d6b7b27c`・既定フラグ・LB=0 と LB=0x10000 を各 1 回)。差の unit は REPORT_N403 §6-2 と同一。

| index | VA (LB=0 側) | LB=0 | LB=0x10000 |
|---|---|---|---|
| 40 | 0x105bd0 | ok | halt0 |
| 153 | 0x265b90 | ok | oob |
| 158 | 0x26d1a0 | ok | oob |
| 291 | 0x432660 | oob | ok |
| 296 | 0x446130 | oob | ok |
| 304 | 0x483140 | oob | abort |
| 555 | 0x7f2500 | oob | abort |
| 745 | 0xabb3b0 | oob | ok |

## 4. trap 位置 (受入 2)

wasm 関数 index は **build ごとに変わる** (例: index 3149 は LB=0x10000 build では `function_535240`、LB=0 build では `function_535c11`)。各 build の `work/m11_boot.cjs.wasm` で `python3 tools/m11/m11_wasmnames.py <wasm> <idx>` して名前を付けた。

LB=0 側 (`M11_TOLERANT_STACK=...` の trap スタック):

| unit | 直接の trap 関数 (offset) | 呼出し元 |
|---|---|---|
| 291・296・304・555 | `function_535c11` (0x194cbb 系) | `function_4fad10` ← `function_4fb910` ← unit 関数 |
| 745 | `function_407e20__lifted` (FastMM_FreeMem 本体・0x13d5d6) | `function_407e20` (probe wrapper) ← `function_409440__lifted` ← `function_409440` (FreeMem wrapper) |

LB=0x10000 側:

| unit | 直接の trap 関数 | 呼出し元 |
|---|---|---|
| 153 | `function_412e40` (0x6b739) | `function_664fd0` ← `function_665b90` |
| 158 | `function_412c20` (0x14cc66) | `function_4136a0` ← `function_413760` ← `function_414bb0` ← `function_653660` |
| 40 | (halt0) `function_412770` C 版 | `function_4128b0__lifted` |

**未特定:** address 0 を読む命令 (受入 2 の後半)。trap の wasm offset から IR 命令への対応は未実施。

### 4-1 function_4128b0 の Halt 分岐 (IR・LB=0 build の定数)

`function_4128b0__lifted` (IR) で `function_412770` (C 版) へ進む条件:

1. `load i64 [0xFA5008]` (= 16404488) が 0 でないこと (LB=0x10000 では +0x10000)。
2. `load i64 [18787760]` が 0 でないこと。
3. `GetCurrentThreadId() == load i32 [18787804]` であること。
4. 通ると `store i64 0 → [18787760]` の後に `function_412770(18787752)` を呼ぶ。

unit 40 の前後 (u32 の下位 4B) を LB 別に読んだ値 (`M11_TOLERANT_PEEK`・`M11_TOLERANT_PEEK_UNITS=40`):

| LB | before | after | kind |
|---|---|---|---|
| 0 | `[18787752]=0 [18787760]=0 [18787804]=0` | 同じ | ok |
| 0x10000 | `[18853288]=0 [18853296]=0 [18853340]=0` | 同じ | halt0 |

- 4 は関数内で `[18787760]` を 0 に戻すため、unit 前後の読みでは条件を判定できない。**呼出し時点** (`function_4128b0` の入口と分岐直前) の値が要る → 子 issue。
- LB 差の候補: 1 の `[0xFA5008]` と 3 の `GetCurrentThreadId` 比較。どちらが LB で変わるかは未確定。

## 5. 新類型の候補 (docs/DEFECTS.md 用・未確定)

- 候補 X: 「手書き C 上書き (`m11_ov.c`) が IR 本体より優先され、IR 側の修正が build の実行経路に入らない」。#3296 の源修正がこれに当たる見込み。類型 ID は未付与。`docs/DEFECTS.md` への登録は子 issue の受入で判断する。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_4128b0` の 412770 呼出し分岐の値 (呼出し時点・LB 別) | LB=0x10000 の unit 40 の halt0 の原因が未特定 | `[M11-N182]` (子 issue) |
| unit 153・158 の OOB 命令 (wasm offset → IR 命令) と LB=0 側 291・296・304・555・745 の OOB 命令 | kind 差 7 件の原因が未特定 | `[M11-N182]` |
| kind 差 0 (受入 3) と新類型の行案 | #3296・#3325 の受入が未達 | `[M11-N182]` |
| #3296 / PR #3327 の源修正が build の実行経路に無い (§1・§2) | #3296 の受入「kind 差 0」は源修正では達成できない見込み | PM 判断 (親 #3296 へのコメント) |
| 寛容起動 pin (874/67) と snapshot 値 (867/74) の差 | REPORT_N403 §6-5 の既存未解決。本件では未確認 | REPORT_N403 §6-6 に残す |

## 7. 再現

- 計測 build: `M11_INSTR_412770=1 M11_TOLERANT_ERR=1 M11_TOLERANT_STACK=40,153,158,291,296,304,555,745 bash tools/m11/m11_lb_tolerant_repro.sh <LB> work/<dir>`
- peek: `M11_TOLERANT_PEEK=<addr,..> M11_TOLERANT_PEEK_UNITS=40 node tools/m11/m11_tolerant.mjs` (build 済みの `work/m11_boot.cjs` を使う。アドレスは LB 分ずらす)
- 既定 (計測 OFF): `bash tools/m11/m11_lb_tolerant_repro.sh 0 work/head_lb0` と `... 0x10000 work/head_lb10000` → `m11_lb_unit_diff.py` で kind_diff 8 (§3)

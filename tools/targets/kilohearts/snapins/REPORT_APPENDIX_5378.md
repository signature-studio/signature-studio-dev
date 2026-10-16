# KH-156 (#5378): Carve EQ (ksge) process 直接 closure の unique 25 関数の lift

- 親: #4863 (KH-122・#3308 の分割) / 元 issue: #5378 (KH-156)。
- 測定起点 = origin/main `e5a694ab1`。測定 commit = 本 PR の lift 定義 commit (`snapins.json` の `carveproc` 節を加えた commit)。
- 素材: `plugins-kilohearts` の `Kilohearts Offline Installer.zip` (Windows 側 `HeartCore.core_64`)。closure の作り方は `rtti_walk` → `callgraph` → `closures` → `carve_iat_census` と同じ。

## 0. 結論

- process 直接 closure (slot 14 = RVA `0x37d210`) は **145 関数** = unique **25** + infra **120**。
  再現: `python3 snapins/scripts/carve_process_split.py work/callgraph.pkl work/closures_sets.pkl snapins/snapins.json`。
- unique 25 の IAT 呼出は **0 件**。infra 120 の IAT 呼出は **60 件** (`callgraph.pkl` の `iat`。名前付き 51 + CFG 間接 9。REPORT_APPENDIX_781 §5 と同じ)。
- unique 25 を `carveproc` (snapins.json) として既存 lift 経路 (`build.py carveproc --path s0 --no-compare`) で lift した。結果: **20 関数**を wasm 化、`undefined_imports = []`。
- 残り 5 callgraph ノード (`0x18037e63f`・`0x180c23e02`・`0x180c23f28`・`0x180c2419a`・`0x180c243df`) は、RetDec の `--select-ranges` が関数入口として扱えず (`stage0 に関数が無い`) 入力から外した。5 件とも `.pdata` の関数開始点ではなく、lift した 20 関数のいずれかの末尾からの **jmp の先** (`0x18037e5e0`→`0x18037e63f`、`0x180c23d90`→`0x180c23e02`、`0x180c23ec0`→`0x180c23f28`、`0x180c240c0`→`0x180c2419a`、`0x180c242c0`→`0x180c243df`)。RetDec 単独では、tail jump 先の共有部か単独関数かを判定できない (実測 n=5)。
- bit-exact 比較は行っていない (`--no-compare`)。受入 1 の bit-exact は親 #4863 の受入 1。

## 1. lift 結果 (実測)

| 項目 | 値 |
|---|---|
| 入力関数 (lift 対象) | 20 (`snapins.json` `carveproc.lift`) |
| RetDec stage-0 所要 | 10.2 s |
| kh_lower (`lowered.ll`) | mov128 166 / flags 28 / merge 23 / callret 74 / store128 124 / storelow 3 |
| globals / stubs | 79 globals / 定義 20・stub 11 |
| emcc 所要 / ピーク RSS | 1.7 s / 117 MB |
| wasm | 184,815 B |
| undefined_imports | `[]` |
| 実行 | `stat.json`: `work/carveproc/main/` (gitignore 対象・commit しない) |

環境: 4 CPU。所要は `build.py` の `retdec_sec`・`emcc_sec` の実測値のみ。load average は未記録。

## 2. infra 120 の判定表

unique 側 25 から呼ばれる infra 関数 (= 11 件)。`carve_process_split.py` の出力 (実測):

| callee | khbase lift 対象か | 呼出元 (unique) | 本 lift での扱い |
|---|---|---|---|
| `0x180005c50` | 対象 | `0x389700`・`0x38a680` | stub (`abort`) |
| `0x18004cf20` | 対象 | `0x37d210` | stub (`abort`) |
| `0x180f878e0` | 対象 | `0x389700`・`0x38a680` | stub (`abort`) |
| `0x180f8791c` | 対象 | `0x389700`・`0x38a680` | stub (`abort`) |
| `0x180fb5f5c` | 対象 | `0x389700`・`0x38a680` | stub (`abort`) |
| `0x180fd8bd4` | 対象 | `0xfd4d48` | stub (`abort`) |
| `0x180fbc1f4` | 外 | `0x37d210`・`0x389700`・`0x38a510` | stub (`abort`) |
| `0x180fcd690` | 外 | `0x389700`・`0xbacaa0` | stub (`abort`) |
| `0x180fcde58` | 外 | `0xbacaa0` | stub (`abort`) |
| `0x180fce0d0` | 外 | `0xbacaa0` | stub (`abort`) |
| `0x181384040` (memmove) | 外 | `0x37d210`・`0x389700` | stub (`abort`)。`khbase` の shim は別 snap-in の設定 |

- 11 件は `carveproc` の `stubs.c` で全て `abort()` の stub (`stubs 11`)。「khbase 対象」は、khbase で lift する予定の関数だが、本 lift の wasm には入っていない。
- memmove (`0x181384040`) は `abort` の stub。unique 側の `0x37d210`・`0x389700` が memmove を呼ぶため、wasm 実行時はこの経路で必ず trap する。wasm 動作は未検証で、memmove の shim 方針は後続 #4863 で決める。
- unique 25 が直接呼ぶ callee は 11 件 (khbase 対象 6・khbase 外 5 = `carve_process_split.py` の出力)。khbase 外の 5 件は本 lift で stub (`abort`)。
- stub 11 件を呼ぶ unique 関数は `0x37d210`・`0x389700`・`0x38a510`・`0x38a680`・`0xbacaa0`・`0xfd4d48`。これらの経路は wasm 実行時に `abort()` で止まる。bit-exact の対象にできるのは stub を解消した後。
- infra 120 の判定 (実測・`carve_process_split.py` の末尾に集計を追加):

| 区分 | 件数 | size B | IAT 呼出 | 判定 |
|---|---|---|---|---|
| khbase lift 対象 (`snapins.json` `khbase.lift`) | 98 | 10,044 | 60 | 共有 (infra_all)。khbase の lift 集合に入る |
| khbase lift 対象外 | 22 | 10,671 | 0 | 共有 (infra_all)。khbase の lift 集合に入らない |
| 合計 | 120 | 20,715 | 60 | 全件が `closures_sets.pkl` の `infra` (到達 snap-in 数 ≥ `INFRA_K` = 8) に含まれる |

- 「共有か個別か」の判定: 120 件とも到達 snap-in 数 ≥ 8 の共有基盤 (`infra_all` 188 件の一部) である。したがって process 専用の個別関数ではなく、snap-in 間で共有される基盤。内訳の khbase 対象 / 対象外は、khbase の lift 集合に入るかどうかの区分。
- 検証: `closures_sets.pkl` の `infra` と突き合わせ、120 件すべてが含まれることを確認。`khbase.lift` の 116 件のうち 98 件が infra 120 に入る。
- 前版の 98 / 22・10,044 B / 10,671 B は本 run で再現した (入力 `work/callgraph.pkl`・`work/closures_sets.pkl` は素材 `plugins-kilohearts` から再生成)。

## 3. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 20 関数の bit-exact (native vs wasm) | 受入 1 の検証 | #4863 (親) の受入 1 |
| 未 lift の infra callee 5 件 (stub) の lift | wasm 実行時に `abort` | 親 #4863 の残作業 (infra 側の判定) |
| 5 アドレスの扱い (jmp 先。関数入口ではない。共有部か単独関数かは未判定) | 受入 1 の残り 5 件 | 親 #4863 の関数入口の定義 |
| khbase 対象外の 22 件 (10,671 B) の lift 方針 | infra 側の判定 | 親 #4863 の残作業 |
| slot 7・13 が native scenario で呼ばれるか | process 以外の呼出経路 | #5377 (KH-155) と KH-130 |

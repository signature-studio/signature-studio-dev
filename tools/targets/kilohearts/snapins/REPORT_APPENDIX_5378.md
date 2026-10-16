# KH-156 (#5378): Carve EQ (ksge) process 直接 closure の unique 25 関数の lift

- 親: #4863 (KH-122・#3308 の分割) / 元 issue: #5378 (KH-156)。
- 測定起点 = origin/main `e5a694ab1`。測定 commit = 本 PR の lift 定義 commit (`snapins.json` の `carveproc` 節を加えた commit)。
- 素材: `plugins-kilohearts` の `Kilohearts Offline Installer.zip` (Windows 側 `HeartCore.core_64`)。closure の作り方は `rtti_walk` → `callgraph` → `closures` → `carve_iat_census` と同じ。

## 0. 結論

> **状態: 本 run で再測定 (infra 判定表は実測で再現)。** 素材 `plugins-kilohearts` の `HeartCore.core_64` から
> `rtti_walk` → `callgraph` (4 proc) → `closures` → `carve_process_split.py` を実行した (stdout 全行は §2)。
> lift (§1) は本 run では再実行していない (前 run の記録)。

- process 直接 closure (slot 14 = RVA `0x37d210`) は **145 関数** = unique **25** + infra **120** (本 run で実測)。
  再現コマンド: `python3 snapins/scripts/carve_process_split.py work/callgraph.pkl work/closures_sets.pkl snapins/snapins.json`。
- unique 25 の IAT 呼出は **0 件**、infra 120 の IAT 呼出は **60 件** (本 run で実測)。
- unique 25 を `carveproc` (snapins.json) として既存 lift 経路 (`build.py carveproc --path s0 --no-compare`) で lift した前 run の結果: **20 関数**を wasm 化、`undefined_imports = []` (前 run の記録。本 run では再実行していない)。
- 残り 5 callgraph ノード (`0x18037e63f`・`0x180c23e02`・`0x180c23f28`・`0x180c2419a`・`0x180c243df`) は、`callgraph.pkl` の関数ノード (`res` のキー) として存在し、それぞれに jmp 辺が 1 本ある (本 run で確認): `0x18037e5e0`→`0x18037e63f`、`0x180c23d90`→`0x180c23e02`、`0x180c23ec0`→`0x180c23f28`、`0x180c240c0`→`0x180c2419a`、`0x180c242c0`→`0x180c243df`。前 run は RetDec の `--select-ranges` が関数入口として扱えず入力から外したと記した (前 run の記録)。`.pdata` の開始点かは未確認。
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

unique 側 25 から呼ばれる infra 関数 (= 11 件)。呼出元と khbase 区分は本 run の `carve_process_split.py` の出力。「本 lift での扱い」は前 run の lift の記録:

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
- `carve_process_split.py` の stdout 全行 (本 run・素材 `plugins-kilohearts` の `HeartCore.core_64`・`rtti_walk` → `callgraph` (4 proc) → `closures` の出力に対して実行):

```
process direct closure 145 / unique 25 / infra 120
unique IAT calls 0 / infra IAT calls 60
infra callees called by the unique side (khbase lift の有無):
  0x180005c50 khbase-lifted  callers=['0x389700', '0x38a680']
  0x18004cf20 khbase-lifted  callers=['0x37d210']
  0x180f878e0 khbase-lifted  callers=['0x389700', '0x38a680']
  0x180f8791c khbase-lifted  callers=['0x389700', '0x38a680']
  0x180fb5f5c khbase-lifted  callers=['0x389700', '0x38a680']
  0x180fbc1f4 not-khbase     callers=['0x37d210', '0x389700', '0x38a510']
  0x180fcd690 not-khbase     callers=['0x389700', '0xbacaa0']
  0x180fcde58 not-khbase     callers=['0xbacaa0']
  0x180fce0d0 not-khbase     callers=['0xbacaa0']
  0x180fd8bd4 khbase-lifted  callers=['0xfd4d48']
  0x181384040 not-khbase     callers=['0x37d210', '0x389700']
callee tally {'khbase-lifted': 6, 'not-khbase': 5}
infra khbase-lifted: n 98 / size B 10044 / IAT calls 60
infra not-khbase: n 22 / size B 10671 / IAT calls 0
```

- `closures.py` の出力は `infra 188 53010 n 42`。
- 実測所要 (本 run・4 CPU・開始時 load average 1.58): `rtti_walk.py` 1.7 s、`callgraph.py` (4 proc・120,856 関数 sweep) 7.1 s、`closures.py` 0.2 s、`carve_process_split.py` は 1 s 未満。
- infra 120 の判定 (本 run の実測):

| 区分 | 件数 | size B | IAT 呼出 | 判定 |
|---|---|---|---|---|
| khbase lift 対象 (`snapins.json` `khbase.lift`) | 98 | 10,044 | 60 | 共有 (infra)。khbase の lift 集合に入る |
| khbase lift 対象外 | 22 | 10,671 | 0 | 共有 (infra)。khbase の lift 集合に入らない |
| 合計 | 120 | 20,715 | 60 | 全件が `closures_sets.pkl` の `infra` (188 件) に含まれる |

- 「共有か個別か」の根拠: 120 件はすべて `closures_sets.pkl` の `infra` (188 件) の部分集合 (本 run で確認: 120 / 120)。unique 25 は `infra` に 0 件 (重なり無し)。したがって process 専用の個別関数ではなく、snap-in 間で共有される基盤。内訳の khbase 対象 / 対象外は、khbase の lift 集合に入るかどうかの区分。

## 3. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 20 関数の bit-exact (native vs wasm) | 受入 1 の検証 | #4863 (親) の受入 1 |
| 未 lift の infra callee 5 件 (stub) の lift | wasm 実行時に `abort` | 親 #4863 の残作業 (infra 側の判定) |
| 5 アドレスの扱い (jmp 先。関数入口ではない。共有部か単独関数かは未判定) | 受入 1 の残り 5 件 | 親 #4863 の関数入口の定義 |
| khbase 対象外の 22 件 (10,671 B) の lift 方針 | infra 側の判定 | 親 #4863 の残作業 |
| slot 7・13 が native scenario で呼ばれるか | process 以外の呼出経路 | #5377 (KH-155) と KH-130 |

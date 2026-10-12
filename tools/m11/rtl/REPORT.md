# m11/rtl REPORT — Delphi RTL の範囲確定と lifter 別 liftdiff 採点 (#129)

**判定: 部分達成 (受入条件は未達 → Refs)**。RTL 範囲の確定と、RetDec route (m11) / x64c route (flelift) の RTL 帯 1,172 関数の
同一条件採点までを実測した。「RTL 関数が native と一致」「m11_ov.c の RTL 手転記を撤去」は未達 (§4)。
OSS 差替え案 (b) は toolchain 選定の判断が要るため未着手 (§5)。

関係: #132 (stage 5/6) は #129 (RTL) / #130 (override) / #90 (間接 call) の成果取込みが前提。#253 (tools/flelift/boot) は
案 (a)「別 lifter で再 lift」を x64c で既に実施済み (RTL 専用 lifter は作らず FLEngine 全体を x64c で lift)。本書はその RTL 帯だけを切り出して測った。

## 1. RTL の範囲 (実測)

`rtl_range.py` = `.text` から tkClass typeinfo を走査し、ClassType(VMT) の `[VMT-0xa8]==typeinfo` で相互確認して `UnitName` を引く
(2,958 クラス / 527 unit が全件相互参照一致。結果 `results/rtl_units.json`)。

| unit (VMT 範囲) | クラス数 |
|---|--:|
| System `0x401a38..0x404740` | 11 |
| System.Types `0x41fd40..0x41ffd0` | 2 |
| System.SysUtils `0x42db78..0x438108` | 58 |
| System.VarUtils / Variants / TypInfo `0x456e98..0x4719b8` | 3 / 15 / 24 |
| System.Hash / Generics.Defaults / SyncObjs `0x4743d8..0x4825f8` | 1 / 6 / 6 |
| System.Rtti `0x482e08..0x4ba120` | 57 |
| System.Classes `0x4c86b8..0x52ea50` | 73 |
| System.WideStrings / Contnrs `0x53e698..0x544388` | 3 / 3 |
| FL 側の最初の unit (AudioPlayer) `0x545a90` | 1 |

RTL コードの帯は **`0x401000`〜`0x545000` 付近** (FL 固有 unit の最初の VMT が 0x545a90)。VMT は unit の code 内にあるため、unit 境界は
VMT 先頭からの近似でしかない (code の厳密な開始/終了は未確定)。`System.Generics.Collections` / `System.Generics.Defaults` は
VMT が 0x136e828 / 0x5279a0 まで散る (原因は未調査) ため、帯は VMT 範囲でなく code 帯で見る。
FastMM4 のクラスは本走査に出ていない (FastMM_GetMem `0x407a50` / FreeMem `0x409440` は System 帯 `0x401000..0x41fd40` の内側)。
InitTable `0x13768b0` は 942 unit。

## 2. 採点 (liftdiff, RTL 帯 `0x401000`〜`0x456e98` = System/Types/SysUtils の 1,172 関数)

両 route に同一 VA 集合・同一パターンを与えた (`batch --set file:`)。boot 状態は m11 = units 22 / flelift = hybrid 928 unit
(`bootstate --mode hybrid`; 素材 snapshot の flelift boot_state は 17 unit の旧版だったため作り直した)。突合: `rtl_compare.py` → `results/rtl_compare.md` / `rtl_verdicts.tsv`。

| route | 一致 | 不一致 | 実行不能 | 自己欠陥確定 (leaf) |
|---|--:|--:|--:|--:|
| m11 (RetDec) | 486 | 537 | 149 | 219 |
| flelift (x64c) | 535 | 125 | 512 | 17 |

* 実行不能 512 の内訳 (x64c): **`no_wasm_definition` 359** (x64c が lift していない = lift 集合 7,031 関数の外。RetDec 側では 270 一致 / 89 不一致で採点できている) / native_fault 79 / native_null_deref 52 / unsupported_sig 11 / hang 11。
  比較可能同士で見る必要がある: **両 route とも採点可能な 643 関数で m11 不一致 429 → x64c 不一致 124** (遷移: 不一致→一致 312 / 一致→一致 207 / 不一致→不一致 117 / 一致→不一致 7)。
* x64c で不一致の主因 (主因タグ): callee_divergence 42 / import_call_seq 19 / zero_init_drop 16 / callsite_arg_drop 14 / unlifted_callee 12 / memory_semantics 7。m11 は callee_divergence 180 / import_arg_diff 92 / memory_semantics 56 / callsite_arg_drop 48 / icall_drop 34 / wasm_trap 34。
* 一致→不一致 7 関数 (0x42d830 / 0x44a590 / 0x4511d0 / 0x41cd70 / 0x412020 / 0x455650 / 0x4090e0): 主因は callee_divergence 4 / unlifted_callee 2 / memory_semantics 1。callee 起因が多く自身の欠陥とは限らないが、個別調査はしていない。
* m11_ov.c の RTL 手転記関数 (7 本) の x64c 側: `_UStrAsg 0x4133f0` は **一致** (m11 は不一致)。参考: #122 が原因と特定した `Move 0x409c80` も x64c は一致 (m11 は不一致。m11_ov.c には無い)。
  `InitUnits 0x4120c0` は m11 一致だが x64c は実行不能 (native_null_deref。x64c route は boot override `fle_ov_initunits` で置換)、`_InitLib 0x412160` / `_StartLib 0x41d8f0` / `0x412510` / `Halt 0x412770` は
  **両 route とも実行不能** (native 単体実行が不能 = 関数単位差分では判定できない)、`0x450560` (SysUtils) は x64c でも不一致 (unlifted_callee)。

## 3. survey (unit 初期化) の trap 数 (他 REPORT の実測の引用; 本 run では再実行していない)

`tools/flelift/boot/REPORT.md` / #253 (FLE-3, commit `ac5d6d4`): 942 unit 隔離 survey は **ok 888 / oob 2 / unlifted 5 / trap 0 / halt0 0**
(m11 baseline: ok 800 / oob 50 / halt0 44 / closure 外 46 / abort 1)。boot 連鎖は 209 unit まで進む (m11 は 17)。x64c route の手転記 override は
`fle_ov_{longjmp,getmem,freemem,initunits}` の 4 つ (m11 route の m11_ov.c は RTL 手転記 + `m11_icall` 等)。

## 4. 受入条件との対応

| 受入条件 | 判定 | 根拠 |
|---|---|---|
| RTL の VA 範囲確定 | 達成 (近似) | §1。unit の code 境界は未確定 |
| (a) 別 lifter で RTL 再 lift | 達成 (x64c; #253) | RTL のみでなく FLEngine 全体 |
| 差替え後 survey の trap 数が減る | 達成 (他 REPORT 値) | §3: trap/halt0/oob 合計 95 → 7 (非 ok, empty/noproc 除く)。本 run で未再現 |
| RTL 関数が liftdiff で native と一致 | **未達** | §2: 一致 535 / 1,172。不一致 125・実行不能 512 (うち 359 は未 lift) |
| m11_ov.c の RTL 手転記を撤去できる | **未達** | m11 route は RetDec のままで、ov は m11 route 内の補修。撤去には m11 route を x64c に置換する必要がある (= #253 の方向) |
| (b) OSS から RTL を wasm ビルド | 未着手 | Delphi/FPC の toolchain 選定にユーザ判断が要る (m11 REPORT §6 から変更なし) |

## 5. 未解決・次の一手

1. **x64c 側 `no_wasm_definition` 359 関数 (RTL 帯)**: 既存 closure (7,421 関数) のうち x64c が lift していない。RetDec 側は 270 一致で採点できるため、
   x64c 側の lift 集合に足せば採点対象になる (足した結果の一致数は未測定)。tools/flelift 側の作業 (本 run は tools/flelift を読取のみとした)。
2. **x64c 不一致 125 の個別化**: 自己欠陥確定は 17。残りは callee 起因 (callee_divergence 42 / unlifted_callee 12 ほか) のため、leaf から順に。
3. **実行不能 (native_fault / null_deref 計 131)**: boot 状態に依存する関数 (`_InitLib`・`0x412510`・`0x4123c0` 等)。#234 の native 全起動で状態を足す。
4. **(b) OSS 差替え**: 採否は toolchain 選定 (Delphi / FPC の可否) で、ユーザ判断が要る。本 run では未調査。

## 6. 再現

```sh
export FL_WIN64_DIR=<fl-win64 の展開先> PATH=/opt/emsdk/upstream/bin:$PATH   # work-m11 / work-liftdiff を tools/*/work に展開
uv run --with pefile python tools/m11/rtl/rtl_range.py $FL_WIN64_DIR/extracted/block00031_PE.bin --json tools/m11/rtl/results/rtl_units.json
# RTL 帯 VA (0x401000..0x456e98) を m11_closure_verdicts.tsv から抜いて /tmp 等に保存 → liftdiff:
cd tools/liftdiff
uv run --with numpy --with capstone --with pefile python3 liftdiff.py bootstate targets/flelift.json --mode hybrid --nobuild
uv run --with numpy --with capstone --with pefile python3 liftdiff.py batch targets/m11.json    --set file:<VA 一覧> --shards 4 --nobuild --state auto --out work/m11/batch_rtl_core.jsonl
uv run --with numpy --with capstone --with pefile python3 liftdiff.py batch targets/flelift.json --set file:<VA 一覧> --shards 4 --nobuild --state auto --out work/flelift/batch_rtl_core_h928.jsonl
cd ../.. && python3 tools/m11/rtl/rtl_compare.py tools/m11/rtl/results/rtl_units.json tools/liftdiff/work/m11/batch_rtl_core.jsonl tools/liftdiff/work/flelift/batch_rtl_core_h928.jsonl --md tools/m11/rtl/results/rtl_compare.md --tsv tools/m11/rtl/results/rtl_verdicts.tsv
```

素材 snapshot 内 `/home/ubuntu/...` ハードコード (`work/flelift/build.json` の wasm パス等) は `--nobuild` のため未参照で、symlink は不要だった
(tools/m11/work, tools/liftdiff/work は main の checkout 側 work/ への symlink とした; `.git/info/exclude` で commit 対象外)。

## 7. 実測 (GitHub Actions runner, 4 core)

| 項目 | 実測 |
|---|---|
| `rtl_range.py` | 2,958 クラス / 527 unit (実行は数秒) |
| `bootstate flelift --mode hybrid --nobuild` | 12.2 秒, units_run 928/942, first_fail 830 |
| `batch m11` (1,172 関数, 4 shard) | 2 分 28.5 秒, load 2.28 |
| `batch flelift` (1,172 関数, 4 shard; 17 unit 旧 boot 状態) | 1 分 28.5 秒 (参考: 結果 一致 542 / 不一致 130 / 実行不能 500。本書の表は 928 unit 状態) |
| `batch flelift` (1,172 関数, 4 shard; 928 unit 状態) | 3 分 12.0 秒 |

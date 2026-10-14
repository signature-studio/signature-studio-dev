# m11/rtl REPORT — Delphi RTL の範囲確定と lifter 別 liftdiff 採点 (#129)

**判定: 部分達成 (受入条件は未達 → Refs)**。RTL 範囲の確定と、RetDec route (m11) / x64c route (flelift) の RTL 帯 1,172 関数の
同一条件採点までを実測した。「RTL 関数が native と一致」「m11_ov.c の RTL 手転記を撤去」は未達 (§4)。
OSS 差替え案 (b) は toolchain 選定の判断が要るため未着手 (§5)。

既知類型との関係: 該当なし (`docs/DEFECTS.md` D1〜D16 のいずれの新規発見でもない。本書は採点と範囲確定で、lift 欠陥の新類型は見ていない。
主因タグの callee_divergence 等は liftdiff の分類名で DEFECTS.md の ID ではない)。
検証起点 commit: `e56e176` (初回採点と §7 の n=3 再実行・ネガコンはこの tree 上で実施。以後の変更は docs / 本 REPORT / `negctl.sh` / `rtl_runs_summary.py` / `results/*.txt` の追加と、レビュー指摘対応 `ff28834` (`rtl_range.py` の ImageBase 化・`rtl_compare.py` の RTL 帯フィルタと `--md` 先頭行) のみ。`ff28834` は採点値 (`results/rtl_units.json` / `rtl_verdicts.tsv`) を変えない — §7-4)。

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

RTL コードの帯は **`0x401000`〜`0x545000` 付近** (FL 固有 unit の最初の VMT が 0x545a90)。ただし **§2 で採点したのは
`0x401000`〜`0x456e98` (System / System.Types / System.SysUtils) の 1,172 関数だけ**で、`0x456e98`〜`0x545000`
(System.VarUtils / Variants / TypInfo / Hash / Generics.Defaults / SyncObjs / Rtti / Classes / WideStrings / Contnrs) は**未採点** (範囲外)。
VMT は unit の code 内にあるため、unit 境界は VMT 先頭からの近似でしかない (code の厳密な開始/終了は未確定)。`System.Generics.Collections` / `System.Generics.Defaults` は
VMT が 0x136e828 / 0x5279a0 まで散る (原因は未調査) ため、帯は VMT 範囲でなく code 帯で見る。
FastMM4 のクラスは本走査に出ていない (FastMM_GetMem `0x407a50` / FreeMem `0x409440` は System 帯 `0x401000..0x41fd40` の内側)。
InitTable `0x13768b0` は 942 unit。

## 2. 採点 (liftdiff, RTL 帯 `0x401000`〜`0x456e98` = System/Types/SysUtils の 1,172 関数)

両 route に同一 VA 集合・同一パターンを与えた (`batch --set file:`)。boot 状態は m11 = units 22 / flelift = hybrid 928 unit
(`bootstate --mode hybrid`; 素材 snapshot の flelift boot_state は 17 unit の旧版だったため作り直した)。突合: `rtl_compare.py` → `results/rtl_compare.md` / `rtl_verdicts.tsv`。

以下の表・数値は **commit 済み `results/` (初回 run = 検証起点 e56e176 での採点) の値**。batch は**セッション (別の Actions run) 間で値が動く**
(同一セッション内の n=3 では 1,172 関数とも不変)。レンジは §7 を正とし、書き分けは次のとおり:

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

| 未解決 | 影響 | 起票先 |
|---|---|---|
| x64c 側 `no_wasm_definition` 359 関数 (RTL 帯): 既存 closure (7,421 関数) のうち x64c が lift していない。RetDec 側は 270 一致で採点できるため、x64c の lift 集合に足せば採点対象になる (足した結果の一致数は未測定。tools/flelift 側の作業で、本 run は tools/flelift を読取のみ) | 受入条件「RTL 関数が native と一致」が 1,172 中 535 で止まる主因 | #410 (受入条件 1 つ目) |
| x64c 不一致 125 の個別化: 自己欠陥確定は 17。残りは callee 起因 (callee_divergence 42 / unlifted_callee 12 ほか) のため leaf から順に。一致→不一致の退行 (初回 7 / 再実行 5。§7) の原因特定を含む | 同上 (不一致 123–125。§7) | #410 (受入条件 2 つ目) |
| batch のセッション間変動 (x64c 18 関数・m11 10 関数が commit 済み TSV とずれる; §7)。原因 (native 側の状態・タイミング・環境差のいずれか) は未調査 | 一致数の増減を 1 run で評価すると誤る | #410 (コメント済み: 原因切り分けを一致数評価の前に行う / n>=3 min–max で比較) |
| 実行不能 (native_fault / null_deref 計 131) 関数: boot 状態に依存する関数 (`_InitLib`・`0x412510`・`0x4123c0` 等)。native 側の状態を足す必要がある | 関数単位差分で判定不能 | #235 [LD-4] (liftdiff 実行不能の被覆拡大)。#234 は CLOSED のため引継ぎ先にしない |
| (b) OSS 差替え: 採否は toolchain 選定 (Delphi / FPC の可否) で、ユーザ判断が要る。本 run では未調査 | #129 の案 (b) が未着手のまま | #441 (`needs-user-input`) |
| RTL 帯の未採点範囲 `0x456e98`〜`0x545000` (VarUtils / Variants / TypInfo / Rtti / Classes 等) の採点 | RTL 全体の一致率は不明 (§1) | #410 (コメントで追記済み) |

## 6. 再現

```sh
export FL_WIN64_DIR=<[WIN64] の展開先> PATH=<[EMSDK]>/upstream/bin:$PATH   # work-m11 / work-liftdiff を tools/*/work に展開
uv run --with pefile python tools/m11/rtl/rtl_range.py $FL_WIN64_DIR/extracted/block00031_PE.bin --json tools/m11/rtl/results/rtl_units.json
# RTL 帯 VA (0x401000..0x456e98) を m11_closure_verdicts.tsv から抜いて <VA 一覧> (1 行 1 VA) に保存 (`results/rtl_verdicts.tsv` の 1 列目と同一) → liftdiff:
cd tools/liftdiff
uv run --with numpy --with capstone --with pefile python3 liftdiff.py bootstate targets/flelift.json --mode hybrid --nobuild
uv run --with numpy --with capstone --with pefile python3 liftdiff.py batch targets/m11.json    --set file:<VA 一覧> --shards 4 --nobuild --state auto --out work/m11/batch_rtl_core.jsonl
uv run --with numpy --with capstone --with pefile python3 liftdiff.py batch targets/flelift.json --set file:<VA 一覧> --shards 4 --nobuild --state auto --out work/flelift/batch_rtl_core_h928.jsonl
cd ../.. && python3 tools/m11/rtl/rtl_compare.py tools/m11/rtl/results/rtl_units.json tools/liftdiff/work/m11/batch_rtl_core.jsonl tools/liftdiff/work/flelift/batch_rtl_core_h928.jsonl --md tools/m11/rtl/results/rtl_compare.md --tsv tools/m11/rtl/results/rtl_verdicts.tsv
```

`rtl_compare.py` は両 route の VA 積集合のうち RTL 帯 `0x401000 <= VA < 0x456e98` (定数 `RTL_LO` / `RTL_HI`) だけを採点し、帯外は stderr に件数を出して除外する
(上の `<VA 一覧>` を絞らなくても帯外が混ざらない)。`--md` の先頭 1 行は `自動生成: <cmd>` (`docs/DOC_MAP.md` §4)。

`tools/shared/env.sh` の既定 `ANALYSIS_DIR` (`docs/REFERENCES.md` `[ANALYSIS-DIR]`) 配下の `win64/` を `[WIN64]` の展開先へ向ける必要がある
(`ANALYSIS_DIR=<任意>` に `win64` symlink を作る)。これが無いと `bootstate` が PE 読込で FileNotFoundError になる。
素材 snapshot の `work/flelift/build.json` 等に埋まる絶対パスは `--nobuild` のため未参照。tools/m11/work, tools/liftdiff/work は
snapshot 展開先への symlink とし、`.git/info/exclude` で commit 対象外にした。

## 7. 実測 (GitHub Actions runner, 4 core)

### 7-1. 所要 (初回 run)

| 項目 | 実測 |
|---|---|
| `rtl_range.py` | 2,958 クラス / 527 unit (実行は数秒) |
| `bootstate flelift --mode hybrid --nobuild` | 12.2 秒, units_run 928/942, first_fail 830 |
| `batch m11` (1,172 関数, 4 shard) | 2 分 28.5 秒, load 2.28 |
| `batch flelift` (1,172 関数, 4 shard; 17 unit 旧 boot 状態) | 1 分 28.5 秒 (参考: 結果 一致 542 / 不一致 130 / 実行不能 500。本書の表は 928 unit 状態) |
| `batch flelift` (1,172 関数, 4 shard; 928 unit 状態) | 3 分 12.0 秒 |

### 7-2. 再現性 (batch はセッション間で動く)

後処理 (`rtl_range.py` / `rtl_compare.py`) は同じ入力 jsonl から同じ `results/` を出す。**batch 自体の結果は保証しない**。
「commit 済み results と cmp 一致」が保証するのは後処理だけで、batch の再現ではない。

同一入力 (RTL 帯 1,172 VA, `--shards 4 --state auto`) の観測 (一致/不一致/実行不能):

| 観測 | m11 | x64c | 両 route 採点可の遷移 (不一致→一致 / 一致→不一致) |
|---|---|---|---|
| 初回 run (e56e176, commit 済み TSV) | 486/537/149 | 535/125/512 | 312 / 7 (採点可 643) |
| reviewer 再実行 (e56e176) | 486/537/149 | 535/123/514 | 311 / 5 |
| 本 run 再実行 n=3 (bootstate hybrid 20.4 秒, first_fail 830, 同 928/942) | 494/529/149 を 3 回とも同値 | 535/123/514 を 3 回とも同値 | 308 / 5 を 3 回とも同値 (採点可 641) |

* **本 run の n=3 内では 1,172 関数のうち verdict が動いた関数は 0** (m11 / x64c とも)。揺れは**セッション間**にある。
* commit 済み TSV との差 (本 run n=3 の 1 回目 vs TSV, VA 単位): m11 10 関数 (不一致→一致 9 / 一致→不一致 1)、x64c 18 関数
  (一致→不一致 5 / 不一致→一致 5 / 不一致→実行不能 5 / 実行不能→不一致 3)。reviewer の報告は x64c で 20 関数。
  x64c の不一致→実行不能 5 は `native_fault_all_patterns` (native 側が失敗)。原因は**未調査** (環境・native 側の状態・タイミングのいずれかは未確定)。
* min–max (上の 3 観測): m11 一致 486–494 / 不一致 529–537 / 実行不能 149。x64c 一致 535 / 不一致 123–125 / 実行不能 512–514。
  本 run の実行不能内訳 (x64c, 3 回同値): no_wasm_definition 359 / native_fault 73 / native_null_deref 58 / unsupported_sig 11 / hang 13
  (初回は 359 / 79 / 52 / 11 / 11、reviewer は 359 / 73 / 57 / 11 / 14)。
* 本 run の x64c 一致→不一致 5 関数: 0x4090e0 / 0x41cd70 / 0x42d830 / 0x44a590 / 0x4511d0 (初回の 7 から `0x412020` / `0x455650` が外れる)。
* 本 run 所要 (4 shard, load は終了時の 1/5/15 分平均): batch flelift 154.6 / 153.2 / 151.4 秒 (load 2.90 / 3.64 / 3.02)、
  batch m11 114.9 / 114.7 / 116.2 秒 (load 2.46 / 2.60 / 2.41)。
* n=3 は `rtl_runs_summary.py` で集計 (`results/rtl_runs_summary.txt`)。3 回は同一セッション内の連続実行で、セッション間のレンジではない。

### 7-3. ネガティブコントロール (`negctl.sh`, `results/negctl.txt`)

`_UStrAsg 0x4133f0` の x64c verdict (match) を 1 件だけ `mismatch` に書き換えて `rtl_compare.py` を再実行した:

| 集計 | 元 | 書換え後 |
|---|---|---|
| x64c 一致/不一致/実行不能 | 535/123/514 | **534/124/514** |
| 遷移 不一致→一致 / 不一致→不一致 | 308 / 117 | **307 / 118** |
| TSV の差分 | - | 1 行 (`0x4133f0`: 列 x64c が match → mismatch) |

m11 側の集計 (494/529/149) は不変。書換え 1 件が集計に 1 件ぶん現れ、他の行は動かない (差分 1 行) ことを確認した。
(`negctl.sh` は本 run の n=3 の 1 回目 jsonl で実行。)

### 7-4. レビュー指摘対応 (`ff28834`) の検証 (batch は再実行していない)

採点値を変える変更ではないため batch (m11 / flelift) は再実行せず、後処理だけをコミット済み `ff28834` で検証した
(初回 batch の jsonl は commit されていないので、`results/rtl_verdicts.tsv` の `va` + 各 route の verdict から `function.va` / `verdict` だけの jsonl を復元して入力にした。
`rtl_compare.py` が読むのはこの 2 項目だけ)。GitHub Actions runner, 所要は `time`、load は終了時の 1 分平均 0.47:

| 検証 | 結果 |
|---|---|
| `rtl_range.py` (`B = pe.OPTIONAL_HEADER.ImageBase`; この PE は `0x400000`), 0.13 秒 | 2,958 クラス / 527 unit。`results/rtl_units.json` と `cmp` 一致、stdout も修正前と一致 (PASS) |
| `rtl_compare.py` を復元 jsonl (1,172 VA) で再生成, 0.03 秒 | `results/rtl_verdicts.tsv` は `cmp` 一致 (PASS)。`results/rtl_compare.md` は先頭 1 行 (`自動生成: <cmd>`) の追加のみで、本体は修正前と一致。再実行しても `cmp` 一致 |
| 帯フィルタ: 帯外を含む実 batch (snapshot の `batch_closure.jsonl` 7,421 関数 × 2 route) | 修正前は 7,421 関数をそのまま採点 (計 m11 2273/2892/2256・x64c 4182/741/2498)。修正後は帯外 6,249 を除外して 1,172 関数 (この snapshot の run での計 m11 574/427/171・x64c 540/116/516。§2 の表とは別 run の値で、比較には使わない) |
| 帯フィルタのネガコン: 復元 jsonl に `0x400fff` / `0x456e97` / `0x456e98` / `0x545a90` / `0x1000000` を追加 | 両 route 採点あり 1,177 → 1,173 (帯内は `0x456e97` のみ。上端 `0x456e98` は排他)。TSV の差分は `0x456e97` の 1 行だけ |
| `negctl.sh` (復元 jsonl): `_UStrAsg 0x4133f0` の x64c を mismatch に書換え | x64c 535/125/512 → 534/126/512、TSV 差分 1 行 (PASS) |

VA/RVA 変換の ImageBase 化は、`ImageBase` が `0x400000` の PE では出力が変わらないことの確認までで、別 ImageBase の PE での動作は確認していない (該当 PE が無い)。

## 8. x64c 側 lift 集合外 359 関数の分類 (#410 受入 1 つ目)

`thunk_classify.py` (PE 静的解析) で分類した。入力は commit 済みの `tools/liftdiff/results/flelift_closure_verdicts.tsv` (RTL 帯 `[0x401000,0x456e98)` の `no_wasm_definition` 359 件を抜き出したもの) と、`fl-win64` の `extracted/block00031_PE.bin`。`work-liftdiff` の batch jsonl は本 run では取得できなかったため使っていない。

| 分類 | 件数 | 根拠 |
|---|--:|---|
| import thunk (先頭 `FF 25` = `jmp [rip+IAT]`、1 命令) | **359** | 全件。PE 上の先頭 2 バイトが `FF 25` (`jmp [rip+disp32]`)。命令境界・call の有無・IR の有無は未確認 (batch 側の情報を本 run では使っていない) |
| その他 | 0 | - |

* 飛び先 IAT は **311 スロット** (呼出数: kernel32 165 / user32 120 / gdi32 53 / advapi32 13 / oleaut32 3 / version 3 / IMAGEHLP 1 / SHFolder 1。上位は `kernel32!FreeLibrary` ×4 など)。
* 同じ 359 件の m11 (RetDec) 側の採点は §2 の注記を正とする (測定値の二重記載を避けるため、ここには数値を書かない)。m11 は thunk を関数として扱える。
* 推定 (未検証): x64c は thunk を wasm 関数として定義せず、呼出側の `jmp [IAT]` を import 直呼びに置き換える (`x64c.py` の `thunks` 経路)。そのため thunk 自体は「定義なし」になる。**lift 集合に pass を足しても thunk 関数の採点は直ちには成立しない** (thunk 単体を比較するには、import 呼出 1 本の wasm 関数を生成する必要がある)。
* 結論: 受入条件「lift 集合外 359 の原因分類」は本節で達成。「lift 集合に pass を追加」は本 run では未着手 (tools/flelift の変更とリビルド・batch 再採点が要るため。起票先: #253 に継続 (未起票の新 issue は PM 判断))。
* 再現: `python3 tools/m11/rtl/thunk_classify.py <block00031_PE.bin> tools/liftdiff/results/flelift_closure_verdicts.tsv` (入力は TSV のみ。batch jsonl を入力にした結果は本 REPORT では主張しない)。

## 9. x64c 不一致の原因別分類 (#410 受入 2 つ目・分類まで; 修復は未着手)

入力は `work-liftdiff` 同梱の `flelift/batch_closure_hybrid.jsonl` (既存の batch 出力。batch は再実行していない) と、commit 済みの `results/rtl_verdicts.tsv` (§7-2 の x64c 列)。その 7,421 行の jsonl から RTL 帯 1,172 関数を抽出する。
集計は `classify_x64c_mismatch.py <batch.jsonl> <rtl_verdicts.tsv>`、件数・主因・全タグ・TSV とのクロス表・退行候補 7 件の状態は `results/x64c_mismatch_classify.txt` が正本。

* 結論: RTL 帯 1,172 関数の batch 判定 = 一致 540 / 不一致 116 / 実行不能 516。
* 件数の出所 (混同を避けるため): 「一致 535 / 不一致 125 / 実行不能 512」は `results/rtl_verdicts.tsv` の x64c 列 (§2 の表と同じ)。batch 判定はこれと一致しない (TSV と batch の差は results txt のクロス表)。`results/flelift_closure_verdicts.tsv` を同じ帯で数えると 563 / 79 / 530 で、これは本節では使わない。
* 退行候補 (一致→不一致) 7 件の定義: `rtl_verdicts.tsv` で m11 = match かつ x64c = mismatch (`rtl_compare.py` の遷移と同じ)。batch 側の status は mismatch 5 (`0x4090e0` / `0x41cd70` / `0x42d830` / `0x44a590` / `0x4511d0`) と unexec 2 (`0x412020` / `0x455650`)。batch で不一致になったのは 5 件のみ。
* 検証状態: `work-liftdiff` 同梱 jsonl で再実行し、results txt と diff 0 行 (再実行 run: 38429463570)。入力 jsonl: sha256 = `d9995bfa90d96266f56f246f7e398809895c9f003ea225a2ec7d10799f6e0e6b`、7,421 行。
* 未達: 上位の原因からの修復 (受入 2 後半)・ネガコン付きの一致数増加 (受入 3)・一致→不一致の退行 7 件の原因特定。修復には tools/flelift の変更とリビルド・batch 再採点が要るため、起票先は #410 に継続 (本 PR は分類まで)。

### 9-1. 退行 7 件の jsonl 上の手がかり (#410 受入 2 後半; 原因は未確定)

jsonl の該当レコードを読んだ結果 (`batch_closure_hybrid.jsonl`、batch 再実行なし)。確定ではなく、次に検証すべき仮説として扱う。取得元は `work-liftdiff` 同梱 `tools/liftdiff/work/flelift/batch_closure_hybrid.jsonl` の行番号 (1 始まり)。各行の抽出は `sed -n '<行>p' batch_closure_hybrid.jsonl | python3 -m json.tool` で行う。

| va | jsonl 行 | batch 判定 | 主なタグ | jsonl 上の手がかり |
|---|---|---|---|---|
| `0x4090e0` | 24 | mismatch | memory_semantics | image 領域の書込み集合が native と wasm で不一致 |
| `0x41cd70` | 85 | mismatch | unlifted_callee, wasm_trap | wasm が lift 閉包外の間接 call 63 件を ret-0 で継続し、OOB trap |
| `0x42d830` | 165 | mismatch | callee_divergence | trace #2 で native 側だけ `0x412d60` に入る (native_extra_entry) |
| `0x44a590` | 192 | mismatch | callee_divergence, unlifted_callee | trace #2 で native `0x415c30` / wasm `0x40faa0`。wasm 側が lift 閉包外の間接 call 18 件を ret-0 で継続 |
| `0x4511d0` | 210 | mismatch | callee_divergence, unlifted_callee | trace #3 で native `0x4103c0` / wasm `0x40faa0`。閉包外の間接 call 9 件 |
| `0x412020` | 68 | unexec | (none) | 差分なし (実行不能) |
| `0x455650` | 217 | unexec | (none) | 差分なし (実行不能) |

* 観測: `0x44a590` と `0x4511d0` は、wasm の入口がどちらも `0x40faa0` に収束している。`work-liftdiff` 同梱 `tools/liftdiff/work/flelift/fle_lifted_tr.c` (生成行 69926 付近) で `0x40faa0` は `0x44a505` から直接 call されており (`call 0x40faa0`)、native 側の呼出先 (`0x415c30` / `0x4103c0`) と一致しない。仮説: x64c の間接 call 解決が、同じ呼出し点でも対象を取り違えている。未検証。
* 2 件 (`0x412020` / `0x455650`) は unexec のため、batch の差分からは原因を取れない。
* 次の一手 (本 run では未実施): 退行 5 件を単独で再採点し、trace 差分の入口 (`0x40faa0`) の間接 call 解決を確認する。修復は tools/flelift の変更が要るため #410 に継続。

### 9-2. 退行 7 件の単独再採点 (n=3、実測)

§9-1 の 7 件を単独 batch で 3 回採点した (帯 batch の再実行は未実施)。m11 列は commit 済み `results/rtl_verdicts.tsv` の値 (再採点していない)。

* 実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 liftdiff.py batch targets/flelift.json --set file:work/regr7/va7.txt --shards 4 --nobuild --state auto --out work/regr7/r{1,2,3}.jsonl` (`va7.txt` は 7 件の VA 一覧、1 回 8〜9 秒、load は未記録)。
* 生 jsonl: `r1`・`r2`・`r3` とも sha256 `34f5803f44b97c62d5f6beeb536da8ec2ba31dd82ab3590e009436c1d9592743` (3 つは同一内容)、各 7 行。`work/` (gitignore) に置き commit しない。
* 集計: `python3 rerun_regression7.py --out results/x64c_regression7_rerun.tsv r1=... r2=... r3=...` → `results/x64c_regression7_rerun.tsv`。

| va | m11 (commit 済み) | 同梱 batch | 単独 r1 / r2 / r3 | 判定 |
|---|---|---|---|---|
| `0x4090e0` | match | mismatch | mismatch / mismatch / mismatch | 退行 (実在) |
| `0x41cd70` | match | mismatch | mismatch / mismatch / mismatch | 退行 (実在) |
| `0x42d830` | match | mismatch | mismatch / mismatch / mismatch | 退行 (実在) |
| `0x44a590` | match | mismatch | mismatch / mismatch / mismatch | 退行 (実在) |
| `0x4511d0` | match | mismatch | **match / match / match** | batch 依存の疑い (単独では退行しない) |
| `0x412020` | match | unexec | **mismatch / mismatch / mismatch** | 退行 (実在)。batch では実行不能で検出されていなかった |
| `0x455650` | match | unexec | **match / match / match** | 非退行 (単独では一致)。batch の unexec は batch 依存 |

* 結論: 退行は 5 件 (`0x4090e0` / `0x41cd70` / `0x42d830` / `0x44a590` / `0x412020`) が単独 n=3 で再現した。`0x4511d0` と `0x455650` は単独では一致で、batch の判定と食い違う (§7-2 の batch 揺れと同種の疑い。原因は未切り分け)。
* 含意: 「一致→不一致の退行 7 件」は 5 件に縮んだ。`0x4511d0` / `0x455650` の食い違いは、同居関数・batch の shard 配置・state の影響のいずれかで、未検証。
* 未実施: 帯 batch 1 回の再採点 (§9-3 の時点では未実施)。

### 9-3. `0x44a590` の分岐点の確認 (仮説「間接 call 解決の取り違え」は棄却)

§9-1 の仮説を、生成 C と元 PE のバイト列で確認した (batch 再実行なし)。

* `0x44a505` は元 PE で `e8 96 55 fc ff` (直接 `call rel32`、飛び先 `0x40faa0`)。生成 C の `f_40faa0()` と一致し、取り違えではない。
* native の分岐点は `0x44a4db` の vtable dispatch (`call qword ptr [rbx-0x28]`)。native はここで `0x415c30` に入る (trace #2)。
* wasm の trace 先頭は `0x44a590 → 0x44a4b0 → 0x40faa0` で、`0x44a4db` の dispatch を通らず `0x44a505` の直接 call に進む。`0x415c30` は lift 済み (`f_415c30` あり) なので、lift 集合外が原因ではない。
* 残る仮説: wasm 側で `0x44a4d8` の `mov rbx, [rax]` の読み値が 0 になり、`0x44a4db` の `ott_dispatch` が `ott_unlifted` (ret 0) に落ちる (evidence「last 0x0」と整合)。ただし読み値の実測は未取得 (wasm 再ビルドと probe が要る)。次の着手点はここ。
* 含意: 「`0x40faa0` 入口の間接 call 解決の取り違え」は、`0x44a505` については否定された。`0x4511d0` (同じ `0x40faa0` 収束) も同種として扱えるかは未検証。

### 9-5. vtable `0x42f670` の native/wasm 実測 (#1936・分割移動先 `REPORT_APPENDIX_1936.md`)

* 結論: native は hybrid boot 後も vtable が PE 初期値 (`0x449380` 等)。wasm は fresh・boot_state 適用後とも 0。`fle_data_install` は呼ばれている (`--init=`)。敷設窓の直接確認 (生成済み `fle_data.c`) は未了。詳細は付録。

### 9-4. `0x44a4d8` の wasm 実測 (#1721; 仮説の一部を棄却)

wasm 側で `0x44a4d8` 周辺の値を probe で実測した (`0x44a4b0` 入口 → `0x44a4db` dispatch 直前)。検証 commit: `main` (576c4976) 上の `tools/liftdiff/work/flelift/` (work-liftdiff 同梱) から派生。

* probe の方法: `fle_lifted_tr.c` のコピーに `ld_fle_probe(tag, v)` を挿入し、`fle_ldbridge.c` のコピーに同関数 (`ld_trace_rec` で `va=0xBEEF..|tag` として記録) を足して `lifted.o`・`bridge.o` だけ再コンパイルした。リンクは `clift.py` と同じフラグ。出力は `tools/liftdiff/work/flelift_probe/` (gitignore、commit しない)。素材の `ld_wasm.cjs` は変更していない。
* 実行: `liftdiff.py run <flelift_probe target> --fn 0x44a590 --pattern p0 --nobuild` (1 case 約 6 秒)。

| probe | 実測値 (wasm) | 意味 |
|---|---|---|
| `[0x15ec5d0]` (ガード) | `0x1e519c0` | 非 0。`je 0x44a4e9` を取らず `0x44a4d8` の分岐に入る |
| `rax` (= `[0x15ec5d0]`) | `0x1e519c0` | |
| `rbx` = `[rax]` (vtable ポインタ) | `0x42f698` | **0 ではない**。仮説「`[rax]` が 0」は棄却 |
| `[rbx-0x28]` (dispatch 先) | `0x0` | `ott_dispatch(0)` → `ott_unlifted` (ret 0) |
| vtable `[0x42f670..0x42f6a0]` (6 slot) | **すべて 0** | PE 上の初期値は `0x449380`・`0x4493a0` 等の有効値 (PE 静的読み) |

* 結論 (wasm 実測): 分岐は「`[rax]` = 0」ではなく、「vtable 本体 (`0x42f670` 付近) が実行時に 0」で `ott_dispatch(0)` に落ちる。原因は vtable の書込み欠落の疑い。
* 根拠の補足: `work/flelift/boot_state.json` の image 書込み run (60 本) に `0x42f670..0x42f6b0` を覆うものは無い。つまり hybrid boot の image 状態では、この vtable は PE の初期値に戻っていない (未書込み扱いで 0)。
* 未確定 (次の着手点): (1) native 側で同じ VA が PE 初期値 (`0x449380`) のままか。native は同じ入口で `0x415c30` に入るので、native の実行時メモリでは vtable が有効なはず。(2) 0 になる原因 (boot の image 書込み経路・heap/image の復元・`ld_w_fix` 等のどれか) の特定。(3) 退行 5 件のうち、同じ vtable 欠落で説明できるものの列挙 (未実施)。

受入条件との対応 (#1721): (1) 読み値の実測 = 達成 (上表)。(2) 仮説の成否 = 部分 (`[rax]` 仮説は棄却、vtable 0 は確定、原因は未特定)。(3) 退行 5 件の列挙 = 未実施。(4) 修復 = 範囲外。

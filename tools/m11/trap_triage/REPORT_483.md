# #483: oob→halt0 になった 12 unit の Error() 原因 = TDictionary の比較器チェーン脱落と修復

**判定: 受入条件 3 件達成。** 検証起点 commit: `m11_ov.c` は `d307abd` から不変 (base = PR #481 HEAD `dd9ba2c`)。
12 unit のうち **9 unit が ok に復帰** (halt0→ok)、残り 3 unit (53 / 56 / 898) は原因を特定して未解決に残した (§6)。
`Error()` の直接の呼出元は 11 unit が `411d20 ← 411e80 ← 8cc190` (= `TDictionary.Add` の「重複キー」例外)。
**例外は本物ではなく、比較器 (IEqualityComparer) の取得・呼出しが 3 箇所で壊れた結果の偽の重複判定**だった。

既知類型との関係 (`docs/DEFECTS.md`): **D4 (DEFECTS.md)** 再発 (`479b40` の TypeInfo.Kind byte 読出し脱落)、
**D15 (DEFECTS.md)** 再発 (`479b40` の `call rax`、`8cbda0` の `call [vt+0x20]`、`8cbce0` の `call [vt+0x18]`)。
加えて新規類型案 2 件 (§7): 「引数 pass-through 脱落」(`8cbda0` / `411e80`)、「vtable・データ表経由でしか到達しない関数が closure 外」
(比較器 getter / メソッド。#474 の `40fb40` と同根)。

## 1. Error() 呼出元の分類 (実測)

#481 HEAD (`dd9ba2c`) の survey (`survey_units.mjs` → `annotate.py`、halt0 32 unit) を `Error()` (`409730` / `412a60`) の直上 frame で分類:

| Error() 呼出元 | unit 数 | 3 段上の呼出元 | 原因類型 |
|---|--:|---|---|
| `411d20` (= RaiseExcept(nil) → `Error(216)`) | 16 | `411e80 ← 8cc190` 11 / `← 814d30` 3 / `← 45a2a0` 1 / `← b41bb0` 1 | **11 件は本 issue (§2)**。他 5 件は §6 |
| `40a1c0` | 8 | `40c1d0 ← …` | 未調査 (898 を含む) |
| `4159e0` / `416db0` | 4 / 3 | `415b10 ← 4170c0` ほか | 未調査 (#447 側) |
| `412770` (Halt0 自身) | 1 | unit 114 | #474 の既知 |

issue の 12 unit (#481 で oob→halt0 になった) = `8cc190` 経由 11 (53, 54, 56, 58, 59, 60, 61, 62, 63, 307, 311) + `40a1c0` 経由 1 (898)。
独立計数: `function_411e80` を呼出し回数を数える版 (`negctl_483.sh raise_head`) で **survey 中の `411e80` 呼出し = 16 回** (上表 411d20 の 16 unit と一致)。

## 2. 原因 (実測 + 逆アセンブル突合)

`8cc190` = `TDictionary.Add(key, value)`: `Grow → hash = 8cbda0 → idx = 8cbce0(Find) → idx >= 0 なら EListError を 448ee0 で生成して 411e80 (RaiseExcept)`。
unit 53 以降の初期化は `8c7a10` (レジストリ登録) から `[registry+0x410]` の辞書に TClass をキーに Add する。2 個目の Add が必ず「重複」と判定された。

| 観測 (`probe_8cc190.c`, `negctl_483.sh probe_head`) | 値 |
|---|---|
| Add 呼出し回数 / 重複判定 (idx >= 0) | 12 / **11** (最初の 1 回だけ空表で通過) |
| FComparer (`[dict+0x18]`) | 12 回とも `0x78b10` = **getter 関数 `478b10` 自身のコード番地** (本来は比較器オブジェクト) |
| `[FComparer]` の先頭 qword | `0xf883d08928ec8348` = 機械語 (`48 83 ec 28 89 d0 83 f8`) |
| hash | 12 回とも定数 `0x28ec8349` (= その qword の下位 32bit + 1) |

壊れている 3 箇所 (いずれも IR `boot_final3.ll` と `disasm_img.py` の機械語を突合):

| 関数 | 機械語 | RetDec 出力 | 類型 |
|---|---|---|---|
| `479b40` (`_LookupVtableInfo(intf, info, size)`) | `movzx rcx, byte [rbx]` (TypeInfo.Kind)・`test cl,2; call rax` (getter 呼出し) | Kind を `xor 0,0` (= 0 固定)、getter 呼出し脱落 | D4 + D15 |
| `8cbda0` (GetHashCode) | `call [vt+0x20]` (rdx = key を渡す) | 呼出し脱落、**key が唯一の使用者を失い IR 署名から消えて 1 引数** → hash = `[FComparer]+1` | D15 + 引数脱落 |
| `8cbce0` (Find) | `call [vt+0x18]` (Equals) → `test al,al` | 呼出し脱落、`al` = `[FComparer]` 下位 byte (≠0) → 常に「等しい」 | D15 |

`53df80` (`TEqualityComparer<TClass>.Default`) は `479b40(1, TypeInfo@0x13c0, 8)` を呼ぶ。TypeInfo.Kind = 19 (tkClassRef) の表項は
`flags=0, data=0xfb2bf0` (静的な比較器実体) なのに、Kind=0 固定の項 (`flags=2, data=478b10`) を引き、`call` が無いため getter の番地がそのまま FComparer になった。

さらに **`411e80` (RaiseExcept(obj)) 自体も壊れている**: IR は `411d20(0, arg1, 0)` で、obj を rdx に入れ rcx を 0 にしている
(機械語は rcx = obj を素通し、rdx = 戻り番地)。このため lift 上は**全ての `raise` が `Error(216)` (obj = nil) → Halt0** になる。
本 PR では `411e80` を直していない (§5: raise が起きた unit を trap のまま残す = 異常の検出信号を保つため)。

## 3. 修正 (`tools/m11/m11_ov.c`、逆アセンブルと突合した C 転記)

| 関数 (VA) | 内容 |
|---|---|
| `function_479b40` | 表 `LVA 0xfb2c28 + intf*0x170 + Kind*16` を正しく引き、`flags&2` で getter を `m11_icall`、`flags&1` で `4781a0` |
| `ov_dict_hash` (`8cbda0` 相当) | key を取り `GetHashCode` を `m11_icall` (`[FComparer.vt+0x20]`)。IR 署名を変えないよう呼出元 `8cc190` / `8cbde0` も転記 |
| `function_8cbce0` | Find: Equals を `m11_icall` (`[vt+0x18]`) |
| `function_8cc190` / `function_8cbde0` | Add / GetItem (EListError 生成 → `411e80` の経路は IR と同じ) |
| closure 外の getter (`disp_find` の追加 switch) | `478420` (tkInteger/Enumeration)・`478540` (tkInt64, IComparer)・`478c70` (tkRecord/MRecord、`471310` 相当の `ov_rec_kind` 込み) |
| closure 外の比較器メソッド | `479b00` (Equals = `cmp rdx,r8`)・`479b10` (GetHashCode = FNV-1a(8B, seed `0x811c9dc5`)、`475ba0` 相当を展開) |

比較器 getter / メソッドが closure 外 (vtable・データ表経由でしか到達しない) ため、`479b40` だけ直すと 10 unit が ok→miss になった (§4 の `nogetters`)。
getter / メソッドは **survey が到達する分だけ**転記した (`flags&2` の getter は他に `4788e0` / `478ce0` / `478f00` / `4793e0` / `478390` / `478860` / `478ed0` / `4793a0` の 8 個、
静的 vtable (先頭 3 slot が QI/AddRef/Release の形) は `.data` 内に 48 本あり、そのメソッドも closure 外。§6)。

## 4. 検証 (`m11_ov.c` = `d307abd`、`bash m11_build.sh` + `node trap_triage/survey_units.mjs`)

ビルドは wasm-ld signature mismatch 0 / undefined symbol 0。分母 = 942 unit。`trap` = oob + halt0 + abort。

| 構成 | ok | oob | halt0 | miss | noproc | trap | 所要 (n=3) | load (1 分値) |
|---|--:|--:|--:|--:|--:|--:|---|---|
| #481 HEAD (`dd9ba2c`, `negctl_483.sh head`) | 839 | 24 | 32 | 46 | 1 | **56** | 7.6–7.8 s (n=2) | 未記録 |
| **本 PR** | **848** | 25 | 22 | 46 | 1 | **47** | 6.06–6.44 s、3 回の JSON は byte 一致 | 0.51–0.58 |

遷移 (`survey_diff.py`): halt0→ok **9** (54, 58, 59, 60, 61, 62, 63, 307, 311) / halt0→oob **1** (53) / halt0→halt0 22 / oob→oob 24 / ok→ok 839 / miss→miss 46 / noproc 1。
**ok→非 ok の退行 0**。trap は 56→47 (−9)。12 unit の行き先: 9 → ok、53 → oob (§6)、56 → halt0 のまま (§6)、898 → halt0 のまま (別系統)。
`411e80` 呼出し回数: 16 → **6** (`raise_full`: 56 の `8cbde0`、245/279/647 の `814d30`、22 の `45a2a0`、509 の `b41bb0`)。

## 5. ネガコン (`bash trap_triage/negctl_483.sh [構成…]`、構成ごとに 1 点だけ外して全 survey)

| 構成 (外すもの) | ok | oob | halt0 | miss | 読み取り |
|---|--:|--:|--:|--:|---|
| `head` (全部外す) | 839 | 24 | 32 | 46 | 基準 |
| `full` (本 PR) | 848 | 25 | 22 | 46 | — |
| `no479b40` | 839 | 35 | 21 | 46 | FComparer が再び getter 番地 → ok −9、oob +10。**479b40 が効いている** |
| `no8cbde0` | 842 | 31 | 22 | 46 | GetItem が壊れた hash に戻る → ok −6、oob +6 |
| `nogetters` (3 getter とも) | 838 | 25 | 22 | **56** | ok→miss 10 (getter が closure 外で miss) |
| `no478420` / `no478540` / `no478c70` | 842 / 847 / 844 | 25 | 22 | 52 / 47 / 50 | getter 1 個ずつの寄与 (ok −6 / −1 / −4) |
| `nocmpmeth` (`479b00`/`479b10` 無し) | 839 | 24 | 22 | **56** | 比較器メソッドが miss: ok −9、miss +10 (53 も oob→miss) |
| `no8cbce0` | 848 | 25 | 22 | 46 | **差なし**: 登録キー間に hash 衝突が無く Equals が判定に効かない (転記は正しさのため) |
| `no8cc190` | 849 | 24 | 22 | 46 | **本 PR より ok +1**: 53 が ok になる。53 の OOB はスタックの残値に依存する (§6) |

注: `no8cc190` は IR の `8cc190` (定数 hash) に戻すと 53 が通る。53 の結果が局所的な副作用に左右されている (§6 の `418190` D4) ため、`full` を最良値とは主張しない。

## 6. 独立再計算 / 未解決

独立再計算: `node trap_triage/recount_483.mjs work/negctl_483/head.json work/negctl_483/full.json` (Node、`survey_diff.py` / `annotate.py` とは別実装。
wasm の export section を直接パースして frame 名を解決し、種別・遷移・ok 退行・halt0 の `Error()` 呼出元を再集計)。
結果は §4 と一致 (種別 839/24/32/46/1 → 848/25/22/46/1、遷移 halt0→ok 9 / halt0→oob 1、ok 退行 0、新 halt0 の呼出元 `411d20` 6 / `40a1c0` 8 / `4159e0` 4 / `416db0` 3 / `412770` 1)。
`survey_units.mjs` は frame 名を実行した wasm で解決して JSON に残すようにした (旧: 関数 index のままビルド間で名前がずれた)。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 53 の OOB: 辞書 Grow → `8cbb00` → `418210` → **`418190` (`_DynArrayClear`) の D4** (`mov rsi,[rbx]` の deref 脱落 → 変数のアドレスを配列として `FreeMem`)。`ov_418190_8cbb00_experiment.patch` で 418190 + 8cbb00 を転記すると 53 は ok になるが **unit 87 が ok→oob** (`59f9a0` 内)。原因未特定のため非採用。実験パッチを当てた build で `heaplog.c` により全 free を取ると、alloc 履歴に無い **非 heap 番地 (スタック) の free** が unit 106 / 298 にある (別の D4 脱落の疑い) | 53 が oob のまま。56 (`8cbde0` = GetItem が 53 の登録漏れでキー無し) もその連鎖 | 新規子チケット (M11, DynArray / FreeMem の D4 全数) |
| `814d30` (unit 245/279/647)・`b41bb0` (509)・`45a2a0` (22) の `raise`: `kind(TypeInfo) ≠ 7 (tkClass)` の検査で EInvalidOperation (`TObjectDictionary` 系の Ownerships 検査と推定。flags 引数の脱落か) | halt0 5 | 新規子チケット (M11) |
| unit 898: `40a1c0 ← 40c1d0 ← 476c30` の `Error()` | halt0 のまま | #447 / 新規子チケット (`40a1c0` 系 8 unit と合わせて) |
| `411e80` の引数脱落 (`411d20(0, arg1, 0)`) | 全 raise が `Error(216)` になる。意図的に未修正 (§2) | 新規子チケット (raise の扱い方針: JS 例外化するか) |
| `8cbe40` の `call [vt+0x10]` / `[vt+0x18]` (KeyNotify / ValueNotify)、`41a7b0` (`_IntfCopy`) の AddRef/Release が脱落したまま | 通知・参照カウントが効かない。survey の分類には出ない | #474 の D15 全数チケットに追記 |
| 比較器 getter 8 個 + 静的 vtable 48 本のメソッドが closure 外 (survey が到達した分のみ転記) | 他 unit が到達すると miss | 同上 (closure 外関数の網羅) |
| `M11_LB_BASE != 0` ビルド・`m11_e2e.sh` は未実行 (PE が無く、fl-win64 を取得していない) | 転記は `R()` と LVA のみで書いたが未確認 | PM のマージ後 |

## 7. DEFECTS.md 行案 (編集は PM 判断)

- D4 観測例: 「`479b40` `_LookupVtableInfo`: `movzx rcx, byte [rbx]` (TypeInfo.Kind) 脱落 → Kind=0 固定」「`418190` `_DynArrayClear`: `mov rsi,[rbx]` 脱落 → 変数のアドレスを配列として FreeMem」。
- D15 観測例: 「Generics.Collections の `IEqualityComparer` 呼出し (`8cbda0` `[vt+0x20]`、`8cbce0` `[vt+0x18]`) と `479b40` の `call rax` (getter): 脱落 → hash 定数・Equals 常に真 → 2 個目の Add が必ず重複例外」。
  `call reg` (レジスタ間接) も、target が解決できない形 (表から引いた getter) では脱落する (D15 の注記「`call reg` は解決済」の反例)。
- 新規案 D17 (fe): **引数 pass-through 脱落** — 関数が受け取った引数レジスタを callee へ素通しするだけ、または脱落した間接 call にしか渡さない場合、
  その引数が IR 署名から消える (`8cbda0` の rdx = key)、または callee 呼出しで 0 になる (`411e80` → `411d20(0, arg1, 0)`)。検出信号: 機械語で rcx/rdx/r8/r9 を書かずに読まれる (live-in) のに IR 署名に対応する引数が無い。

## 8. 検証範囲 / 範囲外

- 範囲: survey (942 unit を先頭から各 1 回) の分類。到達した比較器 getter / メソッドのみ転記。
- 範囲外: `M11_LB_BASE != 0`、`m11_e2e.sh` (PE 要)、#447 併用時の survey、`fl-win64` (本 run は `oc_artifacts` に含まれず未取得)。
  逆アセンブルは PE の代わりに `work/m11_image.bin` (.text 入り) を `capstone` で読む `disasm_img.py` を追加して行った (`pip install capstone` が要る)。
- `find tools/m11 docs -type f -size +20M -not -path '*/work/*'` は該当なし。

## 9. 再現手順

```sh
cd tools/m11   # work/ = work-m11 展開済み。/opt/emsdk が要る。disasm_img.py は capstone (pip) が要る
bash m11_build.sh && node trap_triage/survey_units.mjs work/after.json                # 本 PR: ok 848 / trap 47
python3 trap_triage/survey_diff.py work/negctl_483/head.json work/after.json 53 56 898  # 遷移表と ok 退行 unit
node trap_triage/recount_483.mjs work/negctl_483/head.json work/after.json            # 独立再計算 (別実装)
bash trap_triage/negctl_483.sh [head full no479b40 no8cbce0 no8cc190 no8cbde0 nogetters no478420 no478540 no478c70 nocmpmeth probe_head raise_head raise_full]
python3 trap_triage/disasm_img.py 8cc190 8cbda0 8cbce0 479b40 411e80              # 機械語 (boot_fns.json に無い関数は VA:size)
python3 trap_triage/annotate.py work/negctl_483/head.json                          # Error() 呼出元の分類
```

# #482: `5c03d0` の `call [rbx+0x18]` (node 差替え通知) の脱落を復元

**判定: 受入条件 3 件すべて達成。ただし survey の分類・per-unit 結果は完全に不変** (復元した呼出しは survey 中 4 回だけ、すべて unit 114、
通知先 `5c0e70` の先は no-op)。検証起点 = base `dd9ba2c` (#481 HEAD) / 変更後 `912cea3` の `m11_ov.c` (以降のコミットは `negctl_482.sh` / `disasm_img.py` / docs のみ)。

既知類型との関係 (`docs/DEFECTS.md`): **D15 (DEFECTS.md) の再発**。ただし RetDec 版では `call` だけでなく、それを守る `cmp rax,[old]; je` ごと脱落し、
IR に条件分岐が残らない (D15 の記述は stage-0 の「空ブロック」で、分岐ごと消える形は未記載)。新規類型なし。

## 1. 脱落の特定 (機械語 ↔ IR)

`5c03d0(self=キャッシュ, obj, key)` は 5c0270 / 5c00e0 の呼出し元 (`5c0fc0` と `5c2070` が呼ぶ。`obj+0x18` に参照カウント付き node を持つ所有オブジェクト)。
`obj` は vptr と `+8` Code / `+0x10` Data (通知イベント) / `+0x18` node / `+0x20` ロック / `+0x30` 所有者を持つ (Graphics.pas の TGraphicsObject 相当と**推定**。裏取りは未実施)。

| 機械語 (`disasm_img.py 5c03d0 0x70`) | 意味 | `boot_final3.ll` の `function_5c03d0` |
|---|---|---|
| `5c03fc call 4232e0` (self+0x10) | Lock | あり |
| `5c0406 mov rax,[rax+0x18]` → `[rbp+0x40]` | old := obj.node | あり (`%4`) |
| `5c0419 call 5c00e0` / `5c0422 mov [rcx+0x18],rax` | node := Find(key); obj.node := node | あり (`%5`, store) |
| **`5c0426 cmp rax,old; je 5c043a` / `5c042c..5c0437 mov rcx,obj; mov rbx,[obj]; call [rbx+0x18]`** | **node ≠ old なら obj の VMT スロット +0x18 を呼ぶ (rcx = obj)** | **脱落 (条件分岐ごと無い)** |
| `5c0442 call 5c0270` (old) / `5c0458 call 423980` | Release(old) / Unlock | あり |

兄弟 `5c04b0` (同形、`5c0536` に同じ `call [rbx+0x18]`) は closure 外で IR に無い (`grep -c function_5c04b0 boot_final3.ll` = 0) ため対象外。

## 2. 修正 (`tools/m11/m11_ov.c`)

| 関数 (VA) | 内容 |
|---|---|
| `function_5c03d0` (`1b90bf1`) | 逆アセンブル転記。`if (node != old) m11_icall(Q(Q(obj)+0x18), obj, ...)` を復元 (通知先は obj の VMT から実行時に解決) |
| `function_5c0e70` / `function_5c0810` (`912cea3`) | 通知先の実体。vtable 経由でしか到達しない closure 外の関数 (IR に無い)。`5c0e70` = `5c0810(self)` (`if [self+8] call [self+8](rcx=[self+0x10], rdx=self)`) + `[self+0x30]` があればその VMT スロット +0x18 を呼ぶ。`disp_find` の追加 switch に `5c0e70` を足して icall から解決 |

`5c0e70` を足した理由: 無いと復元した call は icall miss (skip, ret 0) で何も起きない。miss 件数は §4 `no5c0e70`。

## 3. 検証 (`bash m11_build.sh` = wasm-ld signature mismatch 0 / undefined symbol 0 → `node trap_triage/survey_units.mjs`)

分母 = 942 unit。`trap` = oob + halt0 + abort。ビルドは `/opt/emsdk`、素材は work-m11 (2026-10-10 生成)。

| 構成 | ok | oob | halt0 | miss | noproc | trap | 所要 (n=3) | load (1 分値) | per-unit JSON md5 (n=3 全回同一) |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| base `dd9ba2c` | 839 | 24 | 32 | 46 | 1 | **56** | 4.25–4.56 s | 0.48–0.52 | `512d72c0…` |
| `1b90bf1` (5c03d0 のみ) | 839 | 24 | 32 | 46 | 1 | **56** | 4.20–4.54 s | 0.49–0.54 | `01c37358…` |
| **`912cea3` (5c03d0 + 5c0e70/5c0810)** | 839 | 24 | 32 | 46 | 1 | **56** | 4.29–4.31 s | 0.45–0.50 | `29577ac6…` |

- `survey_diff.py` (新規の最終行: kind 以外の全欄 stubs/err/msg/va_mb を比較。frames は wasm module hash と関数 index がビルドごとに変わるため深さのみ): base → `912cea3` で
  **遷移はすべて同一 kind (ok→ok 839 / oob→oob 24 / halt0→halt0 32 / miss→miss 46 / noproc→noproc 1)、ok→非 ok 0 unit、kind 以外も含めた差分 unit 0**。
  md5 が違うのは frames 内の `wasm://wasm/<hash>` と関数 index だけ (同一ビルドの 3 回は md5 一致)。
- **影響 unit = 1 (unit 114) / trap 数の変化 = 0 (56→56)**。`probe` 構成で survey 全体の `5c03d0` 呼出しを数えると **4 回**、すべて unit 114 内
  (`call#1..4`: `obj=10bd8f70/10bd8fc0/10bd9060/10bd90b0`)、4 回とも `node ≠ old`、通知先はすべて `0x5c0e70` (icall 解決 ok)。
  `5c0e70` 入口の `[self+8]` (OnChange Code) と `[self+0x30]` (所有者) は 4 回とも 0 → 先の呼出しは発生せず副作用なし。
- 最小集合 `SV_ONLY=1,17,45,95,114`: 0.26 s で完走 (ok 2 / oob 2 / halt0 1, #481 と同じ)。
- `find tools/m11 docs -type f -size +20M -not -path '*/work/*'` 該当なし。`git status --porcelain=v1 -- tools/m11` クリーン (コミット済み HEAD で実行)。

## 4. ネガコン (`bash tools/m11/trap_triage/negctl_482.sh`, 1 構成ずつ外す。icall 列は最小集合を trace 付きで別実行して数える)

| 構成 (— = 計測コード無し) | survey | `5c03d0` 呼出し (changed & 解決) | `5c0e70` 入口 | icall `0x5c0e70` ok / miss |
|---|---|---|---:|---|
| `full` (現行) | ok 839 / oob 24 / halt0 32 | — | — | **4 / 0** |
| `no5c03d0` (5c03d0 の転記を外す = base と同じ) | 同一 | — | — | **0 / 0** (通知が消える) |
| `no5c0e70` (通知先の転記を外す) | 同一 | — | — | 0 / **4** (4 回とも closure 外 miss で skip) |
| `probe` (full + stderr 記録) | 同一 | 4 (4) | 4 | 4 / 0 |
| `probe_no5c03d0` | 同一 | 0 | **0** | 0 / 0 |

`probe` と `probe_no5c03d0` は同じコード差で `5c0e70` 入口が 4 → 0 になる。**復元を外すと通知は 4 → 0 に戻る** (受入条件 3)。
survey の分類は全構成で base と per-unit 完全一致 (`survey_diff.py` 差分 0) のため、**survey 自体はこの call に対して判定力が無い**
(今回の復元は「通知が起きる」ことを入口計測で確認したもので、「survey が改善した」ことではない)。

注: `SV_TRACE_AT` (trace 出力) を付けた全 survey は全構成共通で unit 134 が ok→oob になる (本件と無関係。trace 無しでは起きない)。
そのため全 survey は trace 無し、icall 計測だけ最小集合の trace 実行に分けた。

## 5. 検証範囲 / 範囲外

- 範囲: survey (942 unit 各 1 回、先頭から順) の分類と per-unit 欄、`5c03d0` 4 呼出しの通知先解決。逆アセンブルは work の `m11_image.bin`
  (LB_BASE=0 の image, offset = RVA) を `disasm_img.py` で読んだ。今回 fl-win64 を取得していないので PE の `.pdata` 境界は使っていない。
- 範囲外: `M11_LB_BASE != 0` のビルド (転記は LVA 座標のみ)、`m11_e2e.sh` (PE 要)、#447 併用時の survey、`OnChange` / 所有者が非 null の通知経路 (survey で 0 回)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `5c0e70` の OnChange / 所有者 (非 null) 経路が未検証。`5c0810` の `call [self+8]` は method pointer の Code 値 (VA か LVA か) を未確認 (icall は両方受ける) | 実機で TFont 等に `OnChange` が付く UI 経路で効く可能性 | #130 にコメント (survey で 0 回) |
| `5c04b0` (同形の `call [rbx+0x18]` あり) が closure 外 | closure に入ったとき同じ脱落が起きる | #474 の REPORT §6 の「D15 / ldfix 検出漏れ全数」子チケットに併記 |
| survey が今回の呼出しに判定力無し (分類・per-unit 欄とも不変) | 同種の D15 復元は survey では退行検出できない | #130 (状態を見る検査の追加案: 復元した call の入口計測を常設) |
| `SV_TRACE_AT` 付き survey で unit 134 が ok→oob | trace を付けた調査の結果が本番と食い違う | 新規子チケット (M11, 全構成共通・本件無関係) |
| trap 56 (#130 の完了条件 < 20 は未達) | #130 の完了条件 | #130 (#481 と同じ) |

DEFECTS.md 行案 (D15 の観測例に追記、編集は PM 判断): 「`5c03d0` (Delphi 参照カウントキャッシュの node 差替え): RetDec が `cmp new,old; je` + `call [reg+0x18]` を分岐ごと脱落 →
通知が一切発生しない (silent)。`call` 単体ではなく、それを守る条件分岐も消える」。

## 7. 再現手順

```sh
cd tools/m11   # work/ = work-m11 展開済み。emsdk (/opt/emsdk) が要る。disasm_img.py は capstone (pip) が要る
python3 trap_triage/disasm_img.py 5c03d0 0x70                                  # 脱落箇所 (5c0426..5c0437)
bash m11_build.sh && node trap_triage/survey_units.mjs work/after.json         # ok 839 / trap 56
python3 trap_triage/survey_diff.py <base の survey.json> work/after.json 114   # 遷移 + ok 退行 + kind 以外の差分 unit
SV_ONLY=1,17,45,95,114 timeout 10 node trap_triage/survey_units.mjs /dev/null # 最小集合
bash trap_triage/negctl_482.sh [full no5c03d0 no5c0e70 probe probe_no5c03d0]   # ablation + 呼出し計測 (終了時 ov.o を再生成)
```

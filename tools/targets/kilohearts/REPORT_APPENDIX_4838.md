# REPORT 付録 (#4838 KH-119): Delay の代入の pointer⇔整数 5 行の規則

#3837 (KH-72) の分割。#3801 付録の P6「代入の pointer⇔整数 14 件」の残件。

## ①. 結論

- 現 HEAD (origin/main `e1071546e`) の emcc census では、代入の pointer⇔整数は **14 件ではなく 5 行**だった (旧 P6 の件数は `bd1b7a297` 時点の値で、現 HEAD とずれる)。
- 5 行を機械語で確定し、`ghidra_to_c.py` の `DELAY_RULES` に 1 行 1 規則で入れた (件数 assert 付き)。現 HEAD の代入の pointer⇔整数は **0 件**。
- Delay の emcc error 行は **316 → 311**、型不一致 (`演算・代入・ポインタ`) は **95 → 90**。
- Gain/Haas/Gate の生成 C は base と同一 (`.c` 同一・`.o` byte 一致・3 本)。

## ②. 5 行の分類と機械語による確定

| 関数 (delay.c の行) | 元の式 | 機械語 (HeartCore.core_64) | 規則 |
|---|---|---|---|
| `FUN_180f88084` (2262・2263) | `param_1[1] = &UNK_18227b1f8;`・`*param_1 = &UNK_1813a3e58;` | `andq $0,0x10(%rcx)`・`leaq 0x12f3168(%rip),%rax`・`movq %rax,0x8(%rcx)`・`leaq …(%rip)`・`movq %rax,(%rcx)` | 8 byte スロットへ leaq 番地を movq で書く。同ビットを `(longlong)&UNK_…` |
| `FUN_180f880a4` (2273・2274) | `param_1[1] = &UNK_18227b208;`・`*param_1 = &UNK_1813a4968;` | 同形 (`180f880a9`・`180f880b4`) | 同上 |
| `FUN_180fd2d38` (5107) | `*param_1 = &UNK_1822849e0;` | `180fd2d8e: leaq …(%rip),%rcx` → `180fd2d99: movq %rcx,(%rax)` | 同上 |

- 規則は `&UNK_<va>` 形で当てる。`tbase` 置換 (`gt_<base> + off`) は `DELAY_RULES` の後に走るため、`gt_` 形では当たらない (初版でこれを見落として件数 assert が 0 で止まった)。
- 件数は 5 規則とも 1 件に固定した。
- 確認の範囲: 上の表は**書込み先の機械語** (leaq + movq) で規則を確定した。issue #4838 の受入「同ビットの明示キャストで足りるか」の確認 (**呼出元の機械語**で 1 件ずつ) は**未実施**。この run には `plugins-kilohearts` 素材が無く、呼出元を読めなかったため。子 issue #4894 [KH-129] で行う (§④)。

## ③. 測定

測定 commit: `7309b3825` (本 PR の規則を入れた最後のコード変更)。base: origin/main `e1071546e` (`git archive` で `ghidra_route`・`snapins/lift`・`snapins/scripts` を展開して同じ手順)。

- 環境: `plugins-kilohearts` (Installer zip → payload.dat → windows.zip/1ccb1df8c8f10745 → HeartCore.core_64)・`toolchain-emsdk` (emcc)・Ghidra 12.1.4 (zip sha256 `ddac49f9…d2db` 一致)・JDK 21 (temurin-21)。n=1。load は測定開始時 0.85 0.93 0.53 (`/proc/loadavg`)。
- コマンド: `FX=bitcast,intload,stackpair,assoc,concat,gtype,lanes bash tools/targets/kilohearts/ghidra_route/gtype_census.sh <work> <base ghidra_route>`。

| 測定 | base origin/main `e1071546e` | HEAD `7309b3825` |
|---|---|---|
| Delay emcc error 行 | 316 | **311** |
| 型不一致 (`演算・代入・ポインタ`) | 95 | **90** |
| 代入の pointer⇔整数 (`conversion assigning to`) | 5 | **0** |
| 引数の pointer⇔整数 (`passing`) | — | 86 (未対象。#3837 の残り) |
| void 代入 (`from incompatible type 'void'`) | — | 7 (未対象。#4672 KH-107) |
| Gain / Haas / Gate の `.o` | 1435 / 3217 / 3756 B | 1435 / 3217 / 3756 B。base と `cmp` 一致 |
| Delay closure を含む lift 集合 | 151 関数 OK | 151 関数 OK |

- 所要 (実測 wall): `gtype_census.sh` 全体 52.7 s (base 比較を含む)。

### ③-2. 測定 commit 以降の差分

- `git diff --stat 7309b3825 HEAD -- tools/targets/kilohearts/ghidra_route` = 0 行 (本 PR の REPORT・DOC_MAP のみ)。
- `git diff --stat e1071546e HEAD -- tools/targets/kilohearts/ghidra_route` = `ghidra_to_c.py` 14 行追加 (本 PR の 5 規則)。基点は測定時の base `e1071546e`。

## ④. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 引数の pointer⇔整数 86 件 | Delay の wasm 化が未完 | #3837 [KH-72] (既存 open) |
| void 代入 7 件 | 同上 | #4672 [KH-107] (既存 open) |
| Delay の突合 1000 trial | emcc が通らないため未実施 | #3073 [KH-41] (既存) |
| 代入 pointer⇔整数 5 行の呼出元機械語での確認 (issue #4838 受入 1 の残り) | 同ビット明示キャストの妥当性が呼出元で未確認 | #4894 [KH-129] (新規) |

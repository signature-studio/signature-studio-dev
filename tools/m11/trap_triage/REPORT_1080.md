# #1080 unit 895: `412770` の null memcpy は Runtime error 210 の直接原因か (親 #684, 起点 #882)

既知類型との関係: D4 (`docs/DEFECTS.md`) の 1 段 deref 脱落の変種。判定の正本は機械語 (`disasm_fn.py`)。

結論: **直接原因ではない**。`412770` の `ptr null` 読みを機械語どおり (`*arg1`) に直しても、
0 埋め領域に差し替えても、unit 895 は halt0 のまま top frame `function_412770` で止まる。
DEFECTS 行案は新規類型ではなく既存 D4 の変種として §5 に置く (本体編集は PM 判断)。
ただし `Runtime error 210` の発生源はこの判定では特定できず、未解決として §6 に残す。

検証起点 (測定 commit): `c4e93550` (main)。素材: `fl-win64` / `work-m11`。

## 1. 環境と手順

- worktree `ws-1080` (branch `1080-m11-412770-null-memcpy`、base `origin/main` = `c4e93550`)。
- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`)。`work-m11` → `tools/m11/work/` (`tar --zstd -xf`)。
- REPORT_882 §1 の手順を実行: `m11_gen_ir2.sh` → `m11_build.sh` → `SV_RAW=1 node trap_triage/survey_units.mjs`。
- 再現スクリプト: `tools/m11/trap_triage/negctl_1080.sh` (HEAD / A / B の 3 通りを build・survey し、終了時に原 IR を復元して `m11_cond.py --check` を通す)。
  パッチ生成は `tools/m11/trap_triage/patch_412770_1080.py`。
- 生成物 (IR・.o・survey JSON) は `tools/m11/work/` と `$RUNNER_TEMP` 配下で、commit しない。

## 2. 観測: `412770` の native と IR

native (`disasm_fn.py 0x412770`、size=95):

- `412770`: `rep movsq` で `[rcx+0x38]` から 30 要素を `rbp+0x20` へ複写。続けて **`mov rsi, qword ptr [rax]`** (rax = arg1)、
  `mov rdi, rax`、`mov ecx, 0x25`、`rep movsq` で `*arg1` から 37 要素を `arg1` へ複写。その後 `call 0x4126f0`。
- lift 段 IR (`boot0.lift.ll` / `boot_final.ll` 共通): 2 本目の複写源が **`ptr null`** になっている (`call void @__asm_rep_movsq_memcpy(ptr %4, ptr null, i64 37)`)。
  機械語の `mov rsi,[rax]` (1 段 deref) が脱落している。DEFECTS D4 と同型。

`412770` の役割: `4126f0` は context (rcx) を復元して `jmp qword ptr [rcx]` する longjmp 相当。
`412770` は `Halt0` 系の脱出経路で、`4128b0` から 2 箇所 (`4128ff` / `4129e8`) で呼ばれる。

wasm 線形メモリ address 0 から 296 B (= 37 × 8) は `m11_image.bin` で全 0 (`nonzero bytes in [0,296): 0`)。
つまり `ptr null` 読みは実際には 0 を読んでいる。

## 3. 実測 (survey、`SV_RAW=1`、negctl_1080.sh)

| 構成 | ok | halt0 | miss | oob | other | noproc | unit 895 |
|---|--:|--:|--:|--:|--:|--:|---|
| HEAD `c4e93550` (原 IR) | 870 | 7 | 47 | 16 | 1 | 1 | halt0 (`412770`、`…1460`) |
| A: `*arg1` を読む (native どおり) | 870 | 7 | 47 | 16 | 1 | 1 | halt0 (`412770`、`…1460`) |
| B: 0 埋め領域 (null の意味論だけ変更) | 872 | 7 | 47 | 14 | 1 | 1 | halt0 (`412770`、`…1480`) |

- 合計は 942 units (870+7+47+16+1+1 = 942、872+7+47+14+1+1 = 942)。
- HEAD vs A: kind 遷移 **0 件**。
- HEAD vs B: kind 遷移 2 件 (304: oob→ok、555: oob→ok)。895 は halt0 のまま。
- B で変わったのは `Runtime error` 表示の**番地** (`…1460`→`…1480`) だけ。表示元 (`MessageBoxA` を呼ぶ関数) は本 run では未特定。ただし 0 埋め領域への差し替えで番地が変わったのは、表示文字列の位置が null 読みの値とは別に決まることを示す。

REPORT_882 の値 (869 / 8) との差 (ok +1、halt0 -1) の原因は未切り分け。本 run の HEAD 値は `870 / 7` で、以後の比較はこの run 内の値で行う。

## 4. 判定

- **受入条件 1 (null memcpy が直接原因か)**: **否**。
  - ネガコン: 原 IR (null 読み) を機械語どおり (A) に直す → 895 の kind・top frame・error 文言 (`…1460`) が不変。
  - B: null 読みを 0 埋め領域に替えると 895 は halt0 のまま。null 読みで halt する経路は本測定では観測されなかった。
  - ただし B では unit 304 / 555 が oob→ok に変わる。`412770` の null 読みは別 unit の OOB には関係しうるため、`412770` の修正を入れるかは #684 の判断とする。
  - 判定は kind (halt0) と top frame (`function_412770`) と error 文言のアドレス (`…1460`) の 3 点で行った。
- **受入条件 2 (直接原因の場合の DEFECTS 行案)**: 直接原因ではないため、新規の行案は不要。
  D4 の変種として §5 に記録する (既存 D4 の再発例として扱うかは PM 判断)。

## 5. DEFECTS 行案 (本体編集は PM 判断・参考)

既存 D4 の再発例に追記する候補 (新規 ID は立てない):

> `412770` (unit 895 の Halt0 経路): `mov rsi,[rax]` (`*arg1`, disp=0) が IR で `ptr null` になる。
> 機械語の 1 段 deref 脱落 (D4 型) だが、この脱落は halt の直接原因ではない (REPORT_1080 §4: A/B とも 895 は halt0 のまま)。
> 出典: [REPORT_1080.md](../tools/m11/trap_triage/REPORT_1080.md)。

## 6. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unit 895 の `Runtime error 210` の発生源 (`412770` の手前の `4128b0` 側か、別経路か) | 895 の halt0 原因が未特定 | #684 (親)。本 issue の範囲外として残す |
| DEFECTS 行案の採否 (D4 再発例への追記) | 文書のみ | PM 判断 (DEFECTS.md 直接編集は PM) |
| HEAD 値の再現差 (REPORT_882 の `869 / 8` と本 run の `870 / 7`) | 比較基準の揺れ | #684 へのコメントで報告 |

## 7. 測定 commit と HEAD までの差分

- 測定 commit: `c4e93550` (実測はこの commit の build・IR 生成で行った)。
- `git diff --stat c4e93550 HEAD -- tools/m11/` の出力 (測定 commit からの追加は 3 ファイルのみ、コード・IR 生成経路は不変):
  ```
  tools/m11/trap_triage/REPORT_1080.md       | 87 ++++++++++++++++++++++++++++++
  tools/m11/trap_triage/negctl_1080.sh       | 44 ++++++++++++++++
  tools/m11/trap_triage/patch_412770_1080.py | 32 +++++++++++
  3 files changed, 163 insertions(+)
  ```
- 上記 3 ファイルは `tools/m11/trap_triage/` 内の新規追加のみで、`tools/m11/work/` や IR 生成スクリプトには触れていない。

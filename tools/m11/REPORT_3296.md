# #3296: function_412770 の rep movsq 源 `ptr null` の修正 (受入 1 達成・受入 2 未達)

親: #3229 (`tools/m11/REPORT_N403.md` §7)。素材: fl-win64 (`block00031_PE.bin`)・work-m11 (`tools/m11/work`)・emsdk (`[EMSDK]`)。
既知類型との関係: D4 (`docs/DEFECTS.md`) の再発例 (1 段 deref の脱落)。新規 ID は立てない。判定の根拠は `tools/m11/trap_triage/REPORT_1080.md` §4・§5 と `tools/m11/REPORT_N403.md` §7-4 (§3 参照)。
測定主体: 本 PR の作業 runner (2026-10-15)。
測定 commit: `3b6651de` (修正のコードを変えた最後の commit。§2 の値はこの commit の build と寛容起動)。
測定 commit から HEAD までのコード差分: §5-1 (main 取り込みで 2 ファイル・docstring 1 行)。規範 6 の『差分 0』は満たさない。

## 1. 機械語と lift IR

- 機械語 (VA 0x412790〜0x41279b): `mov rsi,[rax]` (rax = arg1) → `mov rdi,rax; mov ecx,0x25; rep movsq` (37 qword)。源は `[arg1+0]` の**値** (1 段 deref)。
- lift 段 (`tools/m11/work/boot0.lift.ll`) から既に `call @__asm_rep_movsq_memcpy(ptr %4, ptr null, i64 37)`。`ptr null` の源は boot_final.ll でも lift でもこの 1 箇所だけ。
- 修正: `tools/m11/ldfix/fix_src412770.py` (`m11_gen_ir2.sh` で ldfix の後に適用。対象行が 1 件でない・二重適用・第 1 仮引数が `ptr %arg1` でない場合は assert で停止 (fail-closed))。`load i64 [arg1+0]` → `inttoptr` → 源に置換。

## 2. LB 別の再現 (`bash tools/m11/m11_lb_tolerant_repro.sh <LB> <出力>`)

| 条件 | wall | ok / miss / oob / halt0 / abort / noproc |
|---|---|---|
| LB=0 修正前 (`repro_lb0`) | 16.7 s | 868 / 47 / 19 / 7 / 0 / 1 |
| LB=0 修正後 (`fix_lb0`) | 16.6 s | 868 / 47 / 19 / 7 / 0 / 1 |
| LB=0x10000 修正前 (`repro_lb10000`) | 20.1 s | 868 / 47 / 16 / 8 / 2 / 1 |
| LB=0x10000 修正後 (`fix_lb10000`) | 19.7 s | 868 / 47 / 16 / 8 / 2 / 1 |

- `m11_lb_unit_diff.py` の kind 差は、修正前 (`repro_lb0` vs `repro_lb10000`) も修正後 (`fix_lb0` vs `fix_lb10000`) も **8 件** (unit 40・153・158・291・296・304・555・745。`tools/m11/REPORT_N403.md` §6-2 と同じ)。
- 修正前後の unit 結果差は **0** (`fix_lb0` vs `repro_lb0`、`fix_lb10000` vs `repro_lb10000`)。修正は寛容起動の unit 結果を 1 件も変えなかった。
- REPORT_1080 との対応: `tools/m11/trap_triage/REPORT_1080.md` の A (機械語どおり `*arg1` を読む) は HEAD 対比で kind 遷移 0 件 (同 §3)。本件の修正も同じ読み (`load i64 [arg1+0]` を源にする) で、結果は A と同じく変化 0 件。測定の経路は異なる (REPORT_1080: survey・LB 1 本 / 本節: 寛容起動・LB 2 本)。
- REPORT_1080 の B (0 埋め領域を源にする) では unit 304・555 が oob→ok に変わった (同 §3)。null 源の値が 304・555 に効く可能性はあるが、A 型の本件の修正では変わらない。この差の原因は未確認。
- 推定 (未確認): 修正後の源は `[arg1+0]` の値を指す。その値が 0 なら address 0 を読むため LB 依存が残りうる。arg1 先の値は本 PR では測定していない。
- 受入 1 (機械語どおりの load に戻す lift 修正) は達成。受入 2 (kind 差 0) は未達。

## 3. 判定: D4 の再発例 (新類型ではない)

- 既存 D4 の再発例として扱う。新規 ID は立てない。`docs/DEFECTS.md` 本体の編集は PM 判断 (下の案を提示するのみ)。
- 同一と判断した点: 機械語 `mov rsi,[rax]` (disp=0 の 1 段 deref・基底 rax は引数 arg1 の複写) の load が IR に無い。D4 の検出信号 (機械語のメモリ命令に対応する IR 痕跡が無い) と修復型 (引数から load を挿入する) が一致する。
- 区別した点: D4 の症状は代用値が基底 reg の値になる (`rD := r8`)。本件は代用値が `ptr null` で、arg1 を参照しない。代用値の出所は未特定。この差は既存 D4 の再発例として記録するための注記であり、新類型の根拠にはしない。
- `tools/m11/trap_triage/REPORT_1080.md` §5 と `tools/m11/REPORT_N403.md` §7-4 (#3229 側) の判定 (D4 の変種) と一致する。
- DEFECTS D4 への追記案 (PM 判断。REPORT_1080 §5 の文言に合わせる):
  > `412770` (unit 895 の Halt0 経路・寛容起動の unit 集合): `mov rsi,[rax]` (`*arg1`, disp=0) が IR で `ptr null` になる。機械語の 1 段 deref 脱落 (D4 型)。修正 (`ldfix/fix_src412770.py`) は機械語どおりの読みで、寛容起動の unit 結果は変えない (`tools/m11/REPORT_3296.md` §2)。出典: `tools/m11/REPORT_3296.md`・`tools/m11/trap_triage/REPORT_1080.md`。

## 4. address 0 の中身 (前版の機構の記述を撤回)

- 前版の「address 0 の中身 (LB=0 は PE ヘッダ・LB=0x10000 は 0 埋め)」は根拠が無いため撤回する。`fix_src412770.py` の docstring からも外した (§5-1)。
- 確認したこと:
  - `tools/m11/m11_image_gen.py` 18 行 `KEEP = ('.text', '.data', '.rdata', '.didata')` は、この 4 セクションだけを LVA 座標に敷く。PE ヘッダは像に入らない。
  - 作業用 image (共有 checkout の `tools/m11/work/m11_image.bin`、生成 2026-10-10) の `[0,296)` は全て 0 (非ゼロ 0 バイト)。`tools/m11/trap_triage/REPORT_1080.md` §2 も同じ観測。
- 未確認: LB 別の address 0 の中身 (LB=0 と LB=0x10000 の差の有無)。本 PR では測定していない。LB 依存の機構は未特定 (§5-2)。

## 5. 測定 commit 以降の差分と未解決

### 5-1 測定 commit 以降の差分

`git diff --stat 3b6651de HEAD -- tools/m11 ':(exclude)tools/m11/REPORT*'` (HEAD = `cb394b5e`):

```
 tools/m11/ldfix/fix_src412770.py   |  2 +-
 tools/m11/m11_lb_ir_fn_diff.py     | 55 ++++++++++++++++++++++++++++++++++++++
 tools/m11/m11_lb_tolerant_repro.sh |  1 +
 3 files changed, 57 insertions(+), 1 deletion(-)
```

- `m11_lb_ir_fn_diff.py` (新規・`main` の #3229 側 `c0607b7a`): 関数単位の IR 差分の解析スクリプト。寛容起動の経路では実行されない。
- `m11_lb_tolerant_repro.sh` (+1 行・`main` 側): `cp work/boot_final.ll "$OUT/boot_final.ll"` で、build 後の IR を出力先にコピーするだけ。build も寛容起動の入力も変えない。
- `fix_src412770.py` (docstring 1 行・本 PR): 挙動不変。旧版と新版に同じ入力 (`tools/m11/work/boot_final.ll`) を与えた出力 IR が `cmp` で一致した。
- 上の差分のため規範 6 の『差分 0』は満たさない。HEAD での再測定は本 run では未実施。§2 の値は `3b6651de` の測定。

### 5-2 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| LB 依存 unit 差 8 件 (40・153・158・291・296・304・555・745) の原因。修正後も不変。address 0 の中身・arg1 先の値・unit 40 の Halt 経路・unit 153/158 の OOB の発生箇所は未特定 | 寛容起動の LB 別の結果が違う (silent 誤り)。受入 2 未達 | 子 issue #3325 (`[M11-N181]`) |
| §5-1 の差分を含む HEAD での再測定 (§2 の値は `3b6651de`) | 規範 6 の『差分 0』を満たさない。§2 の値が HEAD のものとは限らない | PM (再測定。本 run では未実施) |
| 他の NULL 源 rep movsq の一般化 (本件 1 件のみ・§1) | 同類型の他箇所は未検査 | 本件では未対応 (DEFECTS 登録後に判断) |
| DEFECTS D4 への再発例の追記 (§3 の案) | docs のみ | PM 判断 |

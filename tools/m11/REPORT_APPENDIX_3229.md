# REPORT_APPENDIX_3229 — #3229 の 8 unit の LB 依存差の切り分け (REPORT_N403.md §7 の全文)

分割移動 (REPORT_N403.md が 250 行を超えるため)。本文の内容は変えていない (main の #3229 の節をそのまま移した)。

## 7. #3229: 8 unit の LB 依存差の切り分け (IR 段まで。機構は未特定)

測定主体: 前回 run (2026-10-14/15) の実測。2026-10-15 の fix run は work-m11・toolchain-emsdk が無く、e2e と IR 再生成をしていない (§7-2 の objdump だけ本 run の実測)。
測定 commit: `c0607b7a` (コードを変えた最後の commit)。`git diff c0607b7a HEAD -- tools/m11 ':(exclude)tools/m11/REPORT*'` の出力は空 (差分 0)。

### 7-1 再現 (前回 run の実測)

| 項目 | LB=0 | LB=0x10000 |
|---|---|---|
| 寛容起動 wall (2 回) | 17.66 s / 17.24 s | 20.20 s / 20.35 s |
| attempted / ok / skipped | 942 / 867 / 74 | 942 / 867 / 74 |
| kind 差 (`m11_lb_unit_diff.py`) | 8 件 (index 40・153・158・291・296・304・555・745) | 同左 |

load average・並列数は前回 run で未記録のため、所要は §6-1 と比べない。

### 7-2 IR 差分と機械語

- 比較は build 後の `boot_final.ll` (`alloca` 拡幅の前後を混ぜない)。前回 run で 7,422 関数中 4,023 の本文が違った (大半は LB 分の定数シフト)。**全件のシフト確認は未実施** (IR が本 run に無い)。確認したのは `function_412770` (差は 2 行: `inttoptr i64 16404480` → `16470016`) と、#3229 本文が挙げる 412770・4128b0・411d20・412e40・412c20・535c11 (前回 run の記録。本 run では再確認していない)。
  → 主張は「確認した関数の IR には LB 依存の差 (シフト以外) は無かった」まで。
- `function_412770` の `__asm_rep_movsq_memcpy(ptr %4, ptr null, i64 37)` は両 LB の IR に残る (LB 非依存)。機械語 (本 run の実測): `tar --zstd -xf fl-win64.tar.zst --wildcards '*block00031_PE.bin'` の後、`objdump -d block00031_PE.bin --start-address=0x412770 --stop-address=0x4127a0` で `41277d mov %rcx,%rax` → `412790 mov (%rax),%rsi` → `rep movsq` 37 qword。rax は arg1 (rcx) なので、源は `[arg1+0]` の load で、IR では `ptr null` になっている。
- LB=0x10000 の `work/m11_image.bin` の先頭 0x10000 バイトは全て 0 (前回 run の実測)。LB=0 で PE ヘッダが address 0 に来る記録は #3229 本文 (判明済み) の引用で、本 run では image を生成していない。

### 7-3 修正の判定 (受入 2: 修正なし・子 #3296 へ)

- LB 直書き: 確認した範囲では見つからず (差は LB 分のシフトだけ)。修正は入れていない。照合文字列の LB 加算は #3160 で修正済み (§6-4)。
- (a) は否定済みのため方針から外す。`function_412770` の源を `[arg1+0]` の load に戻しても 8 件は不変 (#3229 本文の記録。前回 run の実験で、本 run では再実行していない)。この load の脱落は 8 件の原因ではなく、LB に依らない別件。
- 8 件の機構は未特定 (推定のみ)。候補 (未検証): (b) address 0 の内容 (LB=0 の PE ヘッダ / LB=0x10000 の 0 埋め)、(c) `tools/m11/m11_ov.c:194` の icall tkey 換算 (LVA → VA)。検証は子 #3296 で行い、判定は `m11_lb_unit_diff.py` の kind 差。

### 7-4 既知類型の判定 (`docs/DEFECTS.md`)

- 候補 D4 (`mov r64,[r8]` (disp=0, 引数 reg) の deref 脱落)。一致: 機械語 `mov (%rax),%rsi` は disp=0 の deref で、基底 rax は引数 arg1 の複写。IR に対応する load が無い (IR の `ptr null` 行から判断。kh_passes trace は未実行)。修復 (a) は「引数から load を挿入」で、D4 の f7 と同型。
- 相違: D4 の症状は「rD が基底 reg の値 (r8) に化ける」。本件は代用値が `ptr null` で、arg1 を参照しない。null の出所は未特定。
- **判定: D4 の変種として暫定登録** (検出信号と修復型は一致し、代用値だけが違う)。新類型ではないので行案は不要。D4 症状欄への追記は PM 判断 (DEFECTS.md の直接編集は PM)。

### 7-5 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 8 件の機構 (候補 (b)・(c)) の特定と修正 (kind 差 8 → 0) | LB 依存の寛容起動の結果 | 子 #3296 (親 #3229) |
| 全 7,422 関数の LB 差の全件確認 (`m11_lb_ir_fn_diff.py` を全件に適用) | 「LB 直書き無し」の範囲 (現状は確認した関数のみ) | 子 #3296 (work-m11・toolchain-emsdk が要る) |
| `m11_ov.c:194` の tkey 検証と LB=0 の address 0 (PE ヘッダ) の実測 | 候補のみ・#3229 記録の再確認は未実施 | 子 #3296 |
| `function_412770` の `ptr null` 源 (D4 変種) の lift 修正 | kind 差とは独立 (§7-3) | 子 #3296 (別受入) |
| D4 症状欄への「代用値 null」の追記 | DEFECTS の記述 | PM |

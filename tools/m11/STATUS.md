# M11 STATUS (最終更新: 2026-10-10)

## 現状
* **部分達成 (stage 4/6)**: DllMain attach → `_StartLib` → `_InitLib` → `InitUnits(942 unit)` → FastMM4 の GetMem/VirtualAlloc まで wasm 上で実行。
  通常起動は unit #18 (`function_455790`→`446400`→`_UStrAsg`) で OOB trap。unit 隔離 survey は ok 812 / trap 83 / closure 外 46 / proc 無し 1。
* **ldfix 常設化完了 (CAB-131)**: `m11_gen_ir2.sh` が ldfix (load 取り違え修復, F1+F1v+F2+F3a/F3b/F3c) を毎回適用。
  liftdiff `load_dropped` 892→**0** (CAB-231 で残 2)。全既存 e2e 回帰 (stage4 / survey / shimx_link 純リンク) は
  base↔fix 完全同一 (`ldfix/REPORT_CAB131.md`)。
* 再現: `bash tools/m11/m11_e2e.sh` (増分 約 10 秒 / `--full` 約 10 分で RetDec lift から全再生成)。常に exit 0、`M11_SUMMARY {json}` を出す。
  A/B 検収: `bash tools/m11/ldfix/embed_e2e.sh --batch`。
* 数値・原因・修正一覧は `REPORT.md`。CAB-131 の測定は `ldfix/REPORT_CAB131.md`。

## 未解決
1. unit #18 の `_UStrAsg` OOB (dest 旧値が不正; F3a 修復済みの残差 = COW increment 経路の別欠陥, CAB-231 §4.2)。
2. survey trap 83 (OOB 34 / Halt0 48 / abort 1)。上位ボトルネックは **callsite_arg_drop 257 (sigfix 0 詰めの意味補完)**
   → zero_init_drop/arg_drop 複合 42-46 → halt0 53 (`ldfix/REPORT_CAB131.md` §4.1 の優先順)。
3. closure 外呼出し 46 unit (間接 call 先; 例 0x41d0e0 系以外)。
4. `ucomisd/comisd` の flag 未反映 (FPU 比較分岐の意味未保証)、SEH 未対応、ロケール API は 0 を返す stub。
5. RetDec lift の意味保証が無い (間接 call 全滅 / stack 引数脱落 / 2 段 deref 脱落 / 署名不一致 6,600 件)。sigfix の 0 詰めは意味補完ではない。

## 次の一手
1. callsite_arg_drop の機械語突合修復 pass (`ldmach.py` 流用; stage 5 への最短経路, `ldfix/REPORT_CAB131.md` §4.1/§6)。
2. 複合欠陥 (F2 適用 8 関数) の複数 pass 同時適用 + verdict 反転数による結合試験。
3. halt0 53 unit: LoadStringW リソース接続 (shimx hostbridge, CAB-177 系) と 0x1027A4B0 クラスタ 17 unit の共通 helper 特定。
4. survey unit #18 の FastMM OOB (407a50) 単体差分、closure 外 46 unit の icall 表拡張。
5. stage 5/6 (全 unit 完走 → Halt0/longjmp → DllMain TRUE) の達成。

## コミット可否
* **コミット可** (部分達成として): `git add tools/m11` のみ。`work/` `__pycache__` は `.gitignore` 済 (RetDec 出力・IR・wasm・image は再生成物)。
* 他 dir (tools/m1..m10, shim, plugins 等) は未変更・未 add。

## 運用メモ
* node は PATH に無いことがある → `~/.local/share/pnpm/bin` (v26)。`m11_e2e.sh` が自動設定。
* `work/m11_image.bin` は実バイナリ由来 (22.5MB)。wasm に埋め込まず実行時にホストが HEAPU8 へ載せる (EULA 配慮)。コミットしない。

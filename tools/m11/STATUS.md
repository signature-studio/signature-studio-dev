# M11 STATUS (最終更新: 2026-10-10)

## 現状
* **部分達成 (stage 4/6)**: DllMain attach → `_StartLib` → `_InitLib` → `InitUnits(942 unit)` → FastMM4 の GetMem/VirtualAlloc まで wasm 上で実行。
  通常起動は unit #18 (`function_455790`→`446400`→`_UStrAsg`) で OOB trap。unit 隔離 survey は ok 812 / trap 83 / closure 外 46 / proc 無し 1。
* 再現: `bash tools/m11/m11_e2e.sh` (増分 約 10 秒 / `--full` 約 10 分で RetDec lift から全再生成)。常に exit 0、`M11_SUMMARY {json}` を出す。
* 数値・原因・修正一覧は `REPORT.md`。

## 未解決
1. unit #18 の `_UStrAsg` OOB (dest 旧値が不正; RetDec が local ゼロ初期化を落とした疑い、未検証)。
2. survey trap 83 (OOB 34 / Halt0 48 / abort 1)。`function_8cbcb0` (x9 unit 共通) が最優先。
3. closure 外呼出し 46 unit (間接 call 先; 例 0x41d0e0 系以外)。
4. `ucomisd/comisd` の flag 未反映 (FPU 比較分岐の意味未保証)、SEH 未対応、ロケール API は 0 を返す stub。
5. RetDec lift の意味保証が無い (間接 call 全滅 / stack 引数脱落 / 2 段 deref 脱落 / 署名不一致 6,600 件)。sigfix の 0 詰めは意味補完ではない。

## 次の一手
1. lift 検証ハーネス (native vs wasm の関数単位差分) → 誤 lift を機械検出 (最優先)。
2. Delphi RTL (System/SysUtils) は別 lifter か OSS ソースからの差し替えを検討。
3. 間接 call 復元 pass (Ghidra の vtable/jump-table 結果)。
4. `function_8cbcb0` 系 / unit #18 を逆アセンブル突合 → `m11_ov.c` に override 追加 → survey trap < 20 を目標。
5. stage 5/6 (全 unit 完走 → Halt0/longjmp → DllMain TRUE) の達成。

## コミット可否
* **コミット可** (部分達成として): `git add tools/m11` のみ。`work/` `__pycache__` は `.gitignore` 済 (RetDec 出力・IR・wasm・image は再生成物)。
* 他 dir (tools/m1..m10, shim, plugins 等) は未変更・未 add。

## 運用メモ
* node は PATH に無いことがある → `~/.local/share/pnpm/bin` (v26)。`m11_e2e.sh` が自動設定。
* `work/m11_image.bin` は実バイナリ由来 (22.5MB)。wasm に埋め込まず実行時にホストが HEAPU8 へ載せる (EULA 配慮)。コミットしない。

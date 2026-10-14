# liftdiff LD-27 (#1034): m11 型 B 候補 34 件の完全 trace 再検証と戻り後の分岐

本体 [`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) §9 の LD-27 節から分割移動した全文。件数・per-case の正本は [`results/m11_typeb_cause.md`](results/m11_typeb_cause.md)。

## 測定条件

- 測定 commit: `1838f64c` (コード変更の最後の commit)。以後の差分は tests/・results/ に無い (`git diff 1838f64c HEAD -- tools/liftdiff/tests tools/liftdiff/results` は空)。
- 素材: `fl-win64` (`extracted/block00031_PE.bin` のみ展開)・`work-m11` (`tools/m11/work/`)・`work-liftdiff` (`tools/liftdiff/work/`)。`toolchain-retdec`・`toolchain-emsdk` は展開していない (ビルドしないため不要)。
- 実行: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/liftdiff/tests/trace_fullcompare_typeb.py "$PWD/tools/liftdiff/targets/m11.json" > out.txt`。target は絶対パスで渡す (スクリプトが `tools/liftdiff` に chdir するため相対パスは読めない)。所要 6.5 s (load 0.08 〜 0.26)。
- 入力 batch 既定 = `tools/liftdiff/work/m11/batch_closure.jsonl` (trace_head 基準の型 B 候補 34 case)。各 case を xfill=1 / xfill=0 で完全 trace 比較した (68 行)。

## 結果

件数の正本は `results/m11_typeb_cause.md` §1。X = xmm0 入力の脱落、M = MXCSR 経路 (0x40a380 / 0x40a3b0)、R = 未特定。

- **xfill 仮説は棄却**。xfill=0 でも X が 25 件残る。native の xmm0 は xfill の人工値 (1.25+i) ではなく、呼出元が実際に計算した double (例: 0x3ff0・0x403b・0x4049) である。wasm 側の x0 は 0 のまま。
- **X (xmm_arg_drop)**: 代表例 `function_40c1d0` (sigs.json の `params` は `[]`)。機械語は `movsd [rbp+0x28], xmm0` で xmm0 の double を読むが、lift 後 IR は `%1 = xor i128 0, 0; %2 = call i64 @__asm_movsd(i128 %1)` に置換されており、wasm 側の入力は常に 0。0x40c1d0 の戻り後は `mov ecx,eax; cmp cx,0x8000; jb 0x40c24c` で、native は正の double の経路 (0x40c24c) へ、wasm は `rbx == 0` の経路 (`mov ecx,4; mov dl,1; call 0x40a1c0`) へ進み、FP 例外 (0x409730) で trap する。
- **M (MXCSR 経路)**: `function_40a3b0` (`stmxcsr [rsp]; pop rax; ret`) は IR で `call void @__asm_stmxcsr(i32 0); ret i64 0`。wasm の MXCSR 戻り値は常に 0。0 は FP 例外の全アンマスク扱いで、0x40a1c0 が `test eax, 0x20/0x10/8/4` で例外判定し `call 0x409730` へ進む。`tools/m11/m11_ov.c` (#417) は `function_40a3b0 → 0x1f80` の上書きを持つが、この IR には反映されていない。上書きの効果は未実測。
- **R (未特定)**: L = 0x12f9ed0 (大域ポインタの長さを返す leaf)・0xfea6a0 (引数オブジェクトのフィールドを読んで al を返す leaf)・0x4769f0 (完全 trace で notB)・0x40ae30 など。個別原因は未特定。

## 0x40a3d0 の戻り値 rax

0x40a3d0 は `movzx rax, word [rcx+rdx*2]; ret` の leaf。呼出元 0x40c1d0 は `movsd [rbp+0x28], xmm0` の後に `rcx = &[rbp+0x28]`、`edx = 3` で呼ぶ。よって rax = x0 の上位 16 bit。

- native: x0 の上位 16 bit を rax として得る (例: x0 = 0x3ff4000000000000 → rax = 0x3ff4)。
- wasm: x0 = 0 → rax = 0x0000。
- 件数と値の分布は `results/m11_typeb_cause.md` §2。

**注**: rax は leaf の戻り値を直接ダンプしていない (runner に戻り値の記録が無い)。trace の x0 と逆アセンブルから導出した値。直接の実測は runner 側の計装が要る。受入条件の「実測」はこの点で未達。

## 再現手順

1. `work-m11` (`tools/m11/work/`) と `work-liftdiff` (`tools/liftdiff/work/`) を展開する (`tar --zstd -xf <name>.tar.zst -C <repo>`)。
2. `fl-win64` から `extracted/block00031_PE.bin` を取り出し、`FL_WIN64_DIR` を展開先に設定する。
3. 上記の実行コマンドを流す。出力は `results/m11_typeb_cause.md` §3 と一致する。

## 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| R (xfill 別の延べ 9 件) の個別原因 (大域の初期状態・引数オブジェクトの読み) | 型 B 受入条件 1 | #1034 に残す (次 run) |
| M (延べ 6 件) の wasm MXCSR 戻り値 0 の修正効果 (`m11_ov.c` 上書きを liftdiff build に適用したときの一致) | M 類の解消可否 | #1034 に残す (wasm 再ビルドが要る) |
| X 類の修復 (xmm0 入力の接続・sig の float 引数) | X 類 (xfill 別 28 / 25) | 既存 #547 (PLG-F2-4 の ARG pass 接続) |
| rax の直接計測 (runner の戻り値計装) | 受入条件 2 (導出値のみ) | #1034 に残す |
| trace_head 基準の L 算出の不正確さ (集計スクリプトの修正) | 型 B 候補の件数 | 既存 #864 |

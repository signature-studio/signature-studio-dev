# liftdiff LD-27 (#1034): m11 型 B 候補 34 件の完全 trace 再検証と類型分類

LD-27 (#1034) の分析と再現手順の正本。件数・per-case の出力は [`results/m11_typeb_cause.md`](results/m11_typeb_cause.md) (生成物。`## 集計` 行が件数の正本)。本体 [`REPORT_APPENDIX.md`](REPORT_APPENDIX.md) §9 は本ファイルへの参照 1 行だけを持つ。

**結論**: xfill 仮説は棄却 (xfill=0 でも X 類が残る)。X 類 (xmm0 入力の脱落) と M 類 (MXCSR 経路) は機構を特定した。R 類は個別原因が未特定。rax の直接計測も未完のため、#1034 は `Refs` のまま残す。

## 測定条件

- 測定 commit: `1838f64c` (測定時のコード)。その後 `9d900e5e` で `reads_xmm0` の到達不能分岐 (2 行) を削除した。出力は変わらない (削除した `if` は、直前の `if` (`WRITE_ONLY` が `xorps`・`xorpd`・`pxor` を含む) が必ず先に `return False` するため到達しない)。ただし削除後の再実行による確認は未実施 (`work-m11` が素材に無い)。
- 素材: `fl-win64` (`extracted/block00031_PE.bin` のみ展開)・`work-m11` (`tools/m11/work/`)・`work-liftdiff` (`tools/liftdiff/work/`)。`toolchain-retdec`・`toolchain-emsdk` は展開していない (ビルドしないため不要)。
- 実行: `FL_WIN64_DIR=<fl-win64 展開先> python3 tools/liftdiff/tests/trace_fullcompare_typeb.py "$PWD/tools/liftdiff/targets/m11.json" > out.txt`。target は絶対パスで渡す (スクリプトが `tools/liftdiff` に chdir するため相対パスは読めない)。所要 6.5 s (load 0.08 〜 0.26)。
- 入力: `work/m11/batch_closure.jsonl` の trace_head 基準の型 B 候補 34 case (`results/m11_unreachable_diverge.md` §2)。各 case を xfill=1 / xfill=0 で完全 trace 比較した (68 行)。

## 類型

class は `results/m11_typeb_cause.md` の各 case 行の `class=` 欄。件数は集計行を参照する。

- **X (xmm_arg_drop)**: 呼出元 (または L) の entry で「xmm0 を書かれる前に読む」関数があり、その entry の x0 が native ≠ wasm。IR では該当関数の xmm0 入力が `call i64 @__asm_movsd(i128 0)` (`xor i128 0, 0`) に置き換わる (例: `function_40c1d0`)。既存類型 `xmm_arg_drop` (`tools/liftdiff/docs/FORMAT.md` の類型表 107 行)。修復は #547 (PLG-F2-4) の接続で行う。
  - `function_40c1d0` は sig の `params` が `[]` だが、機械語は `movsd [rbp+0x28], xmm0` で xmm0 の double を読む。戻り後は `mov ecx,eax; cmp cx,0x8000; jb 0x40c24c` で、native は正の double の経路 (0x40c24c) へ進み、wasm は `mov ecx,4; mov dl,1; call 0x40a1c0` の経路で FP 例外 (0x409730) により trap する。
- **M (MXCSR 経路)**: L = 0x40a380 (`stmxcsr`/`ldmxcsr` で MXCSR を書く leaf) または 0x40a3b0 (`stmxcsr [rsp]; pop rax; ret` で MXCSR を返す leaf)。wasm の `function_40a3b0` は IR で `call void @__asm_stmxcsr(i32 0)` + `ret i64 0` (`work/m11/ir_instr.ll` の `define weak i64 @function_40a3b0`) のため戻り値は常に 0。native の戻り値は実際の MXCSR (既定値 0x1f80 のため 0 ではないと想定するが、直接計測していない)。0 は FP 例外の全アンマスク扱いとなり、0x40a1c0 の FP 例外判定 (`test eax, 0x20/0x10/8/4` → `call 0x409730`) が wasm 側で例外を送出する。`tools/m11/m11_ov.c` は同じ欠陥 (#417) に `function_40a3b0 → 0x1f80` の上書きを持つが、この IR (liftdiff の build) では `ret i64 0` のままで、上書きは反映されていない。上書きの効果は未実測。
- **R (未特定)**: X にも M にも入らない。戻り後の分岐は各 case 行の `post`・`jcc` 欄。`class=R` の行は次のとおり。
  - xfill=1: fn=0xcd1c20 (L=0xcd1a70、完全 trace で notB)、fn=0xf3c7b0・0xe24ee0・0xe26510 (L=0x12f9ed0、大域ポインタの長さを返す leaf と読むが未確認)。
  - xfill=0: fn=0xf3c7b0・0xe24ee0・0xe26510 (L=0x12f9ed0)、fn=0x4769f0 (L=0x4769f0、完全 trace で notB)、fn=0xff0600 (L=0xfea6a0、引数オブジェクトのフィールドを読んで al を返す leaf と読むが未確認。0xff0600 の `je` が al で決まる)。
  - 注: L=0x40ae30 (fn=0x12e5d80) は両 xfill とも X であり R ではない。個別原因は未特定。

## 0x40a3d0 の戻り値 rax

0x40a3d0 は `movzx rax, word [rcx+rdx*2]; ret` の leaf。呼出元 0x40c1d0 は `movsd [rbp+0x28], xmm0` の後に `rcx = &[rbp+0x28]`、`edx = 3` で呼ぶ。よって rax = x0 の上位 16 bit (x0 は呼出元 entry の x0)。wasm 側の x0 は X 類の行で 0 となる。

値の分布 (L が 0x40a3d0 の行の native 側の上位 16 bit。`results/m11_typeb_cause.md` の各 case 行から再計算した件数。wasm の rax は全件 0x0000):

| rax (native) | xfill=0 | xfill=1 |
|---:|---:|---:|
| 0x3f84 | 1 | 1 |
| 0x3fe2 | 1 | 1 |
| 0x3fe6 | 1 | 1 |
| 0x3ff0 | 2 | 2 |
| 0x3ff4 | 0 | 3 |
| 0x4000 | 3 | 3 |
| 0x403b | 3 | 3 |
| 0x4049 | 2 | 2 |
| 0x4071 | 0 | 1 |
| 0x408f | 3 | 3 |
| 0x40b8 | 1 | 1 |
| 0x40c3 | 2 | 2 |
| 0x40d5 | 1 | 1 |
| 0x7ff0 | 1 | 0 |
| 計 | 21 | 24 |

注: rax は leaf の戻り値を直接ダンプしたものではない (runner に戻り値の記録は無い)。trace の x0 と逆アセンブルから導出した値。直接の実測は runner 側の計装が要る (#1034 の残り)。xfill=0 でも native の x0 は非ゼロ (例: 0x3ff0・0x403b) で、wasm は 0 のまま。よって X の差は xfill の人工値だけでは説明できない。

## 再現手順

1. `work-m11` (`tools/m11/work/`) と `work-liftdiff` (`tools/liftdiff/work/`) を展開する (`tar --zstd -xf <name>.tar.zst -C <repo>`)。`work-m11` が無いときは `bash tools/m11/m11_gen_ir2.sh` で `ir_conditions.json` と IR を作る。
2. `fl-win64` から `extracted/block00031_PE.bin` を取り出し、`FL_WIN64_DIR` を展開先に設定する。
3. 「測定条件」の実行コマンドを流す。出力は `results/m11_typeb_cause.md` の本文 (ヘッダコメントを除く) と一致する (測定時は `cmp` で差 0)。

## issue #1034 からの逸脱

- 生成元は新規の `tests/trace_fullcompare_typeb.py` (issue は `tests/trace_diverge_unreachable.py` §1b の拡張を指定)。理由: 完全 trace の runner 起動が要り、batch jsonl だけを読む §1b の集計に混ぜないため。
- 再現手順の記載先は本ファイル (issue は `REPORT_APPENDIX.md` §9 への追記を指定)。§9 は既に行数上限を超えているため、本文は新規ファイルに置き、§9 には参照 1 行だけを置く。

## 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| R 類 (集計行の R 件数) の個別原因 (大域の初期状態・引数オブジェクトの読み) | 型 B 受入条件 1 | #1034 (Refs) |
| M 類の wasm MXCSR 戻り値 0 の修正効果 (`m11_ov.c` 上書きを liftdiff build に適用したときの一致) | M 類の解消可否 | #1034 (wasm 再ビルドが要る) |
| X 類の修復 (xmm0 入力の接続・sig の float 引数) | X 類 | 既存 #547 (PLG-F2-4 の ARG pass 接続) |
| rax の直接計測 (runner の戻り値計装) | 受入条件 2 (導出値のみ) | #1034 |
| trace_head 基準の L 算出の不正確さ (full-trace で L が変わる件の型 B 再判定) | 型 B 候補の件数 | #1034 (旧 #864 は CLOSED) |
| `9d900e5e` (到達不能分岐 2 行の削除) の実行確認 | 出力不変は論理で確認。実行は未実施 | #1034 (work-m11 の取得後に再実行) |

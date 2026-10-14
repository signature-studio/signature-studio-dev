# icall REPORT 付録: Fresh Air 残落ち 6 件の欠落段の特定 (ICALL-35 / #1612)

> 親: #1454 (ICALL-29)。前段は `REPORT_APPENDIX_1454.md`。計測は `diff/fa_call_trace.py`。

## 0. 結論 (本 run の到達点)

- 受入条件は一部達成。`lost 0` は未達 (修復はしていない)。
- **報告 (本 run で再確認できず)**: 残落ち 6 件の間接 call は、RetDec の **LLVM IR 化 (decode 段 = pass "Input binary to LLVM IR decoding")** で既に call 命令として存在しない。`.dsm` (逆アセンブル) には 6 件すべてある。根拠の stderr ログ・`.dsm` は本 run の環境に無く、§1 の抜粋は貼れない (後述)。
- **報告 (前 run の計測値、本 run で未再確認)**: 前任の「decode 直後の dump に間接 call が無い」は、decoder 段の欠落そのものの観察だった。前任の付録 §4 の解釈を訂正する候補 (確定ではない)。
- **未確定**: decoder 内部のどの処理が call を消すか (pass 名まで未特定)。`0x180c97aa0` の `*(var12) = -1` 警告 5 件との対応も未確認。
- 段の切り分けは「decode 段で消える」まで。以降の段 (pass 143 以降は `!insn.addr` 追跡に切り替わる) での生存は連続判定できていない。

## 1. 計測 (実測)

素材: `plugins-freshair` (`Fresh Air.Win.zip` → `SlateCore.core_64`)、`work-icall` (`rt_freshair-core`)、RetDec v5.0 ([RETDEC])。

- **本 run の環境の状況 (実測)**: `[RETDEC]` は無く、`work-icall`・`plugins-freshair` は未取得 (`$HOME/artifacts` は `fl-win64` のみ)。以下の数値・表は前 run の計測報告で、本 run では再実行していない。stderr ログと `.dsm` も本 run の環境に残っていないため、`fa_call_trace.py` の出力抜粋 (`dumps` 行・6 件の `alive/GONE/n/a` 行) と `.dsm` の該当行は貼れない。
- 基準 `python3 tools/icall/diff/fa_residual.py tools/icall/work/rt_freshair-core` は `lost 6` を再現 (前任と一致)。 ※前 run の報告値
- RetDec 単独実行 (`--select-decode-only --backend-no-opts --output-llvmir --print-after-all`):
  - `0x180c97aa0-0x180c97ee0`: 実行 11 秒、dump 294 段。
  - `0x180da6e60-0x180da73b5`: dump 308 段。
- 判定は `python3 tools/icall/diff/fa_call_trace.py <stderr.log>`。

| VA | 逆アセンブル | decode 段 (pass 001 / pass 1 相当) |
|---|---|---|
| `0x180c97e17` | `call [rax+0x10]` | GONE (`br label` に置換) |
| `0x180c97e38` | `call [rax+0x20]` | GONE |
| `0x180c97e56` | `call [rax+8]` | GONE |
| `0x180c97e71` | `call [rax+0x20]` | GONE |
| `0x180da7261` | `call [rax+0x30]` | GONE (直後は `load @rax` 系に置換) |
| `0x180da72fc` | `call [rax+0x30]` | GONE |

- `.dsm` の間接 call は `0x180c97aa0` 範囲に 4 件 (`0x180c97e17`・`0x180c97e38`・`0x180c97e56`・`0x180c97e71`)。`0x180da6e60` 側は 2 件。計 6 件。
- decode 直後の IR で `0x180c97e00-0x180c97e80` にある "call" 11 件は、すべて `llvm.ctpop` (パリティ intrinsic)。間接 call の数え方に注意。

## 2. 段の切り分け (実測と限界)

※ 以下の表の「6 件の生存」列は**前 run の計測値** (本 run では未再確認)。

| 段 | 判定方法 | 6 件の生存 | 限界 |
|---|---|---|---|
| `.dsm` (RetDec decode 命令) | 逆アセンブル | 6 件あり | — |
| decode 直後 (pass 001) | `; 0xVA` コメント直後の call 行 | 6 件 GONE | pass 内部の処理は未特定 |
| pass 142 (Disassembly generation) | VA コメント | VA コメントあり・`!insn.addr` 無し | 生存は判定していない (コメント判定は decode 段専用) |
| pass 143 以降 | `!insn.addr` メタデータ | 判定の連続性は未検証 | VA 表現が 142→143 で切り替わるため、段間の比較は不能 |

- 前任 §3 の `--backend-no-opts` の結果は、decoder 段で既に消えていたため当然の結果だった。backend の最適化が原因ではないことは、この計測でも支持される (ただし pass 143 以降の連続判定は未完)。

## 3. 未解決 (起票先)

| 項目 | 状態 | 起票先 |
|---|---|---|
| decode 段内で間接 call を消す処理の特定 (pass 名・条件) | 未達 | #1844 (ICALL-43、親 #1612) |
| pass 143 以降の `!insn.addr` 追跡の連続判定 | 未達 | #1844 (ICALL-43) |
| `0x180c97aa0` の `*(var12) = -1` 警告 5 件との対応 | 未達 | #1844 (ICALL-43) |
| `lost 0` (修復 / 段と条件の分類) | 未達 | #1844 (ICALL-43) |
| 本 run で未再確認の §1 計測 (素材 `toolchain-retdec plugins-freshair work-icall` が必要) | 未検証 | 本 PR の未解決表で追跡 (再実行は PR 本文の `oc_artifacts` 行で依頼) |

## 4. 再現手順

`$RETDEC` は `docs/REFERENCES.md` の `[RETDEC]` の所在 (環境変数で指定)。

```
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" tools/icall/work/rt_freshair-core   # 素材名は docs/WORKFLOW.md §11
python3 tools/icall/diff/fa_residual.py tools/icall/work/rt_freshair-core
mkdir -p "$RUNNER_TEMP/plugins-freshair" && tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$RUNNER_TEMP/plugins-freshair"
unzip -q -o "$RUNNER_TEMP/plugins-freshair/Fresh Air.Win.zip" '*SlateCore.core_64' -d "$W"
"$RETDEC/bin/retdec-decompiler" SlateCore.core_64 -o f.c --select-ranges 0x180c97aa0-0x180c97ee0 --select-decode-only --backend-no-opts --output-llvmir f.ll --print-after-all 2> stderr.log
python3 tools/icall/diff/fa_call_trace.py stderr.log
```

一時展開先と `work/` 配下の dump は gitignore 対象で、commit していない。

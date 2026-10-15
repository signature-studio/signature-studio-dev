# icall REPORT 付録: Fresh Air 残落ち 6 件の decode 段での消失 (ICALL-43 / #1844)

> 親: #1612 (ICALL-35)。前段は `REPORT_APPENDIX_1612.md`。計測は `diff/fa_call_trace.py`。

## 0. 結論 (本 run で再確認した範囲)

- 基準 `fa_residual.py` は `lost 6` を再現 (前 run の値と一致)。修復はしていない (`lost 0` は未達)。
- **本 run で確認**: 6 件の間接 call は、RetDec の「Input binary to LLVM IR decoding」段で既に消えている。`fa_call_trace.py` の判定で `0x180c97aa0` 系 4 件・`0x180da6e60` 系 2 件とも decode 段で GONE。
- **本 run で確認**: 消える機構は `Decoder::resolvePseudoCalls()` (decoder.cpp) で、`getJumpTarget` が `Address::Undefined` を返した pseudo call について、直後の命令と `store @_asm_program_counter` を削除する経路。RetDec v5.0 の該当ソースで読めた (§3)。
- **未確定**: 6 件それぞれで `getJumpTarget` が未定義を返した具体的な値 (SymbolicTree の形)。`0x180c97e17` だけ `br` 1 本で残る理由。`*(var12) = -1` 警告 5 件との対応。pass 143 以降の連続追跡。

## 1. 計測 (本 run・実測)

素材: `toolchain-retdec` (RetDec v5.0・展開先は `$RUNNER_TEMP/rt-ex/retdec`)、`plugins-freshair` (`Fresh Air.Win.zip` の `SlateCore.core_64`、36,285,952 B)、`work-icall` (`tools/icall/work/rt_freshair-core`)。

| 項目 | 結果 |
|---|---|
| 基準 `fa_residual.py tools/icall/work/rt_freshair-core` | `non-IAT call sites 91 / lost 6` (`by IR status: {'other_insn:br': 1, 'dropped': 5}`) |
| RetDec 単独実行 1 (範囲 `0x180c97aa0-0x180c97ee0`) | rc=0・13.6 秒・dump 294 段・stderr 4.85 MB |
| RetDec 単独実行 2 (範囲 `0x180da6e60-0x180da73b5`) | rc=0・phase 合計 14.97 秒 (実行 1 の phase 合計 13.55 秒)・dump 308 段 |
| `fa_call_trace.py` (実行 1) | `[001] Input binary to LLVM IR decoding` で `c97aa0` 4 件 GONE。`da6e60` 2 件は範囲外で n/a。`[143] Assembly mapping instruction removal` で全 6 件 GONE |
| `fa_call_trace.py` (実行 2) | `[001] Input binary to LLVM IR decoding` で `da6e60` 2 件 GONE。`c97aa0` は範囲外で n/a |

実行コマンド (両方とも `--select-decode-only --backend-no-opts --output-llvmir --print-after-all`)。

### decode 直後 IR の観察 (実行 1)

- `0x180c97e17` (`call [rax+0x10]`): VA コメント直後が `store volatile ... @_asm_program_counter` → `br label %dec_label_pc_180c97e1a`。call 行なし。
- `0x180c97e38` (`call [rax+0x20]`)・`0x180c97e56` (`call [rax+8]`)・`0x180c97e71` (`call [rax+0x20]`): VA コメント直後の store の後に call 行なし (次の VA コメントへ直行)。
- decode 直後 IR の非 intrinsic な `call` は 11 行 (`function_*` への直接 call) で、`[rax+...]` 型の間接 call は 1 つも残らない。
- `declare void @__pseudo_call(i64)` は宣言のみで、本体の使用は decode 段の出力に無い。

### 数え方の注意

- `0x180c97e00-0x180c97e80` の "call" 11 件は、すべて `llvm.ctpop` (パリティ intrinsic)。間接 call の数え方に使わない。`fa_call_trace.py` は intrinsic を除外する。

## 2. 段の切り分け

| 段 | 判定方法 | 6 件の状態 (本 run) | 限界 |
|---|---|---|---|
| `.dsm` (`before.0.drc.dsm`) | 逆アセンブル | 6 件あり (`call qword ptr [rax + ...]`) | `after.0.drc.dsm` の解釈は本 run で未確認 |
| decode 直後 (pass 001) | `; 0xVA` コメント直後の call 行 | 6 件 GONE | 消去の機構は §3 (ソース側) |
| `[143] Assembly mapping instruction removal` (`fa_call_trace.py` 出力の段名) | `fa_call_trace.py` の判定 | 6 件 GONE (実行 1 は全 6 件、実行 2 は範囲内の 2 件) | `[143]` は `fa_call_trace.py` の dump 番号 |
| pass 143 以降 | `!insn.addr` メタデータ | 連続判定は未検証 | VA 表現の切替で段間比較ができない |

## 3. 消去の機構 (RetDec v5.0 ソース)

`src/bin2llvmir/optimizations/decoder/decoder.cpp` (tag v5.0) を読んだ。

1. `Decoder::resolvePseudoCalls()` (1474 行付近): 各 pseudo call について `getJumpTarget(addr, pseudo, arg0)` を呼ぶ。戻り値が `Address::Undefined` なら、後続の `real` 命令を `user_begin()` の store ごと `eraseFromParent()` する。
2. `Decoder::getJumpTarget()` (823 行付近): `SymbolicTree::OnDemandRda(val, 20)` で値を解く。定数に畳めれば `ci->getZExtValue()` を返す。load を `_imports` と照合し、`getJumpTargetSwitch()` で switch を認識できれば `Undefined`。それ以外は最後に `Undefined` を返す。
3. `[rax+disp]` の間接 call は、レジスタ `rax` の値が静的に定数にならないため、(2) の最後の `Undefined` に落ちると読める。これは未確認の仮説で、6 件それぞれの SymbolicTree の値は未検証。

**限界**: §3 は上流 v5.0 のソースとの照合。同梱バイナリの RetDec が同じ版であることは `retdec-fileinfo` 等で確かめていない (`[未確認]`)。

## 4. 未解決 (起票先)

| 項目 | 状態 | 起票先 |
|---|---|---|
| 6 件それぞれで `getJumpTarget` が `Undefined` を返した値 (SymbolicTree) の確定 | 未達 | #4206 (ICALL-95) |
| `0x180c97e17` が `br` 1 本で残る理由 | 未達 | #4206 (ICALL-95) |
| `*(var12) = -1` 警告 5 件との対応 | 未達 | #4206 (ICALL-95) |
| `lost 0` (修復 / 段と条件の分類) | 未達 | #4206 (ICALL-95) |
| pass 143 以降の `!insn.addr` 追跡の連続判定 | 未達 | 本 PR の REPORT で未解決 (再測定のみのため子を立てない) |
| 同梱 RetDec と v5.0 ソースの版一致 | `[未確認]` | 本 PR の REPORT で未解決 (確認のみのため子を立てない) |

## 5. 再現手順

```
tar --zstd -xf "$ARTIFACTS_DIR/toolchain-retdec.tar.zst" -C "$RUNNER_TEMP/rt-ex"
tar --zstd -xf "$ARTIFACTS_DIR/work-icall.tar.zst" tools/icall/work/rt_freshair-core
python3 tools/icall/diff/fa_residual.py tools/icall/work/rt_freshair-core
mkdir -p "$RUNNER_TEMP/pf" && tar --zstd -xf "$ARTIFACTS_DIR/plugins-freshair.tar.zst" -C "$RUNNER_TEMP/pf"
unzip -q -o "$RUNNER_TEMP/pf/Fresh Air.Win.zip" '*SlateCore.core_64' -d "$RUNNER_TEMP/fa"
RETDEC_BIN="$RUNNER_TEMP/rt-ex/retdec/bin/retdec-decompiler"
"$RETDEC_BIN" "$RUNNER_TEMP/fa/SlateCore.core_64" -o f.c --select-ranges 0x180c97aa0-0x180c97ee0 --select-decode-only --backend-no-opts --output-llvmir f.ll --print-after-all 2> stderr.log
python3 tools/icall/diff/fa_call_trace.py stderr.log
```

一時展開先と `work/` 配下の dump は gitignore 対象で、commit していない。

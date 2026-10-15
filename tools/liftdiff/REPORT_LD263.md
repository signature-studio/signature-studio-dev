# liftdiff LD-263 (#5277) — `6ed480` の戻り型 (double / float) の判定

> 親 #4666 (LD-233) の R4 分割の子。前段 [`REPORT_LD215.md`](REPORT_LD215.md) §1 で「候補 (xmm0) は確定、型は未確定」だった 1 件。
> LD-158 (`REPORT_LD158.md` §3.1) は同関数を『rax 書換えあり・区別不能』で対象外にしていた。
> 結論: **戻り型は double と判定する**。`targets/m11.json` の `ret_override` は本 PR では変えない (親 #4666 / #5276 の受入で e2e とともに反映する)。

## 1. 結論

- `6ed480` の戻りは、`.data` の定数表 (VA `0x13f1cb8`) から `movsd xmm0, qword ptr [rax + rcx*8]` で読んだ **8 バイト**。単精度なら `movss` になるため、戻り型は double。
- rax は戻り値ではなく、表の番地 (`lea rax, [rip + 0xd04831]`) の計算。LD-158 が『rax 書換えあり』としたのはこれで、戻りの決定を妨げない。
- 呼出し元 3 件 (`6ece54`・`6ed54d`・`6eedda`) は、いずれも直後の最初の xmm0 読みが `ucomisd` (倍精度比較)。比較相手の絶対値は `pand` で 64 bit マスク `0x7fffffffffffffff` を掛けている。float なら 32 bit マスクになるため、double と整合する。
- 判定器 `tests/ld263_ret_type.py` の出力は `判定: double` (3 件とも OK、終了 0)。

## 2. 方法 (再現)

- 入力: `FL_WIN64_DIR` の PE `extracted/block00031_PE.bin` (fl-win64 素材 26.1.7.5653 を `$RUNNER_TEMP/fl-win64` に展開)。
- 実行: `python3 tools/liftdiff/tests/ld263_ret_type.py $FL_WIN64_DIR/extracted/block00031_PE.bin`。
- 処理: callee を entry から ret まで逆アセンブルし、ret 直前命令を確認する。表の 0・1 番目を読み値を出す (関数は `test ecx,1; setne` で 0/1 にしか添字を取らない)。呼出し元は、E8 走査で得た 3 件の call 直後から、xmm0 を最初に読む命令を探す。
- 実測: 0.096 秒 (wall。1 回目)。

## 3. 実測

| 項目 | 結果 |
|---|---|
| callee `6ed480` の ret 直前 | `movsd xmm0, qword ptr [rax + rcx*8]` (8 バイト読み) |
| 表 `[0]` / `[1]` (double 解釈) | `9.5367431640625e-07` / `0.5` |
| 呼出し元 `6ece54` の ucomisd 直前マスク | `0x7fffffffffffffff` (64 bit) |
| 呼出し元 `6ed54d` の ucomisd 直前マスク | `0x7fffffffffffffff` (64 bit) |
| 呼出し元 `6eedda` の ucomisd 直前マスク | `0x7fffffffffffffff` (64 bit。`pand xmm1, [rip+0x31]` の読み) |
| 判定 | **double** |

- 注: 表の `[2]` (`0x40490fdb00001413`) と `[3]` (`0x3fc90fdb00000000`) は double として意味を持たない値。関数は添字 0/1 しか使わないため、判定には影響しない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `targets/m11.json` の `ret_override` への反映と e2e (`--m11-only`) PASS | 本 PR では e2e を回していない。`ret_override` は未変更 | #4666 (LD-233) / #5276 |
| 呼出し元の利用が『比較のための絶対値』か『戻り値の利用』か | 比較は戻り値の利用の証拠だが、比較前の値の再利用は完全には排除できない。型判定 (double) には影響しない | #4666 (LD-233) |

## 5. 測定 commit

- 測定 commit: `d53969e98`。

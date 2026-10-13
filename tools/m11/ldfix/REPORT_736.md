# #736 (LD-14): 旧 F3c (block-local) が修復した 15 関数の正しさの再点検

**判定: 部分達成**。旧 F3c-block の 16 関数のうち、戻り値 reg へのコピーだけを修復していた **12 関数の誤修復を門で外した**。残る 3 関数 (10165c0 / 1016970 / 1017ad0) は機械語と一致する修復で、維持した。liftdiff による動的確認は未実施 (§4)。

先行: #509 (`REPORT_509.md` §2.1・§6)。

## 1. 受入条件別

| 受入条件 | 結果 |
|---|---|
| 15 関数の戻り値の由来と修復後 IR の戻り値の突合 | **達成** (§2。逆アセンブルで `rax` の由来を確認) |
| 誤っていたものは門を絞る / 修復を外し、差分を記録 | **達成** (§3。12 関数の門を外した。差分は 12 関数のみ) |
| 動的確認 (native 比較) が必要なものは liftdiff | **未達**。§4 |

## 2. 突合 (機械語 vs 修復後 IR)

`ldmach.Machine.disasm_fn` で fl-win64 の `block00031_PE.bin` を逆アセンブルし、15 関数の全命令列を見た (capstone 5.x / pefile、`$RUNNER_TEMP/venv`)。

- **誤り (12 関数)**: 5c1030 / 607b90 / 6088a0 / 60f010 / 6214a0 / 737d10 / 73b300 / 7cbc20 / 7ff6e0 / 840720 / d243c0 / e404e0。
  戻り値は `mov rax,rcx` (引数ポインタ自身) で、`mov rbx,[rcx]` は `call [rbx+0x18]` の vtable 読みにしか使われない。旧修復は `store i64 %arg1, %rax.N.reg2mem` を `load i64 [%arg1]` 経由に変えており、戻り値が `*arg1` に化けていた。
- **正しい (3 関数)**: 10165c0 / 1016970 / 1017ad0。機械語 `mov rax,[r8]` (= `*arg3`) を stack slot に保存しており、修復 (`store *arg3`) と一致。
- **正しい (409c80)**: §2.1 の 4B path。REPORT_509 §4.4 の動的確認で PASS 済み。

## 3. 門の変更 (`ldfix.py` `fix_f3c_block`)

読んだ値 `rD` が同幅で memory に store されない site を見送る (`f3c_no_val_store`)。`mov rax,rcx` (reg コピー) と call 先は値の store ではないので対象外。

同じ修復前 IR (`boot_final2.ll`) に HEAD 版と変更版を適用し、ラベル接尾辞の SSA 名 (`ldfx*N`) を正規化して比較:

| 比較 | 結果 |
|---|---|
| 本体が異なる関数 | **12** (= 上記の誤り 12 関数。他は一致) |
| `f3c_fns` (block-local の 16 → ) | 修復対象から 12 関数が外れ、残りは 10165c0 / 1016970 / 1017ad0 / 409c80 |
| `audit_lsf.py` の summary (HEAD vs 変更版) | 同一 (`suspect_use_fns` 7、`suspect_mixed_fns` 69、`SUSPECT_VAS` 空) |

注: `fix_f3c_fn` (関数単位収支門) の結果は変更していない。HEAD 版と変更版で `f3c_fns` の総数は 48 → 36 と減るが、それは block-local の 12 を外した分。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修復 (旧) を外した 12 関数の wasm 側の動的確認。liftdiff で native と突合していない | 門の変更が survey / liftdiff の結果を変えるかは未測定 | 本 issue の子 (要 `oc_artifacts: fl-win64 toolchain-emsdk work-m11 work-liftdiff`)。起票は PM 判断 |
| wasm 再ビルドと survey 942 unit の突合 | 未実施 | 同上 |

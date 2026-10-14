[付録] `REPORT.md` §9-4 の分割移動先 (#1721)。本体の結論 1 行は `REPORT.md` §9-4 を参照。

### 9-4. `0x44a4d8` の wasm 実測 (#1721; 仮説の一部を棄却)

wasm 側で `0x44a4d8` 周辺の値を probe で実測した (`0x44a4b0` 入口 → `0x44a4db` dispatch 直前)。検証 commit: `main` (576c4976) 上の `tools/liftdiff/work/flelift/` (work-liftdiff 同梱) から派生。

* probe の方法: `fle_lifted_tr.c` のコピーに `ld_fle_probe(tag, v)` を挿入し、`fle_ldbridge.c` のコピーに同関数 (`ld_trace_rec` で `va=0xBEEF..|tag` として記録) を足して `lifted.o`・`bridge.o` だけ再コンパイルした。リンクは `clift.py` と同じフラグ。出力は `tools/liftdiff/work/flelift_probe/` (gitignore、commit しない)。素材の `ld_wasm.cjs` は変更していない。
* 実行: `liftdiff.py run <flelift_probe target> --fn 0x44a590 --pattern p0 --nobuild` (1 case 約 6 秒)。

| probe | 実測値 (wasm) | 意味 |
|---|---|---|
| `[0x15ec5d0]` (ガード) | `0x1e519c0` | 非 0。`je 0x44a4e9` を取らず `0x44a4d8` の分岐に入る |
| `rax` (= `[0x15ec5d0]`) | `0x1e519c0` | |
| `rbx` = `[rax]` (vtable ポインタ) | `0x42f698` | **0 ではない**。仮説「`[rax]` が 0」は棄却 |
| `[rbx-0x28]` (dispatch 先) | `0x0` | `ott_dispatch(0)` → `ott_unlifted` (ret 0) |
| vtable `[0x42f670..0x42f6a0]` (6 slot) | **すべて 0** | PE 上の初期値は `0x449380`・`0x4493a0` 等の有効値 (PE 静的読み) |

* 結論 (wasm 実測): 分岐は「`[rax]` = 0」ではなく、「vtable 本体 (`0x42f670` 付近) が実行時に 0」で `ott_dispatch(0)` に落ちる。原因は vtable の書込み欠落の疑い。
* 根拠の補足: `work/flelift/boot_state.json` の image 書込み run (60 本) に `0x42f670..0x42f6b0` を覆うものは無い。つまり hybrid boot の image 状態では、この vtable は PE の初期値に戻っていない (未書込み扱いで 0)。
* 未確定 (次の着手点): (1) native 側で同じ VA が PE 初期値 (`0x449380`) のままか。native は同じ入口で `0x415c30` に入るので、native の実行時メモリでは vtable が有効なはず。(2) 0 になる原因 (boot の image 書込み経路・heap/image の復元・`ld_w_fix` 等のどれか) の特定。(3) 退行 5 件のうち、同じ vtable 欠落で説明できるものの列挙 (未実施)。

受入条件との対応 (#1721): (1) 読み値の実測 = 達成 (上表)。(2) 仮説の成否 = 部分 (`[rax]` 仮説は棄却、vtable 0 は確定、原因は未特定)。(3) 退行 5 件の列挙 = 未実施。(4) 修復 = 範囲外。

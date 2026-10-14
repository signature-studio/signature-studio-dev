[付録] `REPORT.md` の §9-5 の分割移動先。本体の結論 1 行は `REPORT.md` §9-5 を参照。

### 9-5. vtable `0x42f670` の native / wasm 実測と敷設経路 (#1936)

測定 commit: `46faf265` (origin/main 取り込み後の作業ブランチ `1936-vtable-zero-probe` の起点。コード変更なし)。
素材: `fl-win64` (`$RUNNER_TEMP/fl-win64`) と `work-liftdiff` (`tools/liftdiff/work/`) を展開。probe 用の一時スクリプトは `tools/liftdiff/work/tmp/` (gitignore・commit しない)。

| 測定 | `0x42f670` | `0x42f680` | `0x42f690` | 備考 |
|---|---|---|---|---|
| native fresh (entry 前) | `0x449380` | `0x40f9b0` | `0x40f9d0` | PE 初期値と一致 |
| native hybrid boot 後 | `0x449380` | `0x40f9b0` | `0x40f9d0` | `0x42f670..0x42f6a0` の 6 slot 全て非 0 (2 回実測で同値) |
| wasm fresh (`fle_data_install` 後) | `0x0` | `0x0` | `0x0` | `.text` の敷設が 47 ページ中ほぼ 0 |
| wasm + boot_state (`state_lines_for` 適用後) | `0x0` | `0x0` | `0x0` | state 適用で値が入らない |

* wasm fresh の `.text` 敷設: 0x401000〜0x42f000 の 47 ページ中、各ページ先頭 256B に非 0 があるのは 0x42f000 の 16B のみ。native は 47 ページ中 27 ページ (0x413000〜0x42f000) で非 0 (0x401000〜0x412000 は両方 0)。
* `fle_data_install` は `--init=` 経由で呼ばれている (`rt/fle_runner.mjs` L22)。呼出しは成立しており、呼び忘れではない。
* 静的 (PE): `0x42f670..0x42f6a0` は `.text` 内。この範囲への RIP 相対参照は 0 件。`0x42f698` の即値 (imm32) は `.text` の 2 箇所 (`0x42f5d0`・`0x42f6d6`) に現れる。`0x15ec5d0` の PE 静的値は 0 (9-4 の runtime 値 `0x1e519c0` は heap ポインタ)。
* 敷設窓: `tools/flelift/fle_data_gen.py` は `.text` を `lift_meta.json` の `jt_ranges` と RIP 相対 `textrefs` の窓だけ敷設する (`x64c.py` L336-337)。`0x42f670` は RIP 相対参照されないため窓に入らない、と読める。**窓の外であることの直接確認 (生成済み `fle_data.c` の窓一覧) は snapshot に無く未実施**。

#### 退行 5 件の分類 (受入 3)

| va | 説明できるか | 根拠 |
|---|---|---|
| `0x44a590` | 候補として説明できる (未確定: 敷設窓の直接確認が未了) | 再採点 (`--state auto`) で `unlifted_callee` high。native `0x44a4b0` → `0x415c30`、wasm `0x44a4b0` → `0x40faa0`。wasm の trace に `0xdead0000` (疑似 return address) が出るのは通常の呼出しで、vtable 0 の印ではない。vtable 0 の dispatch 経路と整合 (9-4 の wasm 実測) |
| `0x4090e0` | 未説明 | `memory_semantics`。trace 入口は一致、image 書込み集合が不一致 |
| `0x41cd70` | 未説明 | `unlifted_callee` + `wasm_trap`。wasm trace に `0x40d050` (lift 閉包外間接 call) が並ぶ。vtable 0 との関係は未検証 |
| `0x42d830` | 未説明 | `callee_divergence`。native のみ `0x412d60` に入る (native_extra_entry)。vtable 経路の証拠なし |
| `0x412020` | 別扱い | 単独 n=3 で退行 (9-2)。batch では unexec。native_fault が出るため vtable 以前の問題の疑い |

#### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x44a590` の `unlifted_callee` (閉包外 indirect call 22 件) の原因 | 窓の修正後も `mismatch` のまま。vtable 以外の要因が残る | #410 継続 |
| `0x4090e0` / `0x41cd70` / `0x42d830` の原因 | 退行 5 件のうち 3 件 | #410 継続 |
| `0x412020` の native_fault | 退行 5 件のうち 1 件 | #410 継続 |

### 9-6. 敷設窓の直接確認と vtable 窓の追加 (#2005)

測定 commit: `cbe7967b` (`fix(flelift): add vtable 0x42f670 to fle_data install window`。コード変更はこの commit のみ)。
素材: `fl-win64` / `toolchain-emsdk` / `work-liftdiff` / `work-m11` を展開 (`work-m11` は `tools/m11/work/`)。`fle_lift.sh` で `lift_meta.json` と `fle_data.c` を再生成 (`tools/flelift/work/lift/`・gitignore)。

1. **敷設窓の直接確認 (受入 1)**: 修正前の生成済み `lift_meta.json` で、`jt_ranges` は 1 件 (`0x42f670` を含まない)、`textrefs` 由来の窓は `0x42f5c0..0x42f620` と `0x42f6f0..0x42f750` のみ。`0x42f670..0x42f6a0` は敷設窓の外。
2. **窓の追加 (受入 2 の前提)**: `tools/flelift/fle_data_gen.py` に `(0x42f670, 0x30)` の窓を追加 (3 行)。
3. **wasm fresh の PEEK (受入 2)**: `fle_data_install` 直後・`fle_init` 後の wasm 線形メモリ。

| 測定 | `0x42f670` | `0x42f680` | `0x42f690` | `0x42f698` |
|---|---|---|---|---|
| wasm fresh 修正後 (`cbe7967b`) | `0x449380` | `0x40f9b0` | `0x40f9d0` | `0x4493a0` |

native 値と修正前 (`0x0`) は §9-5 の表を参照。

4. **`0x44a590` の再採点 (受入 3)**: `liftdiff.py run targets/flelift.json --fn 0x44a590 --state auto` の判定は、修正前後とも `verdict=mismatch`、tag `callee_divergence` (medium, entry_va #2)・`unlifted_callee` (high, 閉包外 indirect call 22 件、最後の VA `0x0`)。窓の追加だけでは `unlifted_callee` は消えなかった。(#1936 時点の記録は 18 件。今回は 22 件で、同一ではない。)
5. **e2e**: `bash tools/flelift/fle_e2e.sh` (`cbe7967b` HEAD): **PASS**、136 秒、load avg 約 1.0。同じ修正を入れた作業ツリー (commit 前) での実行も PASS (141 秒)。

#### 残り (未達)

* 受入 3 の「`unlifted_callee` が消えるか」は、今回の窓追加では消えないと判明。原因は vtable 以外にあると見られるが未特定。
* `0x44a590` の閉包外 indirect call 22 件の呼出先特定は未実施。

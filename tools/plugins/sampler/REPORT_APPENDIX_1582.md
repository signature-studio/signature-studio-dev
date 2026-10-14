# sampler REPORT 付録 (#1582 [PLG-F3-12])

> 正本: `tools/plugins/sampler/REPORT.md` §7。250 行上限のため §7b を無変更で分割移動。

### 7b. [PLG-F3-12] の実測と方式 (HEAD `d16d7f5d` 基準)

- 測定 (summary.csv の列順どおり): `engine_lift.sh 19252` → `unimpl 5` / `emcc_c_rc 1` / `fixcmp 後 1` / `f80 後 0` / `missing_define 2` / `missing_bytes 165` (13 s)。 `engine_lift.sh 19048` → `unimpl 5` / `emcc_c_rc 1` / `fixcmp 後 1` / `f80 後 1` / `missing_define 2` / `missing_bytes 97` (55 s、load 0.69)。
- **回帰の疑い (未解決)**: 19048 の fixcmp 後 `emcc -c` は本 HEAD で rc 1 (`'%arg2' defined with type 'i32' but expected 'i64'`、`e.fixcmp.ll:127191`)。 §5 の「fixcmp 後 rc 0」(#1163 run) は本 HEAD で再現しない。 `engine_fixcmp.py` の `%arg2` 修正 (5457975c) が効いていない原因は未切り分け。 起票先: 子 [PLG-F3-14] の受入条件に含める。
- 残件 (`e.simd.log` の `unimplemented:`): 19252 = `movntps`・`vcomisd`・`vmovsd`・`vucomisd`・`vucomiss`、19048 = `movntps`・`vcomisd`・`vcomisd__22`・`vucomisd`・`vucomiss`。
- 検討した 2 案: (a) `m11_simd2.py` の VEX 形を SSE 形の no-op へ委譲する (**不採用**: flag を反映しないまま `unimpl` から消すと、`declares_unimpl` 0 で silent miscompile が検出不能になる。 `lift/passes/m11_simd2.py` 自体が「flag 未モデルなので委譲せず stub のまま残す」と明記)。 (b) 既存 `lift/passes/ir6_pass.py` ([P1]) を lift 鎖に入れる: `e.final.ll` (19252) に当てると `comis` 76 箇所中 `insert site` 3 件のみ (`hits`: `no_branch` 59・`br_other` 28・`or_cfzf` 2・`br_zf` 1)。 大半は分岐でなく flag を別経路で読むため、[P1] だけでは flag 反映にならない (未解決)。
- 受入条件 (1) (`unimpl_helpers` から消える) と (2) (方式を DECISIONS に記録) の内、(2) は本 PR で DECISIONS D15 に記録。 (1) は flag 反映の実装が要るため子 issue。 (3) `emcc -c` rc 0 は **19252 のみ達成** (`emcc_c_rc_after_f80` 0)。 19048 は本 HEAD で rc 1 (上記の回帰の疑い)。 これは本 issue の変更とは無関係 (変更は `tools/m11/` 側の未コミット編集を取り消し済みで、sampler の lift 経路に影響しない)。

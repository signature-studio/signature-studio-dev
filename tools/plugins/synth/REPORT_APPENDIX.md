# tools/plugins/synth/REPORT_APPENDIX.md — #534: C++ x64 DLL 9 本の `emcc -c` 実測 (HEAD 3418333a)

- 本書は REPORT.md (250 行上限) の付録。 結論は REPORT §5 の表を見る。 本書は HEAD 3418333a での再測定の記録。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 HLL_CAP=100000 bash tools/plugins/synth/cpp_lift.sh <block>` (出力は `tools/plugins/work/synth/cpp<block>/`)
- 素材: `fl-win64` (`tar --zstd -xf` で `$RUNNER_TEMP/fl-win64` に展開 7 秒)。 `toolchain-emsdk` / `toolchain-retdec` は `/opt/emsdk` / `/opt/retdec` に実在
- 環境: Actions runner (4 core)。 `PLUG_AVX256=0` (既定)、`PLUG_F80_LOWER` 未指定 (既定 0)

## A. 実測 (8 本: 並列 4、`xargs -P 4`、総経過 4 分 27 秒)

列: `.pdata` 関数 / define / 欠落 define / 未実装 helper (うち VEX) / i256 trap / 最初の `emcc -c` rc / E1 修復後 rc / lift 秒。

| DLL | block | `.pdata` 関数 | define | 欠落 define | 未実装 helper | i256 trap | `emcc -c` (final) | E1 修復後 | lift 秒 | 最初のエラー |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| BooBass_Eng | 21202 | 1,579 | 1,393 | 211 | 15 | 3 | 1 | 1 | 60 | `'%arg2' defined with type 'i32' but expected 'i64'` (E3) |
| Kepler engine | 23914 | 3,194 | 3,697 | 2 | 103 | 3 | **0** | 0 | 171 | — (通過) |
| Kepler Exo engine | 23916 | 3,193 | 3,694 | 2 | 104 | 3 | 1 | 1 | 162 | `no libcall available for fp_round with type f80` |
| PoiZone engine | 24159 | 1,638 | 1,790 | 1 | 101 | 3 | **0** | 0 | 60 | — (通過) |
| Sakura engine | 24163 | 1,644 | 1,707 | 1 | 84 | 3 | 1 | 1 | 72 | `do not know how to soften fp_extend` |
| Sawer engine | 24167 | 1,676 | 1,833 | 1 | 83 | 3 | 1 | 1 | 70 | `do not know how to soften fp_extend` |
| Transistor Bass engine | 24298 | 3,257 | 3,741 | 2 | 87 | 3 | **0** | 0 | 129 | — (通過) |
| Toxic Biohazard | 24216 | 1,841 | 1,927 | 1 | 94 | 3 | 1 | 1 | 69 | `do not know how to soften fp_extend` |

- 通過は 3 本 (Kepler engine / PoiZone engine / Transistor Bass engine)。 REPORT §5 (旧 HEAD) では 0 本だった。 差分は E1 修復の後段に効いたのか、 `fix_avx256` 等の後の pass 鎖 (#535 以降) によるかは未切り分け。
- Morphine (23944) は未測定。 `cpp_lift.sh` の HLL 打ち切りが `pkill -f` を使うため、今回は並列 run に入れず除外した。
- 失敗 5 本のうち 4 本は x86_fp80 の libcall (`fp_extend` 3 本 / `fp_round` 1 本 + `frem` の f80 を含む)。 `emcc` は f80 を soften できない。 f80 → f64 の lowering (`PLUG_F80_LOWER=1`) は精度を落とすため既定では使わない。
- 1 本 (BooBass_Eng 21202) は E3: `function_180049450(i64 %arg1, i32 %arg2)` の `%arg2` を `inttoptr i64 %arg2 to ptr` で使用。 仮引数の幅を推定で変えると呼出側の上位ビットの扱いを決める必要があり、未実施。

## B. E1 修復 (`fix_icmp_ptr.py`) の効き

- 共有鎖 `lift/passes/fix_icmp_ptr.py` は HEAD に組込済み (PLG-F6-2 #545)。 `engine_fixcmp.py` (synth 局所) は `cpp_lift.sh` の表示用に残っている。
- 本測定では 8 本とも E1 修復後の rc が final と同じ (修復前後で通過/失敗が変わらない)。 E1 は既に共有鎖で解消済みで、残る失敗は E3 と f80 libcall。

## C. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| f80 (x86_fp80) の libcall (`fp_extend` / `fp_round` / `frem`) | 4 本の `emcc -c` 不通過 | #534 (本 issue)。 f80 の扱い (f64 化の精度・同値試験) は別判断 |
| E3 (i32 仮引数の i64 使用) BooBass_Eng `function_180049450` | 1 本 | #534 (本 issue) |
| Morphine (23944) の HLL 段を含む通常経路の実測 | 未測定 | #534 (本 issue) |
| VEX helper 未実装 (Kepler 79 本等) と `PLUG_AVX256` 有効時の再測定 | lift 結果の完全性 | #534 (本 issue) |
| define 欠落 (BooBass_Eng 211 件) の原因 | 1 本 | #534 (本 issue) |
| E2 (SSA 値入り定数式) / E4 (`fix_asm_stores` の def 欠落) の現 HEAD での再測定 | 再測定の未実施 | #534 (本 issue) |

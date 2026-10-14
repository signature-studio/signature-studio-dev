# tools/icall 付録: #1025 (ICALL-17) runner 修正と差分ゼロ

REPORT_APPENDIX_1025.md の後続節。親 #853 (ICALL-12)。REPORT.md §15 から参照。

## runner 修正と差分ゼロ

### 測定の時刻と tree

- 測定 commit (コードを変えた最後の commit): `63e150e2` (`tools/icall/kh_route_run.sh` を変更。`kh_route_build.sh` はヘッダ注記のみ)。
- `63e150e2` の commit 時刻は 19:35:43 UTC。それ以前の測定 (19:21〜19:35) は未コミットの作業 tree で行われた。この窓の数値は次の clean 再測定で置き換える。
- **clean 再測定 (本節の正本)**: コミット済み tree `b757a183` (worktree `/home/runner/work/ws-2845`・`git status` は空) で実行。build 2026-10-14 20:12:18 UTC 開始、run 20:13:29 UTC 開始。素材は `$ARTIFACTS_DIR` の `plugins-kilohearts`・`work-icall`・`work-liftlib` (展開先は `tools/icall/work/`・`tools/liftlib/work/`)、emcc は `/opt/emsdk`。
- 前版の「最終 HEAD で再実行し一致」の記述は、実行ログが無かったため撤回済み。レビュー run `38627376099` (clean `git archive b757a183`) でも同じ値を得たと報告されている (PR #2845 round 2)。

証跡 (clean `b757a183`):

```
$ git diff 63e150e2 b757a183 -- tools/icall ':!tools/icall/REPORT*' | wc -l
0
$ git status --porcelain=v1 -- tools/icall | wc -l
0
$ find tools/icall -type f -size +20M -not -path '*/work/*' | wc -l
0
```

### 実測 (clean `b757a183`)

| 項目 | 実測 |
|---|---|
| `kh_route_build.sh` | rc 0 / real 1m02.9s |
| `kh_route.wasm` | 50,774,127 B (sha256 先頭 `8cc3330d`) |
| `kh_route_run.sh` | rc 0 / real 0.34 s / scenarios 61 / steps 366 / wasm_trap 0 / rax_match 173 |
| 全バッファ bit 一致 | **366/366** (`kh_route_run.sh` の `bit_exact_steps`。不一致バッファ 0) |
| xmm0 一致 | **366/366** (数え方は下) |
| rax 一致 | 173/366。不一致 193 件の内訳は下 |

**xmm0 の数え方**: `kh_route_run.sh` の集計表示 (`bit_exact_steps`) には xmm0 は含まれない。ただし wasm と native の両方が R 行 (`R <scen> <step> <crash> <rax> <xmm0>`) の第 5 フィールドに xmm0 を出力している (`kh_route_run.sh` が生成する `wr_ott.mjs` の R 行を書き換えて出力させている)。`liftlib.harness.diff.parse_out` で `out_native.txt` と `out_wasm.txt` を読み、366 の (scen, step) キーごとに第 5 フィールドを直接比較した (crash 0)。

**rax 不一致 193 件の内訳**: 全件で native が `0x00005a…` (ネイティブ実行プロセス側のアドレス)、wasm が `< 0x40000000` (線形メモリ内オフセット。build 上限 `0x3c000000` より小さい)。両者は同じアドレス空間の値ではない。rax は判定 (bit 一致) には使わない。

**wasm サイズの差 (m4)**: wasm 内に絶対パス `/home/runner/work/…` の文字列が 8 箇所埋め込まれている (`-g`)。同じ commit を build パス長 25 字 (`/home/runner/work/ws-2845`) と 58 字 (symlink・20:14:23〜20:15:25 UTC) で build したところ、50,774,127 B と 50,774,391 B だった (差 264 B = 8 × 33)。サイズはビルド絶対パス長 1 字あたり +8 B で線形に変わる。前版の記録 50,774,295 B (差 +168 B = 8 × 21) と、レビュー run の 50,774,239 B (差 +112 B = 8 × 14) は、記録時の build パス長が異なると見れば説明がつく (記録時のパス長は未記録のため未確認)。58 字の probe wasm は run していない。

### 原因: `_ott_data_install()` が呼ばれていなかった

- `kh_route_run.sh` が生成する `wr_ott.mjs` は `_ott_data_install()` を呼んでいなかった (`tools/icall/diff/fa_cmp.py` と x64c harness は呼ぶ)。そのため `.rdata` / `.data` / `_RDATA` が線形メモリに敷設されず、定数が 0 のまま走っていた。
- 実測 (一時的な debug print。リポジトリには含めず、元に戻した): `__icall_comis` の入力 a は step 1 (scenario 0) で `0000000000000000`。同時点の線形メモリ `0x313d6fc0` (絶対値マスク) は `0000000000000000`。PE 上の値は `7fffffff7fffffff` (`objdump -s`)。修正後は同じ時点で `mask=7fffffff7fffffff`。
- 機械語の対応 (`HeartCore.core_64`): `0x1804b03bf ucomisd xmm2,[1e-15]` → `0x1804b03c7 jae 0x1804b041e`。`a ≥ 1e-15` なら native は store 経路 (`movq`・`shufps`・`movups [self+104],xmm0`) を飛ばし、`0x1804b041e` 以降で `self+104 = 1.0/64 = 0.015625` (`movss [rcx+0x68],xmm0`) 等を書く。wasm は a = 0 で store 経路に入り `[0, X, X, X]` を書いていた。前節の step 1 の差分 (`self+104`: native 0.015625 / wasm 0、`+108`: 1.0 / 0.5) は、この分岐の違いで説明がつく。

### 修正

- `tools/icall/kh_route_run.sh`: 生成する `wr_ott.mjs` で、module 生成直後 (初回と `mk` 後) に `M._ott_data_install()` を呼ぶ。
- `tools/icall/kh_route_build.sh` のヘッダ注記 (「PE data 未敷設」) を現状に合わせた。挙動は不変。
- `ir_fix_vstore.py --direct` (前節の movups 欠落の修復) は残した。ただし本修正だけで差分が 0 になったかは、`--direct` を外して比較していないため未検証。

### 未解決

`ir_fix_vstore` の unresolved 20 件 (`fix_vstore.json`) の内訳は、`__asm_vmovdqa.25` 16 件と `__asm_movups` (i128 store) 4 件。

- `__asm_vmovdqa__25` (C 名。16 件) は `tools/icall/work/kh_route/oi.simd.c:395` の abort スタブ (`fprintf` の後に `abort()`) で、fail-fast。生成元は `tools/m11/m11_simd2.py` (i256 の未実装 helper は abort を生成する)。`simd_merge.json` の `remaining_unimpl_stubs` (13 件) には含まれない (`__asm_vmovdqa`・`__asm_movups` とも不含)。前版の「`remaining_unimpl_stubs` に入れば fail-fast」という対応の推定は機構として誤りで、撤回する。
- `__asm_movups` (4 件) は `oi.simd.c:227` の no-op 定義 (`(void)a; (void)b;`。生成元 `tools/m11/m11_simd2.py` の void 戻り movups 分岐)。wasm では store が落ちる。前版の movups 修復 (`--direct`・63 件) の対象外で、未修復。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| unresolved のうち `__asm_movups` (i128 store) 4 件が no-op のまま (`oi.simd.c:227`)。`__asm_vmovdqa.25` 16 件は abort スタブ (`oi.simd.c:395`) で、trap 0 の 61 シナリオでは実行されていない (間接確認) | 61 シナリオでは全バッファ一致。no-op の 4 件が観測バッファに効くかは未検証。別入力で当該 store が効けば差分になる | 既存の親 #853 へのコメント (提案: no-op 4 件の宛先の確認と、unresolved 20 件の扱い) |
| `ir_fix_vstore.py --direct` の要否 (本修正だけで差分 0 になるか) | 判定には影響しない。修復の必要性は未検証 | 既存の親 #853 へのコメント (提案: `--direct` を外した比較の 1 回実行) |

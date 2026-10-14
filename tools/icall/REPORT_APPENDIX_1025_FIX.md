# tools/icall 付録: #1025 (ICALL-17) runner 修正と差分ゼロ

REPORT_APPENDIX_1025.md の後続節。親 #853 (ICALL-12)。REPORT.md §15 から参照。

## runner 修正と差分ゼロ (2026-10-14 19:21〜19:40 UTC)

測定 commit: `63e150e2` (`tools/icall/kh_route_run.sh` を変えた commit。`kh_route_build.sh` はヘッダ注記のみ変更)。鮮度: `63e150e2..HEAD` の `tools/icall` のうち REPORT 以外は 0 行 (下記 `git diff`)。

### 測定の時刻と tree (訂正・fix 対応)

- 測定窓 19:21〜19:40 UTC は、`63e150e2` のコミット時刻 (19:35:43 UTC) をまたぐ。測定の一部は未コミットの作業 tree で行われた。最終の build / run がコミット済み tree (clean checkout) で行われた時刻は**記録が無く、不明**。
- fix 対応の run (`ws-2845`・HEAD `c02a208c`) では再実行していない。`$ARTIFACTS_DIR` には `fl-win64` のみ (`plugins-kilohearts`・`work-icall`・`work-liftlib`・`toolchain-*` が無い)。`kh_route_build.sh` の入力 (`work/rt_kilohearts-gain/`・`work/kh_pe/`) も無いため、再ビルドできない。
- 前 run の PR 本文の「最終 HEAD `c02a208c` で再実行し同じ数値・sha256 が一致」は、実行ログ (時刻・tree・sha256) を本書に残していなかった。この記述は撤回し、下の未解決に移す。
- コミット済み tree での再実行は、PR 本文の `oc_artifacts:` 行で素材を揃えた次回 review run で行い、結果を本節に追記する。

証跡 (fix 対応の run・HEAD `c02a208c` で実行):

```
$ git diff 63e150e2 HEAD -- tools/icall ':!tools/icall/REPORT*' | wc -l
0
$ git status --porcelain=v1 -- tools/icall | wc -l
0
$ find tools/icall -type f -size +20M -not -path '*/work/*' | wc -l
0
```

素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B) を `tools/icall/work/kh_pe/` に配置。`work-icall` / `work-liftlib` は main checkout の `work/` を symlink で参照。`toolchain-emsdk` は [EMSDK] (`docs/REFERENCES.md` §4)。

| 項目 | 実測 (前 run・commit `63e150e2`) |
|---|---|
| `kh_route_build.sh` | rc 0 / real 1m04s。2 回 build で `kh_route.wasm` / `kh_route.cjs` の sha256 が一致 (前 run の記録) |
| `kh_route.wasm` | 50,774,295 B (sha256 先頭 `03055cd1`) |
| `kh_route_run.sh` | rc 0 / real 0.32 s / scenarios 61 / steps 366 / wasm_trap 0 |
| 全バッファ bit 一致 | **366/366** (不一致 0)。`kh_route_run.sh` の `bit_exact_steps` 出力 |
| xmm0 一致 | **未集計**。`kh_route_run.sh` は xmm0 を判定に使わず出力にも含めない。前 run の 366/366 は数え方の記録が無いため採らない |
| rax 一致 | 173/366 (`kh_route_run.sh` の `rax_match` 出力)。不一致 193 の内訳 (native のホスト空間ポインタ・wasm の線形メモリオフセット) は**未集計**。判定からは除外したまま |

再現: `bash tools/icall/kh_route_build.sh && bash tools/icall/kh_route_run.sh`。

### 原因: `_ott_data_install()` が呼ばれていなかった

- `kh_route_run.sh` が生成する `wr_ott.mjs` は `_ott_data_install()` を呼んでいなかった (`tools/icall/diff/fa_cmp.py` と x64c harness は呼ぶ)。そのため `.rdata` / `.data` / `_RDATA` が線形メモリに敷設されず、定数が 0 のまま走っていた。
- 実測 (一時的な debug print。リポジトリには含めず、元に戻した): `__icall_comis` の入力 a は step 1 (scenario 0) で `0000000000000000`。同時点の線形メモリ `0x313d6fc0` (絶対値マスク) は `0000000000000000`。PE 上の値は `7fffffff7fffffff` (`objdump -s`)。修正後は同じ時点で `mask=7fffffff7fffffff`。
- 機械語の対応 (`HeartCore.core_64`): `0x1804b03bf ucomisd xmm2,[1e-15]` → `0x1804b03c7 jae 0x1804b041e`。`a ≥ 1e-15` なら native は store 経路 (`movq`・`shufps`・`movups [self+104],xmm0`) を飛ばし、`0x1804b041e` 以降で `self+104 = 1.0/64 = 0.015625` (`movss [rcx+0x68],xmm0`) 等を書く。wasm は a = 0 で store 経路に入り `[0, X, X, X]` を書いていた。前節の step 1 の差分 (`self+104`: native 0.015625 / wasm 0、`+108`: 1.0 / 0.5) は、この分岐の違いで説明がつく。

### 修正

- `tools/icall/kh_route_run.sh`: 生成する `wr_ott.mjs` で、module 生成直後 (初回と `mk` 後) に `M._ott_data_install()` を呼ぶ。
- `tools/icall/kh_route_build.sh` のヘッダ注記 (「PE data 未敷設」) を現状に合わせた。挙動は不変。
- `ir_fix_vstore.py --direct` (前節の movups 欠落の修復) は残した。ただし本修正だけで差分が 0 になったかは、`--direct` を外して比較していないため未検証。

### 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `ir_fix_vstore` の unresolved 20 件 (前 run の記録では `__asm_vmovdqa.25` 系 i256)。fail-fast stub との対応は**推定・未確認** (`simd_merge.py` は残存未実装 stub を abort 付きに差し替えるため、名前が `simd_merge.json` の `remaining_unimpl_stubs` に入れば fail-fast。当該 json は本 run に無い) | 61 シナリオでは trap 0・全バッファ一致。別入力で実行されるかは未検証 | 既存の親 #853 へのコメント (提案: unresolved 20 件の名前と `remaining_unimpl_stubs` の照合) |
| `ir_fix_vstore.py --direct` の要否 (本修正のみで差分 0 になるか) | 判定には影響しない。修復の必要性は未検証 | 既存の親 #853 へのコメント (提案: `--direct` を外した比較の 1 回実行) |
| コミット済み tree での再実行 (最終 build / run の時刻・tree の記録、xmm0 の計数、rax 不一致 193 の内訳) | 本 fix run では再実行できず。前 run の「再実行で一致」記述は撤回 | PR #2845 の次回 review run (PR 本文の `oc_artifacts:` の素材で実行し、本節に追記) |

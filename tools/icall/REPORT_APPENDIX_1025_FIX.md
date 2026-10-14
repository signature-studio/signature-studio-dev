# tools/icall 付録: #1025 (ICALL-17) runner 修正と差分ゼロ

REPORT_APPENDIX_1025.md の後続節。親 #853 (ICALL-12)。REPORT.md §15 から参照。

## runner 修正と差分ゼロ (2026-10-14 19:21〜19:40 UTC)

測定 commit: `63e150e2` (`tools/icall/kh_route_run.sh` を変えた commit。`kh_route_build.sh` はヘッダ注記のみ変更)。`63e150e2..HEAD` の `tools/icall` 差分は本節の文言 (下記 `git diff`) のみ。

素材: `plugins-kilohearts` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B) を `tools/icall/work/kh_pe/` に配置。`work-icall` / `work-liftlib` は main checkout の `work/` を symlink で参照。`toolchain-emsdk` は [EMSDK] (`docs/REFERENCES.md` §4)。

| 項目 | 実測 (commit `63e150e2`) |
|---|---|
| `kh_route_build.sh` | rc 0 / real 1m04s。2 回 build で `kh_route.wasm` / `kh_route.cjs` の sha256 が一致 |
| `kh_route.wasm` | 50,774,295 B (sha256 先頭 `03055cd1`) |
| `kh_route_run.sh` | rc 0 / real 0.32 s / scenarios 61 / steps 366 / wasm_trap 0 |
| 全バッファ bit 一致 | **366/366** (不一致 0) |
| xmm0 一致 | 366/366 |
| rax 一致 | 173/366。不一致 193 は全て native = ホスト空間ポインタ (`0x00005a…`)・wasm = 線形メモリ内オフセット (`0x13…`)。計算結果の差ではないため判定から除外 |

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
| 残 unresolved 20 件 (`__asm_vmovdqa.25` 系 i256 の fail-fast stub) | 61 シナリオでは実行されていない (trap 0・全バッファ一致から判断)。別入力で実行されるかは未検証 | 受入範囲外。未起票 |
| `--direct` の要否 (本修正のみで差分 0 になるか) | 修復の必要性の記録のみ。判定には影響しない | 未起票 |

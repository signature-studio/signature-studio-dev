# REPORT_APPENDIX_5897 — #5897 (PY-5398): slot 35 (`call [reg+0x118]`) の実行時 VMT 採取 probe

> 親: #5205 / 前段: #5884 (`tools/python/REPORT_PY72_APPENDIX_3371.md` 追補 4・5)。
> 本付録は採取 probe `slot35_vmt_probe.sh` の実測結果の正本。REPORT 本体 (`REPORT.md`) には結論 1 行だけを書く。

## 0. 結論

- **採取 0 件。** slot 35 の 151 箇所の、どれも boot 中に実行されなかった。受入 1 は「採取できた箇所数 0」で実測を取った。受入 2 (箇所ごとの TPublicChannel / TPreviewChannel 判定) は採取 0 件のため判定できない。
- 理由: 既定経路の boot は units 895 で止まる (停止点 `exit`)。151 箇所を全て lift に載せても (§2)、boot は 895 のまま、slot 35 の呼出し元には入らない。
- probe 機構は動いている。陽性対照 `0x412a0d` (exit 直前) は既定 root の lift で 1 件発火 (§3)。
- したがって「slot 35 の受け手が TPublicChannel / TPreviewChannel か」は、現在の boot 経路 (units 895 止まり) では実行時に観測できない。判定は boot を units 895 より先へ進めた後に行う必要がある。これは #5205 の受入 2 の残件として #5205 に戻す。

## 1. 方式

- `tools/flelift/boot/slot35_vmt_probe.sh` (本 PR で追加)。
- 箇所の列挙: `tools/python/analysis/flapi/pe_slot35_sites.py` の出力 (151 箇所)。
- lift 行 `/* <VA>: call qword ptr [<reg> + 0x118] */` の直前に、`LD64(R[k])` (呼出しレジスタ = 受け手オブジェクトの指す先頭 8 バイト = VMT) を出す probe を `dbg_lift.py` で挿入する。
- レジスタ → `R[]` 添字は `x64c.py` の並び (rax..rdi = 0..7・r8..r15 = 8..15)。
- 出力行 `[S35] site=<VA> reg=<reg> vmt=<hex>`。陽性対照 `[S35-control] site=412a0d` を同時に入れる。
- 既定 build (`work/boot/lift`) は変えない。probe は `work/boot/lift_slot35` にだけ入る。

## 2. 実測

測定 commit: `16c3f5790` (origin/main 取り込み時点・probe 追加前のコード)。probe の追加は本 PR の差分。

| 条件 | lift に載った slot 35 箇所 | boot 結果 (units / stopped_at) | `[S35]` 採取 | 陽性対照 `[S35-control]` |
|---|--:|---|--:|--:|
| 既定 root (`work/boot/lift`) + probe | 63 | 895 / `exit` | 0 | 1 (`0x412a0d`) |
| `FLE_EXTRA_ROOTS` = 98 関数入口 (151 箇所を含む関数) + probe | 151 | 895 / `exit` | 0 | 0 |

- 既定経路の基準 (probe なし・worktree): `FLEBOOT_RESULT units_run=895 stopped_at=895 boot_threw=exit`・`ipp ok` (`ptr_15F34A0=0x7f10001c`)。`fle6_measure.sh` (`FLE_BOOT_RUNS=default`) は rc 0・所要 3 分 22 秒 (lift 81 s・clang-plain 100 s・boot 10 s)。
- `FLE_EXTRA_ROOTS` 付き lift の工程: `fle6_measure.sh` 所要 3 分 29 秒 (lift 84 s・clang-plain 90 s)。`slot35_vmt_probe.sh` の 1 回目は 2 分 18 秒。
- 陽性対照の差: `FLE_EXTRA_ROOTS` 付き lift では `[S35-control]` が 0 件だった。既定 root の lift では 1 件。前段 (`REPORT_APPENDIX_5028`) の `[EXITBR-412a0d]` 発火と同じ条件。`FLE_EXTRA_ROOTS` の追加が exit 枝の経路を変えるかは未確定 (本 PR では扱わない)。

## 3. 陽性対照の確認 (既定 root)

- 既定 root の lift + probe: `[S35-control] site=412a0d` 1 件 (`probes: 64 / 151`・`S35 行: 1`)。`[S35] site` は 0 件。
- 対照が発火するので、probe の仕組み (挿入・ビルド・実行時出力) は動いている。slot 35 の 0 件は「probe が効かない」ではなく「その箇所が boot で実行されない」の結果と読む。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| boot を units 895 より先へ進めて slot 35 の呼出し元を通す | 受入 1 の採取と受入 2 の型判定が 0 件 | #5205 (親の残件) |
| 既定 root の lift に載らない slot 35 の 88 件 (151 - 63) | 既定 root では probe を入れられない。`FLE_EXTRA_ROOTS` で補う必要がある | #5205 |
| `FLE_EXTRA_ROOTS` 追加で exit 枝の陽性対照が消える理由 | 経路の変化か probe 条件の差かが未確定 | #5205 |

# liftlib #2128 (部分達成) — ott_getparam leaf への icall runtime 配線 (付録)

親: [`REPORT.md`](REPORT.md) §11 (leafspec) と [`REPORT_APPENDIX_883.md`](REPORT_APPENDIX_883.md) (BLK 配線の追跡)。
PR: #2162 (`2128-ott-getparam-icall-leaf`)。受入の扱い: 受入 3・4 を達成、受入 2 を達成 (BLK の wasm global 化の配線)、受入 1 は配線のみ達成で表の充足は子 #2161 へ分離。

## 測定 config

| 項目 | 値 |
|---|---|
| 測定 commit (コードを変えた最後の commit) | `f8bd2ea0` (`feat(liftlib): wire icall runtime into ott_getparam leaf (BLK global + table) (Refs #2128)`) |
| 測定 commit の HEAD 条件 | 測定は `f8bd2ea0` の worktree で実施。以後の commit は REPORT・DOC_MAP の追記のみでコード差分は 0 (下記) |
| 変更前の比較 commit | `df2eebde` (測定 commit の親。`ott_getparam` の leaf は icall runtime 未配線) |
| 素材 | `analysis-ott-binaries` → `$HOME/analysis/plugins/ott/binaries/OTT_vst2_win64.dll`、`work-liftlib` → `tools/liftlib/work/`、`work-m6-ott` → `tools/m6/work/` ほか。`OTT_DLL` で F.txt を生成 (`gen_ott_getparam_F.sh`, `0x18011e5a0-0x18011e76c`, 460 bytes) |
| emsdk | `/opt/emsdk` (既存。`emcc` を PATH に通して実行) |
| 負荷 | 測定時の load 0.8〜0.9 (1 分平均)。runner は 4 コア |

## 測定 (`python3 -m liftlib leafspec targets/ott_getparam.json --n 200`)

| 設定 | rc | wall (real) | match / mismatch / wasm_trap / native_crash | gate |
|---|---|---|---|---|
| 変更前 `df2eebde` | 1 | 1.76 s | 0 / 200 / 200 / 0 | FAIL |
| 測定 commit `f8bd2ea0` (1 回目) | 1 | 4.44 s | 147 / 53 / 0 / 0 | FAIL (rate 0.735, thr 1.00) |
| 測定 commit `f8bd2ea0` (2 回目) | 1 | 1.13 s | 147 / 53 / 0 / 0 | FAIL (rate 0.735, thr 1.00) |

- 同一 commit の 2 回で match / mismatch / wasm_trap は一致。wall time は 1.13〜4.44 s と揺れた (初回は emsdk キャッシュ等の冷えた状態の影響を含む可能性がある。未切り分け)。
- 変更前の 1.76 s は本 run の再測定値。`REPORT_APPENDIX_883.md` の旧記録 (4.1〜6.1 s) とは別の機で測った値で、時間の比較には使わない。`wasm_trap` の 200 → 0 と match 0 → 147 のみを効果の根拠にする。
- mismatch 53 件は `<xmm0>` の不一致 (native の戻り xmm0 が非 0 の scenario で、wasm 側は 0)。match の判定は #1270 (HB-H29) の範囲。

## 検証 (unit)

- `python3 tests/test_unit.py` (`tools/liftlib`): T1〜T5 ok。
- T6 は `targets/freshair/work/win/Fresh Air/...` (`work-liftlib-targets`) を要するため未実行 (FileNotFoundError)。今回の `oc_artifacts` に `work-liftlib-targets` が含まれず、素材を展開していない。既存 recipe の回帰は T1〜T5 のみ確認 (受入 4 の範囲)。

## 差分 0 の確認

コード範囲 (`tools/` から `REPORT*.md` を除く) の差分は 0 行。

```
$ git diff f8bd2ea0 HEAD -- tools/ ':(exclude)tools/liftlib/REPORT*.md' | wc -l
0
```

付録追記の commit (`4c2d893b` 以降) の差分は `docs/DOC_MAP.md`・`tools/liftlib/REPORT.md`・本付録のみ。

## 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| dispatch 表が根 1 関数のみで空 (`icall_tbl_n = 0`)・FAIL-FAST 未検証 | 間接 call の target 解決が未検証 | #2161 (HB-H44) |
| match 147/200 (53 件 xmm0 不一致) | gate FAIL のまま | #1270 (HB-H29) |
| T6 以降 (freshair/kilohearts) 未実行 | 既存 recipe の回帰は T1〜T5 のみ | 素材 `work-liftlib-targets` を次 run で指定 |

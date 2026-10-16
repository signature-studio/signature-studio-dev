# tools/plugins/p0c REPORT 付録 M — #5832 (E7: x86_fp80 ↔ i80 bitcast の展開)

> 本体の索引は `tools/plugins/p0c/REPORT.md` §26。 PR #5858 の本文から、測定値・表をここへ移した (`docs/WORKFLOW.md` §5)。

## 1. 変換 bit 一致 (`f80b_rt/run.sh`)

方式: `expand_f80_bitcasts` (`f80_lower.py`) が出した IR を emcc (wasm32) でビルドし、host (x86-64) の `long double` (x87) を期待値として照合する。`gen_cases.c` が期待値を作る。

| 方向 | 件数 | 不一致 | 測定 commit |
|---|--:|--:|---|
| double → x87 像 | 200,000 | 0 | `ce3872372` |
| x87 像 → double (subnormal・tie 含む) | 200,000 | 0 | `ce3872372` |

### 1.1 修正 (指摘 #5858 round 1)

`_f80b_from_image` の carry かつ subnormal 結果の誤りを直した。`sn` と `low` が carry 後の指数 `E` を使っていたため、subnormal の丸め位置が 1 桁ずれた。`E0` (carry 前の指数) で計算するよう変えた。

固定ベクタ 3 件 (`gen_cases.c` の `fx_m` / `fx_e`) を追加した。`run.sh` が必ず検査する。

| 入力 (m, se) | 修正前 (`9418e1050`) | 修正後 (`842bc5ac3`) | native (x87→double) |
|---|---|---|---|
| `0xFFFFFFFFFFFFFFFF`, `0x3BFD` | `0x0.4p-1022` | `0x0.2p-1022` | `0x0.2p-1022` |
| `0xFFFFFFFFFFFFFFFF`, `0x3BFE` | `0x0.8p-1022` | `0x0.4p-1022` | `0x0.4p-1022` |
| `0xFFFFFFFFFFFFFD32`, `0x3BE5` | `0x0.0000004p-1022` | `0x0.0000002p-1022` | `0x0.0000002p-1022` |

修正前の `f80_lower.py` で同じ検査 (固定ベクタ込み) を実行すると `from: n=200003 fail=3` で rc 1。修正後は `from: n=200003 fail=0` で rc 0。

### 1.2 修正後の検査 (emcc 版)

emsdk を導入し (`emsdk install latest`・`activate latest`)、`EMSDK` を設定して `run.sh` を実行した。

- 測定 commit: `7bdaf7443` (HEAD。`842bc5ac3` 以降に `f80_lower.py` / `f80b_rt/` の差分は無い)
- `to: n=200000 fail=0`
- `from: n=200003 fail=0`
- rc 0・所要 3.80 s real (`time bash tools/plugins/p0c/f80b_rt/run.sh`)

## 2. 共有鎖の退行 (T0 / T1, `batch_lift.sh --tier T0/T1`)

測定 commit `ce3872372` (修正前) の値。

- T0: 41 blocks。 `lift_rc` 0・`emcc_c_rc` 0 が 41/41。 closure 関数 781 (REPORT と一致)。 所要: 実測ログ未保存 (PR 本文の記載のみ。時間の数値は採らない)。
- T1: 45 blocks。 `emcc_c_rc` 0 が 44/45。 唯一の不通過は 24161 ReWired (f80 2 関数)。 REPORT §4.3 の既存の結果と同じで、本 PR による変化は無い。 closure 関数 2,835。 所要: 実測ログ未保存 (同上)。
- 退行 0。 本 PR は T0/T1 の f80 関数を 0 〜 2 しか持たないブロックにしか効かないため、差は出ない。

注: 測定 commit 以降に `f80_lower.py` の `_f80b_from_image` (subnormal の丸め位置) を変えた (`842bc5ac3`)。 この修正後の T0/T1 は**未再測定**。

未再測定の理由 (再実行 run の 2026-10-16 に確認): `batch_lift.sh` は `/opt/retdec/bin/retdec-decompiler` (RetDec) を呼ぶが、本 runner に `/opt/retdec` が無い。 `artifacts/` にも `toolchain-retdec` が無い (`$HOME/artifacts` は `fl-win64.tar.zst` のみ)。 `PLUGIN_MATRIX.json` も本 worktree に無い。 `fl-win64` は展開可能 (block 10000 件)。 RetDec の取得元は `docs/REFERENCES.md` に `[未確認]` のため、この run では復元できない。 次に必要な素材: `oc_artifacts: fl-win64 toolchain-retdec` (取得元の確定後)。

## 3. 19165 engine (`engine_lift.sh 19165 900` → `engine_f80_subset.sh`)

測定 commit `ce3872372` (修正前) の値。

| 項目 | 本 PR 前 (REPORT §17) | 本 PR 後 |
|---|---|---|
| `emcc -c` (`e.final.ll`) の最初の error | `invalid cast opcode ... 'double' to 'i80'` (E7) | `do not know how to soften fp_extend` |
| `emcc -c` (`e.final.ll`) rc | 139 (segfault) | 139 (segfault) |
| 部分集合 (f80 関数 5 件を除外) の `emcc -c` rc | 0 | 0 (gate PASS) |
| lift rc / define / f80 関数 (本体) | 0 / 2,608 / 5 | 0 / 2,608 / 5 |

- 測定条件 (PR 本文の記載): `ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges <78 件>" ENGINE_TAG=_noipp_nobad engine_lift.sh 19165 900`。 wall 625 s・実行直後の 1 分平均 load 1.15 (4 core) は PR 本文の記載値で、 ログは保存されていない。
- 測定スクリプトの所在: `engine_lift.sh` と `engine_f80_subset.sh` は `tools/plugins/reverb_delay/` にある (`tools/plugins/lift/` には無い)。
- 本 runner では再測定していない。 `engine_lift.sh` も `lift_ranges.sh` 経由で `/opt/retdec/bin/retdec-decompiler` を呼ぶため、§2 と同じ理由で走らない。 修正後 (`842bc5ac3` 以降) の 19165 は未再測定 (`emcc -c` の rc・最初の error は未確認)。

## 4. 鮮度: `ce3872372` から HEAD までの差分

差分の全文は `REPORT_APPENDIX_M2.md` (`git diff ce3872372 HEAD -- tools/plugins/p0c` の出力)。 要点:

- `f80b_rt/run.sh` の 1 行 (`EMCC` の解決を `$EMSDK` 必須にする変更)。 `EMCC` 変数は `command -v emcc` が先なので、 測定値は影響を受けない (`run.sh` の検査内容は変わらない)。 harness の変更であり、 測定対象の変換は変わらない。
- 続けて `842bc5ac3` の修正 (`f80_lower.py` の `sn` / `low` と `gen_cases.c` の固定ベクタ)。 これは測定対象の変換を変える。 §1.1 の再検査で置換後の値を取った。 §2・§3 は未再測定。

# REPORT_786 付録: #1640 間接 call 0x40944e の行き先・再帰打切り 10 件の不動点

本付録は `REPORT_786.md` §13・§14 の未解決 (#1640) の結果。測定 commit: `e6fa143b` (コードを変えた最後の commit)。
既定経路の件数 (§1〜§3) と既定経路の実測 (§4 の `license_obs.sh`・`probe_1492.py` 通常) は `8c721b4b` で測定した。
`8c721b4b` → `e6fa143b` の差分は `probe_1492.py` の `--no-rec-summary` 追加 (既定経路は不変) と `results/escaped_1492.json` の `elapsed_*` 値のみ。`e6fa143b` → HEAD のコード差分は 0 (文書のみ)。
再現: `bash tools/startup/license_obs/license_obs.sh` (素材 fl-win64)。

## 1. 間接 call 0x40944e の行き先 (受入 1)

- 0x409440 の `call qword ptr [rip+0xf9c844]` (0x40944e) はスロット `0x13a5c98` (`.data`) を読む。IAT import ではない。
- スロットの静的初期値は `0x407e20` (`.pdata` 内の関数先頭)。
- スロットを rip 相対で参照する命令は 2 件 (0x40944e と 0x409470 の call のみ)。絶対参照・即値・再配置ポインタからの参照は 0 件。コードはこのスロットに書き込まない。
- 同種の静的スロット間接 call は `.text` 全体で 12 件 (`escaped_1492.json` の `summary.static_slot_calls`)。
- 結論: 0x40944e の行き先は 0x407e20 に静的に決まる。受入 1 は達成。

## 2. 再帰打切り 10 件の不動点 (受入 2)

- 再帰打切りを外し、`(callee, 入口タグ)` の要約を全体反復で求めた (`fixpoint`: 2 回目で要約が不変 = 収束)。
- 10 件は `approx_recursive_call` に記録する (旧 `untraced_tagged_recursive_call`)。
- アブレーション (測定 commit `e6fa143b`): `probe_1492.py --no-rec-summary` (再帰打切り時に callee の要約を空にする) を実行した。
  - 退避経由の gradeChar byte アクセスは 207 読出し + 138 書込み = 345 件 (通常実行と同一)。キー集合 (`only_cfg` 69 件・`cfg_only_via_callee` 69 件・`approx_recursive_call` 10 件) も通常実行と完全一致。
  - `results/escaped_1492.json` 比較: `elapsed_s` / `elapsed_total_s` 以外のキーは全て一致。
  - 結論: 再帰打切りの 10 件は追加の退避アクセスを生まない。「345」は退避経由 byte アクセスの総数 (読出し 207 + 書込み 138) を指し、アブレーション前後で不変。

## 3. 件数 (受入 3)

| 項目 | 変更前 (`8c721b4b^`) | 変更後 (`8c721b4b`) |
|---|---|---|
| 退避経由の gradeChar byte 読出し | 207 | 207 |
| 退避経由の gradeChar byte 書込み | 69 | **138** (+69) |
| 退避経由の関数 | 20 | **21** (+1) |
| 追加分の由来 | — | 全て 0x40944e → 0x407e20 → 0x407f60 → 0x407570 の経路 (`cfg_only_via_callee` 書込み 69) |
| 線形走査との差 (`cfg_not_in_lin`) | 0 | 69 (線形走査は間接 call を追わない) |
| 未追跡 indirect-call-with-tag | 1 | **0** |
| 未追跡 recursive | 10 | **0** (approx 10 件に変更) |

- `results/escaped_1492.json` を更新 (新キー `approx_recursive_call`・`fixpoint`・`static_slot_calls` を追加)。
- 線形基準 (probe_1220 の 207/69/20) は不変。

## 4. 検証 (既定経路: 測定 commit `8c721b4b`・アブレーション: 測定 commit `e6fa143b`)

| 項目 | 実測 |
|---|---|
| `bash license_obs.sh` (既定経路・`8c721b4b`・1 回目・load average 1 分値 0.47 開始) | 2 分 47.89 秒・rc 0・`ALL OK`・FAIL 0 |
| `bash license_obs.sh` (既定経路・`8c721b4b`・2 回目・load average 1 分値 0.34 開始) | 2 分 47.95 秒・rc 0・`ALL OK`・PASS 40・FAIL 0 (6/6) |
| `probe_1492.py` 単体 (既定経路・`8c721b4b`・1 回目 / 2 回目) | 30.6 秒 / 25.3 秒 (`elapsed_total_s`) |
| `probe_1492.py --no-rec-summary` (アブレーション・§2・`e6fa143b`) | 26.95 秒 (`elapsed_total_s`)・PASS 207/69/20 |

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| スロットへの runtime 書込みは静的に完全には排除できない (計算アドレス経由の書込みは見えない) | 0x407e20 が唯一の行き先である保証は静的解析の範囲内 | #1221 (動的検証) |
| 到達不能 234 ブロック (1,436 命令) の扱い | 追加 0 件を確認済みだが網羅性の証明にならない | #1640 の範囲外として §14 の既存起票のまま |

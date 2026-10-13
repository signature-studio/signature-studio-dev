# REPORT_AU6 — AU-6 (#190) 遅延ポリシー: 目標充填 T の減衰

> **正本**: `tools/audio/REPORT.md` §17。本書は AU-6 の詳細 (実装・検証・未解決)。

## 1. 変更内容

`tools/audio/src/flasio.c` の producer ループ (`thread_fn`):

- underrun が `FLASIO_SHRINK_STABLE_MS` (既定 3000ms) 続くと、underrun で足した `esc` (+B) を B 刻みで 1 段戻す。
- 下限 `max(need, T0)` は下げない。`need` は worklet が観測した burst 由来、`T0` は開始時の下限。拡張とのヒステリシスは「underrun 直後は戻らない (3 秒の静穏が必要)」で持つ。
- `kAsioLatenciesChanged` は既定 OFF (`A.notify_lat`) のまま。T が減衰したときも同フラグで通知するだけで、既定では通知しない。
- 統計 `flasio_stats_t` に `grows` / `shrinks` / `T_max` / `T0` を追加 (`fla_test` の JSON 出力にも追加)。
- テスト用: `fla_test` に `hiccup_stop_ms` (この時刻以降は hiccup を止める) を追加。`page.mjs` / `run.mjs` 経由で指定。

## 2. 検証 (コミット `d9c1248a` で再現)

| 検証 | 結果 |
|---|---|
| `asio_shrink_after_hiccup_b256` (新規) | **PASS** `grows=2 shrinks=2 T0=1536 T_max=2048 T_end=1536`、復帰後 ramp 一致 17000/17000、underruns=2 |
| `asio_shrink_control_no_underrun_b256` (新規) | **PASS** `grows=0 shrinks=0 T=1536`、sine maxErr=1.49e-8 |
| ネガティブコントロール: `FLA_DEFS=-DFLASIO_SHRINK_STABLE_MS=1000000000` で `asio_shrink_after_hiccup_b256` | **FAIL** `grows=2 shrinks=0 T_end=2048` (減衰が無いと T が戻らず、判定が空振りでないことを確認) |
| quick 全体 `node harness/run.mjs --quick` (HEAD `d9c1248a`) | **44/44 PASS**, exit 0, 所要 251.9 s (開始 load 0.08 / 終了 0.65) |
| 参考: 既存 hiccup `asio_ramp_b256_hiccup` | PASS (underruns=5, 復帰後 ramp 17000/17000) |

検証の過程で 2 回判定を修正した (記録): (1) hiccup 期間は underrun による無音挿入が仕様のため、ramp の全体一致を判定に使うと FAIL する → 復帰後の `tail_shift_exact` で判定 (既存 hiccup シナリオと同じ流儀)。(2) quick の 12 秒では停止後の減衰が 2 段で止まった → `hiccup_stop_ms=3000` / `secs=16` に変更。いずれも判定を緩めたのではなく、時間軸の設計 (3 秒ごとに 1 段) に合わせた。

## 3. 検証範囲 / 範囲外

- 範囲: fake シンク (headless Chrome, emcc 6.0.12) での shim 単体。hiccup による強制 underrun からの戻し。
- 範囲外: 実機 (AU-2 #187) の underrun 頻度・burst 分布。減衰閾値 (3 秒) は fake シンクでの暫定値。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 減衰閾値 `FLASIO_SHRINK_STABLE_MS` (3000ms) の実機調整 | 実機で減衰が早すぎ/遅すぎる可能性 | #187 (AU-2) にコメント |
| 安全/低遅延モードの切替 UI (`safeoverloadbox` 相当) | 未実装。ユーザ選択で T の下限を変える経路が無い | #34 以降 (FL 本体結線) |
| `kAsioLatenciesChanged` (selector 6) の利用可否 | 内部コマンド 0x17 の意味が未確定。既定 OFF のまま | #190 (本 issue) 継続 / INVENTORY §6 |

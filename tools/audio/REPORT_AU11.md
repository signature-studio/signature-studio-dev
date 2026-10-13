# tools/audio REPORT 付録: AU-11 (#211)

本体 `REPORT.md` §10 の全文 (250 行上限のため分割移動・内容無変更)。

## 10. AU-11 (#211) 96kHz/B=256 の burst 4096 abort の解消

既知類型との関係: 該当なし (lift 欠陥ではなくランタイム shim の容量判定)。方針は両案の併用: **(b) depth 固定上限 16 を撤廃** (制約は ring 容量 `(depth+2)×B ≤ FLA_MAX_RING=32768` のみ。+2B は動的 T 拡張 `Tmax=ring−2B` の余地) し、**(a) それでも収まらない burst は abort でなく `fla_open` が `FLA_E_BURST_TOO_LARGE` を返し `flasio_create_buffers` が `ASE_NoMemory(-994)` を返す** (AudioContext は CLOSE して CLOSED に戻すので再 CreateBuffers 可)。FL 側は CreateBuffers エラー ("Couldn't create the streaming ASIO buffer." が出る経路) になる。`fla_open` の fail-fast は引数不正・二重 open など呼び側バグに限定。

| 条件 (96kHz) | 挙動 |
|---|---|
| B=256, burst 3072 | depth=16, T=4096f (従来どおり) |
| B=256, burst 4096 | depth=21, T=5376f (56.0ms) で成功 (旧: abort)。ring=32768 に収まる |
| B=512, burst 4096 | depth=11 (計算値) で成功 |
| `(depth+2)×B > 32768` | `ASE_NoMemory`、abort なし。計算上の限界 burst は B=128/256/512 で 25856/25600/24960f (`need=(b+b/4+2B-1)/B` を b=128 刻みで走査) |

e2e 追加 3 本 (`harness/run.mjs`, 計 25 シナリオ): `asio_sine_b512_96k` / `asio_sine_b256_96k_burst4096` / `asio_createbuffers_burst_overflow` (B=256, burst 40000 → depth 197, (197+2)×256=50944 > 32768)。後 2 本は burst をテスト専用フック `fla_test_set_burst_floor()` (`burst_floor=` クエリ) で強制し、環境依存の揺れを決定的に再現する。

実測 (コミット `14fa86a` でビルド (main へリベース後は同内容の `57c9143`。実装 5 ファイルの diff が 0 行であることを確認済み), headless Chrome / emcc 6.0.12, GitHub runner, 並列 1):

| 検証 | 結果 |
|---|---|
| フル e2e 1 回 (`node harness/run.mjs`) | **25/25 PASS**, exit 0, 所要 440.51 s (開始時 load average 0.22 / 終了時 0.03)。soak120: underrun 0・5,763,328f 一致 |
| 96k 3 シナリオ × 6 周 (`--quick`, load average 0.00 開始) | **18/18 PASS** (b256_96k / b512_96k / b256_96k_burst4096 各 6/6)。burst4096 は毎回 T=5376, underrun 0, 正弦最大誤差 1.49e-8 (7 周目以降は打切りのため集計外) |
| burst 溢れ | `first=-994, retry=0, dispose=0, aborted=false` |

検証範囲 / 範囲外: 本 runner の fake シンクでは自然な OPEN 較正 burst は 1024 で、**検収環境で見えた burst 4096 は自然には再現していない**。burst 4096 の経路は強制フックでの検証。実機 burst 分布は未計測。**ネガティブコントロール (旧コードで burst4096 が abort することの再実行) は未実施**。旧挙動の根拠は検収記録 §9 と旧コードの `depth > 16` 判定 (`git show 14fa86a^:tools/audio/src/flaudio.c`) のみ。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| T 縮小が未実装 (burst 4096 で T=56ms 固定) | 96k/B=256 の遅延が burst 最大値に引きずられる | #190 (AU-6) にコメント |
| 実機 burst 分布が未計測 | 自然な burst 4096 の発生頻度・遅延影響が不明 | #187 (AU-2) にコメント |
| 旧コードでの abort 再現 (ネガティブコントロール) 未実施 | 修正前後の差を本 runner で実測していない | 本 PR 本文に明記 |

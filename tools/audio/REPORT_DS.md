# AU-4 (#189) DirectSound shim 付録 (REPORT.md §15 の全文)

REPORT.md の 250 行上限のため全文を移動 (内容は削除していない)。

## 15. AU-4 (#189) DirectSound shim (`src/flds.{h,c}`) と FL の DS バッファ形式の静的確認

既知類型との関係: 該当なし (ランタイム shim 新規実装。lift 欠陥ではない)。検証起点 commit は統合後の `7cb96f1` (main 統合後の HEAD, §15 末尾の表。統合前の `5f7ceb6` の実測は下表の旧 HEAD 行)。設計は `docs/PROTOCOL.md` §8。

**FL の DS バッファ形式 (静的, `bash tools/audio/ds_static.sh` → `results/ds_static.txt`)**: primary `SetFormat` の WAVEFORMATEX 組立は設定 bool `byte[0x15d3296]` で分岐 (0x12afcd0)。0 → `WAVE_FORMAT_PCM` 16bit ステレオ (組立 0x674e10)、非 0 → `WAVE_FORMAT_EXTENSIBLE` + `IEEE_FLOAT` 32bit・mask=3 (組立 0x674e50)。secondary は同じ wfx (0x16bd4b0) を渡す。secondary への書込みも `wBitsPerSample==0x20` で float 直コピー / 16bit 変換に分岐 (0x12af12b)。**結論: FL はユーザ設定で 16bit PCM と float32 の両方を使う** → shim は両形式を受理し、16bit は `v/32768` で float 化 (厳密)。静的イメージの初期値は 0 (=16bit) だが実値は保存設定由来で静的には不定。**推定**: この bool が UI の `ds_32bitbufbox` に対応する (設定 3 bool のうち用途が消去法で残る 1 つ。DFM フィールド表は未解析)。

**呼出面の訂正**: `fl_asio_surface.py` / INVENTORY §2 の DS 集計 (SetVolume×3, SetFrequency, GetFormat×3 等) は disp のみの集計で Delphi オブジェクトへの同 disp 呼出を含んでいた。受け手 (rcx のロード元グローバル) で分類した結果 (`fl_ds_surface.py`): IDirectSound {CreateSoundBuffer×2, SetCooperativeLevel×1}、primary {GetFormat×1, SetFormat×1}、secondary {GetCurrentPosition×2 (play のみ / write のみ), Lock×2, Unlock×2, Play, Stop, SetCurrentPosition, QueryInterface×1}、IDirectSoundNotify {SetNotificationPositions×1}。**SetVolume/SetFrequency は DS オブジェクトに呼ばれない** (走査範囲 `0x12ae000..0x12b2000` 内の結論。受け手未解決の `[+0]` 呼出が 6 件あり、範囲外・未解決分は含めて否定できない)。(INVENTORY.md は生成物扱いのため本 PR では未更新 — 下表)

**実装**: secondary = shim 内循環バイト列、pump スレッドが ring を T まで充填 (flasio と同じ T 拡張則)。play cursor = `out_read` 由来、write cursor = 変換済み + P。Notify は offset 通過で bit (合体)。`SetCurrentPosition` は停止中のみ。非 LOOPING / EXCLUSIVE / WRITEPRIMARY は fail-fast。

**e2e (追加 10 シナリオ, `harness/run.mjs`)**: poll/notify × pcm16/f32 のランプ bit-exact・正弦・44.1k・極小バッファ (4096f)・過負荷・Stop/再開・API 境界 37 項目・EXCLUSIVE fail-fast。

| 検証 (HEAD `5f7ceb6`, headless Chrome / emcc 6.0.12, GitHub runner 4 コア, 並列 1) | 結果 |
|---|---|
| `bash tools/audio/e2e.sh` 1 回目 (11:40:20 開始, FL_WIN64_DIR=展開先, TMPDIR=RUNNER_TEMP) | **37/38**, exit 1, 実測 586 s。FAIL は `asio_ramp_b128_d2` のみ (underrun 1, silence 768, ramp 不一致 922,752/961,024)。他 37 件 PASS |
| 上記 FAIL の再実行 `--only asio_ramp_b128_d2` (同 HEAD) | **1/1 PASS**, exit 0, 実測 73.4 s (load 0.22 → 0.54)。underrun 0・不一致 0/961,024。1 回目の FAIL は一過性の負荷揺れとして扱うが、原因未特定 (再発の監視が必要) |
| **統合後 HEAD `7cb96f1`** (`bash tools/audio/e2e.sh`, runner, FL_WIN64_DIR=`fl-win64` 展開先, EMSDK_ENV=`toolchain-emsdk` 展開先, TMPDIR=RUNNER_TEMP, 12:23:28 開始, load 0.36 → 0.87) | **43/43 PASS**, exit 0, 実測 647 s。`results/results.json` はこの run の出力 (harness 生成, 12:34:15) |
| (統合前 HEAD `5f7ceb6`) フル e2e 2 回目 (`node harness/run.mjs --out results/results.json`, 11:51:39 開始) | **38/38 PASS**, exit 0, 実測 557.6 s (load 0.91 at end)。`results/results.json` はこの run の出力そのもの (手で合成していない) |
| (旧 HEAD `4483b84`) フル e2e 1 回 (`node harness/run.mjs`, 既存 25 + DS 10) | **35/35 PASS**, exit 0, 実測 539 s (開始 load average 0.27 / 終了 1.28)。DS: underrun 0・ramp16 / ramp 不一致 0 (最大 721,408f)・write cursor − play cursor = 1152..2560f (許容 [P, T+2P]) |
| (旧 HEAD `4483b84`) ネガティブコントロール: `flds.c` の 16bit 係数 1/32768 → 1/32767 に壊して `ds_pcm16_poll_ramp_b256 --quick` | **FAIL** (ramp16 mismatches 192384/192384)。戻し後は diff 0 行 |

検証範囲 / 範囲外: fake シンク + 合成クライアント (FL の呼出手順の再現) のみ。**実 FL (FLEngine) からの呼出は未実施** (COM vtable アダプタ = AU-1 待ち)。DS の `Lock`→`Unlock` を介さない書込みや、FL の play cursor 利用方式 (`pbtrackingmode` 連動) は未検証。16bit 変換の FL 側係数・ディザは未解析 (shim は厳密 /32768)。独立検収の別算法検算は検収側に委ねる。

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `byte[0x15d3296]` = `ds_32bitbufbox` の対応は推定 (DFM 未解析) | 形式の既定が 16/32 のどちらかは不明 (両対応なので shim 影響なし) | #189 コメント (PM 判断で DFM 解析を別チケット化) |
| INVENTORY.md §2 の DS 集計の訂正反映 (生成物扱いのため未編集) | 旧集計 (SetVolume 等) が残る | #11 にコメント (PM が生成元整備) |
| 実 FL からの DS 呼出 e2e | COM アダプタ未実装 | #98 (AU-1) |
| 実機での DS cursor 精度・write-ahead | fake シンクのみ | #187 (AU-2) |

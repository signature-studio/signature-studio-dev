# AU-46 (#4297) burst_gate_test.mjs の CI 配線 — 付録

親: #3432 (AU-38)。REPORT.md は 250 行上限のため、本件の全文をここに置く (REPORT.md は変更しない)。

## 1. 配線方式の判断

前回 run (#4297 の 1 件目の結論) では、`.github/` の変更 (`scripts-test.yaml` の glob 追加) が要るため停止した。
`.github/` の workflow 変更は規約上 diff の依頼 (`pm-apply`) になるため、今回は `.github/` を変えずに済む方式を採った。

- 採用: `tools/pm/test_audio_burst_gate.py` (unittest)。`.github/workflows/scripts-test.yaml` の glob `tools/pm/test_*.py` が拾い、`python3 -m unittest discover -s tools/pm -p 'test_*.py'` で実行される。
- `scripts-test.yaml` の `paths:` には `tools/pm/**` が入っているため、本 PR (`tools/pm/` の変更) で同 workflow も起動する。
- 不採用: `.github/` の glob 追加 (workflow 変更の依頼が要る) / `e2e.yaml` への step 追加 (e2e の重い job に node テストを相乗りさせる)。

## 2. 同層テストの扱い (受入条件 2)

CI から呼ぶ node テストは次の 3 本に揃えた (Linux・ブラウザ不要で閉じるもの)。ラッパーの対象は `tools/pm/test_audio_burst_gate.py` の `CASES`。

| テスト | 元の issue | CI 配線 |
|---|---|---|
| `burst_gate_test.mjs` | AU-38 (#3432) | 本 PR で配線 |
| `worklet_jump_check.mjs` | AU-29 (#3115) | 本 PR で配線 |
| `safari_mock_test.mjs` | AU-35 (#3193) | 本 PR で配線 (`SAFARIDRIVER` に `safaridriver_mock.mjs` を渡す) |

対象外:
- `fla_test.c`・`flmidi_test.c`: C のテストで、node の glob 実行とは別。CI 配線は本 issue の範囲外。
- `page.mjs`・`page_midi.mjs`・`index*.html`: テストではなくページ本体。

## 3. 実測

測定 commit: PR 本文の「測定 commit」欄に記載 (`tools/pm/test_audio_burst_gate.py` 追加・`tools/audio/` 差分 0)。

- `python3 -m unittest discover -s tools/pm -p 'test_audio_burst_gate.py' -v` → 3/3 OK (0.555 s)
- `python3 -m unittest discover -s tools/pm -p 'test_*.py'` → 58 tests OK (0.628 s)
- 単体の実行: `burst_gate_test.mjs` 9/9 PASS・`worklet_jump_check.mjs` rc=0・`safari_mock_test.mjs` rc=0 (mock)

## 4. ネガティブコントロール

- 規則を 1 件壊す: `tools/audio/harness/burst.mjs` の `burstGate` を `runs > 0` から `runs >= 0` に変更 → `test_burst_gate` が FAIL (`FAIL burst_hist 無し (取得失敗) は FAIL` 他)。元に戻して OK を再確認 (`tools/audio/` の差分 0)。
- worklet 側の制御は、`sed` の置換が効いておらず無効だった (PASS のまま)。`git checkout --` で元に戻した。本 PR の負の制御は burst 側の 1 件で満たす。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `fla_test.c`・`flmidi_test.c` の CI 配線 | C 側のテストは CI から実行されない | 必要なら別 issue (本 issue の範囲外) |
| `worklet_jump_check.mjs` の負の制御 (規則を壊して FAIL) は未実測 | 配線は確認済みだが、worklet 側の FAIL 経路は実機未確認 | 本 PR の範囲で未実施 |

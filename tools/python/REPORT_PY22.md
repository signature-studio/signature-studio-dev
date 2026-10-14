# PY-22 (#1053): flcpt / flrack の関数実装と Chord progression の関数呼び出し検証

結論: **未達 (部分達成)**。`flcpt` / `flrack` の関数・メソッドは未実装。戻り値を実測できたのは 9 関数中 3 件で、
残り 6 件は FL 側の型・戻り値が repo に無いため呼べなかった。実装は子 issue に分割する (§5)。

## 1. 入力と前提

| 項目 | 手順 | 実測 |
|---|---|---|
| fl-win64 展開 | `tar --zstd -xf fl-win64.tar.zst` (`$RUNNER_TEMP/fl-win64`) | 成功 |
| emsdk 展開 | `tar --zstd -xf toolchain-emsdk.tar.zst` | 成功 |
| CPython wasm | `build_cpython_wasm.sh` | exit 0 |
| pyc 抽出 | `analysis/extract_pyc_blocks.py` | pyc 40 本 (MCPTools 含む) |
| pyscript 2 本 | block24772 → `cpt.pyscript`、block24775 → `stack.pyscript` | 当時は手動配置 (抽出器は pyscript を書かなかった)。現在の抽出器は `pyscript/{cpt,stack}.pyscript` を書く (REPORT_PY84.md §4.2) |
| API stubs | `git clone IL-Group/FL-Studio-API-Stubs` | `flcpt` / `flrack` を含まない |
| flpy 再リンク | `build_flpy.sh` | exit 0 |

FL 由来物は `work/` (gitignore) に置き、commit しない。

## 2. 既存 e2e (変更なし・HEAD で再現)

| 実測 | 値 |
|---|---|
| `node tests/chord_progression_e2e.mjs` | 41/41 PASS、0.3 s |
| `node tests/chord_progression_e2e.mjs --neg` | 34/41、FAIL 7、exit 1 |

## 3. 呼び出し probe (`tests/chord_progression_call_probe.mjs`)

`flcpt.cpt` / `flcpt.chordPool` を「読まれた属性を記録する」スタブに置き換えて、代表関数を呼んだ結果。
**戻り値は一切作っていない**。`OK` は例外なしで返ったことだけを示し、戻り値の正しさは未検証。

| 関数 | 結果 | 読まれた flcpt 属性 |
|---|---|---|
| apply_chord_preset | OK (早期 return) | cpt.chordMarkerCount, cpt.resolution |
| get_chord_name | AttributeError: 'list' object has no attribute 'split' | - |
| text_to_chord | StopIteration | cpt.addChordMarker, cpt.chordMarkerCount |
| get_chord_root | TypeError: '<=' not supported between int and Rec | cpt.getChordMarker, .time |
| get_chord_preset_str | OK | cpt.chordMarkerCount |
| get_rhythm_preset_str | IndexError | cpt.chordMarkerCount |
| get_chord_pool_preset_str | NotImplementedError | - |
| analyse_chord | StopIteration | cpt.chordMarkerCount |
| reset | OK | chordPool.clear, cpt.clearChordMarkers, cpt.genre |

集計: 9 関数中 呼べた 3 (うち apply_chord_preset は `chordMarkerCount` が 0 のため早期 return で、実処理に入っていない)、
呼べなかった 6。

## 4. 未達の理由

- `flapi_table.json` の `flcpt` / `flrack` は **クラス名と属性名の一部** のみ (`"~70 attr"`・`"..."` の省略あり)。
  関数の引数・戻り値の型は無い。
- 公開 API stubs (`IL-Group/FL-Studio-API-Stubs`) にも `flcpt` / `flrack` は無い。
- 戻り値を作ると、それは実 FL の値ではない mock になる (issue 本文が禁じる「根拠なし」の戻り値)。
  よって実装は、FL 実機の戻り値を取れる根拠が揃うまで行わない。

### 4.1 import 時の mock 値一覧 (`tests/chord_progression_call_probe.mjs`)

probe が import 時に入れる値。いずれも実 FL の値ではなく **mock (根拠なし)**。実 FL 照合は #81 (PY-9)。

| 対象 (probe の行) | 入れた値 | 種別 | 起票先 |
|---|---|---|---|
| `flrack.rack.loop_starter_config` (69 行) | `'{"mock": true, "genres": {}, "loops": []}'` | mock (根拠なし) | #81 |
| `flpianoroll.score.PPQ` (71 行) | `96` | mock (根拠なし) | #81 |
| `flrack.rack.flr` / `flrack.flr` (69・70 行) | 空の `types.SimpleNamespace` | mock (根拠なし) | #81 |
| `flcpt.cpt` (63 行) | 読まれた属性を記録する `Rec('cpt')` | mock (根拠なし) | #81 |
| `flcpt.chordPool` (66 行) | 読まれた属性を記録する `Rec('chordPool')` | mock (根拠なし) | #81 |
| `flcpt.ChordMarker` / `ChordAlternative` / `CPT` / `ChordPool` (64・65・67・68 行) | 空の `type(...)` クラス | mock (根拠なし) | #81 |
| `Rec` の dunder (`__bool__`→False、`__int__`/`__index__`→0、`__float__`→0.0、`__len__`→0、`__iter__`→空、`__lt__`/`__gt__`→False) | 固定値 | mock (根拠なし) | #81 |
| `flrack` モジュール全体 (61・62 行) | 空の `types.ModuleType` | mock (根拠なし) | #1327 (実装) / #81 (照合) |

結論: 上の値で得た戻り値・例外・「読まれた属性」の表 (§3) は **mock 値に依存する結果**。実 FL の動作の証拠にはならない。`Rec` の固定値に依存する分岐は、実 FL と一致しない可能性がある。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `flcpt` / `flrack` の関数・メソッド実装 (型・戻り値の実測根拠が必要) | Chord progression の関数の戻り値は未検証 | #1327 (`[PY-30]`) |
| `enveditor` と Audio scripts 12 本 | 本 issue の対象外 | 既存 #1054 (`[PY-23]`)・#1312 (`[PY-23]` partial)・#1310 (`[PY-28]`) が担当 (新規起票しない) |
| 実 FL の戻り値照合 | mock 値と実値の一致は未確認 | #81 (PY-9) |

## 6. 再現

```
bash build_cpython_wasm.sh
FLPY_OUT=... bash build_flpy.sh          # FL_WIN64_DIR=<fl-win64 展開先> EMSDK_DIR=<emsdk>
node tests/chord_progression_e2e.mjs      # 41/41
node tests/chord_progression_e2e.mjs --neg # exit 1 (34/41)
node tests/chord_progression_call_probe.mjs # 呼び出し表 (9 関数)
```

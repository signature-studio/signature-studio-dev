# PY-7 (#78): Chord progression 41 本の import / エントリポイント実行 — mock 条件つき

結論: Chord progression の **41 本 (pyc 39 + pyscript 2) を wasm CPython 上で 41/41 import・実行** (mock 条件つき)。ネガティブコントロール (pyc 先頭 1 バイトを壊す) で 7 本が FAIL し exit 1。**実 FL の戻り値とは照合していない** (実 FL 照合は #81 PY-9)。

## 1. 入力 (FL 由来・gitignore・commit しない)

| 項目 | 手順 | 実測 |
|---|---|---|
| fl-win64 展開 | `tar --zstd -xf fl-win64.tar.zst` | 5.5 s |
| CPython wasm | `build_cpython_wasm.sh` | 4m05.2s (本 run) |
| pyc 抽出 | `analysis/extract_pyc_blocks.py` (magic `cb0d0d0a` → marshal → `co_filename` で配置) | pyc 40 本 (MCPTools 1 + Chord progression 39)、0.1 s 未満 |
| pyscript 2 本 | block24772 = `cpt.pyscript` (CPT comms, `from control import *`)、block24775 = `stack.pyscript` (Stack comms, `from control_rack import *` + `initialise_system()`) | 先頭行・内容で同定 |
| flpy 再リンク | `build_flpy.sh` | 7.1 s |

`co_filename` は `.py` 名のため、配置時に `.pyc` 名へ変換する (sourceless import 用)。

## 2. 実行結果 (wasm 上, `tests/chord_progression_e2e.mjs`)

| 実測 | 値 |
|---|---|
| 3 回 (load 0.02〜0.11) | 41/41 PASS × 3、スクリプト内 0.5 秒 |
| ネガティブコントロール (`--neg`: `Chords/data.pyc` 先頭 1 バイト反転) | 34/41、FAIL 7、exit 1 |

FAIL 7 (neg) の内訳: `Chords/data.pyc` 自身と、それを import する `control` / `control_rack` 等 (`bad magic number`)。

## 3. mock 値 (根拠なし・実 FL の値ではない)

| 対象 | mock 値 | 根拠 |
|---|---|---|
| `flrack.rack.loop_starter_config` | `{"mock":true, "version", "compatible_from" (同梱 asset の値), "genres" (同梱 asset の値), "loops":[]}` の JSON | **根拠なし**。`rack.load_config` の分岐 (`version` 比較・`remote_config` 採用) を通すため。実 FL の値ではない |
| `flpianoroll.score.PPQ` | `96` | **根拠なし**。import 時の参照のみ満たす (flpianoroll 既定 `DEFAULT_PPQ = 96` と同値。実 FL 値の裏付けではない) |
| `flcpt` (`cpt` / `ChordMarker` / `ChordAlternative` / `chordPool` / `CPT` / `ChordPool`) | 空の型・名前空間 | **根拠なし**。import 時の名前参照のみ満たす。`flapi_table.json` に関数表は無い |
| `flrack.flr` | 空の名前空間 | **根拠なし** |
| `Notes/pattern_presets.cpt` | 空ファイル | **根拠なし**。FL 付随の未抽出データ (block25163 は別物と確認) |
| `Notes/genres` | FL 同梱 block24797 (平文 JSON, 191 KB) を配置 | 実データ。ただし `loop_starter_config` 側は上記 mock 経由で使う |

## 4. 実行できた本数 (エントリポイント = import 時の実行 + pyscript の exec)

- pyc 39 本: import ok 39/39 (`Chords` 8 / `Notes` 14 / `States` 3 / `consonance` 2 / `toolbox` 2 / `control`・`control_rack`・`rack`・`util`・`util_rack`・`asset_io`・`constants`・`constants_rack`・`flcpt_proxy` 等)。
- pyscript 2 本: `cpt.pyscript` exec ok、`stack.pyscript` exec ok (`initialise_system()` まで実行)。
- **実行できない本数: 0**。ただし「エントリポイント」は FL の `createDialog` / `apply` ではなく、**import 時のトップレベル実行**を指す。Chord progression の pyc は FL から呼ばれる関数 (`apply_chord_preset` 等) を、この検証では呼んでいない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実 FL の `loop_starter_config` / `PPQ` / CPT 既定値 | mock 値のため、import は通っても実 FL と同一動作の保証は無い | #81 (PY-9) |
| `flcpt` / `flrack` の関数・メソッド実装 (classes 名のみ) | Chord progression の関数 (`apply_chord_preset` 等) の戻り値は未検証 | 親 #35 / 別 issue に分割 (PM 判断) |
| `Notes/pattern_presets.cpt` の抽出元 | 空ファイル mock | FL の付随データ抽出 (fl-win64 の別 block を要調査) |
| `fetch_inputs.sh` / `run_all.sh` の `/home/ubuntu` 固定パス | runner では env 指定が必要 | REPORT §10 既存 |

## 6. 再現

```
PY312=work/build-native/install/bin/python3.12   # build_cpython_wasm.sh で作る (run_all.sh step 15 と同じ)
FL_WIN64_DIR=<fl-win64 展開先>/extracted "$PY312" analysis/extract_pyc_blocks.py work/fl_extract
# pyscript 2 本: block24772 → work/fl_extract/pyscript/cpt.pyscript、block24775 → stack.pyscript
bash build_flpy.sh && node tests/chord_progression_e2e.mjs      # 41/41
node tests/chord_progression_e2e.mjs --neg                       # exit 1 (ネガコン)
```

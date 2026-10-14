# tools/python REPORT: PY-167 (#3181) flrack.flr の型・戻り値の PE 根拠

> 正本: `tools/python/REPORT_PY22.md` §4.1・§5 (flrack の mock 一覧と未解決)。親 #3176 の PY-166 (`REPORT_PY166.md`・PR #3183) とは独立に、main から測定した。

## 結論

- **`flrack.flr` は FLEngine PE に存在しない。** NUL 終端の `flr` は全 PE block で 0 件。`flrack` 系の名前は `flrack`・`flrack.Channel`・`flrack.Channels`・`flrack.Rack` の 4 件のみ (VA は §1)。
- **同梱 pyc は `flrack.flr` を一度も読まない。** `LOAD_ATTR flr` は全 pyc で 0 件。よって `chord_progression_call_probe.mjs` の mock `flrack.flr` と `flrack.rack.flr` (および `chord_progression_e2e.mjs` の同じ 2 行) は、どの pyc からも読まれない。
- **Chord progression が使う `flr` は C 側の属性ではなく、pyc の module global** (`rack.py` 285 行 `flr = Rack()`)。型は pyc 内の Python クラス `rack.Rack` のインスタンスで、PE の VA は無い (根拠は pyc のみ)。`from rack import flr` で 5 モジュールが取り込む (§2)。
- **根拠が取れない部分** (mock・根拠なし): `flr` の各メソッド・属性の戻り値。読取の名前と件数は §2 で確定したが、戻り値は `rack.py` の Python 本体の解析が要る。mock 表の置換と合わせて子 #3182 (PY-168) に移す (§4)。

## 手段

- PE: `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flrack_flr_probe.py` (本 PR で追加)。`<展開先>` は `tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先>` で得る。
- pyc: `python3.12 analysis/py167_flr_pyc.py <展開先>/extracted` (本 PR で追加)。同梱 pyc は magic `cb 0d 0d 0a` (CPython 3.12 の bytecode) のため、3.12 以外の `dis` では命令を読めない (3.14 では IndexError)。

## 1. PE の確定 (`flrack.flr` の不在)

| 名前 | PE 上の件数・VA (block00031_PE.bin) | 読み |
|---|---|---|
| `flr` (NUL 終端) | 全 `block*_PE.bin` で **0 件** | C 側に `flr` という名前の属性・型名は無い |
| `flrack` | VA `0xd336b3` | モジュール名 |
| `flrack.Channel` | VA `0xd33998` | 型名 |
| `flrack.Channels` | VA `0xd33a28` | 型名 |
| `flrack.Rack` | VA `0xd33be4` | 型名 (PY-166 の属性表と同じ `flrack.Rack` 型) |

- 部分一致の `flr` は PE に 6 件ある (`flrack` 系 4 件 + `flrMidiNote`・`flrMidiCC` 2 件)。後者 2 件は別の名前で、`flr` という属性ではない。
- よって `flrack.flr` の型・戻り値は **PE に根拠が無い (存在しない)**。VA は付けられない。

## 2. pyc の確定 (`flr` の実体)

| 項目 | 結果 (`py167_flr_pyc.py`) |
|---|---|
| 定義 | `block24774_DATA.bin` (`./rack.py`) の 285 行 `flr = Rack()` (`STORE_GLOBAL`)。`Rack` は同 module 119 行の class |
| `from rack import flr` の元 | `control_rack.py` (block24771)・`util.py` (block24776)・`util_rack.py` (block24777)・`Notes/drum_setup.py` (block24795)・`Notes/drums.py` (block24796)。各 1 件 |
| `flrack` 属性として `flr` を読む | **0 件** (全 pyc の `LOAD_ATTR flr` は 0) |
| `flr` に続く属性読取 (上位) | `config` 152・`get_channel` 43・`channels` 26・`genre` 22・`random_presets` 10・`get_group` 9・`stack_ids` 9・`progression_cid` 9・`groups` 7・`pattern_scale_root` 6・`update` 2 ほか |
| `flrack` に続く属性読取 | `rack` 21・`RackError` 15・`fl_rack` 8・`value_to_label_map` 2 (`rack.py` の `flrack` は C モジュール。`control_rack.py`・`util_rack.py` の `flrack` は `import rack as flrack` の別名) |

- 名前参照の元は `block24774_DATA.bin` の file offset 43908 付近 (`fl2py` の `inner` の `co_names` `('flr', 'update')`)。issue の 3 件はこの系統。
- `rack.Rack` の型: pyc 定義の Python クラス (PE 外)。`Rack()` の戻り値はそのインスタンス。型の根拠は pyc の `STORE_GLOBAL` (285 行)。

## 3. mock 表との照合

| mock 行 | 内容 | pyc の実態 | 判定 |
|---|---|---|---|
| `chord_progression_call_probe.mjs` 69 行 `flrack.rack.flr` / `chord_progression_e2e.mjs` 76 行 | 空の `SimpleNamespace` | `flrack.rack.flr` の読取 0 件 (`LOAD_ATTR flr` は 0) | **未読の mock** (根拠なし)。probe の結果には影響しない |
| `chord_progression_call_probe.mjs` 70 行 `flrack.flr` / `chord_progression_e2e.mjs` 77 行 | 空の `SimpleNamespace` | `flrack.flr` は PE に無く、pyc も読まない | **存在しない名前の mock** (根拠なし)。実体は `rack.flr` (`Rack` インスタンス) |

- 型 `rack.Rack` と戻り値の mock (`flr.config` 等の中身) は mock 表に無い。`flr` の実体を mock するなら `rack.flr` を `Rack` 相当のスタブで置くことになる (#3182)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `flr` の各メソッド・属性の戻り値 (`rack.py` の `Rack` クラスの本体) | 戻り値は mock のまま。読取の名前と件数だけ確定 | 子 #3182 (PY-168) |
| mock 表の `flrack.flr`・`flrack.rack.flr` を `rack.flr` の定義へ置換 (2 probe) | 未読のため現行 probe の結果は変わらないが、表と実態が食い違う | 子 #3182 (PY-168) |
| `flr` の値の実 FL 照合 | 実機の値との一致は未確認 | #81 (PY-9) |

## 5. 検証

- 測定 commit: `d4715757` (probe 2 本を追加した commit。以後の commit は本 REPORT と `docs/DOC_MAP.md` の行だけ)。
- コード差分: `git diff d4715757 HEAD -- tools/python/analysis` の出力は 0 行 (本 REPORT の commit は analysis に触れない)。

| コマンド | 結果 | wall |
|---|---|---|
| `FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flrack_flr_probe.py` (`d4715757`) | rc 0・`flr` 0 件・`flrack` 系 4 件 (VA は §1) | 20.5 秒 |
| `python3.12 analysis/py167_flr_pyc.py <展開先>/extracted` (`d4715757`) | rc 0・`from rack import flr` 5 件・`flrack.flr` 読取 0 件 | 3.4 秒 |

- 素材: `fl-win64.tar.zst` を `$RUNNER_TEMP/fl-win64` に展開 (5.6 秒)。`toolchain-emsdk` は未使用。
- e2e (`chord_progression_call_probe.mjs`・`chord_progression_e2e.mjs`) は**未実行**。`src/` と mock 表を変えていないことと、`dist/flpy.js` が未ビルドで wasm の再ビルドが要るため。mock の変更は #3182 で行い、その時に再測定する。

## 再現

```
tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先>
FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_flrack_flr_probe.py
python3.12 analysis/py167_flr_pyc.py <展開先>/extracted
```

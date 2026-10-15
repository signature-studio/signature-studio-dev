# tools/python REPORT: PY-297 (#4070) flrack.rack.loop_starter_config 未設定時の属性読出しの実測

> 正本: `tools/python/REPORT_PY168.md` (未設定時の `load_config` と e2e FAIL 4)・`tools/python/REPORT_PY166.md` (PE 上の型 T_OBJECT_EX)。本付録は PY-297 の実測のみ。

## 結論

- 受入条件 1: `load_config` を経由しない入口として、`flrack.rack.loop_starter_config` の**直接属性読出し**を特定し、probe で実測した。未設定の読出しは `AttributeError` になった。
- 限界: この実測の `flrack.rack` は **mock (根拠なし)** の `__slots__` クラスである。本物の `flrack` は FL 本体の native モジュールで、この wasm には無い。`AttributeError` は CPython の T_OBJECT_EX (未設定 NULL の読出し) の性質に基づく推定を wasm 上で確かめたもので、FL 実機の挙動の実測ではない。
- 受入条件 2 (呼べた数の変化の REPORT 記載) と 3 (反映できない部分の `mock (根拠なし)` 明記) は本 run では扱わない。3 のうち本付録で明記したのは `flrack.rack` の型だけである。

## 1. 入口の特定

`work/fl_extract/` (FL 由来・gitignore) の全 pyc を走査し、`loop_starter_config` を名前で参照する関数を調べた。

| pyc | 関数 | 参照 |
|---|---|---|
| `rack.pyc` | `Rack.load_config` (132 行目) | 137 行で `flrack.rack.loop_starter_config` に `STORE_ATTR` (書込み)、140 行で `json.loads(flrack.rack.loop_starter_config)` を読む。`try` の `except AttributeError` は 141 行 |
| 上記以外 | (なし) | 0 件 |

- `load_config` の 140 行の読出しは `try` で囲まれ、`AttributeError` は `remote_config = {}` に置き換わる (REPORT_PY168 の結論どおり)。このため `load_config` の経路では AttributeError は外へ出ない。
- `load_config` を経由しない入口は、`flrack.rack.loop_starter_config` を直接読む式である (呼出し側の任意のコードから読める)。

## 2. 実測

probe: `node tests/loop_starter_unset_probe.mjs` (`work/fl_extract/` と `dist/flpy.js` が前提)。`flrack.rack` は `__slots__ = ('loop_starter_config',)` の mock クラスで、属性は未設定にした。

| 呼び出し | 結果 |
|---|---|
| `rack.Rack().load_config()` (未設定・従来の `SimpleNamespace` mock) | `OK` (例外なし) |
| `flrack.rack.loop_starter_config` (直接読出し・未設定・`flrack.rack` は `_Rack`) | `AttributeError: '_Rack' object has no attribute 'loop_starter_config'` |
| `rack.Rack().load_config()` (未設定・`flrack.rack` は `_Rack`) | `OK` (例外なし) |

- 直接読出しの AttributeError は、mock の `__slots__` 未設定属性を wasm の CPython 3.12.1 が読んだ結果である。FL 実機の値ではなく、この probe は CPython の挙動の確認に留まる。

- 直接読出しの AttributeError は、wasm の CPython 3.12.1 上で `__slots__` 未設定メンバの読出しとして発生した (CPython の T_OBJECT_EX と同じ扱い)。
- `load_config` の `OK` は REPORT_PY168 の `OK` と同じで、`try` が AttributeError を吸収したことを示す。

## 3. 反映できない部分 (mock (根拠なし) の明記)

| 項目 | 状態 | 根拠 | 起票先 |
|---|---|---|---|
| `flrack.rack` の型 (`_Rack` の `__slots__`) | **mock (根拠なし)**。本物の flrack は FL の native モジュールで、この wasm に無い | PE 上の型 T_OBJECT_EX (REPORT_PY166)。型そのものは未確認 | #4070 の残り (受入条件 3) |
| 未設定時の読出しが実 FL で AttributeError になるか | **未確認**。T_OBJECT_EX の仕様からの推定 | REPORT_PY166 (PyMemberDef 前提・全行 offset 0 の理由は未確定) | #3182 のコメントで追跡 (旧 #81 は CLOSED) |
| `loop_starter_config` の実 FL の値 | **未確認** | mock 値のまま | #3182 のコメントで追跡 |

## 4. 再現

```
cd tools/python
PY312=work/build-native/install/bin/python3.12
FL_WIN64_DIR=<fl-win64 展開先>/extracted $PY312 analysis/extract_pyc_blocks.py work/fl_extract
node tests/loop_starter_unset_probe.mjs
```

前提の生成物 (gitignore): `fetch_inputs.sh` (rc 0)・`build_cpython_wasm.sh` (rc 0・4 分 10 秒)・`FLPY_SKIP_TABLE=1 build_flpy.sh` (rc 0・22.6 秒・`flpy.wasm` 5,924,680 B)。`extract_pyc_blocks.py` は fl-win64 の全 DATA block (25,166 件) が必要で、一部だけの展開では `pyscript ... 0 block` で rc 3 になる。

測定 commit: `0ccb27aac` (probe の変更を含むコミット)。`git diff 0ccb27aac HEAD -- tools/python` は 0 行 (測定後にコード変更は無い)。

# PY-5405 付録: G1 `0xbd0ba0` の実行時値 (#5932・部分達成)

親: #5493 (PY-5352)・#5145 (PY-4874)。前段: #5458 付録 `REPORT_PY73_APPENDIX_5458.md` (entry から unicorn で 19,956 命令・0.02 秒で抜ける)。
静的解析の結論 (RVA `0x7d0ba0` → file offset `0x7cffa0`・LE u64 `0x0000000000bd0c68`・`.reloc` に DIR64 あり) は #5932 のコメント (ポンプ波 42) に従う。

## 1. 結論

- 受入条件 (初期化時点と `0x11c8950` 呼出し前の両方で G1 を採取し、静的値 `0x0000000000bd0c68` と照合する) は **部分達成**。
- 初期化時点: G1 = `0x0000000000bd0c68` (優先基底 `0x400000` で読込み・照合一致)。
- `0x11c8950` 呼出し前: **未採取**。`0x11c8950` への到達は 0 回。前例と同じく初期化の途中で抜けるため、呼出し前の値は得られない。
- 静的値と実行時値の照合は、初期化時点の 1 点だけ成立。呼出し前の照合は未達。

## 2. 測定

- 素材: `fl-win64` の `block00031_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'`・`<展開先>/extracted/block00031_PE.bin`)。
- unicorn 2.1.4 (`uv pip install unicorn==2.1.4 pefile capstone`・repo 外ではなく gitignore の `work/venv`)。
- ハーネス: `tools/python/analysis/flapi/g1_runtime_5932.py`。
  `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/g1_runtime_5932.py 2000000 60`
- 実行結果 (上限 200 万命令・60 秒): base `0x400000`・19,956 命令・0.02 秒・終了 `正常終了`・戻り先 `0x100ffff0`・最後の code `0x1376892`。
  - G1 at first instruction (init) = `0x0000000000bd0c68`
  - `0x11c8950` hits = 0・G1 at callee entry = 未到達

## 3. 判定表

| 時点 | G1 の値 | 静的値との照合 | 根拠 |
|---|---|---|---|
| 初期化の先頭 (entry 直後) | `0x0000000000bd0c68` | 一致 (基底 `0x400000`) | `g1_runtime_5932.py` の `init` 採取 |
| `0x11c8950` 呼出し前 | **未確認 (手段の限界: 初期化が途中で戻り `0x11c8950` に届かない)** | 未照合 | `callee hits=0` |

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 初期化が途中で longjmp 相当に抜ける原因 (import スタブの戻り値・副作用) | `0x11c8950` 呼出し前の G1 が採れない | #5932 (Refs・残件) |
| 実行時の読込み基底 B を確定した上での `B + 0x7d0c68` の照合 | 基底 `0x400000` 以外での値 | #5932 (Refs・残件) |

子 issue は起票していない (本 run の範囲は初期化時点の採取と、再現手段の確定まで)。

# PY-5405 付録: G1 `0xbd0ba0` の実行時値 (#5932・部分達成)

親: #5493 (PY-5352)・#5145 (PY-4874)。前段: #5458 付録 `REPORT_PY73_APPENDIX_5458.md` (entry から unicorn で 19,956 命令・0.02 秒で抜ける)。
静的解析の結論 (RVA `0x7d0ba0` → file offset `0x7cffa0`・LE u64 `0x0000000000bd0c68`・`.reloc` に DIR64 あり) は #5932 のコメント (ポンプ波 42) に従う。

## 1. 結論

- 受入条件 (初期化時点と `0x11c8950` 呼出し前の両方で G1 を採取し、静的値 `0x0000000000bd0c68` と照合する) は **部分達成**。
- 初期化時点: G1 = `0x0000000000bd0c68` (優先基底 `0x400000` で読込み・照合一致)。
- `0x11c8950` 呼出し前: **未採取**。`0x11c8950` への到達は 0 回。初期化は正常に return し、`0x11be0a0` を通る handler が trace に現れないため届かない (経緯と根拠は §4)。
- 静的値と実行時値の照合は、初期化時点の 1 点だけ成立。呼出し前の照合は未達。

## 2. 測定

- 素材: `fl-win64` の `block00031_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C <展開先> --wildcards '*block00031_PE.bin'`・`<展開先>/extracted/block00031_PE.bin`)。
- unicorn 2.1.4 (`uv pip install unicorn==2.1.4 pefile capstone`・repo 外ではなく gitignore の `work/venv`)。
- ハーネス: `tools/python/analysis/flapi/g1_runtime_5932.py`。
  `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/g1_runtime_5932.py 2000000 60`
- 同じ素材の全命令 trace (§4 の根拠): `FL_WIN64_DIR=<展開先> python3 tools/python/analysis/flapi/g1_trace_5932.py /tmp/opencode/full_trace.txt` (出力先は引数で必須)。
- 実行結果 (上限 200 万命令・60 秒): base `0x400000`・19,956 命令・0.02 秒・終了 `正常終了`・戻り先 `0x100ffff0`・最後の code `0x1376892`。
  - G1 at first instruction (init) = `0x0000000000bd0c68`
  - `0x11c8950` hits = 0・G1 at callee entry = 未到達

## 3. 判定表

| 時点 | G1 の値 | 静的値との照合 | 根拠 |
|---|---|---|---|
| 初期化の先頭 (entry 直後) | `0x0000000000bd0c68` | 一致 (基底 `0x400000`) | `g1_runtime_5932.py` の `init` 採取 |
| `0x11c8950` 呼出し前 | **未確認 (初期化は正常に return し、`0x11be0a0` を通る handler が trace に現れないため届かない。§4 参照)** | 未照合 | `callee hits=0`・trace の `0x11be0a0 executed=False` |

## 4. 訂正 (前 run の「初期化が途中で抜ける」は誤り)

前 run は「初期化が longjmp 相当に途中で抜ける」と書いたが、全命令の trace で誤りと確認した。

- `analysis/flapi/g1_trace_5932.py` で entry `0x1376820` の全命令 (19,956 命令) を記録した。
- entry は `0x412020` の初期化テーブル走査で handler を **896 件** 呼び、`0x1376892: ret` で正常に return している。
- `0x412680` / `0x4126f0` の対は、longjmp ではなく関数内の文脈切替 (`0x412760`→`0x412680` で保存、`0x4126f0` で復元) で、異常終了ではない。
- `0x11c8950` の呼出し元 `0x11be0a0` は trace に 1 度も現れない (`executed=False`)。つまり `0x11c8950` に届かないのは、初期化が途中で抜けるからではなく、この経路を初期化テーブルの handler が通らないため。
- 残る原因の候補: `0x11be0a0` を呼ぶ handler が、import の戻り値 0 (rax=0) により分岐で外れている。未確定。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x11be0a0` を呼ぶ handler の特定 (`0x11be0a0` を指す参照元の列挙と、import 戻り値 0 による分岐の確認) | `0x11c8950` 呼出し前の G1 が採れない | #5932 (Refs・残件) |
| 実行時の読込み基底 B を確定した上での `B + 0x7d0c68` の照合 | 基底 `0x400000` 以外での値 | #5932 (Refs・残件) |

子 issue は起票していない (本 run の範囲は前 run の誤り訂正と、呼出し経路の確定まで)。

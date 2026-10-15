# REPORT_APPENDIX_4923: `0x1000ba05` の引数 (edx) の形と、有効な番地を渡した突合 (PLG-G2-68)

親 issue: #4147 (PLG-G2-50)。 本付録の対象 issue: #4923。 前段の経緯: `REPORT_APPENDIX_4087.md` §2・§5。

## 1. 結論

- `0x1000ba05` の引数 `edx` は **ポインタ** で、指す先の **8 バイトの double** を読む。 `[edx+4]` (上位 dword) の指数部が全 1 (Inf/NaN) のときは、符号と指数を組み直して ST(0) に積む。 それ以外は `fld qword [edx]` で積む。 戻り値は `eax` (上位 dword の該当部)・ST(0) に積んだ値。
- 呼出し元は `.text` (VA `0x10001000`) の直接 `call 0x1000ba05` が 4 箇所 (逆アセンブルで確認)。 直前の lea は 3 箇所が `lea edx,[esp+8]` (`0x10009cfc`・`0x10009d79`・`0x10009db6` → call `0x10009d0c`・`0x10009d7d`・`0x10009dba`)、1 箇所が `lea edx,[esp+0xc]` (`0x10009cd9` → call `0x10009cdd`)。 いずれも呼出し元のスタック上の double の番地を渡す。 `0x10009cd9` を指す直接の参照 (rel/abs) は `.text` 内に見つからなかった。 ジャンプテーブル経由の入口は未確認。 harness が `edx=0` に固定していたため、native が `[0+4]` を読んで rc -11 になっていた (#4087)。
- `edx` に OBJ 窓 (`0x10F80000`) の番地を入れ、先頭 8 バイトに double を置く入力で、native と wasm を **2000 / 2000 行一致** (eax・ST(0) の float64 bit・x87 深さ・OBJ 窓)。 native・wasm とも rc 0 で終わる。
- 同じ commit の既存 harness (`edx=0`) では、`fn_1000ba05` は native rc -11 のまま (§3)。 既定ゲートの経路は変えていない。

## 2. 入力と突合 (測定)

- 測定 commit: `f74f87006` (本 PR の HEAD。 origin/main `dfeecc239` を取り込んだ merge commit)。 branch `4923-x87-ba05-edx` で測った。
- 入力: `probe_ba05_4923.py` が作る。 seed 4923。 行数 2000。 double の種類を 6 通りに循環させる (normal・inf・nan・zero・denorm・big 指数)。 符号は乱数。 OBJ 窓の残り (0x540 − 8 B) は乱数。 `edx = OBJ (0x10F80000)`。 `ecx = OBJ`。 引数 6 本は 0。
- 変更点は native・glue の `call_guest` の `edx` だけ (`xor %edx,%edx` を外し、`R[RDX] = ecx` にする)。 既存の `x87_fn_native.c`・`x87_fn_glue.c` は変えていない。 プローブ用の複製を `work/ba05_4923/` に作る。

| 種類 | 一致 / 行数 |
|---|---|
| normal | 334 / 334 |
| inf | 334 / 334 |
| nan | 333 / 333 |
| zero | 333 / 333 |
| denorm | 333 / 333 |
| big | 333 / 333 |
| **全体** | **2000 / 2000** |

- 一致の自明性: native の出力は eax の種類 655、ST(0) の float64 bit の種類 1337。 x87 深さは全行 1。 OBJ 窓は全行で入力の先頭 8 B と一致 (`mem` 差分 0 行)。 Inf/NaN 分岐 (callee 側 `1000ba12: je 0x1000ba17`) の行を含む。
- 実測 (測定 commit `f74f87006`): `lift_text.py` real 18.96 s・rc 0 (load1 1.52 時点)。 `probe_ba05_4923.py` real 19.16 s・rc 0 (load1 1.32 時点)。
- 再現: `cd tools/plugins/slayer_engine_ia32 && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 lift_text.py && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 probe_ba05_4923.py` (`emcc` を PATH に入れる)。

## 3. 既存 harness との比較 (同じ commit)

- `probe12_4087.py` (既存・`edx=0`) を同じ commit `f74f87006` で実行 (real 10.15 s・load1 1.37 時点): `fn_1000ba05` は native rc -11・out_lines 0、wasm rc 0・out_lines 16。 wasm は読み先 0x4 が線形メモリ内なので trap せず、読んだ値は native と比べられない (`REPORT_APPENDIX_4087.md` §3 の結論と同じ)。
- したがって、既存の 16 行 (`edx=0`) の wasm 出力は、差分試験の根拠にしない。 本付録の 2000 行 (edx = 有効な番地) が、この関数の突合の根拠。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 既存 harness (`x87_fn_native.c`・`x87_fn_glue.c`) の `edx` を有効な番地にする変更 | 既定の経路では `0x1000ba05` は突合できない。 本付録はプローブの複製で測った | #4147 (PLG-G2-50) |
| 呼出し元 4 箇所 (直接 call。`0x10009cd9` への参照・ジャンプテーブル経由は未確認) の、呼出し時の x87 深さ・double の値の実際の分布 | 本付録の入力は代表値の循環。 実呼出しの入力の分布は未測定 | #4147 (PLG-G2-50) |

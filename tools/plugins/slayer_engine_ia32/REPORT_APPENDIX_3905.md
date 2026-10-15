# REPORT_APPENDIX_3905 — fs: (TEB) を読み書きする関数の native vs wasm 突合 (#3905 PLG-G2-37)

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §13 (結論 1 行)。 本付録が測定値の正本。
- 由来: `REPORT_APPENDIX_3128.md` §5・§8 (fs: の列挙と未達)。 import の方式は `REPORT_APPENDIX_3127.md` §3 (KERNEL32 方針表)。
- 既知類型との関係: 該当なし (`docs/DEFECTS.md` の既存 ID には当たらない。 本件は実行結果の突合)。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (sha256 `84b64c43…de724a9`)。
- 測定 commit: `c71986f10` (`feat(plugins): fs: TEB native vs wasm diff for 3 functions (PLG-G2-37)`。 コードを変えた最後の commit)。 検証 HEAD: `2217f6748` (main 取り込み後の merge commit。 §3 の時間値はこの HEAD の run)。 `c71986f10..2217f6748` で測定対象コードの差分は 0 行。

## 1. 結論と範囲

- fs: を含む 8 関数のうち、 KERNEL32 import を **既存の native モデル (`native_entry.c` の `n_*`) だけで通る 3 本** (`0x1000a307`・`0x1000a42e`・`0x100106a5`) を突合した。 192 / 192 件が bit 一致、 ネガコンで FAIL を検出。
- **範囲は縮めた**: 残り 5 本 (`0x1001147e`・`0x1001157b`・`0x100115c7`・`0x100116db`・`0x1001178f`) は `MultiByteToWideChar`・`WideCharToMultiByte`・`LCMapStringA/W`・`GetStringTypeA/W` を直接または推移的に呼ぶ。 これらは #3127 の方針表で **fail-fast** のため native は exit 9 で止まる。 この 5 本は未突合 (§6 の子 issue)。
- TEB の内容は、 0 埋め (`ott_teb_blk` と同じ模型) と非 0 (ExceptionList 等の乱数 64 B) の両方を入れた。

## 2. 方式

| 項目 | 内容 |
|---|---|
| native の fs 基底 | `mmap` で `0x00838000` に 4 KiB の TEB 領域を作り、 `set_thread_area` (syscall 243) で GDT の TLS entry に base を向け、 `mov %0, %%fs` で fs を設定 (`native_entry.c` の `set_fs_base`) |
| TEB の内容 | 入力行の 8 番目の欄 (hex 64 B)。 欄が無い行は 0 埋め。 行ごとに書き換える |
| wasm の fs 基底 | `rt32_glue.c` の `g_teb[64]` を `ott_fsbase` に入れる (`ott_set_teb`)。 `entry_wasm.mjs` は行ごとに同じ内容を入れる |
| 出力 | `idx va eax mem(OBJ 128 B) heap(64 B) [teb(64 B)]`。 TEB 欄は入力に欄がある行だけ付く |
| 入力 | `diff_teb.py` の `gen_scen`。 seed 3905、 入口 3 本 × 64 行 = 192 行。 偶数行は TEB 0 埋め、 奇数行は非 0 |
| 範囲の制約 | `0x1000a42e` の `a0` と `0x100106a5` の `a0`・`a1` を小さく絞る (`LIM_SIZE`・`a0 < 0x8000`・`a1 < 0x10`)。 `HeapAlloc` の巨大サイズ経路に入ると native の heap モデル (4 KiB の bump 領域) を超えて SIGSEGV するため (§4) |

## 3. 実測 (検証 HEAD `2217f6748`、 n=1 の run + ネガコン。 emsdk 6.0.12 を上流から新規取得して実行)

| 項目 | 値 |
|---|---|
| 突合 (`python3 diff_teb.py`) | `[compare] PASS: 192 / 192 件が bit 一致、不一致 0 件`・`[diff_teb] PASS`・exit 0 |
| ネガコン (`python3 diff_teb.py --nega`) | `[compare] FAIL: 191 / 192 件が bit 一致、不一致 1 件`・`[nega] 1 bit 壊した出力を検出 (FAIL, exit 1)。 ネガコン OK`・exit 0 |
| 非自明性 (OBJ) | native 実行で OBJ 領域が変わった行 **0 / 192** (`[effect]`)。 OBJ 領域は TEB に依存しない比較のため、 この突合の感度は下記の eax と TEB 欄が担う |
| 感度 (eax) | 3 入口とも eax は全行で単一の値 (`1000a307`: `00000001`、 `1000a42e`・`100106a5`: `10800008`)。 TEB の 0 埋めと非 0 で eax は変わらなかった。 **TEB の値が結果に効くことは示していない** (下記の注を参照) |
| TEB の書込み | 呼出し後の TEB は 192 / 192 行とも入力と一致 (`fs:[0]` を入口で保存し出口で戻す)。 この 3 入口は TEB の値を結果に出さない |
| 回帰 (`python3 diff_entry.py`) | `[compare] PASS: 448 / 448 件が bit 一致`・exit 0 (`native_entry.c`・`rt32_glue.c` の変更後)。 ネガ `FAIL: 447 / 448` |
| 回帰 (`python3 diff_runtime.py`) | `[compare] PASS: 128 / 128 件が bit 一致`・exit 0 |
| ビルド・実行 | native build 0.24 s、 wasm emcc 9.56 s (emsdk 6.0.12)。 native run 0.014 s、 wasm(node) 0.088 s。 load1 0.59 (`diff_teb.py` の `[build]`・`[run]` 行の値) |

注: 3 入口は `fs:[0]` を入口で保存し出口で戻すだけで、 TEB の内容は eax にも OBJ にも出ない。 よって「TEB の値に依存しない」ことを突合で確かめたのは 0 埋めと非 0 の 2 通りの範囲に限る。 TEB の値が効く経路 (例外処理で ExceptionList を辿る経路) は、 この 3 入口では通らない。


## 4. 落ちた経路 (測定の過程)

- 最初の入力 (`a0` が 32 bit 全域) では、 `0x1000a42e` と `0x100106a5` の一部行で native が SIGSEGV (rc -11) した。 `a0` が `0x00f00000` 以上で native の heap bump が領域を超えて `memset` するため (`h32_alloc` の範囲外)。 wasm 側はこの経路を実行していない (native が先に落ちるため) ので、 巨大サイズでの wasm 側の挙動は測っていない。 突合の前に範囲を絞った。
- 範囲を絞った後も TEB 欄の内容は native の入口を落とさなかった (TEB を外した 1 行も同じ結果)。 TEB の内容と SIGSEGV は無関係。

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64   # tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst --wildcards '*block22434_PE.bin'
export EMSDK=$RUNNER_TEMP/emsdk/emsdk PATH=$RUNNER_TEMP/emsdk/emsdk/upstream/emscripten:$PATH   # tar --zstd -xf $ARTIFACTS_DIR/toolchain-emsdk.tar.zst -C $RUNNER_TEMP/emsdk
python3 tools/plugins/slayer_engine_ia32/lift_text.py     # work/lift_text/ott_lifted.c (472 関数・41 import)
python3 tools/plugins/slayer_engine_ia32/diff_teb.py      # 突合 (exit 0)
python3 tools/plugins/slayer_engine_ia32/diff_teb.py --nega
python3 tools/plugins/slayer_engine_ia32/diff_entry.py    # 回帰 (exit 0)
python3 tools/plugins/slayer_engine_ia32/diff_runtime.py  # 回帰 (exit 0)
```

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x1001147e`・`0x1001157b`・`0x100115c7`・`0x100116db`・`0x1001178f` の native vs wasm 突合 (文字列系 import `MultiByteToWideChar`・`WideCharToMultiByte`・`LCMapStringA/W`・`GetStringTypeA/W` が native で未実装 (fail-fast)。 #3619・#3946 で native boot の問題も残る) | fs: を含む 8 関数のうち 5 本が未突合。 受入条件の「8 関数」は未達 | [PLG-G2-52] #4356 (親 #3905) |
| 実 Windows の TEB 実値 | 0 埋め模型と実値の差が出力に出るかは未検証 (Linux では実値を得られない) | #3905 の範囲外 (issue 本文の範囲外に明記) |
| `HeapAlloc` の巨大サイズ経路 (`a0` が大きい) | native の heap モデルが巨大サイズで落ちる。 この経路の突合は未実施。 実 Windows は失敗 (0) を返すため、 モデルの改修が要る | [PLG-G2-53] #4357 (親 #3905) |

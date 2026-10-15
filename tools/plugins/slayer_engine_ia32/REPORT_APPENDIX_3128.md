# REPORT_APPENDIX_3128 — Slayer_Engine.dll の実行時の未検証 3 点 (#3128 PLG-G2-27)

- 親 REPORT: `tools/plugins/slayer_engine_ia32/REPORT.md` §13 (結論 1 行)。 本付録が測定値の正本。
- 由来: `REPORT_APPENDIX_1098.md` §7 → #1223 → 本 issue。 3 点とも #1223 の leaf 4 本では通らない。
- 既知類型との関係 (`docs/DEFECTS.md`): 該当なし。 本件は実行結果の突合と列挙で、新類型は観測していない。
- 起動・GUI に関わらない (製品 KPI は対象外)。 入力は fl-win64 の `block22434_PE.bin` (sha256 `84b64c43…de724a9`)。
- 測定 commit: `ec85963e0` (コードを変えた最後の commit。 `diff_runtime.py`・`runtime_enum.py`・`diff_entry.py` の build 関数化)。

## 1. 結論

| 論点 | 結果 | 件数 |
|---|---|---|
| (a) 間接 call (`ott_dispatch`) | native と wasm が 128 / 128 件 bit 一致 (n=3 とも)。 ネガコンは 1 bit で FAIL | 呼先の出現 2 入口 × 64 行 |
| (b) `sahf` の AF 未反映 | AF を読む命令 (lahf・pushf/pushfd・daa・das・aaa・aas) は lift 済み 472 関数に **0 件**。 sahf (AF を書く) は 32 件 / 13 関数だが、読む側が無いので観測差は出ない。 native 突合は出現 0 のため対象外 | 読む命令 0 件 |
| (c) `fs:` (TEB) | fs: を含む命令は 18 件 (関数×命令の組。 distinct VA 15、8 関数)。 **全て `fs:[0]` (SEH chain head)**。 TEB の値を読むのは `mov eax, fs:[0]` の 5 件。 8 関数は IAT (import) を通るため **native 単独実行できず、native 突合は未達** → 子 issue | 18 件 (read 5・write 13) |

- (a) の差分は 0 件のため修復の子 issue は不要。 (c) の native 突合は import 実装が要るため、子 issue に切る (§8)。

## 2. (a) 間接 call の入口と方式

入口は間接 call を含む関数 2 本。 どちらも `p = a0 = OBJ (0x10F80000)`、 `obj = [p+0x40] = OBJ`、 `vtable = [obj] = OBJ+0x60` として、 行ごとに候補の関数を vtable の slot に入れる (`diff_runtime.py` の `ENTRIES`・`gen_scen`)。

| 入口 | 呼出しの形 (逆アセンブル) | slot | 候補の呼先 (ret N が push 数と一致する関数) | 行ごとの出現 (seed 3128) |
|---|---|---|---|---|
| `0x10001060` | `push a1`; `mov edx,[ecx]`; `call [edx+8]` | `OBJ+0x68` | `0x10001240`・`0x10001230`・`0x100011d0`・`0x10009310`・`0x10001ba0` (ret 4) | 14・14・7・14・15 |
| `0x10001080` | `push a2`; `push a1`; `mov edx,[ecx]`; `call [edx+4]` | `OBJ+0x64` | `0x10001b40`・`0x10001210`・`0x10001b90`・`0x10001ab0` (ret 8) | 14・18・20・12 |

- 候補は OBJ 以外のメモリを参照しない関数に限る (例: `0x10008630` は `[a1]` を書くため除外)。
- native: `native_entry.c` (freestanding ELF。 `call [edx+N]` は実機械語のまま)。 wasm: `rt32_glue.c` の `ott_call32` → `ott_dispatch(va)` → lift の `f_<va>`。
- 検証範囲: 呼先が lift 済みの候補 (9 本) のみ。 未 lift の呼先は `ott_dispatch` の `default` で `ott_unlifted` が abort する (fail-fast。 本入力では発生しない)。

## 3. (a) 実測 (測定 commit `ec85963e0`、 n=3)

| 項目 | 値 |
|---|---|
| 突合 (`python3 diff_runtime.py`) | `[compare] PASS: 128 / 128 件が bit 一致、不一致 0 件`・`[diff_runtime] PASS`・exit 0 (3 回とも同一) |
| 非自明性 | native 実行で OBJ 領域が変わった行 63 / 128 (`[effect]`)。 内訳は呼先が書く候補 (`0x10001240`・`0x10001230`・`0x100011d0`・`0x10009310` と `0x10001b40`) の行数 49 + 14 = 63 と一致 (書かない `0x10001ba0`・`0x10001210`・`0x10001b90`・`0x10001ab0` の行は変化なし) |
| ビルド (n=3) | native gcc 0.04 s、 wasm emcc 5.63–5.76 s (emsdk 6.0.12 = `[EMSDK]` の既存 install。 `toolchain-emsdk` は展開していない) |
| 実行 (n=3) | native 0.001 s、 wasm (node) 0.042 s |
| load (cpu 4、並列 1) | load1 0.52–0.59 (`diff_runtime.py` の run 直前) |
| ネガコン (`python3 diff_runtime.py --nega`) | wasm 1 行目の eax の 1 bit を壊す → `[compare] FAIL: 127 / 128 件が bit 一致、不一致 1 件`・`[nega] … ネガコン OK`・exit 0 (判定器は exit 1 で落ちた) |
| 回帰 (`python3 diff_entry.py`、 #1223 の leaf 4 本) | `[compare] PASS: 256 / 256`・`[diff_entry] PASS`。 ネガコン `FAIL: 255 / 256`・exit 0。 `diff_entry.py` は build を関数化しただけで判定は不変 |

## 4. (b) AF を読む命令の列挙

- 入力: `work/lift_text/ott_lifted.c` の命令コメント (`/* VA: mnemonic */`)。 lift 済み関数 472、 命令の出現 21,354 (distinct VA 20,431)。
  lift は `lift_text.py` の現行出力 (第 2 パス・#2814 後)。 `REPORT_APPENDIX_1098.md` の 465 関数とは別版。 `diff_entry.py` は現行版でも 256/256 PASS。
- 列挙 (`python3 runtime_enum.py`):

| 種類 | 命令 | 出現 (distinct VA) | 含む関数 |
|---|---|---|---|
| AF を読む | lahf・pushf/pushfd・daa・das・aaa・aas | **0** (0) | 0 |
| AF を書く (runtime は反映しない) | sahf | 32 (30) | 13 |

- 検算 (`xcheck`、 命令の先頭バイトで数える別手法): 0x9f (lahf)・0x9c (pushf)・0x27/0x2f/0x37/0x3f (daa 系) は 0 件。 0x9e (sahf) は 30 件 (distinct VA 30 と一致)。
- 判定: sahf は AF を書くが、lift 済み範囲に AF を読む命令が無いため、AF 未反映による観測差は生じない (列挙の結果。 推定ではない)。 AF を読む命令が未 lift の関数にある場合は対象外 (未被覆は `REPORT_APPENDIX_1098.md` §3・#2814)。
- native 突合: 出現 0 のため不要。

## 5. (c) `fs:` (TEB) の列挙

| 項目 | 値 |
|---|---|
| fs:/gs: を含む命令 | 18 (関数×命令の組)、 distinct VA 15、 含む関数 8 |
| 読み / 書き | 読み 5 (`mov eax, dword ptr fs:[0]`)・書き 13 (`mov dword ptr fs:[0], esp` 5 件、 `mov dword ptr fs:[0], ecx` 8 件) |
| offset | 全て `fs:[0]` (ExceptionList = SEH chain head)。 他の offset (StackLimit・Self・PEB・TLS 等) は 0 件。 `gs:` は 0 件 |
| 検算 (先頭バイト 0x64/0x65) | distinct VA 15 (一致) |
| 含む関数 | `0x1000a307`・`0x1000a42e`・`0x100106a5`・`0x1001147e`・`0x1001157b`・`0x100115c7`・`0x100116db`・`0x1001178f` |
| 単独 native 実行 | **不可**。 8 関数はいずれも直接・間接で IAT (import) を呼ぶ (`pure` 0 / 8、 `runtime_enum.py`) |

- 値の流れ (`0x1000a307` の例): prologue `mov eax, fs:[0]` → `push eax` (旧 chain を frame.Next に保存) → `mov fs:[0], esp` (frame 登録) … epilogue `mov ecx, [ebp-0x10]` → `mov fs:[0], ecx` (旧 chain を復元)。 TEB の実値は frame を経由して戻されるだけで、 例外が無い限り eax・OBJ 領域に出ない見込み (**推定**。 native 突合で確かめる項目)。
- 模型との関係: lift の `ott_teb_blk` (0 埋め) は、 読みが 0 を返すので frame に 0 を積む。 実 Windows では非 0 の chain head が入る。 Linux では実 TEB 値を得られないため、実値との突合は本 run の範囲外。

## 6. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/fl-win64   # tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64
# emcc (emsdk 6.0.12) が PATH に無ければ、 `[EMSDK]` の upstream/emscripten を PATH に足す (`docs/REFERENCES.md` §4)
python3 tools/plugins/slayer_engine_ia32/lift_text.py          # work/lift_text/ を作る
python3 tools/plugins/slayer_engine_ia32/runtime_enum.py       # (b)(c) の列挙と検算 → work/runtime_enum.json
python3 tools/plugins/slayer_engine_ia32/diff_runtime.py       # (a) 突合 (exit 0)
python3 tools/plugins/slayer_engine_ia32/diff_runtime.py --nega  # (a) ネガコン (exit 0 = 検出)
python3 tools/plugins/slayer_engine_ia32/diff_entry.py         # 回帰 (exit 0)
```

## 7. 鮮度 (WORKFLOW §6)

- 測定 commit `ec85963e0` 以降のコード差分 (`git diff ec85963e0 HEAD -- tools/plugins/slayer_engine_ia32/diff_entry.py tools/plugins/slayer_engine_ia32/diff_runtime.py tools/plugins/slayer_engine_ia32/runtime_enum.py tools/plugins/slayer_engine_ia32/native_entry.c tools/plugins/slayer_engine_ia32/rt32_glue.c tools/plugins/slayer_engine_ia32/entry_wasm.mjs tools/plugins/slayer_engine_ia32/lift_text.py tools/ott/rt tools/ott/lift`) の出力は 0 行 (PR 本文に同じ出力を添える)。
- 測定は `ec85963e0` の内容 (`git status` は work/ を除き空) で行った。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| fs: を含む 8 関数の native vs wasm 突合 (import の実装が要る。 非 0 の TEB 内容での突合を含む) | (c) の native 突合が未達。 eax・OBJ 以外の出力 (frame) の差は未検出 | 子 `[PLG-G2-37]` (親 #3128、依存 #3127) |
| 実 Windows の TEB 実値 | 0 埋め模型と実値の差が出力に出るかは未検証 (Linux では実値を得られない) | 子 `[PLG-G2-37]` の本文に含める |
| 未 lift 関数 (未被覆 10,682 B) の AF 読み・fs: 参照 | 列挙は lift 済み関数のみ | #2814 (PLG-G2-22) |

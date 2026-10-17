# tools/plugins/f2 REPORT_APPENDIX_3374 — PLG-F3-37 (#3374): Delphi 例外 (0xeedfade) の `-E` 経路の実測

- 測定 commit: **c4b6efbfe** (`unicorn_trace.py` の `-E` を追加した最後のコード commit)。
- 鮮度: 測定 commit `c4b6efbfe` 以降の `unicorn_trace.py` の差分はコメント追記のみ (§4)。HEAD `fe4adb84b` で再測定済み (§1)。
- 入力: `block19148_PE.bin` (fl-win64、`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 extracted/block19148_PE.bin`)。
- 依存: `uv venv $RUNNER_TEMP/f2venv && VIRTUAL_ENV=$RUNNER_TEMP/f2venv uv pip install unicorn==2.1.4 pefile capstone`。
- 実 FL の host 値は得られない。

## 0. 結論 (先出し)

1. `-E` は `RaiseException(0xeedfade)` を、戻り番地を含む EHANDLER フレームの kind=2 scope の landing pad (`0x411305`) へ移す。既定 (オプション無し) の挙動は変えていない。
2. `-E` で landing pad に入った後、`0x411a5b` から `MessageBoxA` の致命経路へ進み、DllMain は `rax=0` で終わる。列は `0x5e0340` に届かない。受入 1 は**未達** (#3374 に残す)。
3. kind=2 の意味は未確定。標準的な catch-all とは一致するとは言えない (§3)。

## 1. 実測

コマンド (`-E` の有無で 2 回。`$PE` は上記の展開先):

```
python3 tools/plugins/f2/unicorn_trace.py $PE 0x8525f0 -H -V -S -L -N -p 0x409090 -r rdx=1 -t 0x410ef0 -t 0x411017 -t 0x5e0340 -q 0x8cd068 -q 0x8bf040 -w 0x8bf040:0x8bf048 -m 2000000 [-E]
```

| 実行 | 結果 | wall (time real) | RaiseException | 致命経路 |
|---|---|---|---|---|
| 既定 | `returned to sentinel rax=0x0`・`[0x8cd068]` 0→0・`[0x8bf040]` 0→0x4455a0・`0x5e0340` 入場 0 | 1.442 s | 1 件 (`ret=0x41101d`) | `MessageBoxA` 1 件 (`ret=0x411a5b`) |
| `-E` | `seh: 0xeedfade を 0x411305 へ移す (rsp=0x300ffa60)`・`returned to sentinel rax=0x0`・`[0x8cd068]` 0→0・`0x5e0340` 入場 0 | 1.452 s | 1 件 (catch して移送) | `MessageBoxA` 1 件 (`ret=0x411a5b`) |

- 負荷: 測定前の `/proc/loadavg` は `1.35 0.49 0.18`、測定後は `1.35` と `1.24` (1 分値)。
- 既定と `-E` の差は `-E` の seh 行の有無と RaiseException の扱いだけ。

HEAD `fe4adb84b` での再測定 (コメント追記後。pr-lint `violations=0`):

| 実行 | 結果 | wall (time real) | 負荷 (測定前・後の 1 分値) |
|---|---|---|---|
| 既定 | `rax=0`・`[0x8cd068]` 0→0・`[0x8bf040]` 0→0x4455a0・RaiseException 1 件・`MessageBoxA` 1 件 | 1.456 s | 0.50 / 0.54 |
| `-E` | `seh: 0xeedfade を 0x411305 へ移す (rsp=0x300ffa60)`・`rax=0`・`[0x8cd068]` 0→0・RaiseException 1 件・`MessageBoxA` 1 件 | 1.455 s | 0.50 / 0.54 |

## 2. scope の実在 (静的)

- 関数 `0x411290` (flags=3・frame reg=rbp) の scope 2 件 (`block19148_PE.bin` の `.pdata`・UnwindData を直接読んだ値):
  - `[0x4112bd, 0x411305)` handler=2・jump=`0x411305` (`-E` が使う scope。戻り番地 `0x4112f9`・call site `0x4112f6` を含む)
  - `[0x411306, 0x411316)` handler=0・jump=`0x411320`

## 3. kind 値 (handler 欄) の分布

ファイル全体の EHANDLER scope を数えた値 (`.pdata` 全体):

| handler 欄 | 件数 | jump 先の関係 |
|---|---|---|
| 0 | 1110 | 全件 jump > end |
| 2 | 879 | 全件 jump == end |
| 16 以上 | 29 | (kind 値ではない) |

- 値 1 は 0 件。reviewer の「0・1・2 が混在」は、この集計では確認できなかった。
- kind=2 の jump 先 (879 件) の先頭命令は全件 `nop`。kind=0 の jump 先は上位が `sub; call`・`push; sub` で始まる (kind=0 の先頭命令の全件集計は未実施)。kind=2 の 2〜3 命令目の上位形は `nop; cmp; je` (667 件) など。
- ここまでの binary 側の根拠では、kind=2 が Delphi の except (EOutOfMemory など) に当たるかは**確定しない**。標準の MSVC catch-all (C_specific_handler の except) と一致するかも未確認。

## 4. 鮮度

- 測定 commit `c4b6efbfe` 以降に `unicorn_trace.py` へ入れた変更は、`seh_catch` のコメント追記 (指摘 3・4 への対応) のみ。コードの挙動は変えていない。
- `git diff c4b6efbfe fe4adb84b -- tools/plugins/f2/unicorn_trace.py` の追加行は 2 行 (コメント)。`seh_catch` の中の `#` 行だけ。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| kind=2 の意味 (Delphi の except か) は未確定 | `-E` の catch が正しい except かは未確定 | #3374 に残す |
| `-E` の後、`0x411a5b` の `MessageBoxA` 致命経路へ進み `0x5e0340` に届かない | 受入 1 未達。`[0x8cd068]` は 0 のまま | #3374 に残す |
| `eh_frames` は offset 0・rbp frame の関数だけを扱う。経路上の中間フレームの callee-saved (rbx など) は復元しない | 他の対象へ広げるときに誤る | #3374 に残す (対象 `0x411290` は push なしで問題なし) |

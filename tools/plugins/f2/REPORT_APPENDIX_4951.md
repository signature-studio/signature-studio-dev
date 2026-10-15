# tools/plugins/f2 REPORT_APPENDIX_4951 — PLG-F3-45 (#4951): `[0x8bf040]` を書く関数の特定

- 親: #3374 (受入 3 の原文移送)。前提の記録: `REPORT_APPENDIX_3295.md` §3 (書込み元 `rip=0x44569f` の初出)。
- 測定 commit: 本付録を含む commit (コード変更なし。`unicorn_trace.py`・`write_origin.py` は未変更)。
- 担当 dir: `tools/plugins/f2/` のみ。入力: `$RUNNER_TEMP/fl-win64/extracted/block19148_PE.bin` (`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C $RUNNER_TEMP/fl-win64 extracted/block19148_PE.bin`、2.5 秒)。
- 依存: unicorn 2.1.4 / pefile / capstone (`uv venv` で作成、§4)。

## 0. 結論 (先出し)

1. **受入は達成**: `[0x8bf040]` を書く関数は **`0x445600`〜`0x4456c9`** (pdata の関数境界と一致)。書込み命令は `0x44569f` の `mov qword ptr [rax], rcx` で、`rcx=0x4455a0` を書く。
2. 関数 `0x445600` は、関数ポインタ表 (8 entry) を `.bss` に書く初期化関数 (`lea rcx,[rip+x]` → `mov [rax], rcx` の組)。`0x8bf040` は表の 1 entry。その値 `0x4455a0` は、`0x410ef0` が `call [0x8bf040]` で呼ぶ先 (3295 §3) で、`[rcx+0x28]`・`0x40f060`・`call [rbx]` を行う小関数。
3. 実行時の呼出し: `0x445600` は trace で `#1` のみ (`-t 0x445600` で 1 回)、書込みは `-p 0x409090` (prelude) の中で起きる。`0x445600` の直接 call は PE 内に 0 件。関数ポインタ経由で呼ばれたものと見られる (呼出し元は未特定)。
4. 観測: `[0x8bf040]` の値 `0x4455a0` は、`0x410ef0` の `call qword [0x8bf040]` (`0x410ffa`、3295 §3) の呼び先になる。trace の 3 回の入場 (`rcx=0x300ff4d8`・`0x300ff4d8`・`0x300ff6f8`) は、`[rcx]=0x10eedfade` (例外コード `0xeedfade` の例外オブジェクト) を引数に受けている。呼出し元の経路 (`0x410ef0` 由来か) は未確認。

## 1. 測定 (commit は §0 のとおり、逐次)

| 実行 | 結果 | 備考 |
|---|---|---|
| M-A (`-w 0x8bf040:0x8bf048 -q 0x8bf040`、`-t` なし) | `before [0x8bf040]=0x0`・`after 0x4455a0`・書込み `rip=0x44569f` | 3295 §3 の再現。wall 1.41 秒 (`time` 実測) |
| M-B (M-A + `-t 0x445600 -t 0x4455a0 -t 0x411a80`) | `trace 0x445600 #1` (rcx=0x20・rax=0x445790)、`trace 0x4455a0 #1`〜`#3`、`trace 0x411a80 #1` (rcx=0xcb) | 書込みの直前に `0x445600` が 1 回入る |
| write_origin | `pdata fn [0x445600,0x4456c9): 1 件`・書込み元 `0x44569f` (1 種)・unmapped 0 | `write_origin.py <PE> <trace出力>` の結果 |

- M-B の出力は `$RUNNER_TEMP/mB.txt` (work/ 相当、commit しない)。

## 2. 関数 `0x445600` の構造 (逆アセンブル)

- `0x445600`: `sub rsp,0x28` → `mov rcx, [rip-0x1841b]`・`call 0x4441a0` で結果を `[rip+0x47ffa8]` に格納 (`0x445619`)。`0x445635` も同様。
- `0x44563c`〜`0x4456c1`: `mov rax,[rip+x]` (slot 先の読込み) → 格納の組が 8 組。うち 7 組は `lea rcx,[rip+y]` → `mov [rax], rcx` (関数ポインタの格納)、1 組 (`0x445665`) は `.data` からの qword 複写。slot 先 (`rax` の読込み元) は `0x8bcc50`・`0x8bd260`・`0x8bcf70`・`0x8bd200`・`0x8bd268`・`0x8bd2f0`・`0x8bda00`・`0x8bcbb0` (slot 先の番地の全体像は未確認)。
- `0x8bd2f0` の値は `0x8bf040`。`0x445691` で `rax=[0x8bd2f0]`、`0x445698` の `lea rcx,[rip-0xff]` = `0x4455a0`。よって `0x44569f` の `mov [rax], rcx` が `[0x8bf040] = 0x4455a0` を書く。
- 関数 `0x4455a0` (`0x4455a0`〜`0x4455d1`): 引数 `rcx` (例外オブジェクト) の `[rcx+0x28]` を `rsi` に取り、`0x40f060(rsi, [rip-0x196f7])` の真偽が真なら `call [rbx]` (`rbx=[rsi]`、vtable 先)。`0x40f060` の中身と用途は未確認 (§3)。

## 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x445600` の呼出し元 (関数ポインタ経由。PE 内の直接 call 0 件・絶対 qword 参照 0 件) | 誰がこの初期化を起動するかは未特定。書込みは prelude で実測済み | #3374 (PLG-F3-37、raise 経路の扱いを決める親 issue) |
| `0x40f060` の判定の中身 (`0x4455a0` の分岐条件) | `[0x8bf040]` を呼ぶかどうかの条件。raise の扱い (受入 2 相当) に必要 | #3374 (PLG-F3-37) |
| `0x4455a0` の 3 回の入場の呼出し元 (`[rcx]=0x10eedfade` の例外オブジェクトを扱う) | raise 経路の戻り先の決定 | #3374 (PLG-F3-37) |

## 4. 検証コマンド (リポジトリ直下、`PE=$RUNNER_TEMP/fl-win64/extracted/block19148_PE.bin`、`T=$RUNNER_TEMP/f2venv/bin/python`)

- M-A: `$T tools/plugins/f2/unicorn_trace.py $PE 0x8525f0 -H -V -S -p 0x409090 -r rdx=1 -t 0x411a80 -t 0x5e0340 -q 0x8cd068 -w 0x8cd068:0x8cd070 -w 0x8bf040:0x8bf048 -q 0x8bf040 -m 2000000`
- M-B: `$T tools/plugins/f2/unicorn_trace.py $PE 0x8525f0 -H -V -S -p 0x409090 -r rdx=1 -t 0x445600 -t 0x4455a0 -t 0x411a80 -w 0x8bf040:0x8bf048 -q 0x8bf040 -m 2000000 > mB.txt`
- write_origin: `$T tools/plugins/f2/write_origin.py $PE mB.txt`
- 環境: `uv venv $RUNNER_TEMP/f2venv && VIRTUAL_ENV=$RUNNER_TEMP/f2venv uv pip install unicorn==2.1.4 pefile capstone`

## 5. 鮮度

- 測定 commit: 本付録を含む commit。`git diff <測定 commit> HEAD -- tools/plugins/f2/*.py` は、本付録の commit では空 (`.py` は未変更)。

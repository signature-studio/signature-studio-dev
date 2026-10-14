# #911 付録: 分岐の実行確認 (LD-71 / #1967)

## 6f. #1967 (LD-71): 分岐の実行確認 (既存 v5.0 バイナリへの uprobe。ソースビルドはしていない)

測定 commit: `748c595e` (ws-1967 の基点。repo のコードは使っていない)。素材: `toolchain-retdec` の v5.0 バイナリと `fl-win64` の `block00031_PE.bin` (sha256 `b2c64da4…9496d`)。uprobe は `perf probe -x` で関数内の 3 つの `convertConstantToType` 呼び出し点 (`+768` siteA、`+1426` siteB、`+1475` siteC) に張った。

| 範囲 (`--select-ranges`) | siteA | siteB | siteC |
|---|---|---|---|
| 41a670-41a6f4 (全体) | 2 | 0 | 3 |
| 41a6a0-41a6a3 | 1 | 0 | 0 |
| 41a6d3-41a6d6 | 1 | 0 | 0 |
| 41a6b3-41a6b7 (対照) | 0 | 0 | 0 |
| 666b10-666b13 | 1 | 0 | 0 |
| 666b20-666b23 | 1 | 0 | 0 |
| 666a60-666b20 | 4 | — | — |

- 41a6a0・41a6d3 の各 1 回は、§6c の deref 脱落 2 命令と一致する。
- **未確定**: siteA が L163〜166 (`gv` の分岐) に当たるかは、バイナリに DWARF が無く (`addr2line` は `??`) 逆アセンブル照合でのみ推定した。siteA は別の `convertConstantToType` 呼び出し (ngv 系) と区別できていない。
- 所要: 41a670-41a6f4 の 1 回 7.54 秒 (real、n=1、4 コア)。load average は**未測定** (元の測定時に記録していない)。
- 再現: `tools/m11/ldfix/uprobe_1967.sh` (env: `RETDEC_BIN`・`PE_BIN`・`FUNC_BASE`)。**未検証**: 本 run では `toolchain-retdec` が無く未実行、`perf` は tracefs 権限無しで probe 登録を試せなかった。`FUNC_BASE` (呼び出し元関数の VA) は付録に記録が無く未確定。初回実行で構文と件数を確かめること。


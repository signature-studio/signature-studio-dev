# #5092 (M11-31): unit 144 の 0x6c の出所 — survey trace 計測

> **正本**: `tools/m11/REPORT.md` §21 (本節は #5092 の計測結果)。

## 1. 目的

OFF (lift 版) で `function_412d60` に渡る `dest = 0x6c` を生む読みの元を特定する (受入 1)。
前 run の「次の一手」は、`m11_survey.mjs` に unit 144 の実行中だけ trace を on にする切替 (`M11_SURVEY_TRACE=1`) を足し、
`M11_PROBE_LIST=1` の build で `[probe_free]` と `[m11]` trace を採ること。

## 2. 測定

測定 commit: `b900bf5ad` (origin/main 取り込み時点)。コード変更は `tools/m11/m11_survey.mjs` (trace 切替のみ)。

| 手順 | rc | 結果 |
|---|---|---|
| `FL_WIN64_DIR=<fl-win64 展開先> bash m11_gen_ir2.sh` | 0 | `ir_sha256` = `b202c157a80807f2…`・ldfix = applied |
| `M11_PROBE_LIST=1 bash m11_build.sh` | 0 | wasm-ld 署名不一致 0 / 未定義 0 |
| `M11_PROBE_LIST=1 M11_SURVEY_TRACE=1 M11_SURVEY_STACK=144 node m11_survey.mjs` | 0 | **ok 873 / trap 21 / miss 47 / noproc 1 / clobber 0** (基準 #3643 と一致。挙動不変) |

unit 144 (`0x25c540`) の trace 行 (`[survey][trace144]`):

```
[m11][icall] 0x25c540
[m11][UStrAsg] dest=0x10aa1118 src=0x6c old=0x0
[probe_free] arg1=5c hdr=0 [hdr]=865901
```

## 3. 解釈

- `UStrAsg` の `src=0x6c` は、文字列代入の源が `0x6c` であることを示す。これは `412d60` の `dest` とは別の経路で、`0x6c` が `412d60` に届いたとは言えない。
- `[probe_free] arg1=0x5c` は `409440` に範囲外の `arg1` (0x5c) が渡ったことを示す。`0x6c` とは別の値。
- 本 run の trace では `412d60` の呼出しが出ていない。前 run の観測 (`dest=0x11ec7f8, Q=0` の 1 件) と合わせ、`0x6c` の出所は**未特定**のまま。

## 4. 受入

受入 1 (`412d60` に渡る `0x6c` を生む読みの元の特定): **未達**。

## 5. 未解決

- `0x6c` が `412d60` の `dest` に届く経路の特定 (起票先: #5092 の次 run)。
- IR sha が基準 `597757f4…` と異なる件 (本 run は `b202c157…`)。main の進行による差の可能性。未切り分け (起票先: #5092 の次 run)。

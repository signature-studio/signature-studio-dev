# #5092 (M11-31): unit 144 の 0x6c の出所 — survey trace 計測

> **正本**: 本ファイル (`tools/m11/REPORT_5092.md`)。`REPORT.md` には節を足さない (250 行上限)。

## 1. 目的

OFF (lift 版) で `function_412d60` に渡る `dest = 0x6c` を生む読みの元を特定する (受入 1)。
前 run の「次の一手」は、`m11_survey.mjs` に unit 144 の実行中だけ trace を on にする切替 (`M11_SURVEY_TRACE=1`) を足し、
`M11_PROBE_LIST=1` の build で `[probe_free]` と `[m11]` trace を採ること。

## 2. 測定

測定 commit: `4489454cc` (コードを変えた最後の commit は `00d75e83a` 以前の survey 変更。実行コードは `b900bf5ad` から `4489454cc` まで `tools/m11/m11_survey.mjs` の 5 行のみ)。
実行コード差分 (`git diff b900bf5ad 4489454cc -- tools/m11/m11_survey.mjs`):

```diff
@@ -3,6 +3,7 @@
+//           M11_SURVEY_TRACE=1 (unit 144 の実行中だけ m11_set_trace(1) し、[probe_free]/[probe_list]/[m11] 行を [survey][trace144] で出す。build は M11_PROBE_LIST=1 が要る)
@@ -83,7 +84,11 @@ for (let i = SV_FROM; i < SV_END; i++) {
   if (process.env.M11_SURVEY_PROGRESS === '1') fs.writeSync(2, '[progress] unit ' + i + ' ' + va + ' begin\n');
+  const trU = process.env.M11_SURVEY_TRACE === '1' && i === 144;
+  const errN0 = errs.length;
+  if (trU) mod._m11_set_trace(1);
   try { r = mod._m11_call_unit(i); } catch (e) { err = e; }
+  if (trU) { mod._m11_set_trace(0); for (const l of errs.slice(errN0)) if (/\[probe_free\]|\[probe_list\]|\[m11\]/.test(l)) console.error('[survey][trace144] ' + l.trimEnd()); }
   if (process.env.M11_SURVEY_PROGRESS === '1') fs.writeSync(2, '[progress] unit ' + i + ' ' + va + ' end\n');
```

素材は `[WIN64]` (fl-win64)・work-m11 (lift 中間物)・`[RETDEC]` (toolchain-retdec)・`[EMSDK]` (toolchain-emsdk) を使用。`[RETDEC]`・`[EMSDK]` の実在を確認済み。

| 手順 | rc | 結果 |
|---|---|---|
| `FL_WIN64_DIR=<fl-win64 展開先> bash m11_gen_ir2.sh` | 0 | `ir_sha256` = `b202c157a80807f2…`・ldfix = applied |
| `FL_WIN64_DIR=<fl-win64 展開先> M11_PROBE_LIST=1 bash m11_build.sh` | 0 | wasm-ld 署名不一致 0 / 未定義 0 |
| `M11_PROBE_LIST=1 node m11_survey.mjs` (既定 OFF) | 0 | **ok 873 / trap 21 / miss 47 / noproc 1 / clobber 0** (基準 #3643 と一致。挙動不変) |
| `M11_PROBE_LIST=1 M11_SURVEY_TRACE=1 M11_SURVEY_STACK=144 node m11_survey.mjs` | 0 | 集計は既定 OFF と同一 (ok 873 / trap 21 / miss 47 / noproc 1 / clobber 0) |

unit 144 (`0x25c540`) の trace 行 (stderr では `[survey][trace144]` 接頭辞付き):

```
[m11][icall] 0x25c540
[m11][UStrAsg] dest=0x10aa13e8 src=0x6c old=0x0
[probe_free] arg1=5c hdr=0 [hdr]=865901
```

注: 初版の記録の `UStrAsg dest` は `0x10aa1118` だった。本節の再測定では `0x10aa13e8`。差の原因は未切り分け。`dest=0x6c` を観測しなかったという結論は変わらない。

## 3. 解釈

- `UStrAsg` の `src=0x6c` は、文字列代入の源が `0x6c` であることを示す。これは `412d60` の `dest` とは別の経路で、`0x6c` が `412d60` に届いたとは言えない。
- `[probe_free] arg1=0x5c` の入力を観測した (`0x6c` とは別の値)。`409440` 側の範囲判定は計装していない。
- 本 trace の対象 (UStrAsg / probe_free / icall) では `dest=0x6c` を観測しなかった。`412d60` 自体は計装していない (入口に trace が無い)。前 run の観測 (`dest=0x11ec7f8, Q=0` の 1 件) と合わせ、`0x6c` の出所は**未特定**のまま。

## 4. 受入

受入 1 (`412d60` に渡る `0x6c` を生む読みの元の特定): **未達**。

## 5. 未解決

- `0x6c` が `412d60` の `dest` に届く経路の特定 (起票先: #5092 の次 run)。
- IR sha が基準 `597757f4…` と異なる件 (本 run は `b202c157…`)。main の進行による差の可能性。未切り分け (起票先: #5092 の次 run)。

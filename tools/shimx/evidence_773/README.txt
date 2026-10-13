# #773 裏付けログ (SHX-T9 survey)
HEAD(測定 commit): 0f5d70cc
image: tools/m11/work/shimx_link/m11_sx_trace_soft_fix.cjs
image sha256: b674477d77504ea4d8368a6b4e72f05989ddcadf1cb8a015de39025fb3466a90
baseline image: tools/m11/work/m11_boot.cjs sha256 e826e6c0a8e8ff85bff0afacfed7368b23b7da4740ace099a415c4b2fb71f1b2
EMSDK: 6.0.12 (/opt/emsdk) / llvm-nm: /usr/local/bin/llvm-nm -> /opt/emsdk/upstream/bin/llvm-nm
build: 5 variant とも [sxlink] OK (signature mismatch=1 undefined=0 duplicate=0)
pre  = a5adb2fc 版 survey_trace.mjs を同じ image に当てた結果
post = 0f5d70cc 版 survey_trace.mjs を同じ image に当てた結果
base = m11_boot.cjs に 0f5d70cc 版 survey_trace.mjs を当てた結果
plain_soft = m11_sx_plain_soft.cjs (sha256 546bbec7…・同一 rebuild 由来)。修正前 harness の range 783 は trace 無しの plain_soft でも出る (REPORT §3 の注記どおり)。
注: 「修正前 (pre)」は a5adb2fc の survey_trace.mjs を harness 側で再現したもの (tools/m11/shimx_link/survey_trace_pre.mjs を一時的に置いて実行し、直後に削除)。

## 素材 image との関係 (指摘 1 への対応)
- `oc_artifacts: work-m11` の素材に含まれる `m11_sx_trace_soft_fix.cjs` は sha256 `f100dd66…` で、本 evidence の image (`b674477d…`) とは別物。
- 素材 image は 2026-10-10 に build されたもの。その link log (`link_trace_soft_fix.log`) は空で、`signature mismatch` の検査結果も無い。
- 素材の `.cjs` には対応する `.cjs.wasm` が含まれず、単体では起動できない (ENOENT)。素材 image では survey を測れない。
- 本 evidence の image は 2026-10-13 に、素材の `boot_final3.ll` / `m11_image.bin` などの入力から `e2e.sh` で作り直したもの (`build_log.txt`)。`signature mismatch=1` (`midiOutShortMsg`) は現在の `tools/shimx/src/midi_conv.c` 由来の警告。
- 数値の正は本 evidence の image。素材版は再現不能のため参照しない。
546bbec7e5cd14784dbf700477637c5a3830b3f64b782e34e0d598ecae44972a  tools/m11/work/shimx_link/m11_sx_plain_soft.cjs

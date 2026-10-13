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
plain_soft = m11_sx_plain_soft.cjs (sha256 は m11_sx_plain_soft.cjs の build 時の値)。修正前 harness の range 783 は trace 無しの plain_soft でも出る (REPORT §3 の注記どおり)。
注: 「修正前 (pre)」は a5adb2fc の survey_trace.mjs を harness 側で再現したもの (tools/m11/shimx_link/survey_trace_pre.mjs を一時的に置いて実行し、直後に削除)。
546bbec7e5cd14784dbf700477637c5a3830b3f64b782e34e0d598ecae44972a  tools/m11/work/shimx_link/m11_sx_plain_soft.cjs

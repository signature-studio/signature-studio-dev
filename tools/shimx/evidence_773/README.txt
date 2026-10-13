# #773 裏付けログ (SHX-T9 survey)
HEAD(測定 commit): 本ファイルを含む commit (build.sh は 05b2c71b と同一・コード差分なし)
image (測定対象): tools/m11/work/shimx_link/m11_sx_trace_soft_fix.cjs sha256 b674477d77504ea4d8368a6b4e72f05989ddcadf1cb8a015de39025fb3466a90
baseline image: tools/m11/work/m11_boot.cjs sha256 e826e6c0a8e8ff85bff0afacfed7368b23b7da4740ace099a415c4b2fb71f1b2
EMSDK: 6.0.12 (/opt/emsdk, emsdk install 6.0.12 で導入) / llvm-nm: /opt/emsdk/upstream/bin/llvm-nm (build.sh が PATH に戻す)
build: 5 variant とも clean rebuild (obj / gen / tmp / *.cjs 削除後) で [sxlink] OK (signature mismatch=1 undefined=0 duplicate=0)。ログ: build_logs/
image sha256 一覧: image_sha256.txt

## 測定 (survey_full_*.txt が全出力、SXL_SURVEY 行を含む)
- survey_full_pre_a5adb2fc.txt: a5adb2fc 版 survey_trace.mjs を測定 image に当てた結果 (range 783)
- survey_full_post_0f5d70cc.txt: 修正後 survey_trace.mjs (本 PR) を測定 image に当てた結果
- survey_full_baseline_m11_boot.txt: m11_boot.cjs に修正後 survey_trace.mjs を当てた結果
- survey_full_material_work-m11_f100dd66.txt: 素材 work-m11 同梱の m11_sx_trace_soft_fix.cjs (sha256 f100dd66…, 2026-10-10 build) に修正後 survey_trace.mjs を当てた結果。
  素材の .cjs には対応する .cjs.wasm が同梱されており (2026-10-10 build、link log は空)、測定できる。ただし上の測定 image とは別物。

## 旧 sxl_survey_*.txt
- sxl_survey_*.txt は SXL_SURVEY 行の summary の転記 (survey_full_*.txt の対応行と同一)。
- sxl_survey_pre_plain_soft_a5adb2fc.txt は trace 無し (m11_sx_plain_soft, sha256 546bbec7…) の結果。range 783 が trace 機能と無関係であることの根拠。ただし本 commit の run では再測定していない (前 run の転記。image の sha256 は本 run の clean rebuild と一致)。

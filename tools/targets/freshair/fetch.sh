#!/usr/bin/env bash
# 素材展開: $FA_DL (既定 ~/ダウンロード) の Fresh Air.Win.zip / Fresh Air.pkg → work/win, work/mac/x (再実行可)
# CI: plugins-freshair の tarball を展開したディレクトリを FA_DL に指定する (docs/WORKFLOW.md §11)。
#   work-liftlib-targets が先に work/win/Fresh Air を作っていても、factory .epf 8 本は zip から補完する (#693)。
set -euo pipefail
FA="$(cd -- "$(dirname -- "$0")" && pwd)"; DL="${FA_DL:-$HOME/ダウンロード}"
FACTORY='Fresh Air/C__ProgramData_Slate Digital/Fresh Air/FACTORY Presets/Factory Bank'
mkdir -p "$FA/work/win" "$FA/work/mac/x"
if [ ! -d "$FA/work/win/Fresh Air" ]; then
  unzip -q -o "$DL/Fresh Air.Win.zip" -d "$FA/work/win" || true
elif [ "$(ls "$FA/work/win/$FACTORY"/*.epf 2>/dev/null | wc -l)" -ne 8 ]; then
  unzip -q -o "$DL/Fresh Air.Win.zip" "$FACTORY/*" -d "$FA/work/win" || true
fi
n_epf=$(ls "$FA/work/win/$FACTORY"/*.epf 2>/dev/null | wc -l || true)
[ "$n_epf" -eq 8 ] || { echo "[fetch] ERROR: factory .epf が 8 本ではない ($n_epf 本)" >&2; exit 1; }
if [ -f "$DL/Fresh Air.pkg" ] && command -v xar >/dev/null 2>&1; then
  cd "$FA/work/mac"
  [ -f Distribution ] || xar -xf "$DL/Fresh Air.pkg"
  for p in 1_-_AU 2_-_VST3 3_-_APP,_Uninstaller 4_-_Content; do
    if [ -z "$(ls -A "x/$p" 2>/dev/null)" ]; then mkdir -p "x/$p"; (cd "x/$p" && gzip -dc "../../$p.pkg/Payload" | cpio -idm --quiet); fi
  done
else
  echo "[fetch] WARN: mac 展開を skip (Fresh Air.pkg または xar が無い。lift2 は win のみ使う)" >&2
fi
echo "[fetch] win: $(find "$FA/work/win" -type f | wc -l) files, factory .epf: $n_epf, mac: $(find "$FA/work/mac/x" -type f | wc -l) files"

#!/usr/bin/env bash
# fw_pack_stage1.sh — framework stage-1 成果物を R2 素材 work-fw-stage1 (#610) として梱包・検証する。
#   bash fw_pack_stage1.sh pack   [SRC_DIR] [OUT.tar.zst]   # 既定 SRC=tools/plugins/work/fw / OUT=work/work-fw-stage1.tar.zst
#   bash fw_pack_stage1.sh verify [TARBALL]                 # 構成 (12 ファイル・パス・非空・JSON) を検査。不合格は exit 1
# tarball の最上位は tools/plugins/work/fw/ (agent-setup が $GITHUB_WORKSPACE へ展開する work-* 規約)。
# upload は依頼者: aws s3 cp OUT s3://signature-studio-artifacts/artifacts/work-fw-stage1.tar.zst --endpoint-url <R2>
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../../shared/env.sh"
PREFIX="tools/plugins/work/fw"
FILES="fw_icall.dll fw_map.json fw0.restored.ll fw1.restored.ll fw2.restored.ll fw3.restored.ll \
fw4.restored.ll fw5.restored.ll fw6.restored.ll fw7.restored.ll r2.restored.ll r3.restored.ll"
cmd="${1:-}"; shift || true

verify() {
  local tb="$1" list n=0 bad=0 f
  [ -f "$tb" ] || { echo "[pack] tarball 無し: $tb" >&2; return 1; }
  list="$(tar --zstd -tvf "$tb" | awk '{print $3, $6}')"
  for f in $FILES; do
    local sz
    sz="$(printf '%s\n' "$list" | awk -v p="$PREFIX/$f" '$2==p {print $1}')"
    if [ -z "$sz" ] || [ "$sz" -le 0 ]; then echo "[pack] 欠落/空: $PREFIX/$f" >&2; bad=1; else n=$((n+1)); fi
  done
  local extra
  extra="$(printf '%s\n' "$list" | awk '{print $2}' | grep -v '/$' | grep -vxF "$(for f in $FILES; do echo "$PREFIX/$f"; done)" || true)"
  [ -z "$extra" ] || { echo "[pack] 想定外のエントリ: $extra" >&2; bad=1; }
  tar --zstd -xOf "$tb" "$PREFIX/fw_map.json" | python3 -c 'import json,sys; m=json.load(sys.stdin); assert m' \
    || { echo "[pack] fw_map.json が不正 JSON/空" >&2; bad=1; }
  echo "[pack] verify: ${n}/12 ファイル OK, bad=$bad, size=$(stat -c %s "$tb") B"
  [ $bad = 0 ]
}

case "$cmd" in
  pack)
    SRC="${1:-$REPO_ROOT/$PREFIX}"; OUT="${2:-$HERE/work/work-fw-stage1.tar.zst}"
    mkdir -p "$(dirname "$OUT")"
    for f in $FILES; do [ -s "$SRC/$f" ] || { echo "[pack] SRC 欠落/空: $SRC/$f" >&2; exit 1; }; done
    tar --zstd -cf "$OUT" --transform "s,^,$PREFIX/," -C "$SRC" $FILES
    verify "$OUT" ;;
  verify) verify "${1:?tarball}" ;;
  *) echo "usage: $0 pack [SRC] [OUT] | verify TARBALL" >&2; exit 2 ;;
esac

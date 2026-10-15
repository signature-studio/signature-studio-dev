#!/usr/bin/env bash
# QuickEq (KH 0x18035fb10 / SC 0x180ac5550) の param 写像の根拠を逆アセンブルで再現する (#4976 / FA-60)。判定はしない。
#   usage: bash tools/targets/freshair/ks_fa60_quickeq_map.sh   (素材: work-liftlib-targets を展開済み)
# 出力: 両側で P の各 dword を読み、同じスタック slot (rsp+0x20/0x28/0x30) と xmm2/xmm3 に渡す命令の行。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
KH="$HERE/../kilohearts/work/winpkg/HeartCore.core_64"
SC="$HERE/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64"
[ -f "$KH" ] && [ -f "$SC" ] || { echo "missing core (work-liftlib-targets を展開する)" >&2; exit 2; }
kh=$(python3 "$HERE/disasm.py" "$KH" 0x18035fb10 1754)
sc=$(python3 "$HERE/disasm.py" "$SC" 0x180ac5550 2090)
need() { grep -qF "$2" <<<"$1" || { echo "MISSING [$3]: $2" >&2; exit 1; }; }
need "$kh" "mov      rax, qword ptr [rdx + 0x3188]" "KH P 取得"
need "$kh" "movss    xmm4, dword ptr [rax]" "KH P+0"
need "$kh" "movss    xmm5, dword ptr [rax + 4]" "KH P+4"
need "$kh" "movss    xmm2, dword ptr [rax + 0xc]" "KH P+0xc -> xmm2"
need "$kh" "movss    xmm3, dword ptr [rax + 0x10]" "KH P+0x10 -> xmm3"
need "$kh" "movd     dword ptr [rsp + 0x30], xmm1" "KH P+8 -> [rsp+0x30]"
need "$kh" "call     0x180362700" "KH design 呼出"
need "$sc" "mov      rax, qword ptr [rcx + 0x90]" "SC P 取得"
need "$sc" "movss    xmm0, dword ptr [rax + 0x9e0c]" "SC 0x9e0c"
need "$sc" "movss    xmm1, dword ptr [rax + 0x9dc4]" "SC 0x9dc4"
need "$sc" "movss    xmm2, dword ptr [rax + 0x9e9c]" "SC 0x9e9c -> xmm2"
need "$sc" "movss    xmm3, dword ptr [rax + 0x9ee4]" "SC 0x9ee4 -> xmm3"
need "$sc" "movss    dword ptr [rsp + 0x30], xmm1" "SC 0x9e54 -> [rsp+0x30]"
need "$sc" "call     0x180ad5ce0" "SC design 呼出"
echo "OK: QuickEq の P 写像の根拠行 (KH P+0/4/8/0xc/0x10 ⇄ SC 0x9dc4/0x9e0c/0x9e54/0x9e9c/0x9ee4) を確認"

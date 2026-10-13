#!/usr/bin/env bash
# GUI-6 のネガティブコントロール: 1 箇所を壊すと selftest / Chrome e2e が FAIL することを確認する (壊したコピーを build/negctl に作り、リポジトリのソースは変更しない)。
# 使い方: bash tools/gui/input/negctl.sh   — 全ケースで「検出 (FAIL した)」なら exit 0、1 件でも検出漏れなら exit 1
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; GUI="$(cd "$HERE/.." && pwd)"; ROOT="$(cd "$GUI/../.." && pwd)"
set +u; . "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1 || true; set -u
W="$GUI/build/negctl"; rm -rf "$W"; mkdir -p "$W"
miss=0
mutate() {  # name file sed-expr
  local name="$1" file="$2" expr="$3"; local d="$W/$name"; mkdir -p "$d"; cp -r "$GUI/src" "$GUI/include" "$GUI/test" "$d/"; mkdir -p "$d/build"
  cp "$GUI"/build/gui_api.h "$GUI"/build/gui_stubs.c "$GUI"/build/gui_reach_tab.c "$d/build/" 2>/dev/null
  cp "$GUI"/build/gui_rename.h "$GUI"/build/gui_wrap_i64.c "$d/build/" 2>/dev/null || true
  local before; before=$(md5sum "$d/$file" | cut -d' ' -f1); sed -i "$expr" "$d/$file"
  [ "$before" != "$(md5sum "$d/$file" | cut -d' ' -f1)" ] || { echo "NEGCTL $name: mutation did not change $file (broken control)"; miss=$((miss+1)); return; }
  echo "$d"
}
selftest_of() {  # dir -> exit code of selftest built from that dir
  local d="$1"
  gcc -O1 -g -w -fsanitize=address,undefined -fno-sanitize-recover=undefined -pthread -I "$d/include" -I "$d/src" -I "$d/build" \
    "$d"/src/gui_platform.c "$d"/src/gui_reach.c "$d"/build/gui_reach_tab.c "$d"/src/gui_core.c "$d"/src/gui_gdi.c "$d"/src/gui_headless.c "$d"/build/gui_stubs.c "$d/test/selftest.c" -o "$d/selftest" -lm 2>"$d/cc.log" || { echo "build-error"; return 3; }
  # 既知の flake (#489: gui_headless.c blit_surf の ASan UAF) で最終行が出ずに abort することがある → 「[selftest] N passed」行が出るまで最大 5 回再試行。出なければそのまま (= 未検出扱い)
  local out i; for i in 1 2 3 4 5; do out=$("$d/selftest" 2>&1); echo "$out" | grep -q "^\[selftest\] [0-9]* passed" && break; done
  echo "$out" | grep -E "^\[selftest\] [0-9]* passed" || echo "$out" | tail -1
}
check() { # name file expr
  local d; d=$(mutate "$1" "$2" "$3") || return; [ -d "$d" ] || return
  local out; out=$(selftest_of "$d"); local rc=$?
  if echo "$out" | grep -qE "[1-9][0-9]* failed"; then echo "NEGCTL $1: detected ($out)"; else echo "NEGCTL $1: NOT DETECTED ($out)"; miss=$((miss+1)); fi
}
check nc1-scancode-to-vk-disabled src/gui_core.c 's|{ uint32_t lvk = kbd_layout_vk((b >> 8) \& 0xFF, (b >> 1) \& 1); if (lvk) vk = lvk; }||'
check nc2-de-z-y-swapped src/gui_core_ext.inc "s|LL(0x15, 'Z', 'z')|LL(0x15, 'Y', 'y')|"
check nc3-altgr-ignored src/gui_core_ext.inc 's|if (ctrl \&\& alt) return e->g; |if (0) return e->g; |'
check nc4-ime-commit-lparam src/gui_core_ext.inc 's|send_message(w->h, WM_IME_COMPOSITION_, 0, GCS_RESULTSTR_);|send_message(w->h, WM_IME_COMPOSITION_, 0, GCS_COMPSTR_);|'
check nc5-zoom-end-count src/gui_core_ext.inc 's| - (phase >= 2 ? 1 : 0); uint32_t want| ; uint32_t want|'
check nc6-clipcursor-no-clamp src/gui_core.c 's|if (g_cclip_on) { if (cx < g_cclip.left)|if (0) { if (cx < g_cclip.left)|'
check nc7-mapvk-letter-lowercase src/gui_core_ext.inc "s|if (c >= 'A' && c <= 'Z' && ch >= 'a' && ch <= 'z') ch -= 32;||"
check nc8-pointerlock-push-dropped src/gui_core.c 's|out_cmd(GUI_CMD_POINTER_LOCK, 0, (uint32_t)want, 0, 0, 0, 0);|;|'
echo "[negctl] (shim 側 8 ケース) 検出漏れ: $miss"
# ---- host (gui.js) 側: build/js のコピーを壊して Chrome e2e が FAIL することを確認 ----
host_nc() {  # name sed-expr
  local name="$1" expr="$2" d="$W/host-$1"; mkdir -p "$d"; cp -r "$GUI/build/js" "$d/js"
  local before; before=$(md5sum "$d/js/gui.js" | cut -d' ' -f1); sed -i "$expr" "$d/js/gui.js"
  [ "$before" != "$(md5sum "$d/js/gui.js" | cut -d' ' -f1)" ] || { echo "NEGCTL host-$name: mutation did not change gui.js (broken control)"; miss=$((miss+1)); return; }
  local out; out=$(GUI_JS_DIR="$d/js" node "$HERE/e2e.mjs" 2>&1); local rc=$?
  if [ $rc -ne 0 ] && echo "$out" | grep -q "^FAIL"; then echo "NEGCTL host-$name: detected (exit $rc, $(echo "$out" | grep -c '^FAIL') FAIL)"; else echo "NEGCTL host-$name: NOT DETECTED (exit $rc)"; miss=$((miss+1)); fi
}
host_nc scancode-dropped 's|const flags = (e.repeat ? 1 : 0) \| (sc\[1\] ? 2 : 0) \| (sc\[0\] << 8)|const flags = (e.repeat ? 1 : 0)|'
host_nc ime-update-dropped 's|send(2, e.data, e.data.length);|void 0;|'
host_nc touch-as-mouse 's|if (e.pointerType === "touch") {|if (false) {|'
host_nc pointerlock-request-dropped 's|this.lockRequests++;|;|'
echo "[negctl] 合計 検出漏れ: $miss"
exit $((miss ? 1 : 0))

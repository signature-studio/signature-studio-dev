#!/usr/bin/env bash
# 1 コマンド E2E (LGL-3, #86): 単体テスト -> 整合検査 -> vite build で NOTICES を成果物へ -> 成果物走査 -> ネガティブコントロール -> deploy ゲート
#   usage: FL_WIN64_DIR=<FL 抽出物> bash tools/legal/notices/e2e.sh [--wasm <dir>]   (--wasm: 実ビルドした wasm を成果物に足して走査する。tools/shared/work/build/sidemod など)
set -uo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"
W="${TMPDIR:-/tmp}/notices-e2e.$$"; rm -rf "$W"; mkdir -p "$W"
trap 'rm -rf "$W"' EXIT
WASM=""; [ "${1:-}" = "--wasm" ] && WASM="$2"
: "${FL_WIN64_DIR:?FL_WIN64_DIR (FL 抽出物) が必要}"
fail=0
ok()   { echo "PASS  $*"; }
ng()   { echo "FAIL  $*"; fail=1; }
expect_fail() { # name expected_exit pattern cmd...
  local name="$1" code="$2" pat="$3"; shift 3
  local out; out="$("$@" 2>&1)"; local rc=$?
  if [ "$rc" = "$code" ] && grep -q -- "$pat" <<<"$out"; then ok "NEG $name (exit $rc)"; else ng "NEG $name: exit=$rc (期待 $code) pattern=[$pat]"; echo "$out" | head -5; fi
}
S=$(date +%s.%N)
echo "== 1. 単体テスト"; node --test tools/legal/notices/notices.test.mjs > "$W/unit.log" 2>&1 && ok "unit: $(grep -E '^# (pass|fail)' "$W/unit.log" | tr '\n' ' ')" || { ng "unit"; tail -30 "$W/unit.log"; }
echo "== 2. 整合検査 (素材不要)"; node tools/legal/notices/cli.mjs check && ok "check" || ng "check"
echo "== 3. vite build (NOTICES_STRICT=1)"
NOTICES_STRICT=1 node_modules/.bin/vite build --outDir "$W/dist" --emptyOutDir > "$W/vite.log" 2>&1 && ok "vite build" || { ng "vite build"; tail -5 "$W/vite.log"; }
for f in THIRD_PARTY_NOTICES.txt THIRD_PARTY_NOTICES.html; do [ -s "$W/dist/$f" ] && ok "dist/$f $(stat -c %s "$W/dist/$f") B" || ng "dist/$f が無い"; done
grep -q "The FreeType Project (www.freetype.org)" "$W/dist/THIRD_PARTY_NOTICES.txt" && ok "FreeType 謝辞" || ng "FreeType 謝辞が無い"
grep -q "^\[NOTICES-INCOMPLETE\]" "$W/dist/THIRD_PARTY_NOTICES.txt" && ng "INCOMPLETE" || ok "INCOMPLETE ではない"
echo "== 4. 成果物走査 (NOTICES + 任意の実 wasm)"
mkdir -p "$W/art"; cp "$W/dist/THIRD_PARTY_NOTICES."* "$W/art/"
[ -n "$WASM" ] && find "$WASM" -maxdepth 1 -name '*.wasm' -exec cp {} "$W/art/" \;
node tools/legal/notices/cli.mjs check --artifact "$W/art" --json "$W/art.json" && ok "artifact scan: $(node -e 'console.log(JSON.stringify(require("fs").existsSync(process.argv[1])?JSON.parse(require("fs").readFileSync(process.argv[1])).artifacts[0].detected:{}))' "$W/art.json")" || ng "artifact scan"
echo "== 5. ネガティブコントロール"
cp -r tools/legal/notices/records "$W/records"; cp tools/legal/notices/registry.json "$W/registry.json"
rm "$W/records/freetype-2.7.json"
NOTICES_RECORDS_DIR="$W/records" expect_fail "再ビルド記録の欠落 (freetype)" 1 "records/freetype-2.7.json が無い" node tools/legal/notices/cli.mjs check
cp tools/legal/notices/records/freetype-2.7.json "$W/records/"
python3 - "$W" <<'PY'
import json, sys
w = sys.argv[1]
r = json.load(open(f"{w}/registry.json"))
for c in r["components"]:
    if c["id"] == "ffmpeg": c["coveredBy"] = []
json.dump(r, open(f"{w}/registry-uncovered.json", "w"), ensure_ascii=False)
for c in r["components"]:
    if c["id"] == "ffmpeg": c["bundled"] = False; c["reason"] = "test"; c["coveredBy"] = ["tools/shared/oss/ffmpeg", "tools/shared/oss/sidemod"]
json.dump(r, open(f"{w}/registry-unbundled.json", "w"), ensure_ascii=False)
for c in r["components"]:
    if c["id"] == "open-sans": c["bundled"] = False; c["reason"] = "test"
json.dump(r, open(f"{w}/registry-fontunbundled.json", "w"), ensure_ascii=False)
rec = json.load(open(f"{w}/records/lame-3.99.5.json")); rec["build"]["args"][0]["args"] += " --enable-gpl"
json.dump(rec, open(f"{w}/records/lame-3.99.5.json", "w"), ensure_ascii=False)
PY
NOTICES_RECORDS_DIR="$W/records" expect_fail "記録に GPL フラグ" 1 "禁止フラグ --enable-gpl" node tools/legal/notices/cli.mjs check
NOTICES_REGISTRY="$W/registry-uncovered.json" expect_fail "build.sh が registry に無い (oss/ffmpeg)" 1 "oss/ffmpeg/build.sh: OSS 再ビルドスクリプトが registry の coveredBy に無い" node tools/legal/notices/cli.mjs check
python3 - "$W" <<'PY'
import json, os, sys
w = sys.argv[1]
rel = lambda p: os.path.relpath(p, ".")
rows = open("tools/gui/test/fonts.tsv", encoding="utf-8").read().splitlines()
def registry_with(name, comp, ledger_rows):
    p = f"{w}/{name}.tsv"; open(p, "w", encoding="utf-8").write("\n".join(ledger_rows) + "\n")
    r = json.load(open("tools/legal/notices/registry.json"))
    for c in r["components"]:
        if c["id"] == comp: c["coveredBy"] = ["tools/gui/test/fetch_fonts.sh", rel(p)]
    json.dump(r, open(f"{w}/registry-{name}.json", "w"), ensure_ascii=False)
registry_with("ledger-sha", "open-sans", [l.replace(l.split("\t")[2], "0" * 64) if l.startswith("OpenSans-Regular.ttf\t") else l for l in rows])
registry_with("ledger-row", "barlow", [l for l in rows if not l.startswith("Barlow-Regular.ttf\t")])
r = json.load(open("tools/legal/notices/registry.json"))
bs = next(c for c in r["components"] if c["id"] == "barlow")["fontAsset"]["files"][0]["sha256"]
for c in r["components"]:
    if c["id"] == "open-sans": c["fontAsset"]["files"][0]["sha256"] = bs
json.dump(r, open(f"{w}/registry-swap.json", "w"), ensure_ascii=False)
PY
NOTICES_REGISTRY="$W/registry-ledger-sha.json" expect_fail "台帳の sha256 を壊す (open-sans・fonts.tsv 側)" 1 "OpenSans-Regular.ttf: sha256 が取得スクリプトの検証値に無い" node tools/legal/notices/cli.mjs check
NOTICES_REGISTRY="$W/registry-ledger-row.json" expect_fail "台帳から行を消す (barlow・fonts.tsv 側)" 1 "Barlow-Regular.ttf: sha256 が取得スクリプトの検証値に無い" node tools/legal/notices/cli.mjs check
NOTICES_REGISTRY="$W/registry-swap.json" expect_fail "sha256 の取り違え (open-sans に barlow の sha256)" 1 "OpenSans-Regular.ttf: sha256 が取得スクリプトの検証値に無い" node tools/legal/notices/cli.mjs check
mkdir -p "$W/empty"; echo "<html>" > "$W/empty/index.html"
expect_fail "NOTICES の無い成果物" 1 "THIRD_PARTY_NOTICES.txt が成果物に無い" node tools/legal/notices/cli.mjs check --artifact "$W/empty"
if [ -n "$WASM" ]; then
  NOTICES_REGISTRY="$W/registry-unbundled.json" expect_fail "実 ffmpeg.wasm を同梱するが registry は bundled=false" 1 'ffmpeg の痕跡.*bundled=false' node tools/legal/notices/cli.mjs check --artifact "$W/art"
  mkdir -p "$W/gpl"; cp "$W/art/"* "$W/gpl/"; printf 'libavcodec license: GPL version 2 or later\0' >> "$W/gpl/ffmpeg.wasm"
  expect_fail "GPL ビルドの痕跡を ffmpeg.wasm に注入" 1 "同梱禁止の部品 ffmpeg-gpl-build" node tools/legal/notices/cli.mjs check --artifact "$W/gpl"
  mkdir -p "$W/br"; cp "$W/dist/THIRD_PARTY_NOTICES."* "$W/br/"
  node -e 'const z=require("zlib"),fs=require("fs");fs.writeFileSync(process.argv[2],z.brotliCompressSync(fs.readFileSync(process.argv[1])))' "$W/art/ffmpeg.wasm" "$W/br/ffmpeg.wasm.br"
  NOTICES_REGISTRY="$W/registry-unbundled.json" expect_fail "brotli 圧縮した ffmpeg.wasm も検出" 1 'ffmpeg の痕跡.*bundled=false' node tools/legal/notices/cli.mjs check --artifact "$W/br"
fi
mkdir -p "$W/stale"; cp "$W/dist/THIRD_PARTY_NOTICES."* "$W/stale/"; sed -i 's/^Registry digest: sha256:./Registry digest: sha256:0/' "$W/stale/THIRD_PARTY_NOTICES.txt"
expect_fail "古い NOTICES (registry digest 不一致)" 1 "一致しない" node tools/legal/notices/cli.mjs check --artifact "$W/stale"
echo "== 6. deploy ゲート (05-stage)"
expect_fail "05-stage: NOTICES の無い dist は exit 7" 7 "notices-gate\[05-stage\]: FAIL" node deploy/scripts/05-stage.mjs --src "$W/empty" --out "$W/site-ng" --skip-release-guard
if node deploy/scripts/05-stage.mjs --src "$W/dist" --out "$W/site-ok" --skip-release-guard > "$W/stage.json" 2> "$W/stage.err"; then grep -q "notices-gate\[05-stage\]: PASS" "$W/stage.err" && ok "05-stage: NOTICES 付き dist は gate PASS ($(grep -c . "$W/stage.json") 行の JSON)" || ng "gate PASS 行が無い"; else ng "05-stage (NOTICES 付き)"; cat "$W/stage.err" | head; fi
[ -s "$W/site-ok/THIRD_PARTY_NOTICES.txt" ] && ok "stage 済み site に NOTICES" || ng "stage 済み site に NOTICES が無い"
node deploy/scripts/05-stage.mjs --src "$W/empty" --out "$W/site-skip" --skip-release-guard --skip-notices-gate > /dev/null 2> "$W/skip.err" && grep -q "省略" "$W/skip.err" && ok "--skip-notices-gate は明示バイパス (警告つき)" || ng "--skip-notices-gate"
echo "== 7. 代替フォント (Open Sans / Barlow, #616) × release guard / NOTICES"
RG="node tools/legal/release-guard/cli.mjs"
if bash tools/gui/test/fetch_fonts.sh > "$W/fetch.log" 2>&1; then
  FD="tools/gui/work"
  mkdir -p "$W/fontart"; cp "$W/dist/THIRD_PARTY_NOTICES."* "$W/fontart/"; cp "$FD"/OpenSans-Regular.ttf "$FD"/Barlow-Regular.ttf "$W/fontart/"
  node tools/legal/notices/cli.mjs check --artifact "$W/fontart" --json "$W/fontart.json" && ok "代替フォント入り成果物: NOTICES 検査 PASS (検出 $(node -e 'console.log(Object.keys(JSON.parse(require("fs").readFileSync(process.argv[1])).artifacts[0].detected).join(","))' "$W/fontart.json"))" || ng "代替フォント入り成果物の NOTICES 検査"
  grep -q '"open-sans"' "$W/fontart.json" && grep -q '"barlow"' "$W/fontart.json" && ok "成果物走査が実フォント 2 本を sha256 で検出" || ng "成果物走査が代替フォントを検出していない"
  expect_fail "NOTICES 検査: 代替フォントを載せ registry が bundled=false" 1 'open-sans の痕跡.*bundled=false' env NOTICES_REGISTRY="$W/registry-fontunbundled.json" node tools/legal/notices/cli.mjs check --artifact "$W/fontart"
  mkdir -p "$W/fontnotices"; cp "$W/dist/THIRD_PARTY_NOTICES."* "$W/fontnotices/"
  expect_fail "NOTICES 検査: 代替フォント無し成果物でも NOTICES の component 欠落は検出 (open-sans 削除)" 1 'に同梱 component open-sans が無い' bash -c "sed -i '/\\[component:open-sans\\]/d' '$W/fontnotices/THIRD_PARTY_NOTICES.txt'; node tools/legal/notices/cli.mjs check --artifact '$W/fontnotices'"
  if $RG build --from "$FL_WIN64_DIR/extracted" --out "$W/denylist" > "$W/dl.json" 2> "$W/dl.err"; then
    ok "deny-list 生成 (FL 抽出物 $(node -e 'const j=JSON.parse(require("fs").readFileSync(process.argv[1]));console.log(j.files+" file sha / "+j.windows+" windows")' "$W/dl.json"))"
    $RG scan --src "$W/fontart" --denylist "$W/denylist" > "$W/rg.out" 2>&1 && grep -q "allow-list 許容 2 files" "$W/rg.out" && ok "release guard: 代替フォント入り成果物は PASS (allow-list 許容 2 files)" || { ng "release guard: 代替フォント入り成果物"; head -5 "$W/rg.out"; }
    expect_fail "release guard NEG: allow-list 無しだと代替フォントは window 一致で FAIL (allow-list が効いている証拠)" 6 "window" $RG scan --src "$W/fontart" --denylist "$W/denylist" --allowlist /nonexistent
    mkdir -p "$W/flfont"; cp "$FL_WIN64_DIR/extracted/block24367_DATA.bin" "$W/flfont/Barlow-Regular.ttf"
    expect_fail "release guard NEG: FL 同梱の Barlow-Regular.ttf (別バイト列) は allow-list があっても FAIL" 6 "file" $RG scan --src "$W/flfont" --denylist "$W/denylist"
    mkdir -p "$W/modfont"; cp "$FD/OpenSans-Regular.ttf" "$W/modfont/"; printf 'X' >> "$W/modfont/OpenSans-Regular.ttf"
    expect_fail "release guard NEG: 代替フォントを 1 B 改変すると allow-list から外れ FAIL" 6 "window" $RG scan --src "$W/modfont" --denylist "$W/denylist"
    mkdir -p "$W/flslice"; head -c 40000 "$FL_WIN64_DIR/extracted/block25164_PE.bin" > "$W/flslice/x.bin"
    expect_fail "release guard NEG: FL の PE 40000 B 切出しは allow-list 追加後も FAIL (検出力が落ちていない)" 6 "window" $RG scan --src "$W/flslice" --denylist "$W/denylist"
  else ng "deny-list 生成"; tail -5 "$W/dl.err"; fi
else ng "fetch_fonts.sh (ネットワーク / sha256 検証)"; tail -3 "$W/fetch.log"; fi
echo "total $(echo "$(date +%s.%N) - $S" | bc) s, loadavg $(cut -d' ' -f1-3 /proc/loadavg)"
[ "$fail" = 0 ] && echo "ALL PASS" || { echo "FAILED"; exit 1; }

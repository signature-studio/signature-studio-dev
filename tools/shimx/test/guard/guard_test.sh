#!/usr/bin/env bash
# SHX-T36 (#3069) 停止規則のガード: test.sh の規則を外すと落ちることを確かめる。
#   G1a: emcc が終了 0 で出力を作らない → test.sh は非 0 で終了し、出力が無いと明示する (偽の成功を出さない)
#   G1b: emcc が終了 0 で空ファイルを作る → 同上
#   G2 : M11 IR・M8 IR が無い → step 6 は SKIP し、生成物 4 件 (BACKLOG.md・data/coverage.json・data/inventory.csv・inventory.md) の sha256 が変わらない
# 子の test.sh は SHIMX_GUARD_CHILD=1 で 7b を省き、--quick で走らせる。
# 使い方: bash tools/shimx/test/guard/guard_test.sh   (test.sh の 7b からも呼ばれる)
set -euo pipefail

HERE="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
TEST_SH="$HERE/test.sh"
W="$HERE/work/guard"; rm -rf "$W"; mkdir -p "$W"
GEN=(BACKLOG.md data/coverage.json data/inventory.csv inventory.md)
ok() { echo "[guard] OK: $*"; }
ng() { echo "[guard] FAIL: $*" >&2; exit 1; }
sha_gen() { (cd "$HERE" && sha256sum "${GEN[@]}"); }
child() {  # $1=ログ名  $2...=VAR=値。子の test.sh (--quick) の終了コードを返す
    local log="$1"; shift
    local rc=0
    env SHIMX_GUARD_CHILD=1 "$@" bash "$TEST_SH" --quick > "$W/$log.out" 2>&1 || rc=$?
    echo "$rc"
}

cat > "$W/emcc_empty.sh" <<'EOF'
#!/usr/bin/env bash
# -o の次の引数に空ファイルを作って終了 0 (出力は作るが空)
while [ $# -gt 0 ]; do if [ "$1" = -o ]; then : > "$2"; exit 0; fi; shift; done
exit 0
EOF
chmod +x "$W/emcc_empty.sh"

rc=$(child g1a SHIMX_EMCC=/bin/true)
[ "$rc" -ne 0 ] || ng "G1a: emcc が出力を作らないのに test.sh が終了 0 (偽の成功)"
grep -q "出力が無い・空" "$W/g1a.out" || ng "G1a: 出力が無い旨の FAIL が出ていない (rc=$rc)"
ok "G1a: emcc 無出力 → test.sh rc=$rc・『出力が無い・空』の FAIL を表示"

rc=$(child g1b SHIMX_EMCC="$W/emcc_empty.sh")
[ "$rc" -ne 0 ] || ng "G1b: 空ファイルを出す emcc で test.sh が終了 0 (偽の成功)"
grep -q "出力が無い・空" "$W/g1b.out" || ng "G1b: 空出力の FAIL が出ていない (rc=$rc)"
ok "G1b: 空ファイルを出す emcc → test.sh rc=$rc・『出力が無い・空』の FAIL を表示"

rm -f "$HERE/work/ir_m11.json"   # 古い JSON で入力欠落が隠れないよう消す (gen_inventory は ir_m11.json を読む)
bak="$W/gen_bak"; mkdir -p "$bak"
for f in "${GEN[@]}"; do
    mkdir -p "$bak/$(dirname "$f")"; cp "$HERE/$f" "$bak/$f"
    printf '\n# guard sentinel (#3069)\n' >> "$HERE/$f"   # 直前の実行結果に依存しないよう、既知の印を付けてから子を走らせる
done
trap 'for f in "${GEN[@]}"; do cp "$bak/$f" "$HERE/$f"; done' EXIT
before="$(sha_gen)"
rc=$(child g2 SHIMX_M11_IR="$W/no_boot_final2.ll" SHIMX_M8_IR="$W/no_ott_m8.ll")
[ "$rc" -eq 0 ] || ng "G2: 入力欠落で test.sh が rc=$rc (期待 0)"
grep -q "SKIP: 入力" "$W/g2.out" || ng "G2: step 6 の SKIP 表示が無い"
after="$(sha_gen)"
[ "$before" = "$after" ] || ng "G2: 入力欠落で生成物 4 件が上書きされた (sentinel が消えた)"
ok "G2: 入力欠落 → test.sh rc=0・SKIP・生成物 4 件を上書きしない (sentinel 付きのまま sha256 不変)"

echo "[guard] 全 OK (G1a・G1b・G2)"

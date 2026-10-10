#!/usr/bin/env bash
# shimx オブジェクトをビルドして work/obj/*.o と work/nm.txt (定義済みシンボル) と src/proctable.c を更新する。
#   bash scripts/build_objs.sh [MT|ST]    (既定 MT=-pthread)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")/.." && pwd)"
MODE="${1:-MT}"
set +u; . /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; set -u
OBJ="$HERE/work/obj_$MODE"
mkdir -p "$OBJ"
rm -f "$OBJ"/*.o
FLAGS=(-O1 -w -Wno-error=int-conversion -Wno-implicit-function-declaration -fno-strict-aliasing)
[ "$MODE" = MT ] && FLAGS+=(-pthread)
for f in "$HERE"/src/*.c; do
    b="$(basename "$f" .c)"
    [ "$b" = proctable ] && continue
    emcc -c "${FLAGS[@]}" "$f" -o "$OBJ/$b.o"
done
llvm-nm --defined-only -g "$OBJ"/*.o > "$HERE/work/nm_$MODE.txt"
llvm-nm --defined-only -g -A "$OBJ"/*.o > "$HERE/work/nm_by_file_$MODE.txt"
python3 "$HERE/scripts/gen_proctable.py" --nm "$HERE/work/nm_$MODE.txt" --out "$HERE/src/proctable.c"
emcc -c "${FLAGS[@]}" "$HERE/src/proctable.c" -o "$OBJ/proctable.o"
echo "[build_objs] $MODE: $(ls "$OBJ"/*.o | wc -l) objects"

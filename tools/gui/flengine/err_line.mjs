// WIN-37 (#3696): 例外を先頭 1 行の文字列にする (cfi_probe.mjs の boot.err / call.err が使う)。
//   Error は message。message を持たない object (m11_throw_dllmain_done・shim の fail-fast が投げる object) は JSON にする。
//   stack は out.*.stack に別に残すので JSON からは外す。JSON にできない object (循環参照など) は key 名だけにする。
export function errLine(e) {
  if (e && typeof e.message === 'string' && e.message) return e.message.split('\n')[0];
  if (e !== null && typeof e === 'object' && !(e instanceof Error)) {
    let s;
    try { s = JSON.stringify(e, (k, v) => (k === 'stack' ? undefined : v)); } catch { s = undefined; }
    return (s === undefined ? '{' + Object.keys(e).join(',') + '}' : s).split('\n')[0];
  }
  return String(e).split('\n')[0];
}

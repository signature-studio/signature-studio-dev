// hb_lib.js — emscripten JS library: plugin→host upcall import (guest が呼ぶ audioMaster 経路)
mergeInto(LibraryManager.library, {
  hb_host_call__sig: 'iiiiiiif',
  hb_host_call: function (eff, op, idx, vlo, vhi, ptr, opt) {
    return Module.hbHostCall(eff, op, idx, vlo, vhi, ptr, opt);
  },
});

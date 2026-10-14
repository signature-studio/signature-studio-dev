// vst3host.cpp — CAB-68 [SR-1] Serum 2 最小 VST3 host (native / wine 駆動)
//
// 実 DLL (work/Serum2_win64.vst3 および authstub 適用版) を LoadLibrary し
// GetPluginFactory → IComponent (SerumDSP) / IEditController (SerumController) を
// instantiate → VST3 初期化シーケンス (initialize / setBusArrangements / setupProcessing /
// 32bit float 2in2out / 128 frames) → setState/getState 往復 → process 駆動まで行う。
//
// 目的:
//   1. factory 4 CID 列挙 (moduleinfo.json 突合)
//   2. vtable 実測ダンプ — CAB-71 §7 の med ABI slot を実測確定 (slotmap.json)
//   3. 0x800010 (kParamTitlesChanged|0x800000) 通知の観測 (IComponentHandler::restartComponent)
//   4. demo bit (obj+0x22792) の挙動: 合成 licensed state / demo マーカ state での差分観測
//   5. DSP sanity: process で非ゼロ音声出力 (認可 stub 依存なし)
//
// build: x86_64-w64-mingw32-g++ (build.sh) / run: wine64 (e2e.sh)
// VST3 SDK ヘッダ: work/vst3sdk (setup_sdk.sh で取得・gitignore)

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "pluginterfaces/base/funknown.h"
#include "pluginterfaces/base/ipluginbase.h"
#include "pluginterfaces/base/ibstream.h"
#include "pluginterfaces/vst/ivstcomponent.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "pluginterfaces/vst/ivsthostapplication.h"
#include "pluginterfaces/vst/ivstevents.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"
#include "pluginterfaces/vst/ivstprocesscontext.h"
#include "pluginterfaces/vst/ivstmessage.h"
#include "pluginterfaces/gui/iplugview.h"

using namespace Steinberg;
using namespace Steinberg::Vst;

// ---------------------------------------------------------------------------
// logging
// ---------------------------------------------------------------------------
static FILE* gLogFile = nullptr;   // <out>/log.txt
static FILE* gSum = nullptr;       // <out>/summary.json (手書き JSON, 1 key 1 行)

static void L(const char* fmt, ...) {
  char buf[2048];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  fputs(buf, stdout);
  fputc('\n', stdout);
  fflush(stdout);
  if (gLogFile) {
    fputs(buf, gLogFile);
    fputc('\n', gLogFile);
    fflush(gLogFile);
  }
}

// SR-1c #256: x86 デバッグレジスタ DR0 で 4 byte 書込 watch を張り、VEH で書込 RIP と値を記録する。
static volatile int* gWatchAddr = nullptr;
static int gWatchHits = 0;
static LONG CALLBACK watchVeh(PEXCEPTION_POINTERS ep) {
  if (ep->ExceptionRecord->ExceptionCode == EXCEPTION_SINGLE_STEP && gWatchAddr && (ep->ContextRecord->Dr6 & 0xF) &&
      gWatchHits < 64) {
    CONTEXT* c = ep->ContextRecord;
    c->Dr6 = 0;
    gWatchHits++;
    HMODULE m = nullptr;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS, (LPCSTR)(uintptr_t)c->Rip, &m);
    char mod[MAX_PATH] = "?";
    if (m) GetModuleFileNameA(m, mod, MAX_PATH);
    L("[watch] hit#%d RIP=%p (base=%p, %s) value=%d", gWatchHits, (void*)c->Rip, (void*)m,
      strrchr(mod, '\\') ? strrchr(mod, '\\') + 1 : mod, *gWatchAddr);
    // SR-27 #1836: frame pointer 省略のため RSP 走査ではなく .pdata の unwind 情報で呼出連鎖を辿る
    {
      CONTEXT u = *c;
      for (int depth = 0; depth < 32; depth++) {
        DWORD64 base = 0;
        PRUNTIME_FUNCTION rf = RtlLookupFunctionEntry(u.Rip, &base, nullptr);
        if (!rf) {
          L("[unwind] d=%d RIP=%p no-pdata", depth, (void*)u.Rip);
          break;
        }
        HMODULE um = nullptr;
        char umod[MAX_PATH] = "?";
        GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS, (LPCSTR)(uintptr_t)u.Rip, &um);
        if (um) GetModuleFileNameA(um, umod, MAX_PATH);
        L("[unwind] d=%d RIP=%p mod=%s fn=0x%lx (base=%p) rva=0x%llx", depth, (void*)u.Rip,
          strrchr(umod, '\\') ? strrchr(umod, '\\') + 1 : umod, (unsigned long)rf->BeginAddress, (void*)base,
          (unsigned long long)(u.Rip - base));
        PVOID hd = nullptr;
        ULONG64 est = 0;
        RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, u.Rip, rf, &u, &hd, &est, nullptr);
        if (!u.Rip) break;
      }
    }
    if (m) {  // QI の IID 候補 (lea rdx の解決先 RVA 0x11be750 / 0x11be8e8, 実行時に .data へ格納される)
      const DWORD rvas[2] = {0x11be750, 0x11be8e8};
      for (int i = 0; i < 2; i++) {
        const unsigned char* p = (const unsigned char*)m + rvas[i];
        L("[watch] iid@%lX = %02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X", (unsigned long)rvas[i],
          p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9], p[10], p[11], p[12], p[13], p[14], p[15]);
      }
    }
    return EXCEPTION_CONTINUE_EXECUTION;
  }
  return EXCEPTION_CONTINUE_SEARCH;
}
static void armWatch(volatile int* addr) {
  gWatchAddr = addr;
  AddVectoredExceptionHandler(1, watchVeh);
  // DR0 = addr, DR7: L0=1, RW0=01 (write), LEN0=11 (4 byte)
  CONTEXT c = {};
  c.ContextFlags = CONTEXT_DEBUG_REGISTERS;
  GetThreadContext(GetCurrentThread(), &c);
  c.Dr0 = (DWORD64)addr;
  c.Dr7 = (1ULL << 0) | (1ULL << 16) | (3ULL << 18);
  SetThreadContext(GetCurrentThread(), &c);
  L("[watch] armed DR0=%p (controller iface+0xdc)", (void*)addr);
}

static void S(const char* key, const char* value) {  // summary へ "key": value
  if (gSum) fprintf(gSum, "  \"%s\": %s,\n", key, value);
}
static void SI(const char* key, long long v) {
  char b[64];
  snprintf(b, sizeof(b), "%lld", v);
  S(key, b);
}
static void SF(const char* key, double v) {
  char b[64];
  snprintf(b, sizeof(b), "%.6g", v);
  S(key, b);
}

static const char* tresName(tresult r) {
  switch (r) {
    case kResultOk: return "kResultOk(kResultTrue)";
    case kResultFalse: return "kResultFalse";
    case kInvalidArgument: return "kInvalidArgument";
    case kNotImplemented: return "kNotImplemented";
    case kNoInterface: return "kNoInterface";
    case kOutOfMemory: return "kOutOfMemory";
    default: return "kOther";
  }
}

static std::string uidHex(const TUID uid) {
  static const char* hx = "0123456789ABCDEF";
  std::string s;
  for (int i = 0; i < 16; i++) {
    s += hx[(uid[i] >> 4) & 0xF];
    s += hx[uid[i] & 0xF];
  }
  return s;
}

// ---------------------------------------------------------------------------
// 既知関数テーブル (CAB-71 REPORT / authstub REPORT の実測 VA → RVA)
// ---------------------------------------------------------------------------
struct KnownFn { uint32_t rva; const char* name; };
static const KnownFn kKnownFns[] = {
    {0x4fad0, "SerumDSP::setState"},
    {0x4ffc0, "SerumDSP::setState EH funclet"},
    {0x56670, "SerumDSP::process"},
    {0x506b0, "DSP state reload (0x1800506b0)"},
    {0x501c0, "show_msg_helper (dialog)"},
    {0x4e3d0, "dialog queue push"},
    {0xc2b50, "SerumController::setState"},
    {0xc6090, "SerumController::getState"},
    {0xc3080, "controller state/demo loader"},
    {0x3dcf0, "SerumDSP ctor"},
    {0xa9f40, "SerumController ctor"},
    {0xac190, "SerumController dtor"},
    {0x89ea80, "Locate License dialog"},
};
static const char* knownFnName(uint32_t rva) {
  for (auto& k : kKnownFns)
    if (k.rva == rva) return k.name;
  return nullptr;
}
static const char* knownVtableName(uint32_t rva) {
  switch (rva) {
    case 0xa23f58: return "CAB-71: SerumDSP ctor vtable obj+0x00";
    case 0xa24048: return "CAB-71: SerumDSP ctor vtable obj+0x30 (IComponent)";
    case 0xa2bb98: return "CAB-71: SerumController 主 vtable (104 slots)";
    case 0xa2bf58: return "CAB-71: SerumController vtable slot6/7 (IEditController)";
    default: return nullptr;
  }
}

static uintptr_t gDllBase = 0;

// vtable を実読みして slot → RVA をダンプ (med ABI slot 確定の本体)
static void dumpVtable(const char* label, void* itf, int nSlots, bool json = true) {
  if (!itf) {
    L("[vtable] %s: interface NULL", label);
    return;
  }
  void** vptr = *(void***)itf;
  uintptr_t vRVA = (uintptr_t)vptr - gDllBase;
  const char* vtKnown = knownVtableName((uint32_t)vRVA);
  L("[vtable] %s: itf=%p vtable=%p (RVA 0x%llx)%s%s", label, itf, (void*)vptr,
    (unsigned long long)vRVA, vtKnown ? " <- " : "", vtKnown ? vtKnown : "");
  if (json && gSum) {
    fprintf(gSum, "  \"%s_vtable_rva\": \"0x%llx\",\n", label, (unsigned long long)vRVA);
    fprintf(gSum, "  \"%s_slots\": [", label);
    for (int i = 0; i < nSlots; i++) {
      void* fn = vptr[i];
      uint32_t rva = (uint32_t)((uintptr_t)fn - gDllBase);
      const char* kn = knownFnName(rva);
      fprintf(gSum, "%s{\"i\":%d,\"off\":\"0x%x\",\"rva\":\"0x%x\"%s%s%s}", i ? "," : "", i,
              i * 8, rva, kn ? ",\"known\":\"" : "", kn ? kn : "", kn ? "\"" : "");
    }
    fprintf(gSum, "],\n");
  }
  for (int i = 0; i < nSlots; i++) {
    void* fn = vptr[i];
    uint32_t rva = (uint32_t)((uintptr_t)fn - gDllBase);
    const char* kn = knownFnName(rva);
    if (kn) L("[vtable]   slot %2d (off 0x%02x) = RVA 0x%-7x %s", i, i * 8, rva, kn);
  }
}

// ---------------------------------------------------------------------------
// host 側オブジェクト
// ---------------------------------------------------------------------------

// --- MemoryStream (IBStream + ISizeableStream) ------------------------------
struct MemStream : public IBStream, public ISizeableStream {
  std::vector<char> data;
  int64_t pos = 0;
  uint32_t refc = 1;

  static MemStream* fromFile(const std::string& path) {
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return nullptr;
    MemStream* s = new MemStream();
    char buf[65536];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0) s->data.insert(s->data.end(), buf, buf + n);
    fclose(f);
    return s;
  }
  static MemStream* create() { return new MemStream(); }
  bool saveTo(const std::string& path) {
    FILE* f = fopen(path.c_str(), "wb");
    if (!f) return false;
    if (!data.empty()) fwrite(data.data(), 1, data.size(), f);
    fclose(f);
    return true;
  }

  tresult PLUGIN_API queryInterface(const TUID _iid, void** obj) override {
    if (memcmp(_iid, IBStream_iid, sizeof(TUID)) == 0 ||
        memcmp(_iid, FUnknown_iid, sizeof(TUID)) == 0) {
      *obj = (IBStream*)this;
      addRef();
      return kResultOk;
    }
    if (memcmp(_iid, ISizeableStream_iid, sizeof(TUID)) == 0) {
      *obj = (ISizeableStream*)this;
      addRef();
      return kResultOk;
    }
    L("[P->H] MemStream::queryInterface unknown iid=%s -> kNoInterface", uidHex(_iid).c_str());
    *obj = nullptr;
    return kNoInterface;
  }
  uint32_t PLUGIN_API addRef() override { return ++refc; }
  uint32_t PLUGIN_API release() override {
    uint32_t r = --refc;
    if (r == 0) delete this;
    return r;
  }
  tresult PLUGIN_API read(void* buffer, int32 numBytes, int32* numBytesRead) override {
    int64_t avail = (int64_t)data.size() - pos;
    int32_t n = (int32_t)((numBytes < avail) ? numBytes : (avail < 0 ? 0 : avail));
    if (n > 0 && !data.empty()) memcpy(buffer, data.data() + pos, n);
    pos += n;
    if (numBytesRead) *numBytesRead = n;
    return kResultTrue;
  }
  tresult PLUGIN_API write(void* buffer, int32 numBytes, int32* numBytesWritten) override {
    if ((int64_t)data.size() < pos + numBytes) data.resize((size_t)(pos + numBytes));
    if (numBytes > 0) memcpy(data.data() + pos, buffer, numBytes);
    pos += numBytes;
    if (numBytesWritten) *numBytesWritten = numBytes;
    return kResultTrue;
  }
  tresult PLUGIN_API seek(int64 p, int32 mode, int64* result) override {
    int64_t np = p;
    if (mode == kIBSeekSet) np = p;
    else if (mode == kIBSeekCur) np = pos + p;
    else if (mode == kIBSeekEnd) np = (int64_t)data.size() + p;
    pos = np;
    if (result) *result = pos;
    return kResultTrue;
  }
  tresult PLUGIN_API tell(int64* p) override {
    if (p) *p = pos;
    return kResultTrue;
  }
  tresult PLUGIN_API getStreamSize(int64& size) override {
    size = (int64_t)data.size();
    return kResultTrue;
  }
  tresult PLUGIN_API setStreamSize(int64 size) override {
    data.resize((size_t)size);
    return kResultTrue;
  }
};

// --- AttributeList / Message (IAttributeList / IMessage — connect 時に createInstance 要求) ---
struct AttrList : public IAttributeList {
  uint32_t refc = 1;
  std::vector<std::pair<AttrID, int64>> ints;
  std::vector<std::pair<AttrID, double>> floats;
  std::vector<std::pair<AttrID, std::string>> strs;
  std::vector<std::pair<AttrID, std::vector<char>>> bins;
  tresult PLUGIN_API queryInterface(const TUID _iid, void** obj) override {
    if (memcmp(_iid, IAttributeList_iid, sizeof(TUID)) == 0 ||
        memcmp(_iid, FUnknown_iid, sizeof(TUID)) == 0) {
      *obj = (IAttributeList*)this;
      addRef();
      return kResultOk;
    }
    *obj = nullptr;
    return kNoInterface;
  }
  uint32_t PLUGIN_API addRef() override { return ++refc; }
  uint32_t PLUGIN_API release() override {
    uint32_t r = --refc;
    if (r == 0) delete this;
    return r;
  }
  template <typename T>
  T* find(std::vector<std::pair<AttrID, T>>& v, AttrID id) {
    for (auto& p : v)
      if (strcmp(p.first, id) == 0) return &p.second;
    return nullptr;
  }
  tresult PLUGIN_API setInt(AttrID id, int64 value) override {
    auto* p = find(ints, id);
    if (p) *p = value;
    else ints.emplace_back(id, value);
    return kResultTrue;
  }
  tresult PLUGIN_API getInt(AttrID id, int64& value) override {
    auto* p = find(ints, id);
    if (!p) return kResultFalse;
    value = *p;
    L("[P->H] IAttributeList::getInt('%s') = %lld", id, (long long)value);
    return kResultTrue;
  }
  tresult PLUGIN_API setFloat(AttrID id, double value) override {
    auto* p = find(floats, id);
    if (p) *p = value;
    else floats.emplace_back(id, value);
    return kResultTrue;
  }
  tresult PLUGIN_API getFloat(AttrID id, double& value) override {
    auto* p = find(floats, id);
    if (!p) return kResultFalse;
    value = *p;
    return kResultTrue;
  }
  tresult PLUGIN_API setString(AttrID id, const char16* string) override {
    std::string s;
    for (int i = 0; string && string[i]; i++) s += (char)string[i];
    auto* p = find(strs, id);
    if (p) *p = s;
    else strs.emplace_back(id, s);
    return kResultTrue;
  }
  tresult PLUGIN_API getString(AttrID id, char16* string, uint32 size) override {
    auto* p = find(strs, id);
    if (!p) return kResultFalse;
    uint32 i = 0;
    for (; i + 1 < size && i < p->size(); i++) string[i] = (char16)(*p)[i];
    string[i] = 0;
    L("[P->H] IAttributeList::getString('%s') = '%s'", id, p->c_str());
    return kResultTrue;
  }
  tresult PLUGIN_API setBinary(AttrID id, const void* data, uint32 numBytes) override {
    std::vector<char> v((const char*)data, (const char*)data + numBytes);
    auto* p = find(bins, id);
    if (p) *p = v;
    else bins.emplace_back(id, v);
    return kResultTrue;
  }
  tresult PLUGIN_API getBinary(AttrID id, const void*& data, uint32& numBytes) override {
    auto* p = find(bins, id);
    if (!p) return kResultFalse;
    data = p->data();
    numBytes = (uint32)p->size();
    return kResultTrue;
  }
};

struct HostMsg : public IMessage {
  uint32_t refc = 1;
  std::string msgId;
  AttrList attrs;
  tresult PLUGIN_API queryInterface(const TUID _iid, void** obj) override {
    if (memcmp(_iid, IMessage_iid, sizeof(TUID)) == 0 ||
        memcmp(_iid, FUnknown_iid, sizeof(TUID)) == 0) {
      *obj = (IMessage*)this;
      addRef();
      return kResultOk;
    }
    *obj = nullptr;
    return kNoInterface;
  }
  uint32_t PLUGIN_API addRef() override { return ++refc; }
  uint32_t PLUGIN_API release() override {
    uint32_t r = --refc;
    if (r == 0) delete this;
    return r;
  }
  void PLUGIN_API setMessageID(FIDString messageID) override {
    msgId = messageID ? messageID : "";
    L("[P->H] IMessage::setMessageID('%s')", msgId.c_str());
  }
  FIDString PLUGIN_API getMessageID() override { return msgId.c_str(); }
  IAttributeList* PLUGIN_API getAttributes() override {
    attrs.addRef();
    return &attrs;
  }
};

// --- HostApplication (IHostApplication) -------------------------------------
struct HostApp : public IHostApplication {
  uint32_t refc = 1;
  tresult PLUGIN_API queryInterface(const TUID _iid, void** obj) override {
    if (memcmp(_iid, IHostApplication_iid, sizeof(TUID)) == 0 ||
        memcmp(_iid, FUnknown_iid, sizeof(TUID)) == 0) {
      *obj = (IHostApplication*)this;
      addRef();
      return kResultOk;
    }
    // #1360: 実験オプション。0x180037600 が context に対して IVst3ToAUWrapper / IVst3ToAAXWrapper を QI し、
    // 両方失敗で +0xdc を 2 にする (REPORT_SR1c §4-2)。S2HOST_WRAPPER_QI=1 のときだけ両 IID に kResultOk を返す。
    static const TUID kAUWrapperIid = {(char)0xC5,(char)0xC6,(char)0xB8,(char)0xA3,(char)0x95,(char)0xC0,(char)0x88,(char)0x46,(char)0xB0,(char)0x91,0x6F,0x0B,(char)0xB6,(char)0x97,(char)0xAA,0x44};
    static const TUID kAAXWrapperIid = {(char)0xC6,(char)0x9D,0x31,0x6D,(char)0xC5,0x60,0x42,0x62,(char)0xB3,0x2C,(char)0x95,0x1B,(char)0x93,(char)0xBE,(char)0xF4,(char)0xC6};
    if (getenv("S2HOST_WRAPPER_QI") && (memcmp(_iid, kAUWrapperIid, sizeof(TUID)) == 0 ||
                                       memcmp(_iid, kAAXWrapperIid, sizeof(TUID)) == 0)) {
      L("[P->H] HostApp::queryInterface wrapper iid=%s -> kResultOk (S2HOST_WRAPPER_QI)", uidHex(_iid).c_str());
      *obj = (FUnknown*)this;
      addRef();
      return kResultOk;
    }
    L("[P->H] HostApp::queryInterface unknown iid=%s -> kNoInterface", uidHex(_iid).c_str());
    *obj = nullptr;
    return kNoInterface;
  }
  uint32_t PLUGIN_API addRef() override { return ++refc; }
  uint32_t PLUGIN_API release() override {
    uint32_t r = --refc;
    if (r == 0) delete this;
    return r;
  }
  tresult PLUGIN_API getName(String128 name) override {
    const char16_t* n = u"WebStudioHost CAB-68";
    for (int i = 0; i < 128; i++) name[i] = (char16)n[i];
    L("[P->H] slot3 IHostApplication::getName -> WebStudioHost CAB-68");
    return kResultTrue;
  }
  tresult PLUGIN_API createInstance(TUID cid, TUID _iid, void** obj) override {
    L("[P->H] slot4 IHostApplication::createInstance cid=%s iid=%s", uidHex(cid).c_str(),
      uidHex(_iid).c_str());
    if (memcmp(_iid, IBStream_iid, sizeof(TUID)) == 0) {
      *obj = (IBStream*)MemStream::create();
      return kResultOk;
    }
    if (memcmp(_iid, IMessage_iid, sizeof(TUID)) == 0) {
      *obj = (IMessage*)new HostMsg();
      return kResultOk;
    }
    *obj = nullptr;
    return kNotImplemented;
  }
};

// --- ComponentHandler (IComponentHandler + IComponentHandler2) ---------------
struct Handler : public IComponentHandler, public IComponentHandler2 {
  uint32_t refc = 1;
  // 観測集計
  long long restartCalls = 0;
  std::vector<int32_t> restartFlags;
  long long beginEditCalls = 0, performEditCalls = 0, endEditCalls = 0, setDirtyCalls = 0,
            requestOpenEditorCalls = 0;

  tresult PLUGIN_API queryInterface(const TUID _iid, void** obj) override {
    if (memcmp(_iid, IComponentHandler_iid, sizeof(TUID)) == 0 ||
        memcmp(_iid, FUnknown_iid, sizeof(TUID)) == 0) {
      *obj = (IComponentHandler*)this;
      addRef();
      return kResultOk;
    }
    if (memcmp(_iid, IComponentHandler2_iid, sizeof(TUID)) == 0) {
      *obj = (IComponentHandler2*)this;
      addRef();
      return kResultOk;
    }
    L("[P->H] Handler::queryInterface unknown iid=%s -> kNoInterface", uidHex(_iid).c_str());
    *obj = nullptr;
    return kNoInterface;
  }
  uint32_t PLUGIN_API addRef() override { return ++refc; }
  uint32_t PLUGIN_API release() override {
    uint32_t r = --refc;
    if (r == 0) delete this;
    return r;
  }
  // IComponentHandler: slot3..6 (vtable offset 0x18..0x30)
  tresult PLUGIN_API beginEdit(ParamID id) override {
    beginEditCalls++;
    L("[P->H] slot3 IComponentHandler::beginEdit(paramId=%u)", id);
    return kResultTrue;
  }
  tresult PLUGIN_API performEdit(ParamID id, ParamValue value) override {
    performEditCalls++;
    L("[P->H] slot4 IComponentHandler::performEdit(paramId=%u value=%.6f)", id, value);
    return kResultTrue;
  }
  tresult PLUGIN_API endEdit(ParamID id) override {
    endEditCalls++;
    L("[P->H] slot5 IComponentHandler::endEdit(paramId=%u)", id);
    return kResultTrue;
  }
  tresult PLUGIN_API restartComponent(int32 flags) override {
    restartCalls++;
    restartFlags.push_back(flags);
    L("[P->H] slot6 IComponentHandler::restartComponent(flags=0x%x) *** 0x800010 観測点 ***",
      flags);
    return kResultTrue;
  }
  // IComponentHandler2: slot3..6
  tresult PLUGIN_API setDirty(TBool state) override {
    setDirtyCalls++;
    L("[P->H] slot3 IComponentHandler2::setDirty(%u)", state);
    return kResultTrue;
  }
  tresult PLUGIN_API requestOpenEditor(FIDString name) override {
    requestOpenEditorCalls++;
    L("[P->H] slot4 IComponentHandler2::requestOpenEditor(name=%s)", name ? name : "(null)");
    return kResultFalse;  // GUI 無し
  }
  tresult PLUGIN_API startGroupEdit() override { return kResultTrue; }
  tresult PLUGIN_API finishGroupEdit() override { return kResultTrue; }
};

// --- EventList (IEventList) --------------------------------------------------
struct EventList : public IEventList {
  uint32_t refc = 1;
  std::vector<Event> ev;
  long long pluginAdds = 0;
  tresult PLUGIN_API queryInterface(const TUID _iid, void** obj) override {
    if (memcmp(_iid, IEventList_iid, sizeof(TUID)) == 0 ||
        memcmp(_iid, FUnknown_iid, sizeof(TUID)) == 0) {
      *obj = (IEventList*)this;
      addRef();
      return kResultOk;
    }
    *obj = nullptr;
    return kNoInterface;
  }
  uint32_t PLUGIN_API addRef() override { return ++refc; }
  uint32_t PLUGIN_API release() override {
    uint32_t r = --refc;
    if (r == 0) delete this;
    return r;
  }
  int32 PLUGIN_API getEventCount() override { return (int32)ev.size(); }
  tresult PLUGIN_API getEvent(int32 index, Event& e) override {
    if (index < 0 || index >= (int32)ev.size()) return kInvalidArgument;
    e = ev[index];
    return kResultTrue;
  }
  tresult PLUGIN_API addEvent(Event& e) override {
    pluginAdds++;
    L("[P->H] IEventList::addEvent(type=%u offset=%d) [plugin→host 出力イベント]", e.type,
      e.sampleOffset);
    ev.push_back(e);
    return kResultTrue;
  }
};

// --- ParameterChanges (IParameterChanges / IParamValueQueue) -----------------
struct ParamQueue : public IParamValueQueue {
  uint32_t refc = 1;
  ParamID pid = 0;
  std::vector<std::pair<int32, ParamValue>> pts;
  tresult PLUGIN_API queryInterface(const TUID _iid, void** obj) override {
    if (memcmp(_iid, IParamValueQueue_iid, sizeof(TUID)) == 0 ||
        memcmp(_iid, FUnknown_iid, sizeof(TUID)) == 0) {
      *obj = (IParamValueQueue*)this;
      addRef();
      return kResultOk;
    }
    *obj = nullptr;
    return kNoInterface;
  }
  uint32_t PLUGIN_API addRef() override { return ++refc; }
  uint32_t PLUGIN_API release() override {
    uint32_t r = --refc;
    if (r == 0) delete this;
    return r;
  }
  ParamID PLUGIN_API getParameterId() override { return pid; }
  int32 PLUGIN_API getPointCount() override { return (int32)pts.size(); }
  tresult PLUGIN_API getPoint(int32 index, int32& sampleOffset, ParamValue& value) override {
    if (index < 0 || index >= (int32)pts.size()) return kInvalidArgument;
    sampleOffset = pts[index].first;
    value = pts[index].second;
    return kResultTrue;
  }
  tresult PLUGIN_API addPoint(int32 sampleOffset, ParamValue value, int32& index) override {
    pts.emplace_back(sampleOffset, value);
    index = (int32)pts.size() - 1;
    return kResultTrue;
  }
};
struct ParamChanges : public IParameterChanges {
  uint32_t refc = 1;
  std::vector<ParamQueue*> qs;
  tresult PLUGIN_API queryInterface(const TUID _iid, void** obj) override {
    if (memcmp(_iid, IParameterChanges_iid, sizeof(TUID)) == 0 ||
        memcmp(_iid, FUnknown_iid, sizeof(TUID)) == 0) {
      *obj = (IParameterChanges*)this;
      addRef();
      return kResultOk;
    }
    *obj = nullptr;
    return kNoInterface;
  }
  uint32_t PLUGIN_API addRef() override { return ++refc; }
  uint32_t PLUGIN_API release() override {
    uint32_t r = --refc;
    if (r == 0) delete this;
    return r;
  }
  int32 PLUGIN_API getParameterCount() override { return (int32)qs.size(); }
  IParamValueQueue* PLUGIN_API getParameterData(int32 index) override {
    if (index < 0 || index >= (int32)qs.size()) return nullptr;
    return qs[index];
  }
  IParamValueQueue* PLUGIN_API addParameterData(const ParamID& id, int32& index) override {
    ParamQueue* q = new ParamQueue();
    q->pid = id;
    qs.push_back(q);
    index = (int32)qs.size() - 1;
    L("[P->H] IParameterChanges::addParameterData(id=%u) [plugin→host 出力 param]", id);
    return q;
  }
};

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------
static bool readFile(const std::string& path, std::vector<char>& out) {
  FILE* f = fopen(path.c_str(), "rb");
  if (!f) return false;
  char buf[65536];
  size_t n;
  while ((n = fread(buf, 1, sizeof(buf), f)) > 0) out.insert(out.end(), buf, buf + n);
  fclose(f);
  return true;
}
static std::string jsonEscape(const std::string& s) {
  std::string r;
  for (char c : s) {
    if (c == '"' || c == '\\') {
      r += '\\';
      r += c;
    } else if ((unsigned char)c < 0x20) {
      char b[8];
      snprintf(b, sizeof(b), "\\u%04x", c);
      r += b;
    } else
      r += c;
  }
  return r;
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------
int main(int argc, char** argv) {
  // usage: vst3host.exe <dll> <statedir|-> <outdir> [blocks]
  if (argc < 4) {
    fprintf(stderr, "usage: %s <dll.vst3> <statedir|-> <outdir> [blocks]\n", argv[0]);
    return 2;
  }
  const char* dllPath = argv[1];
  std::string stateDir = argv[2];
  std::string outDir = argv[3];
  int nBlocks = (argc > 4) ? atoi(argv[4]) : 64;
  const char* contentDir = (argc > 5) ? argv[5] : nullptr;  // Tables/.. を含むルート (CWD)

  CreateDirectoryA(outDir.c_str(), nullptr);
  std::string logPath = outDir + "\\log.txt";
  std::string sumPath = outDir + "\\summary.json";
  gLogFile = fopen(logPath.c_str(), "w");
  gSum = fopen(sumPath.c_str(), "w");
  fprintf(gSum, "{\n");

  L("=== vst3host (CAB-68) start ===");
  L("dll=%s state=%s out=%s blocks=%d content=%s", dllPath, stateDir.c_str(), outDir.c_str(),
    nBlocks, contentDir ? contentDir : "(CWDのまま)");
  if (contentDir) {
    BOOL ok = SetCurrentDirectoryA(contentDir);
    L("SetCurrentDirectory(%s) = %d", contentDir, (int)ok);
    SI("set_content_cwd", ok ? 1 : 0);
  }

  // --- load DLL ---
  HMODULE hDll = LoadLibraryA(dllPath);
  if (!hDll) {
    L("!! LoadLibrary failed gle=%lu", (unsigned long)GetLastError());
    SI("load_ok", 0);
    fprintf(gSum, "  \"_end\": 1\n}\n");
    fclose(gSum);
    return 1;
  }
  gDllBase = (uintptr_t)hDll;
  L("LoadLibrary ok: base=%p (imagebase 0x180000000 と照合可)", hDll);
  SI("load_ok", 1);
  char baseBuf[64];
  snprintf(baseBuf, sizeof(baseBuf), "\"0x%llx\"", (unsigned long long)gDllBase);
  S("dll_base", baseBuf);

  typedef void (*VoidFn)();
  VoidFn initDll = (VoidFn)GetProcAddress(hDll, "InitDll");
  VoidFn exitDll = (VoidFn)GetProcAddress(hDll, "ExitDll");
  typedef void* (*GetPluginFactoryFn)();
  GetPluginFactoryFn getFactory = (GetPluginFactoryFn)GetProcAddress(hDll, "GetPluginFactory");
  L("exports: InitDll=%p ExitDll=%p GetPluginFactory=%p", initDll, exitDll, getFactory);
  SI("has_InitDll", initDll ? 1 : 0);
  SI("has_ExitDll", exitDll ? 1 : 0);
  SI("has_GetPluginFactory", getFactory ? 1 : 0);
  if (initDll) {
    L("InitDll() 呼出…");
    initDll();
    L("InitDll() 返回");
  }

  if (!getFactory) {
    L("!! GetPluginFactory 無し");
    return 1;
  }
  IPluginFactory* factory = (IPluginFactory*)getFactory();
  if (!factory) {
    L("!! GetPluginFactory が NULL");
    return 1;
  }
  L("IPluginFactory* = %p", factory);
  dumpVtable("IPluginFactory", factory, 8);

  // --- factory info ---
  PFactoryInfo fi;
  memset(&fi, 0, sizeof(fi));
  tresult r = factory->getFactoryInfo(&fi);  // slot 3
  L("getFactoryInfo(slot3) = %s vendor='%s' url='%s' flags=0x%x", tresName(r), fi.vendor,
    fi.url, fi.flags);
  S("factory_vendor", ("\"" + jsonEscape(fi.vendor) + "\"").c_str());
  SI("factory_class_count", factory->countClasses());  // slot 4

  // --- class 列挙 (getClassInfo2 via IPluginFactory2) ---
  int32_t nClasses = factory->countClasses();
  std::string cidList = "[";
  TUID cidComponent, cidController;
  memset(cidComponent, 0, 16);
  memset(cidController, 0, 16);
  bool gotCompCidF = false, gotCtrlCidF = false;
  for (int32_t i = 0; i < nClasses; i++) {
    PClassInfo2 ci;
    memset(&ci, 0, sizeof(ci));
    tresult r2 = ((IPluginFactory2*)factory)->getClassInfo2(i, &ci);  // slot 6
    if (r2 != kResultOk) {
      PClassInfo ci1;
      memset(&ci1, 0, sizeof(ci1));
      factory->getClassInfo(i, &ci1);  // slot 5
      L("class[%d] getClassInfo2 failed (%s) fallback name='%s' cat='%s'", i, tresName(r2),
        ci1.name, ci1.category);
      continue;
    }
    std::string cidHex = uidHex(ci.cid);
    L("class[%d] cid=%s name='%s' category='%s' sub='%s' version='%s'", i, cidHex.c_str(),
      ci.name, ci.category, ci.subCategories, ci.version);
    if (i) cidList += ",";
    cidList += "\"" + cidHex + "\"";
    // moduleinfo.json との対応: moduleinfo の CID hex は dword 単位で逆順
    // (例: "Serum 2" Audio Module: moduleinfo=56534558...6735073... / in-memory=58455356...73667350...)
    // → in-memory 値を createInstance に使う
    if (!gotCompCidF && strcmp(ci.category, "Audio Module Class") == 0 &&
        strcmp(ci.name, "Serum 2") == 0) {
      memcpy(cidComponent, ci.cid, 16);
      gotCompCidF = true;
    }
    if (!gotCtrlCidF && strcmp(ci.category, "Component Controller Class") == 0 &&
        strcmp(ci.name, "Serum 2") == 0) {
      memcpy(cidController, ci.cid, 16);
      gotCtrlCidF = true;
    }
  }
  S("factory_cids", (cidList + "]").c_str());
  SI("cid_component_found", gotCompCidF ? 1 : 0);
  SI("cid_controller_found", gotCtrlCidF ? 1 : 0);
  S("cid_component_inmemory", ("\"" + uidHex(cidComponent) + "\"").c_str());
  S("cid_controller_inmemory", ("\"" + uidHex(cidController) + "\"").c_str());
  // moduleinfo.json の CID (Serum2 本体 2 クラス) と dword 逆順一致するか
  {
    // moduleinfo.json の CID hex = FUID(l1,l2,l3,l4) の「引数順」16進4 dword。
    // in-memory bytes へは from4Int 変換 (= INLINE_UID と同一の配列) で比較する。
    const char* hexC = "56534558667350736572756D20320000";  // Audio Module "Serum 2"
    unsigned l[4];
    for (int i = 0; i < 4; i++) sscanf(hexC + i * 8, "%8x", &l[i]);
    TUID conv;
    for (int i = 0; i < 4; i++) conv[i] = (char)((l[0] >> (i * 8)) & 0xFF);          // l1 LE
    conv[4] = (char)((l[1] >> 16) & 0xFF); conv[5] = (char)((l[1] >> 24) & 0xFF);
    conv[6] = (char)(l[1] & 0xFF);         conv[7] = (char)((l[1] >> 8) & 0xFF);
    for (int i = 0; i < 4; i++) conv[8 + i] = (char)((l[2] >> (24 - i * 8)) & 0xFF);  // l3 BE
    for (int i = 0; i < 4; i++) conv[12 + i] = (char)((l[3] >> (24 - i * 8)) & 0xFF); // l4 BE
    SI("cid_moduleinfo_fuid_conv_match", memcmp(conv, cidComponent, 16) == 0 ? 1 : 0);
    S("cid_moduleinfo_fuid_conv", ("\""
      + uidHex(conv) + "\"").c_str());
  }

  HostApp* hostApp = new HostApp();
  Handler* handler = new Handler();

  // --- create component (SerumDSP) ---
  IComponent* comp = nullptr;
  L("[dbg] IComponent_iid(in-memory)=%s", uidHex(IComponent_iid).c_str());
  L("[dbg] IEditController_iid(in-memory)=%s", uidHex(IEditController_iid).c_str());
  r = factory->createInstance(cidComponent, IComponent_iid, (void**)&comp);  // slot 6
  L("createInstance(Serum2 component, IComponent) = %s comp=%p", tresName(r), comp);
  SI("create_component_ok", (r == kResultOk && comp) ? 1 : 0);
  if (!comp) return 1;
  dumpVtable("SerumDSP_IComponent", comp, 20);

  IAudioProcessor* proc = nullptr;
  r = comp->queryInterface(IAudioProcessor_iid, (void**)&proc);
  L("component->queryInterface(IAudioProcessor) = %s proc=%p", tresName(r), proc);
  SI("query_iaudioprocessor_ok", (r == kResultOk && proc) ? 1 : 0);
  if (proc) dumpVtable("SerumDSP_IAudioProcessor", proc, 14);

  // --- initialize (component) ---
  r = comp->initialize((FUnknown*)hostApp);  // IPluginBase slot3
  L("component->initialize(hostApp) = %s", tresName(r));
  SI("component_initialize", (long long)r);

  // --- controller class id ---
  TUID gotCtrlCid;
  memset(gotCtrlCid, 0, 16);
  r = comp->getControllerClassId(gotCtrlCid);  // IComponent slot5
  L("component->getControllerClassId(slot5) = %s cid=%s", tresName(r),
    uidHex(gotCtrlCid).c_str());
  S("component_getcontrollercid",
    ("\"" + uidHex(gotCtrlCid) + "\"").c_str());
  SI("controller_cid_matches_moduleinfo",
    memcmp(gotCtrlCid, cidController, 16) == 0 ? 1 : 0);

  // --- create controller (SerumController) ---
  IEditController* ctrl = nullptr;
  r = factory->createInstance(cidController, IEditController_iid, (void**)&ctrl);
  L("createInstance(Serum2 controller, IEditController) = %s ctrl=%p", tresName(r), ctrl);
  SI("create_controller_ok", (r == kResultOk && ctrl) ? 1 : 0);
  if (!ctrl) return 1;
  dumpVtable("SerumController_IEditController", ctrl, 20);
  // S2HOST_WATCH=1: ctrl iface+0xdc (= controller base+0x10c) への書込 PC を DR0 で捕まえる (SR-1c #256)
  if (getenv("S2HOST_WATCH")) armWatch((volatile int*)((unsigned char*)ctrl + 0xdc));

  r = ctrl->initialize((FUnknown*)hostApp);  // IPluginBase slot3
  L("controller->initialize(hostApp) = %s", tresName(r));
  SI("controller_initialize", (long long)r);
  {
    unsigned char* cb0 = (unsigned char*)ctrl;
    L("[probe] ctrl iface+0xdc=%d +0x22790=%u +0x22792=%u (initialize 後)", *(int*)(cb0 + 0xdc),
      cb0[0x22790], cb0[0x22792]);
  }
  r = ctrl->setComponentHandler((IComponentHandler*)handler);  // slot16
  L("controller->setComponentHandler(handler=%p) = %s", (IComponentHandler*)handler,
    tresName(r));
  SI("set_component_handler", (long long)r);

  // createView("editor") — GUI 無し運用だが controller 側の editor 状態フラグ (+0x10c) を
  //立てるためにフレーム取得のみ行う (open/setFrame はしない = ウィンドウは生成されない)
  {
    IPlugView* view = ctrl->createView(ViewType::kEditor);  // slot17
    L("controller->createView('editor') = view=%p (%s)", view, view ? "取得" : "NULL");
    SI("create_view", view ? 1 : 0);
    if (view) {
      unsigned char* cbv = (unsigned char*)ctrl;
      L("[probe] ctrl iface+0xdc after createView = %d", *(int*)(cbv + 0xdc));
      SI("gate_0xdc_after_createview", *(int*)(cbv + 0xdc));
      view->release();  // open/setFrame はしない (headless 維持)
    }
  }

  // --- connection points ---
  IConnectionPoint* cpComp = nullptr;
  IConnectionPoint* cpCtrl = nullptr;
  comp->queryInterface(IConnectionPoint_iid, (void**)&cpComp);
  ctrl->queryInterface(IConnectionPoint_iid, (void**)&cpCtrl);
  L("queryInterface(IConnectionPoint): comp=%p ctrl=%p", cpComp, cpCtrl);
  SI("comp_has_iconnectionpoint", cpComp ? 1 : 0);
  SI("ctrl_has_iconnectionpoint", cpCtrl ? 1 : 0);
  if (cpComp && cpCtrl) {
    r = cpComp->connect(cpCtrl);
    L("cpComp->connect(cpCtrl) = %s", tresName(r));
    r = cpCtrl->connect(cpComp);
    L("cpCtrl->connect(cpComp) = %s", tresName(r));
  }

  // --- bus 構成 ---
  int32_t nIn = comp->getBusCount(kAudio, kInput);    // slot7
  int32_t nOut = comp->getBusCount(kAudio, kOutput);  // slot7
  L("getBusCount: audio in=%d out=%d", nIn, nOut);
  SI("bus_audio_in", nIn);
  SI("bus_audio_out", nOut);
  int32_t nEvIn = comp->getBusCount(kEvent, kInput);
  L("getBusCount: event in=%d", nEvIn);
  SI("bus_event_in", nEvIn);
  for (int32_t d = 0; d < 2; d++) {
    BusDirection dir = d == 0 ? kInput : kOutput;
    int32_t cnt = d == 0 ? nIn : nOut;
    for (int32_t b = 0; b < cnt; b++) {
      BusInfo bi;
      memset(&bi, 0, sizeof(bi));
      r = comp->getBusInfo(kAudio, dir, b, bi);  // slot8
      char nameBuf[256];
      for (int c = 0; c < 128 && bi.name[c]; c++) nameBuf[c] = (char)bi.name[c], nameBuf[c + 1] = 0;
      L("getBusInfo(%s,%d) = %s name='%s' ch=%d busType=%d flags=0x%x",
        d == 0 ? "in" : "out", b, tresName(r), nameBuf, bi.channelCount, bi.busType, bi.flags);
      comp->activateBus(kAudio, dir, b, true);  // slot10
    }
  }
  for (int32_t b = 0; b < nEvIn; b++) {
    comp->activateBus(kEvent, kInput, b, true);
  }

  SpeakerArrangement inArr = 0x3 /*kStereo*/;
  SpeakerArrangement outArr = 0x3 /*kStereo*/;
  if (proc) {
    // 入力 bus が無い (Serum2 instrument は out のみ) 場合は outputs だけ申請
    r = (nIn > 0) ? proc->setBusArrangements(&inArr, 1, &outArr, 1)
                  : proc->setBusArrangements(nullptr, 0, &outArr, 1);  // slot3
    L("setBusArrangements(%s) = %s", nIn > 0 ? "in=kStereo,out=kStereo" : "0in,out=kStereo",
      tresName(r));
    SI("set_bus_arrangements", (long long)r);
    SpeakerArrangement outArrCur = 0;
    r = proc->getBusArrangement(kOutput, 0, outArrCur);  // slot4
    L("getBusArrangement(out,0) = %s arr=0x%llx", tresName(r),
      (unsigned long long)outArrCur);
  }

  // --- process setup (32bit float / 128 frames / realtime) ---
  ProcessSetup setup;
  setup.processMode = kRealtime;
  setup.symbolicSampleSize = kSample32;
  setup.maxSamplesPerBlock = 128;
  setup.sampleRate = 48000.0;
  if (proc) {
    r = proc->setupProcessing(setup);  // slot7
    L("setupProcessing(kRealtime,kSample32,128,48000) = %s", tresName(r));
    SI("setup_processing", (long long)r);
  }

  // --- controller +0x10c (demo bit gate) の遷移観測 + 1 を待つポーリング ---
  {
    unsigned char* cb0 = (unsigned char*)ctrl;
    int seen[4] = {0, 0, 0, 0};
    int lastVal = *(int*)(cb0 + 0xdc);
    seen[lastVal & 3]++;
    L("[gate] ctrl iface+0xdc 初期値=%d — 1 への遷移を最大 3 秒ポーリング", lastVal);
    for (int i = 0; i < 60 && lastVal != 1; i++) {
      Sleep(50);
      int v = *(int*)(cb0 + 0xdc);
      if (v != lastVal) {
        L("[gate] +0xdc: %d -> %d (%d ms 後)", lastVal, v, (i + 1) * 50);
        lastVal = v;
      }
      seen[lastVal & 3]++;
    }
    L("[gate] 最終 +0xdc=%d (観測ヒストグラム 0:%d 1:%d 2:%d 3:%d)", lastVal, seen[0], seen[1],
      seen[2], seen[3]);
    SI("gate_0xdc_final", lastVal);
  }

  // --- 状態フェーズ (statedir != "-") ---
  std::string savedProcPath = outDir + "\\saved_processor_state.bin";
  std::string savedCtrlPath = outDir + "\\saved_controller_state.bin";
  bool haveStatePhase = (stateDir != "-");
  {
    unsigned char* cb0 = (unsigned char*)ctrl;
    L("[probe] ctrl iface+0xdc=%d +0x22790=%u +0x22792=%u (connect/bus/setup 後)",
      *(int*)(cb0 + 0xdc), cb0[0x22790], cb0[0x22792]);
  }
  if (haveStatePhase) {
    // setState 前の ダイアログキュー/docCopy 状態
    {
      unsigned char* base = (unsigned char*)comp - 0x30;
      unsigned char* q = base + 0x139bc8;
      unsigned char* dc = base + 0x3f0;
      unsigned char sum = 0, sum2 = 0;
      for (int i = 0; i < 64; i++) sum ^= q[i];
      for (int i = 0; i < 32; i++) sum2 ^= dc[i];
      L("[dsp-probe] dialogQueue xor64=%02x docCopy xor32=%02x (setState 前)", sum, sum2);
      SI("dsp_dialog_queue_xor_before", (long long)sum);
      SI("dsp_doccopy_xor_before", (long long)sum2);
    }
    // demo bit ヒューリスティック probe (IEditController this + 0x22790/0x22792)
    unsigned char* cb = (unsigned char*)ctrl;
    L("[probe] demo bit heuristic: *(ctrl+0x22790)=%u *(ctrl+0x22792)=%u (restore 前)",
      cb[0x22790], cb[0x22792]);

    std::string pPath = stateDir + "\\processor_state.json";
    std::string cPath = stateDir + "\\controller_state.json";
    MemStream* sProc = MemStream::fromFile(pPath);
    MemStream* sCtrl = MemStream::fromFile(cPath);
    if (!sProc || !sCtrl) {
      L("!! state file 読出失敗: %s / %s", pPath.c_str(), cPath.c_str());
      return 1;
    }
    L("[restore] processor_state.json %lld bytes", (long long)sProc->data.size());
    L("[restore] controller_state.json %lld bytes", (long long)sCtrl->data.size());

    tresult r1 = comp->setState(sProc);  // IComponent slot12 → 0x4fad0
    L("[restore] component->setState(slot12) = %s", tresName(r1));
    SI("restore_comp_setstate", (long long)r1);
    {
      // SerumDSP base = IComponent this - 0x30 (ctor が obj+0x30 に IComponent vtable 0xa24048)
      unsigned char* base = (unsigned char*)comp - 0x30;
      // ダイアログキュー (FUN_18004e3d0 の push 先 obj+0x139bc8) と doc copy (obj+0x3f0) の変化観測
      unsigned char* q = base + 0x139bc8;
      unsigned char* dc = base + 0x3f0;
      unsigned char sum = 0;
      for (int i = 0; i < 64; i++) sum ^= q[i];
      unsigned char sum2 = 0;
      for (int i = 0; i < 32; i++) sum2 ^= dc[i];
      L("[dsp-probe] dialogQueue@+0x139bc8 xor64=%02x docCopy@+0x3f0 xor32=%02x (setState 後)", sum,
        sum2);
      SI("dsp_dialog_queue_xor", (long long)sum);
      static unsigned char qBefore[64];
      memcpy(qBefore, q, 64);
      (void)qBefore;
    }
    {
      unsigned char* cb1 = (unsigned char*)ctrl;
      L("[probe] ctrl iface+0xdc=%d +0x22792=%u (comp setState 後)", *(int*)(cb1 + 0xdc),
        cb1[0x22792]);
    }

    MemStream* sProc2 = MemStream::fromFile(pPath);
    tresult r2 = ctrl->setComponentState(sProc2);  // IEditController slot5
    L("[restore] controller->setComponentState(slot5) = %s", tresName(r2));
    SI("restore_ctrl_setcomponentstate", (long long)r2);
    sProc2->release();
    {
      unsigned char* cb1 = (unsigned char*)ctrl;
      L("[probe] ctrl iface+0xdc=%d +0x22792=%u (ctrl setComponentState 後)",
        *(int*)(cb1 + 0xdc), cb1[0x22792]);
    }

    // #341: 実験オプション。0x1800c2cd7 の `cmp [this+0xdc],1; jne` ゲート (headless では 2 のまま, REPORT §3-3) を
    // 環境変数 S2HOST_FORCE_GATE=<n> で強制し、ゲート内の productVersion 比較 (0x1800c2d39) に到達させる。
    {
      const char* fg = getenv("S2HOST_FORCE_GATE");
      int forced = fg ? atoi(fg) : -1;
      if (fg) *(int*)(cb + 0xdc) = forced;
      SI("force_gate_requested", forced);
      SI("gate_0xdc_before_ctrl_setstate", *(int*)(cb + 0xdc));
    }
    tresult r3 = ctrl->setState(sCtrl);  // IEditController slot6 → 0xc2b50
    L("[restore] controller->setState(slot6) = %s", tresName(r3));
    SI("restore_ctrl_setstate", (long long)r3);
    L("[probe] demo bit heuristic: *(ctrl+0x22790)=%u *(ctrl+0x22792)=%u (restore 後)",
      cb[0x22790], cb[0x22792]);
    SI("demo_bit_probe_22792_after_restore", (long long)cb[0x22792]);

    // save (getState)
    MemStream* oProc = MemStream::create();
    tresult r4 = comp->getState(oProc);  // IComponent slot13
    L("[save] component->getState(slot13) = %s (%lld bytes)", tresName(r4),
      (long long)oProc->data.size());
    SI("save_comp_getstate", (long long)r4);
    SI("save_comp_bytes", (long long)oProc->data.size());
    oProc->saveTo(savedProcPath);
    oProc->release();

    MemStream* oCtrl = MemStream::create();
    tresult r5 = ctrl->getState(oCtrl);  // IEditController slot7 → 0xc6090
    L("[save] controller->getState(slot7) = %s (%lld bytes)", tresName(r5),
      (long long)oCtrl->data.size());
    SI("save_ctrl_getstate", (long long)r5);
    SI("save_ctrl_bytes", (long long)oCtrl->data.size());
    oCtrl->saveTo(savedCtrlPath);

    // demo マーカの有無 (kAudioUnitParameterFlag_IsHighResolution)
    {
      const char* marker = "kAudioUnitParameterFlag_IsHighResolution";
      const std::string body(oCtrl->data.begin(), oCtrl->data.end());
      bool has = body.find(marker) != std::string::npos;
      L("[save] controller state 内 demo マーカ (%s): %s", marker, has ? "有り (demo bit==1 想定)"
                                                                        : "無し (licensed 想定)");
      SI("saved_controller_has_demo_marker", has ? 1 : 0);
      // demoVersion キー (processor 由来が混入するか)
      bool hasDv = body.find("demoVersion") != std::string::npos;
      SI("saved_controller_has_demoversion_key", hasDv ? 1 : 0);
      L("[save] controller state 先頭 512B: %s",
        jsonEscape(body.substr(0, body.size() < 512 ? body.size() : 512)).c_str());
    }
    oCtrl->release();
    sProc->release();
    sCtrl->release();

    // roundtrip 2: 保存した state をもう一度 restore (自己整合 = 復元保存されることの実証)
    MemStream* s2 = MemStream::fromFile(savedProcPath);
    MemStream* s3 = MemStream::fromFile(savedCtrlPath);
    if (s2 && s3) {
      tresult q1 = comp->setState(s2);
      tresult q2 = ctrl->setState(s3);
      L("[roundtrip2] restore(saved) comp->setState=%s ctrl->setState=%s", tresName(q1),
        tresName(q2));
      SI("roundtrip2_comp", (long long)q1);
      SI("roundtrip2_ctrl", (long long)q2);
      MemStream* o2 = MemStream::create();
      MemStream* o3 = MemStream::create();
      comp->getState(o2);
      ctrl->getState(o3);
      bool same = o2->data == s2->data && o3->data == s3->data;
      L("[roundtrip2] save→restore→save byte 一致: %s (proc %s, ctrl %s)", same ? "YES" : "NO",
        o2->data == s2->data ? "same" : "diff", o3->data == s3->data ? "same" : "diff");
      SI("roundtrip2_bytes_identical", same ? 1 : 0);
      o2->release();
      o3->release();
    }
    if (s2) s2->release();
    if (s3) s3->release();
  } else {
    // save-only (seed run): 初期化直後の既定 state を保存 (payload 抽出源)
    MemStream* oProc = MemStream::create();
    tresult r4 = comp->getState(oProc);  // IComponent slot13
    L("[seed] component->getState = %s (%lld bytes)", tresName(r4),
      (long long)oProc->data.size());
    oProc->saveTo(savedProcPath);
    oProc->release();
    MemStream* oCtrl = MemStream::create();
    tresult r5 = ctrl->getState(oCtrl);  // IEditController slot7
    L("[seed] controller->getState = %s (%lld bytes)", tresName(r5),
      (long long)oCtrl->data.size());
    oCtrl->saveTo(savedCtrlPath);
    oCtrl->release();
  }

  // --- controller param 情報 (生存確認) ---
  int32_t nParams = ctrl->getParameterCount();  // slot8
  L("controller->getParameterCount(slot8) = %d", nParams);
  SI("controller_param_count", nParams);

  // --- process フェーズ ---
  const int kFrames = 128;
  static float inCh[2][kFrames];
  static float outCh[2][kFrames];

  if (proc && nBlocks > 0) {
    ProcessContext ctx;
    memset(&ctx, 0, sizeof(ctx));
    ctx.state = ProcessContext::kPlaying | ProcessContext::kTempoValid |
                ProcessContext::kProjectTimeMusicValid;
    ctx.sampleRate = 48000.0;
    ctx.tempo = 120.0;
    ctx.timeSigNumerator = 4;
    ctx.timeSigDenominator = 4;

    EventList* inEvents = new EventList();
    EventList* outEvents = new EventList();
    ParamChanges* inParams = new ParamChanges();
    ParamChanges* outParams = new ParamChanges();

    // SR-5: 参照レンダの MIDI ノート (既定 60)。ネガコンは S2HOST_PITCH で別ノートにする
    const int notePitch = getenv("S2HOST_PITCH") ? atoi(getenv("S2HOST_PITCH")) : 60;
    Event noteOn;
    memset(&noteOn, 0, sizeof(noteOn));
    noteOn.busIndex = 0;
    noteOn.type = Event::kNoteOnEvent;
    noteOn.sampleOffset = 0;
    noteOn.noteOn.channel = 0;
    noteOn.noteOn.pitch = (int16)notePitch;
    noteOn.noteOn.tuning = 0.f;
    noteOn.noteOn.velocity = 1.0f;
    noteOn.noteOn.length = -1;
    noteOn.noteOn.noteId = 1;
    inEvents->addEvent(noteOn);

    AudioBusBuffers inBuses[1], outBuses[1];
    static float* inChanPtrs[2] = {inCh[0], inCh[1]};
    static float* outChanPtrs[2] = {outCh[0], outCh[1]};
    inBuses[0].numChannels = 2;
    inBuses[0].silenceFlags = 0;
    inBuses[0].channelBuffers32 = inChanPtrs;
    outBuses[0].numChannels = 2;
    outBuses[0].silenceFlags = 0;
    outBuses[0].channelBuffers32 = outChanPtrs;

    std::vector<float> allOut;  // interleaved L,R (全ブロック)
    allOut.reserve((size_t)nBlocks * kFrames * 2);

    long long nonzero = 0, totalCells = 0;
    float peak = 0.f;
    for (int b = 0; b < nBlocks; b++) {
      // 入力は無音 (instrument の主入力 bus)。出力は毎ブロック zero クリア
      for (int i = 0; i < kFrames; i++) {
        inCh[0][i] = 0.f;
        inCh[1][i] = 0.f;
        outCh[0][i] = 0.f;
        outCh[1][i] = 0.f;
      }
      if (b == 24) {  // note off
        Event off;
        memset(&off, 0, sizeof(off));
        off.busIndex = 0;
        off.type = Event::kNoteOffEvent;
        off.sampleOffset = 0;
        off.noteOff.channel = 0;
        off.noteOff.pitch = (int16)notePitch;
        off.noteOff.velocity = 0.f;
        off.noteOff.tuning = 0.f;
        off.noteOff.noteId = 1;
        inEvents->addEvent(off);
      }

      ProcessData data;
      memset(&data, 0, sizeof(data));
      data.processMode = kRealtime;
      data.symbolicSampleSize = kSample32;
      data.numSamples = kFrames;
      data.numInputs = (nIn > 0) ? 1 : 0;
      data.numOutputs = 1;
      data.inputs = (nIn > 0) ? inBuses : nullptr;
      data.outputs = outBuses;
      data.inputEvents = inEvents;
      data.outputEvents = outEvents;
      data.inputParameterChanges = inParams;
      data.outputParameterChanges = outParams;
      data.processContext = &ctx;

      ctx.projectTimeSamples += kFrames;
      ctx.projectTimeMusic += (double)kFrames / 48000.0 / 2.0;

      tresult rp = proc->process(data);  // IAudioProcessor slot9
      if (rp != kResultOk && rp != kResultTrue) {
        L("!! process block %d = %s", b, tresName(rp));
        SI("process_error_block", b);
        break;
      }
      for (int i = 0; i < kFrames; i++) {
        float l = outCh[0][i], rr = outCh[1][i];
        if (l != 0.f) nonzero++;
        if (rr != 0.f) nonzero++;
        float a = l < 0 ? -l : l;
        if (a > peak) peak = a;
        a = rr < 0 ? -rr : rr;
        if (a > peak) peak = a;
        allOut.push_back(l);
        allOut.push_back(rr);
      }
      totalCells += 2 * kFrames;
    }
    L("[audio] blocks=%d frames=%d nonzero_cells=%lld/%lld peak=%.6f", nBlocks,
      nBlocks * kFrames, nonzero, totalCells, peak);
    SI("audio_blocks", nBlocks);
    SI("audio_nonzero_cells", nonzero);
    SI("audio_total_cells", totalCells);
    SF("audio_peak", peak);
    // 出力 (f32 interleaved L,R) を保存 (検証用・小)
    {
      std::string ap = outDir + "\\audio_f32_interleaved.raw";
      FILE* f = fopen(ap.c_str(), "wb");
      if (f) {
        if (!allOut.empty()) fwrite(allOut.data(), sizeof(float), allOut.size(), f);
        fclose(f);
      }
    }
    // SR-5: 参照 WAV (32-bit float, 2ch, SR 48 kHz)。WAV 本体は work/ に置き commit しない
    {
      std::string wp = outDir + "\\render_f32.wav";
      FILE* f = fopen(wp.c_str(), "wb");
      if (f) {
        const uint32_t dataBytes = (uint32_t)(allOut.size() * sizeof(float));
        const uint32_t rate = 48000;
        const uint16_t ch = 2, bits = 32, fmtTag = 3;
        const uint16_t align = ch * bits / 8;
        const uint32_t byteRate = rate * align;
        const uint32_t fmtSize = 16, riffSize = 4 + (8 + fmtSize) + (8 + dataBytes);
        fwrite("RIFF", 1, 4, f); fwrite(&riffSize, 4, 1, f); fwrite("WAVE", 1, 4, f);
        fwrite("fmt ", 1, 4, f); fwrite(&fmtSize, 4, 1, f);
        fwrite(&fmtTag, 2, 1, f); fwrite(&ch, 2, 1, f); fwrite(&rate, 4, 1, f);
        fwrite(&byteRate, 4, 1, f); fwrite(&align, 2, 1, f); fwrite(&bits, 2, 1, f);
        fwrite("data", 1, 4, f); fwrite(&dataBytes, 4, 1, f);
        if (!allOut.empty()) fwrite(allOut.data(), sizeof(float), allOut.size(), f);
        fclose(f);
      }
      L("[render] render_f32.wav (32-bit float, 2ch, 48000 Hz, %u frames)", (unsigned)(allOut.size() / 2));
    }
    L("[audio] outputEvents(plugin→host)=%lld inEvents(host→plugin)=%lld",
      outEvents->pluginAdds, inEvents->ev.size());
    SI("output_events_count", outEvents->pluginAdds);
    outEvents->release();
    inEvents->release();
    outParams->release();
    inParams->release();
  }

  // --- 後片付け ---
  L("[exit] restartComponent 呼出数=%lld flags 履歴:", handler->restartCalls);
  for (size_t i = 0; i < handler->restartFlags.size(); i++)
    L("[exit]   [%lld] flags=0x%x", (long long)i, handler->restartFlags[i]);
  SI("restart_component_calls", handler->restartCalls);
  {
    std::string fl = "[";
    for (size_t i = 0; i < handler->restartFlags.size(); i++) {
      char b[32];
      snprintf(b, sizeof(b), "%s\"0x%x\"", i ? "," : "", handler->restartFlags[i]);
      fl += b;
    }
    S("restart_flags", (fl + "]").c_str());
  }
  SI("beginEdit_calls", handler->beginEditCalls);
  SI("performEdit_calls", handler->performEditCalls);
  SI("endEdit_calls", handler->endEditCalls);
  SI("setDirty_calls", handler->setDirtyCalls);
  SI("requestOpenEditor_calls", handler->requestOpenEditorCalls);

  if (proc) {
    proc->setProcessing(false);
    proc->release();
  }
  r = comp->setActive(false);
  L("component->setActive(false) = %s", tresName(r));
  r = comp->terminate();
  L("component->terminate() = %s", tresName(r));
  r = ctrl->terminate();
  L("controller->terminate() = %s", tresName(r));
  comp->release();
  ctrl->release();
  if (cpComp) cpComp->release();
  if (cpCtrl) cpCtrl->release();
  hostApp->release();
  handler->release();
  if (exitDll) {
    L("ExitDll() 呼出…");
    exitDll();
  }
  FreeLibrary(hDll);
  L("=== vst3host end ===");
  fprintf(gSum, "  \"_end\": 1\n}\n");
  fclose(gSum);
  if (gLogFile) fclose(gLogFile);
  return 0;
}

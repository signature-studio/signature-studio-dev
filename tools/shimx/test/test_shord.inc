/* SHX-T8 (#175) のテスト: 序数 import 3 API / CP932 / Crypt ハッシュ。test_ole_shell.c から include する。 */
#include "cp932_vec.inc"

/* ---------------- shell32 #74 SHCreateStdEnumFmtEtc / shlwapi #12 SHCreateMemStream / #219 QISearch ---------------- */
typedef struct { uint64_t vtbl; LONG refs; } TObj;
static uint64_t g_tobj_vt[3];
static HRESULT t_qi(void* s, const GUID* i, void** o) { (void)i; *o = s; ((TObj*)s)->refs++; return S_OK; }
static ULONG t_addref(void* s) { return (ULONG)++((TObj*)s)->refs; }
static ULONG t_release(void* s) { return (ULONG)--((TObj*)s)->refs; }

static void test_shord(void) {
    static const GUID iidEnum = { 0x00000103, 0, 0, { 0xC0, 0, 0, 0, 0, 0, 0, 0x46 } };
    static const GUID iidUnk  = { 0x00000000, 0, 0, { 0xC0, 0, 0, 0, 0, 0, 0, 0x46 } };
    static const GUID iidOther = { 0x12345678, 0x1111, 0x2222, { 1, 2, 3, 4, 5, 6, 7, 8 } };

    /* --- #74: 3 件の FORMATETC (うち 1 件は ptd 付き) を列挙 --- */
    uint8_t fe[3][32]; memset(fe, 0, sizeof fe);
    *(uint16_t*)fe[0] = 0x0F; *(uint32_t*)(fe[0] + 16) = 1; *(int32_t*)(fe[0] + 20) = -1; *(uint32_t*)(fe[0] + 24) = 1;
    *(uint16_t*)fe[1] = 0x01; *(uint32_t*)(fe[1] + 16) = 1; *(int32_t*)(fe[1] + 20) = -1; *(uint32_t*)(fe[1] + 24) = 1;
    uint8_t* ptd = (uint8_t*)CoTaskMemAlloc(16); memset(ptd, 0xAB, 16); *(uint32_t*)ptd = 16;
    *(uint16_t*)fe[2] = 0x02; *(uint64_t*)(fe[2] + 8) = (uint64_t)(uintptr_t)ptd; *(uint32_t*)(fe[2] + 16) = 1; *(int32_t*)(fe[2] + 20) = -1; *(uint32_t*)(fe[2] + 24) = 5;
    LPVOID en = NULL;
    CHECK(SHCreateStdEnumFmtEtc(3, fe, &en) == S_OK && en);
    memset(ptd, 0, 16); CoTaskMemFree(ptd);                                    /* 入力 ptd は列挙側が深いコピーを持つ */
    uint64_t* vt = (uint64_t*)(uintptr_t)*(uint64_t*)en;
    HRESULT (*Next)(void*, ULONG, void*, ULONG*) = (HRESULT (*)(void*, ULONG, void*, ULONG*))(uintptr_t)vt[3];
    HRESULT (*Skip)(void*, ULONG) = (HRESULT (*)(void*, ULONG))(uintptr_t)vt[4];
    HRESULT (*Reset)(void*) = (HRESULT (*)(void*))(uintptr_t)vt[5];
    HRESULT (*Clone)(void*, void**) = (HRESULT (*)(void*, void**))(uintptr_t)vt[6];
    ULONG (*Rel)(void*) = (ULONG (*)(void*))(uintptr_t)vt[2];
    ULONG got = 99; uint8_t o[2][32];
    CHECK(Next(en, 2, o, &got) == S_OK && got == 2 && *(uint16_t*)o[0] == 0x0F && *(uint16_t*)o[1] == 0x01);
    void* cl = NULL; CHECK(Clone(en, &cl) == S_OK && cl && cl != en);        /* 位置 2 を引き継ぐ */
    CHECK(Next(cl, 2, o, &got) == S_FALSE && got == 1 && *(uint16_t*)o[0] == 0x02 && *(uint32_t*)(o[0] + 24) == 5);
    uint8_t* gp = (uint8_t*)(uintptr_t)*(uint64_t*)(o[0] + 8);
    CHECK(gp && *(uint32_t*)gp == 16 && gp[15] == 0xAB);                      /* ptd 内容が保たれる (深いコピー) */
    CoTaskMemFree(gp);
    CHECK(Next(cl, 1, o, &got) == S_FALSE && got == 0);                      /* 末尾 */
    CHECK(Reset(en) == S_OK && Skip(en, 1) == S_OK && Next(en, 1, o, &got) == S_OK && *(uint16_t*)o[0] == 0x01);
    CHECK(Skip(en, 5) == S_FALSE);
    void* q = NULL;
    CHECK(((HRESULT (*)(void*, const GUID*, void**))(uintptr_t)vt[0])(en, &iidEnum, &q) == S_OK && q == en);
    CHECK(((HRESULT (*)(void*, const GUID*, void**))(uintptr_t)vt[0])(en, &iidOther, &q) == E_NOINTERFACE && q == NULL);
    CHECK(Rel(en) == 1 && Rel(en) == 0 && Rel(cl) == 0);
    CHECK(SHCreateStdEnumFmtEtc(0, NULL, &en) == S_OK && en);                  /* 0 件列挙 */
    vt = (uint64_t*)(uintptr_t)*(uint64_t*)en;
    CHECK(((HRESULT (*)(void*, ULONG, void*, ULONG*))(uintptr_t)vt[3])(en, 1, o, &got) == S_FALSE && got == 0);
    ((ULONG (*)(void*))(uintptr_t)vt[2])(en);
    CHECK(SHCreateStdEnumFmtEtc(1, NULL, &en) == E_INVALIDARG && SHCreateStdEnumFmtEtc(1, fe, NULL) == E_POINTER);

    /* --- #12: SHCreateMemStream はデータのコピーを持つ IStream --- */
    char src[6] = "hello";
    LPVOID ms = SHCreateMemStream((const BYTE*)src, 5);
    CHECK(ms);
    memset(src, 'X', 5);                                                       /* コピー済み: 元を壊しても影響なし */
    vt = (uint64_t*)(uintptr_t)*(uint64_t*)ms;
    char buf[16]; ULONG n = 0;
    CHECK(((HRESULT (*)(void*, void*, ULONG, ULONG*))(uintptr_t)vt[3])(ms, buf, 16, &n) == S_FALSE && n == 5 && !memcmp(buf, "hello", 5));
    uint64_t np = 0;
    CHECK(((HRESULT (*)(void*, int64_t, DWORD, uint64_t*))(uintptr_t)vt[5])(ms, 0, 2, &np) == S_OK && np == 5);      /* サイズ = 5 */
    CHECK(((ULONG (*)(void*))(uintptr_t)vt[2])(ms) == 0);
    LPVOID e0 = SHCreateMemStream(NULL, 0);
    CHECK(e0);
    vt = (uint64_t*)(uintptr_t)*(uint64_t*)e0;
    CHECK(((HRESULT (*)(void*, int64_t, DWORD, uint64_t*))(uintptr_t)vt[5])(e0, 0, 2, &np) == S_OK && np == 0);
    ((ULONG (*)(void*))(uintptr_t)vt[2])(e0);

    /* --- #219: QISearch (QITAB = { const IID* @0; DWORD offset @8 } × n + {NULL}) --- */
    typedef struct { TObj a; TObj b; } Two;
    g_tobj_vt[0] = (uint64_t)(uintptr_t)t_qi; g_tobj_vt[1] = (uint64_t)(uintptr_t)t_addref; g_tobj_vt[2] = (uint64_t)(uintptr_t)t_release;
    Two two = { { (uint64_t)(uintptr_t)g_tobj_vt, 1 }, { (uint64_t)(uintptr_t)g_tobj_vt, 1 } };
    struct { uint64_t piid; uint32_t off; uint32_t pad; } tab[3] = {
        { (uint64_t)(uintptr_t)&iidEnum, (uint32_t)offsetof(Two, b), 0 },
        { 0, 0, 0 }, { 0, 0, 0 } };
    void* out = (void*)1;
    CHECK(QISearch(&two, tab, &iidEnum, &out) == S_OK && out == &two.b && two.b.refs == 2 && two.a.refs == 1);   /* AddRef は一致オブジェクトに 1 回 */
    out = (void*)1;
    CHECK(QISearch(&two, tab, &iidOther, &out) == E_NOINTERFACE && out == NULL && two.b.refs == 2);
    CHECK(QISearch(&two, tab, &iidUnk, &out) == S_OK && out == &two.b && two.b.refs == 3);                  /* IID_IUnknown は先頭エントリで応答 */
    CHECK(QISearch(&two, tab, &iidEnum, NULL) == E_POINTER);
}

/* ---------------- CP932 ---------------- */
static void test_cp932(void) {
    /* (1) DBCS 有効セル全件 (Python codec cp932 が出力した 9604 件) を MB→WC と WC→MB で双方向検査 */
    unsigned bad_mb2wc = 0, bad_wc2mb = 0;
    for (unsigned i = 0; i < k_cp932_cells_n; i++) {
        unsigned code = k_cp932_cells[i] >> 16; WCHAR uni = (WCHAR)(k_cp932_cells[i] & 0xFFFF);
        char mb[3] = { (char)(code >> 8), (char)(code & 0xFF), 0 };
        WCHAR w[4] = { 0 };
        int n = MultiByteToWideChar(932, 0, mb, 2, w, 4);
        if (n != 1 || w[0] != uni) bad_mb2wc++;
        /* 逆方向: Unicode → CP932 は多対一 (NEC/IBM 拡張の重複) があり得るので「往復で同一 Unicode に戻る」ことを検査 */
        char back[4] = { 0 }; BOOL used = TRUE;
        int m = WideCharToMultiByte(932, 0, &uni, 1, back, 4, NULL, &used);
        WCHAR w2[4] = { 0 };
        if (m < 1 || used || MultiByteToWideChar(932, 0, back, m, w2, 4) != 1 || w2[0] != uni) bad_wc2mb++;
    }
    fprintf(stderr, "[shimx-test] cp932: DBCS cells=%u mb2wc_bad=%u wc2mb_roundtrip_bad=%u\n", k_cp932_cells_n, bad_mb2wc, bad_wc2mb);
    CHECK(k_cp932_cells_n == 9604 && bad_mb2wc == 0 && bad_wc2mb == 0);

    /* (2) 単一バイト: 0x00-0x7F, 0xA1-0xDF (半角カナ U+FF61..FF9F) */
    for (unsigned b = 0; b < 0x80; b++) { char c = (char)b; WCHAR w; CHECK(MultiByteToWideChar(932, 0, &c, 1, &w, 1) == 1 && w == b); }
    for (unsigned b = 0xA1; b <= 0xDF; b++) { char c = (char)b; WCHAR w; CHECK(MultiByteToWideChar(932, 0, &c, 1, &w, 1) == 1 && w == 0xFF61 + (b - 0xA1)); }

    /* (3) 文字列: 「日本語ABCｱ」= 93FA 967B 8CEA 41 42 43 B1 */
    const char sj[] = "\x93\xFA\x96\x7B\x8C\xEA" "ABC\xB1";
    WCHAR w[32]; int n = MultiByteToWideChar(932, 0, sj, -1, w, 32);
    CHECK(n == 8 && w[0] == 0x65E5 && w[1] == 0x672C && w[2] == 0x8A9E && w[3] == 'A' && w[6] == 0xFF71 && w[7] == 0);
    CHECK(MultiByteToWideChar(932, 0, sj, -1, NULL, 0) == 8);                  /* サイズ問合せ (終端込み) */
    CHECK(MultiByteToWideChar(932, 0, sj, -1, w, 7) == 0 && GetLastError() == ERROR_INSUFFICIENT_BUFFER);
    char mb[32];
    CHECK(WideCharToMultiByte(932, 0, w, -1, mb, 32, NULL, NULL) == 11 && !memcmp(mb, sj, 11));   /* 往復: 6+3+1+NUL = 11 B */
    CHECK(WideCharToMultiByte(932, 0, w, -1, NULL, 0, NULL, NULL) == 11);
    CHECK(WideCharToMultiByte(932, 0, w, -1, mb, 10, NULL, NULL) == 0 && GetLastError() == ERROR_INSUFFICIENT_BUFFER);

    /* (4) 無効列: リード単独 / 無効トレイル / 未割当 */
    BOOL used = FALSE;
    CHECK(MultiByteToWideChar(932, 0, "\x81", 1, w, 4) == 1 && w[0] == 0x30FB);                 /* 末尾の孤立リード → 既定文字 U+30FB */
    CHECK(MultiByteToWideChar(932, 0, "\x81\x20", 2, w, 4) == 2 && w[0] == 0x30FB && w[1] == 0x20);   /* 無効トレイルは 1 バイト再解釈 */
    CHECK(MultiByteToWideChar(932, MB_ERR_INVALID_CHARS, "\x81\x20", 2, w, 4) == 0 && GetLastError() == ERROR_NO_UNICODE_TRANSLATION);
    CHECK(MultiByteToWideChar(932, MB_ERR_INVALID_CHARS, "\x81", 1, w, 4) == 0 && GetLastError() == ERROR_NO_UNICODE_TRANSLATION);
    CHECK(MultiByteToWideChar(932, 0, "\xFD", 1, w, 4) == 1 && w[0] == 0xF8F1);                 /* EUDC への best-fit (bestfit932 の MBTABLE) */

    /* (5) WC→MB: 変換不能は既定文字 '?' + used。Unicode の「あ」(U+3042) は 82A0 */
    WCHAR u[3] = { 0x3042, 0x2764, 0 };                                                        /* U+2764 は CP932 に無い */
    int m = WideCharToMultiByte(932, 0, u, 2, mb, 32, NULL, &used);
    CHECK(m == 3 && (unsigned char)mb[0] == 0x82 && (unsigned char)mb[1] == 0xA0 && mb[2] == '?' && used);
    used = FALSE; m = WideCharToMultiByte(932, 0, u + 1, 1, mb, 32, "#", &used);
    CHECK(m == 1 && mb[0] == '#' && used);
    /* WC_NO_BEST_FIT_CHARS: 厳密往復できない best-fit (例: U+00E0 'à' → 'a' に best-fit) は不変換 */
    WCHAR bf = 0x00E0; used = FALSE;
    CHECK(WideCharToMultiByte(932, 0, &bf, 1, mb, 8, NULL, &used) == 1 && mb[0] == 'a' && !used);               /* 既定は best-fit */
    CHECK(WideCharToMultiByte(932, WC_NO_BEST_FIT_CHARS, &bf, 1, mb, 8, NULL, &used) == 1 && mb[0] == '?' && used);
    /* サロゲートペア (U+1F3B5) は 932 に無い → 2 文字ぶん '?' 2 つ */
    WCHAR sp[2] = { 0xD83C, 0xDFB5 };
    CHECK(WideCharToMultiByte(932, 0, sp, 2, mb, 8, NULL, &used) == 2 && mb[0] == '?' && mb[1] == '?');

    /* (6) CP_ACP を 932 に切替: GetACP / GetCPInfo / CharNextExA / ACP 依存 API */
    shimx_set_acp(932);
    CHECK(GetACP() == 932 && IsValidCodePage(932));
    CHECK(MultiByteToWideChar(CP_ACP, 0, "\x82\xA0", 2, w, 4) == 1 && w[0] == 0x3042);
    CHECK(WideCharToMultiByte(CP_ACP, 0, u, 1, mb, 8, NULL, NULL) == 2 && (unsigned char)mb[0] == 0x82 && (unsigned char)mb[1] == 0xA0);
    CPINFO ci; CHECK(GetCPInfo(CP_ACP, &ci) && ci.MaxCharSize == 2 && ci.LeadByte[0] == 0x81 && ci.LeadByte[1] == 0x9F &&
                     ci.LeadByte[2] == 0xE0 && ci.LeadByte[3] == 0xFC && ci.LeadByte[4] == 0);
    CPINFOEXW cx; CHECK(GetCPInfoExW(932, 0, &cx) && cx.CodePage == 932 && cx.UnicodeDefaultChar == 0x30FB && cx.MaxCharSize == 2);
    const char* p = "\x82\xA0" "a";
    CHECK(CharNextExA(932, p, 0) == p + 2 && CharNextExA(932, p + 2, 0) == p + 3 && CharNextExA(932, p + 3, 0) == p + 3);
    CHECK(CharNextExA(1252, p, 0) == p + 1);
    shimx_set_acp(1252);
    CHECK(GetACP() == 1252 && IsDBCSLeadByteEx(CP_ACP, 0x81) == FALSE);
}

/* ---------------- advapi32 Crypt ハッシュ ---------------- */
static void hex_of(const BYTE* b, DWORD n, char* o) { static const char* H = "0123456789abcdef"; for (DWORD i = 0; i < n; i++) { o[i*2] = H[b[i] >> 4]; o[i*2+1] = H[b[i] & 15]; } o[n*2] = 0; }
static int hash_hex(HANDLE prov, DWORD alg, const void* data, DWORD len, int chunk, char* out) {
    HANDLE h = 0;
    if (!CryptCreateHash(prov, alg, 0, 0, &h) || !h) return 0;
    for (DWORD off = 0; off < len; ) { DWORD c = len - off < (DWORD)chunk ? len - off : (DWORD)chunk; if (!CryptHashData(h, (const BYTE*)data + off, c, 0)) return 0; off += c; }
    DWORD sz = 0, nn = 4;
    if (!CryptGetHashParam(h, 4 /*HP_HASHSIZE*/, (BYTE*)&sz, &nn, 0) || nn != 4) return 0;
    BYTE v[32]; DWORD vn = sizeof v;
    if (!CryptGetHashParam(h, 2 /*HP_HASHVAL*/, v, &vn, 0) || vn != sz) return 0;
    hex_of(v, vn, out);
    return CryptDestroyHash(h) ? 1 : 0;
}
static void test_crypt(void) {
    HANDLE prov = 0;
    CHECK(CryptAcquireContextA(&prov, NULL, NULL, 24 /*PROV_RSA_AES*/, 0xF0000000u /*VERIFYCONTEXT*/) && prov);
    HANDLE bad = 0x77; CHECK(!CryptAcquireContextA(&bad, NULL, NULL, 999, 0) && GetLastError() == 0x80090014u && bad == 0);   /* 失敗時は *phProv = 0 */
    HANDLE prov2 = 0; CHECK(CryptAcquireContextA(&prov2, NULL, NULL, 24, 0xF0000000u) && prov2);
    char hx[80];
    static const struct { DWORD alg; const char* in; const char* hex; } kv[] = {
        /* 公開テストベクトル (RFC 1321 / FIPS 180-4) */
        { 0x8003, "",    "d41d8cd98f00b204e9800998ecf8427e" },
        { 0x8003, "abc", "900150983cd24fb0d6963f7d28e17f72" },
        { 0x8003, "message digest", "f96b697d7cb7938d525a2f31aaf161d0" },
        { 0x8004, "",    "da39a3ee5e6b4b0d3255bfef95601890afd80709" },
        { 0x8004, "abc", "a9993e364706816aba3e25717850c26c9cd0d89d" },
        { 0x800C, "",    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" },
        { 0x800C, "abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" },
    };
    for (unsigned i = 0; i < sizeof kv / sizeof kv[0]; i++) {
        CHECK(hash_hex(prov, kv[i].alg, kv[i].in, (DWORD)strlen(kv[i].in), 1000, hx));
        CHECK(!strcmp(hx, kv[i].hex));
        CHECK(hash_hex(prov, kv[i].alg, kv[i].in, (DWORD)strlen(kv[i].in), 1, hx) && !strcmp(hx, kv[i].hex));     /* 1 バイトずつ流しても同一 */
    }
    /* 64B ブロック境界 (55/56/63/64/65 B) と百万 'a' (FIPS 180-4 の長入力ベクトル) */
    static const struct { DWORD alg; const char* hex; } mil[] = {
        { 0x8003, "7707d6ae4e027c70eea2a935c2296f21" }, { 0x8004, "34aa973cd4c4daa4f61eeb2bdbad27316534016f" },
        { 0x800C, "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0" } };
    char* big = (char*)malloc(1000000); memset(big, 'a', 1000000);
    for (int i = 0; i < 3; i++) { CHECK(hash_hex(prov, mil[i].alg, big, 1000000, 977, hx) && !strcmp(hx, mil[i].hex)); }
    free(big);
    /* 境界長: 既知値 (Python hashlib で生成した 'a'×N の digest 先頭 8 hex) */
    static const struct { int n; const char *md5, *sha1, *sha256; } bd[] = {
        { 55, "ef1772b6dff9a122358552954ad0df65", "c1c8bbdc22796e28c0e15163d20899b65621d65a", "9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318" },
        { 56, "3b0c8ac703f828b04c6c197006d17218", "c2db330f6083854c99d4b5bfb6e8f29f201be699", "b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a" },
        { 63, "b06521f39153d618550606be297466d5", "03f09f5b158a7a8cdad920bddc29b81c18a551f5", "7d3e74a05d7db15bce4ad9ec0658ea98e3f06eeecf16b4c6fff2da457ddc2f34" },
        { 64, "014842d480b571495a4a0363793f7367", "0098ba824b5c16427bd7a1122a5a442a25ec644d", "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb" },
        { 65, "c743a45e0d2e6a95cb859adae0248435", "11655326c708d70319be2610e8a57d9a5b959d3b", "635361c48bb9eab14198e76ea8ab7f1a41685d6ad62aa9146d301d4f17eb0ae0" },
    };
    char* a = (char*)malloc(80); memset(a, 'a', 80);
    for (unsigned i = 0; i < sizeof bd / sizeof bd[0]; i++) {
        CHECK(hash_hex(prov, 0x8003, a, bd[i].n, 7, hx) && !strcmp(hx, bd[i].md5));
        CHECK(hash_hex(prov, 0x8004, a, bd[i].n, 7, hx) && !strcmp(hx, bd[i].sha1));
        CHECK(hash_hex(prov, 0x800C, a, bd[i].n, 7, hx) && !strcmp(hx, bd[i].sha256));
    }
    free(a);

    /* API 契約 */
    HANDLE h = 0;
    CHECK(!CryptCreateHash(prov, 0x8001 /*CALG_MD2*/, 0, 0, &h) && h == 0 && GetLastError() == 0x80090008u);   /* 未対応 ALG_ID */
    CHECK(!CryptCreateHash(prov, 0x8003, 0, 0, NULL));
    CHECK(!CryptCreateHash(prov, 0x8003, 1, 0, &h) && GetLastError() == 0x80090003u);                          /* 鍵付きは非対応 */
    CHECK(!CryptCreateHash(0x1234, 0x8003, 0, 0, &h) && GetLastError() == 0x80090001u);                        /* 不正 prov */
    CHECK(CryptCreateHash(prov, 0x8003, 0, 0, &h) && h);
    CHECK(CryptHashData(h, (const BYTE*)"abc", 3, 0));
    BYTE v[32]; DWORD vn = 0;
    CHECK(CryptGetHashParam(h, 2, NULL, &vn, 0) && vn == 16);                                                   /* サイズ問合せは確定しない */
    CHECK(CryptHashData(h, (const BYTE*)"d", 1, 0));                                                            /* まだ追記できる */
    vn = 8; CHECK(!CryptGetHashParam(h, 2, v, &vn, 0) && GetLastError() == ERROR_MORE_DATA && vn == 16);       /* 小さい → MORE_DATA */
    vn = 16; CHECK(CryptGetHashParam(h, 2, v, &vn, 0) && vn == 16);
    hex_of(v, 16, hx); CHECK(!strcmp(hx, "e2fc714c4727ee9395f324cd2e7f331f"));                                  /* md5("abcd") */
    CHECK(!CryptHashData(h, (const BYTE*)"e", 1, 0) && GetLastError() == 0x8009000Cu);                         /* 確定後の追記は BAD_HASH_STATE */
    vn = 16; BYTE v2[16]; CHECK(CryptGetHashParam(h, 2, v2, &vn, 0) && !memcmp(v, v2, 16));                    /* 再取得は同値 */
    DWORD alg = 0, an = 4; CHECK(CryptGetHashParam(h, 1 /*HP_ALGID*/, (BYTE*)&alg, &an, 0) && alg == 0x8003);
    CHECK(CryptDestroyHash(h) && !CryptDestroyHash(h) && GetLastError() == 0x80090002u);                        /* 二重 Destroy */
    CHECK(!CryptHashData(h, (const BYTE*)"x", 1, 0) && GetLastError() == 0x80090002u);                         /* 解放済みハンドル (世代検出) */
    HANDLE h2 = 0; CHECK(CryptCreateHash(prov, 0x8003, 0, 0, &h2) && h2 != h);                                  /* スロット再利用でも別ハンドル値 */
    CryptDestroyHash(h2);
    CHECK(CryptReleaseContext(prov, 0) && !CryptReleaseContext(prov, 0));
    CHECK(!CryptCreateHash(prov, 0x8003, 0, 0, &h) && GetLastError() == 0x80090001u);                          /* 解放済み prov */
    CHECK(CryptReleaseContext(prov2, 0));
}

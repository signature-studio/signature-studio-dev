/* G03: Authenticode 署名ゲート (engine 0x1375990 ×2 / host)。
 *
 * これは「署名を検証しない shim」であり、署名の偽造・改変ではない: WebStudio は wasm 再ビルド物で Authenticode
 * 署名自体が成立しないため、エンジンの自己整合検査 (WinVerifyTrust==0 && 署名者名 == "Image Line NV") に
 * 呼出順どおりの値を返す。cfg.trust=0 なら全て shimx 既定 (検証失敗) に委譲する。
 * ライセンス/登録/アクティベーション判定には一切関与しない (REPORT §6 参照)。
 */
#include "ws_internal.h"

static uint8_t g_ctx[64];          /* PCCERT_CONTEXT ダミー (Win64: 40B。非 NULL であれば良い) */
static uint8_t g_store[16], g_msg[16];
static const char kSigner[] = "Image Line NV";     /* 13 文字 */

static int own(LPVOID c) { return g_ws_cfg.trust && c == (LPVOID)g_ctx; }

LONG __wrap_WinVerifyTrust(HWND w, GUID* action, LPVOID data) {
    WS_INC(verify_trust);
    return __real_WinVerifyTrust(w, action, data);          /* trust_ok=1 なら 0 (VERIFY/CLOSE とも) */
}

BOOL __wrap_CryptQueryObject(DWORD t, const void* o, DWORD ex, DWORD ef, DWORD fl, LPDWORD enc, LPDWORD ct, LPDWORD ft,
                             LPVOID* st, LPVOID* msg, const void** ctx) {
    WS_INC(crypt_query);
    if (!g_ws_cfg.trust) return __real_CryptQueryObject(t, o, ex, ef, fl, enc, ct, ft, st, msg, ctx);
    if ((t != 1 && t != 2) || !o) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    if (!(ex & 0x400u)) { SetLastError(0x80092009u /* CRYPT_E_NO_MATCH */); return FALSE; }   /* PKCS7_SIGNED_EMBED 以外は無し */
    if (enc) *enc = 0x10001;      /* X509_ASN_ENCODING | PKCS_7_ASN_ENCODING */
    if (ct) *ct = 10;             /* CERT_QUERY_CONTENT_PKCS7_SIGNED_EMBED */
    if (ft) *ft = 1;              /* CERT_QUERY_FORMAT_BINARY */
    if (st) *st = (LPVOID)g_store;
    if (msg) *msg = (LPVOID)g_msg;
    if (ctx) *ctx = NULL;
    return TRUE;
}

BOOL __wrap_CryptMsgGetParam(LPVOID m, DWORD type, DWORD idx, LPVOID buf, LPDWORD n) {
    WS_INC(crypt_msg_param);
    if (!g_ws_cfg.trust || m != (LPVOID)g_msg) return __real_CryptMsgGetParam(m, type, idx, buf, n);
    if (!n) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    if (type == 5) {                              /* CMSG_SIGNER_COUNT_PARAM */
        if (!buf || *n < 4) { *n = 4; if (buf) { SetLastError(ERROR_MORE_DATA); return FALSE; } return TRUE; }
        *(DWORD*)buf = 1; *n = 4; return TRUE;
    }
    if (type == 6 && idx == 0) {                  /* CMSG_SIGNER_INFO_PARAM: sizeof(CMSG_SIGNER_INFO) (Win64) = 0x88 */
        const DWORD need = 0x88;
        if (!buf) { *n = need; return TRUE; }
        if (*n < need) { *n = need; SetLastError(ERROR_MORE_DATA); return FALSE; }
        memset(buf, 0, need);                     /* Issuer/SerialNumber blob 長 0, 属性 0 件 */
        *n = need;
        return TRUE;
    }
    SetLastError(WS_CRYPT_E_INVALID_MSG);
    return FALSE;
}

LPVOID __wrap_CertFindCertificateInStore(LPVOID store, DWORD enc, DWORD flags, DWORD type, const void* para, LPVOID prev) {
    WS_INC(cert_find);
    if (!g_ws_cfg.trust || store != (LPVOID)g_store) return __real_CertFindCertificateInStore(store, enc, flags, type, para, prev);
    if (prev) { SetLastError(WS_CRYPT_E_NOT_FOUND); return NULL; }     /* 列挙は 1 件で終わり */
    return (LPVOID)g_ctx;
}

DWORD __wrap_CertGetNameStringW(LPVOID c, DWORD type, DWORD flags, LPVOID tp, LPWSTR out, DWORD n) {
    WS_INC(cert_name);
    if (!own(c) || type != 4 /* CERT_NAME_SIMPLE_DISPLAY_TYPE */ || (flags & 1u /* ISSUER */))
        return __real_CertGetNameStringW(c, type, flags, tp, out, n);
    const DWORD len = (DWORD)(sizeof kSigner - 1);
    if (!out || n == 0) return len + 1;                     /* 長さ照会 = 14 (NUL 込み) */
    DWORD k = (len < n - 1) ? len : n - 1;
    for (DWORD i = 0; i < k; i++) out[i] = (WCHAR)(unsigned char)kSigner[i];
    out[k] = 0;
    return k + 1;
}
DWORD __wrap_CertGetNameStringA(LPVOID c, DWORD type, DWORD flags, LPVOID tp, LPSTR out, DWORD n) {
    WS_INC(cert_name);
    if (!own(c) || type != 4 || (flags & 1u)) return __real_CertGetNameStringA(c, type, flags, tp, out, n);
    const DWORD len = (DWORD)(sizeof kSigner - 1);
    if (!out || n == 0) return len + 1;
    DWORD k = (len < n - 1) ? len : n - 1;
    memcpy(out, kSigner, k); out[k] = 0;
    return k + 1;
}

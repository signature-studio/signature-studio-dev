// Headless post-script: function census + protection-related xrefs (strings / imports) + decompile of hit functions.
// args: <outdir>
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.data.*;
import java.io.*;
import java.util.*;
import java.util.regex.*;

public class SerumSurvey extends GhidraScript {
    static final String STR_RE = "(?i)(licen[sc]e|demoVersion|^Expire|not authorized|authori[sz]|Download Update|Update Available|InstallerPrefs|activat|serial|Ed25519|unlock|trial|xferrecords|https?://|OfflineRender|machine|hardware|MTS_)";
    static final String[] API = {"CryptAcquireContextA","CryptCreateHash","CryptHashData","CryptGetHashParam","RegOpenKeyExA","RegQueryValueExW",
        "InternetOpenA","InternetOpenUrlA","InternetReadFile","HttpQueryInfoW","WSAStartup","socket","bind","listen","accept","send","recv","WSAPoll",
        "IsDebuggerPresent","OutputDebugStringA","GetTickCount","GetTickCount64","QueryPerformanceCounter","GetVersionExW","GetNativeSystemInfo","GetSystemInfo",
        "CoCreateGuid","VirtualProtect","ShellExecuteW","ShellExecuteExA","LoadLibraryA","LoadLibraryW","GetProcAddress","CreateThread","CreateFileMappingW","FindResourceA","DeviceIoControl",
        "GetDiskFreeSpaceW","GetDriveTypeW","SHGetKnownFolderPath","GetModuleFileNameW","ReadDirectoryChangesW","CreateMutexW","MessageBoxA"};

    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        File out = new File(a.length > 0 ? a[0] : "/tmp/opencode");
        out.mkdirs();
        Program p = currentProgram;
        FunctionManager fm = p.getFunctionManager();
        // 1. function census
        try (PrintWriter w = new PrintWriter(new File(out, "functions.csv"))) {
            w.println("addr,size,name,thunk");
            for (Function f : fm.getFunctions(true)) {
                w.println(f.getEntryPoint() + "," + f.getBody().getNumAddresses() + "," + f.getName().replace(',', '_') + "," + f.isThunk());
            }
        }
        println("FN_TOTAL=" + fm.getFunctionCount());
        // 2. string xrefs
        Pattern re = Pattern.compile(STR_RE);
        Listing l = p.getListing();
        Set<Function> hits = new LinkedHashSet<>();
        try (PrintWriter w = new PrintWriter(new File(out, "string_xrefs.txt"))) {
            DataIterator di = l.getDefinedData(true);
            while (di.hasNext()) {
                Data d = di.next();
                if (!(d.getDataType() instanceof StringDataType || d.getDataType() instanceof TerminatedStringDataType
                      || d.getDataType() instanceof UnicodeDataType || d.getDataType() instanceof TerminatedUnicodeDataType
                      || d.getDataType().getName().toLowerCase().contains("string"))) continue;
                Object v = d.getValue();
                if (v == null) continue;
                String s = v.toString();
                if (s.length() > 200 || !re.matcher(s).find()) continue;
                StringBuilder sb = new StringBuilder();
                ReferenceIterator ri = p.getReferenceManager().getReferencesTo(d.getAddress());
                int n = 0;
                while (ri.hasNext()) {
                    Reference r = ri.next();
                    Function f = fm.getFunctionContaining(r.getFromAddress());
                    sb.append(" ").append(r.getFromAddress()).append("@").append(f == null ? "?" : f.getEntryPoint().toString());
                    if (f != null) { hits.add(f); }
                    if (++n > 8) break;
                }
                w.println(d.getAddress() + " \"" + s.replace("\n", "\\n") + "\" refs:" + sb);
            }
        }
        // 3. API xrefs
        try (PrintWriter w = new PrintWriter(new File(out, "api_xrefs.txt"))) {
            SymbolTable st = p.getSymbolTable();
            for (String api : API) {
                for (Symbol s : st.getSymbols(api)) {
                    ReferenceIterator ri = p.getReferenceManager().getReferencesTo(s.getAddress());
                    List<String> callers = new ArrayList<>();
                    while (ri.hasNext()) {
                        Reference r = ri.next();
                        Function f = fm.getFunctionContaining(r.getFromAddress());
                        String e = f == null ? "?" : f.getEntryPoint().toString();
                        if (!callers.contains(e)) callers.add(e);
                    }
                    w.println(api + " (" + s.getAddress() + ") callers=" + callers.size() + " " + (callers.size() > 40 ? callers.subList(0, 40) : callers));
                }
            }
        }
        // 4. decompile hit functions (cap)
        DecompInterface di = new DecompInterface();
        di.openProgram(p);
        int k = 0;
        try (PrintWriter w = new PrintWriter(new File(out, "decomp_hits.c"))) {
            for (Function f : hits) {
                if (k++ >= 60) break;
                if (f.getBody().getNumAddresses() > 20000) { w.println("// skipped huge " + f.getName() + " " + f.getEntryPoint()); continue; }
                DecompileResults r = di.decompileFunction(f, 60, monitor);
                w.println("// ==== " + f.getName() + " @ " + f.getEntryPoint() + " size=" + f.getBody().getNumAddresses());
                if (r != null && r.getDecompiledFunction() != null) w.println(r.getDecompiledFunction().getC());
            }
        }
        println("DONE survey; hits=" + hits.size());
    }
}

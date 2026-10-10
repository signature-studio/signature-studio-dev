// hostbridge: 汎用クエリ。引数: <out> <mode> <items...>
//   mode=xrefstr : UTF-16LE / ASCII 文字列を探し、参照元関数を列挙
//   mode=callers : 外部(import)シンボル名の呼出元関数を列挙
//   mode=decomp  : 関数エントリアドレス(hex)を decompile
//   mode=disasm  : 関数エントリアドレス(hex)を逆アセンブル
//   mode=callees : 関数のコールツリー(1段)
//@category Analysis
import java.io.*;
import java.util.*;
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.symbol.*;

public class Query extends GhidraScript {
    PrintWriter out;
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        out = new PrintWriter(new FileWriter(a[0]));
        String mode = a[1];
        try {
            for (int i = 2; i < a.length; i++) {
                switch (mode) {
                    case "xrefstr": xrefstr(a[i]); break;
                    case "callers": callers(a[i]); break;
                    case "decomp": decomp(a[i]); break;
                    case "disasm": disasm(a[i]); break;
                    case "callees": callees(a[i]); break;
                    case "refsto": refsto(a[i]); break;
                    case "decompall": decompall(a[i], a[i+1]); i += 1; break;
                    case "grepins": grepins(a[i], a[i+1], a[i+2]); i += 2; break;
                }
            }
        } finally { out.close(); }
    }

    Function fnAt(Address ad) { return currentProgram.getFunctionManager().getFunctionContaining(ad); }

    void xrefstr(String pat) throws Exception {
        out.println("=== xrefstr '" + pat + "'");
        Memory mem = currentProgram.getMemory();
        byte[][] encs = new byte[2][];
        encs[1] = pat.getBytes("US-ASCII");
        encs[0] = pat.getBytes("UTF-16LE");
        for (int e = 0; e < 2; e++) {
            Address start = mem.getMinAddress();
            while (true) {
                Address hit = mem.findBytes(start, encs[e], null, true, monitor);
                if (hit == null) break;
                out.println("  hit(" + (e == 0 ? "u16" : "a") + ") @" + hit);
                Set<String> seen = new TreeSet<>();
                for (int back = 0; back <= 16; back += 1) {
                    Address t = hit.subtract(back);
                    for (Reference r : getReferencesTo(t)) {
                        Function f = fnAt(r.getFromAddress());
                        seen.add("    ref from " + r.getFromAddress() + " in " + (f == null ? "?" : f.getName() + "@" + f.getEntryPoint()) + " (to " + t + ")");
                    }
                }
                for (String s : seen) out.println(s);
                start = hit.add(1);
            }
        }
    }

    void callers(String name) throws Exception {
        out.println("=== callers of '" + name + "'");
        SymbolTable st = currentProgram.getSymbolTable();
        for (Symbol s : st.getSymbols(name)) {
            out.println("  symbol " + s.getName() + " @" + s.getAddress() + " type=" + s.getSymbolType());
            Set<String> seen = new TreeSet<>();
            for (Reference r : getReferencesTo(s.getAddress())) {
                Function f = fnAt(r.getFromAddress());
                seen.add("    from " + r.getFromAddress() + " in " + (f == null ? "?" : f.getName() + "@" + f.getEntryPoint()));
            }
            for (String x : seen) out.println(x);
        }
    }

    void decomp(String hex) throws Exception {
        Address ad = toAddr(hex);
        Function f = fnAt(ad);
        out.println("=== decomp " + hex + " -> " + (f == null ? "NONE" : f.getName() + " @" + f.getEntryPoint() + " size=" + f.getBody().getNumAddresses()));
        if (f == null) return;
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        DecompileResults r = di.decompileFunction(f, 120, monitor);
        if (r.decompileCompleted()) out.println(r.getDecompiledFunction().getC());
        else out.println("DECOMP FAILED: " + r.getErrorMessage());
    }

    void disasm(String hex) throws Exception {
        Address ad = toAddr(hex);
        Function f = fnAt(ad);
        out.println("=== disasm " + hex + " -> " + (f == null ? "NONE" : f.getName() + " @" + f.getEntryPoint()));
        if (f == null) return;
        Listing l = currentProgram.getListing();
        InstructionIterator it = l.getInstructions(f.getBody(), true);
        while (it.hasNext()) { Instruction in = it.next(); out.println("  " + in.getAddress() + ": " + in); }
    }

    void refsto(String hex) throws Exception {
        Address ad = toAddr(hex);
        Function tf = fnAt(ad);
        out.println("=== refsto " + hex + " (" + (tf == null ? "?" : tf.getName()) + ")");
        Set<String> seen = new TreeSet<>();
        for (Reference r : getReferencesTo(ad)) {
            Function f = fnAt(r.getFromAddress());
            seen.add("  from " + r.getFromAddress() + " in " + (f == null ? "?" : f.getName() + "@" + f.getEntryPoint()) + " " + r.getReferenceType());
        }
        for (String s : seen) out.println(s);
    }

    void grepins(String re, String lo, String hi) throws Exception {
        out.println("=== grepins /" + re + "/ in [" + lo + "," + hi + "]");
        java.util.regex.Pattern p = java.util.regex.Pattern.compile(re);
        Listing l = currentProgram.getListing();
        AddressSet as = new AddressSet(toAddr(lo), toAddr(hi));
        InstructionIterator it = l.getInstructions(as, true);
        while (it.hasNext()) {
            Instruction in = it.next();
            String t = in.toString();
            if (p.matcher(t).find()) {
                Function f = fnAt(in.getAddress());
                out.println("  " + in.getAddress() + ": " + t + "   [" + (f == null ? "?" : f.getEntryPoint().toString()) + "]");
            }
        }
    }

    void decompall(String lo, String hi) throws Exception {
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(new AddressSet(toAddr(lo), toAddr(hi)), true);
        int n = 0;
        while (it.hasNext()) {
            Function f = it.next();
            out.println("//// FUNC " + f.getEntryPoint() + " size=" + f.getBody().getNumAddresses());
            DecompileResults r = di.decompileFunction(f, 60, monitor);
            if (r.decompileCompleted()) out.println(r.getDecompiledFunction().getC());
            else out.println("DECOMP FAILED");
            n++;
        }
        out.println("//// total " + n);
    }

    void callees(String hex) throws Exception {
        Address ad = toAddr(hex);
        Function f = fnAt(ad);
        out.println("=== callees " + hex + " -> " + (f == null ? "NONE" : f.getName()));
        if (f == null) return;
        Set<String> seen = new TreeSet<>();
        for (Function c : f.getCalledFunctions(monitor)) seen.add("  " + c.getName() + "@" + c.getEntryPoint());
        for (String s : seen) out.println(s);
    }
}

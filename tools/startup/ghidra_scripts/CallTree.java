// Ghidra headless postScript: root 関数群から BFS で呼出木を作り、各関数の callee / 参照文字列 / import API を TSV 出力。
// args: <out.tsv> <depth> <maxFuncs> <root1,root2,...|@file> [skipBelowSize]
//@category Analysis
import java.io.*;
import java.nio.file.*;
import java.util.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.data.*;
import ghidra.program.model.mem.*;

public class CallTree extends GhidraScript {
    String strAt(Address a) {
        try {
            Data d = getDataAt(a);
            if (d != null && d.hasStringValue()) {
                Object v = d.getValue();
                if (v != null) return v.toString();
            }
            // fallback: try read as UTF-16 / ASCII
            Memory m = currentProgram.getMemory();
            byte[] b = new byte[160];
            int n = m.getBytes(a, b);
            StringBuilder sb = new StringBuilder();
            int i = 0;
            // ascii
            while (i < n && b[i] >= 0x20 && b[i] < 0x7f) { sb.append((char) b[i]); i++; }
            if (sb.length() >= 4 && (i >= n || b[i] == 0)) return sb.toString();
            sb.setLength(0);
            i = 0;
            while (i + 1 < n && b[i + 1] == 0 && b[i] >= 0x20 && b[i] < 0x7f) { sb.append((char) b[i]); i += 2; }
            if (sb.length() >= 4 && (i + 1 >= n || (b[i] == 0 && b[i + 1] == 0))) return sb.toString();
        } catch (Exception e) {}
        return null;
    }
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        String out = a[0];
        int depth = Integer.parseInt(a[1]);
        int max = Integer.parseInt(a[2]);
        List<String> roots = new ArrayList<>();
        if (a[3].startsWith("@")) { for (String l : Files.readAllLines(Paths.get(a[3].substring(1)))) { l = l.trim(); if (!l.isEmpty() && !l.startsWith("#")) roots.add(l.split("\\s+")[0]); } }
        else roots.addAll(Arrays.asList(a[3].split(",")));
        long minSize = a.length > 4 ? Long.parseLong(a[4]) : 0;
        FunctionManager fm = currentProgram.getFunctionManager();
        ReferenceManager rm = currentProgram.getReferenceManager();
        Listing lst = currentProgram.getListing();
        Map<Address,Integer> seen = new LinkedHashMap<>();
        Deque<Address> q = new ArrayDeque<>();
        for (String r : roots) {
            Address ad = toAddr(Long.parseUnsignedLong(r.replace("0x",""), 16));
            Function f = getFunctionAt(ad);
            if (f == null) { disassemble(ad); f = createFunction(ad, null); }
            if (f != null && !seen.containsKey(f.getEntryPoint())) { seen.put(f.getEntryPoint(), 0); q.add(f.getEntryPoint()); }
        }
        try (PrintWriter pw = new PrintWriter(new FileWriter(out))) {
            pw.println("addr\tdepth\tsize\tname\tcallees\tstrings\timports");
            while (!q.isEmpty() && seen.size() <= max) {
                Address e = q.poll();
                Function f = fm.getFunctionAt(e);
                if (f == null) continue;
                int dp = seen.get(e);
                Set<String> callees = new LinkedHashSet<>(), strs = new LinkedHashSet<>(), imps = new LinkedHashSet<>();
                InstructionIterator it = lst.getInstructions(f.getBody(), true);
                while (it.hasNext()) {
                    Instruction ins = it.next();
                    for (Reference r : ins.getReferencesFrom()) {
                        Address to = r.getToAddress();
                        if (r.getReferenceType().isCall() || r.getReferenceType().isJump()) {
                            Function g = fm.getFunctionAt(to);
                            if (g == null) g = fm.getFunctionContaining(to);
                            Symbol sy = currentProgram.getSymbolTable().getPrimarySymbol(to);
                            if (g != null && g.isExternal()) { imps.add(g.getName()); }
                            else if (to.isExternalAddress()) { imps.add(sy != null ? sy.getName() : to.toString()); }
                            else if (g != null && !g.getEntryPoint().equals(e)) {
                                callees.add(g.getEntryPoint().toString());
                                if (dp < depth && !seen.containsKey(g.getEntryPoint()) && g.getBody().getNumAddresses() >= minSize) { seen.put(g.getEntryPoint(), dp + 1); q.add(g.getEntryPoint()); }
                            }
                        } else if (r.getReferenceType().isData() || r.getReferenceType().isRead()) {
                            if (to.isExternalAddress()) { Symbol sy = currentProgram.getSymbolTable().getPrimarySymbol(to); imps.add(sy != null ? sy.getName() : to.toString()); }
                            else {
                                String s = strAt(to);
                                if (s != null) strs.add(s.replaceAll("[\\p{Cntrl}]"," ").replace(" | ","/"));
                                else {
                                    // pointer to IAT entry?
                                    Data d = getDataAt(to);
                                    if (d != null && d.isPointer()) {
                                        Reference[] rr = d.getReferencesFrom();
                                        for (Reference x : rr) if (x.getToAddress().isExternalAddress()) { Symbol sy = currentProgram.getSymbolTable().getPrimarySymbol(x.getToAddress()); imps.add(sy != null ? sy.getName() : x.getToAddress().toString()); }
                                    }
                                }
                            }
                        }
                    }
                }
                pw.println(e + "\t" + dp + "\t" + f.getBody().getNumAddresses() + "\t" + f.getName() + "\t" + String.join(",", callees) + "\t" + String.join(" | ", strs) + "\t" + String.join(",", imps));
            }
        }
        println("CallTree: " + seen.size() + " funcs -> " + out);
    }
}

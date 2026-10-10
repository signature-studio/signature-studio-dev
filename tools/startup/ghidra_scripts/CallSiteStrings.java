// Ghidra headless postScript: 対象 callee アドレス範囲への全 call site について、直前の lea で積まれた文字列リテラル引数 (rcx/rdx/r8/r9) を抽出。
// args: <out.tsv> <loAddr> <hiAddr>   (callee が [lo,hi) に入る call/jmp を対象)
// 出力: caller_func \t call_addr \t callee \t rcx \t rdx \t r8 \t r9
//@category Analysis
import java.io.*;
import java.util.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.data.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.lang.Register;

public class CallSiteStrings extends GhidraScript {
    String strAt(Address a) {
        try {
            Memory m = currentProgram.getMemory();
            byte[] b = new byte[260];
            int n = m.getBytes(a, b);
            StringBuilder sb = new StringBuilder();
            int i = 0;
            while (i < n && b[i] >= 0x20 && b[i] < 0x7f) { sb.append((char) b[i]); i++; }
            if (sb.length() >= 2 && (i >= n || b[i] == 0)) return "A:" + sb;
            sb.setLength(0);
            i = 0;
            while (i + 1 < n) {
                int c = (b[i] & 0xff) | ((b[i + 1] & 0xff) << 8);
                if (c == 0) break;
                if (c < 0x20 && c != 9) return null;
                if (c > 0x7e && c < 0xa0) return null;
                sb.append((char) c); i += 2;
            }
            if (sb.length() >= 1 && i + 1 < n) return "W:" + sb;
        } catch (Exception e) {}
        return null;
    }
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        long lo = Long.parseUnsignedLong(a[1], 16), hi = Long.parseUnsignedLong(a[2], 16);
        Listing lst = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();
        String[] regs = { "RCX", "RDX", "R8", "R9" };
        int cnt = 0;
        try (PrintWriter pw = new PrintWriter(new FileWriter(a[0]))) {
            pw.println("caller\tcall\tcallee\trcx\trdx\tr8\tr9");
            FunctionIterator fit = fm.getFunctions(true);
            while (fit.hasNext()) {
                Function f = fit.next();
                InstructionIterator it = lst.getInstructions(f.getBody(), true);
                while (it.hasNext()) {
                    Instruction ins = it.next();
                    if (!(ins.getFlowType().isCall() || ins.getFlowType().isJump())) continue;
                    Address tgt = null;
                    for (Reference r : ins.getReferencesFrom()) if (r.getReferenceType().isFlow()) { tgt = r.getToAddress(); break; }
                    if (tgt == null) continue;
                    long t = tgt.getOffset();
                    if (t < lo || t >= hi) continue;
                    String[] val = new String[4];
                    boolean[] done = new boolean[4];
                    Instruction p = ins.getPrevious();
                    for (int k = 0; k < 16 && p != null; k++, p = p.getPrevious()) {
                        if (p.getFlowType().isCall() || p.getFlowType().isJump() || p.getFlowType().isTerminal()) { if (p.getFlowType().isCall()) { /* args clobbered after call; stop */ break; } else break; }
                        String mn = p.getMnemonicString();
                        for (int ri = 0; ri < 4; ri++) {
                            if (done[ri]) continue;
                            Object[] o0 = p.getOpObjects(0);
                            boolean writesReg = false;
                            if (p.getNumOperands() > 0 && o0.length > 0 && o0[0] instanceof Register) {
                                Register rg = (Register) o0[0];
                                String nm = rg.getBaseRegister().getName();
                                if (nm.equalsIgnoreCase(regs[ri])) writesReg = !mn.equals("CMP") && !mn.equals("TEST") && !mn.equals("PUSH");
                            }
                            if (!writesReg) continue;
                            done[ri] = true;
                            if (mn.equals("XOR") && p.getNumOperands() > 1) {
                                Object[] x1 = p.getOpObjects(1);
                                if (x1.length > 0 && x1[0] instanceof Register && ((Register) x1[0]).getBaseRegister().getName().equalsIgnoreCase(regs[ri])) val[ri] = "#0";
                            }
                            if (mn.equals("LEA") || mn.equals("MOV")) {
                                for (Reference r : p.getReferencesFrom()) {
                                    if (r.getReferenceType().isData() || r.getReferenceType().isRead()) {
                                        String s = strAt(r.getToAddress());
                                        if (s != null) { val[ri] = s.replaceAll("[\\p{Cntrl}]", " "); break; }
                                    }
                                }
                                if (val[ri] == null && mn.equals("MOV") && p.getNumOperands() > 1) {
                                    Object[] o1 = p.getOpObjects(1);
                                    if (o1.length > 0 && o1[0] instanceof ghidra.program.model.scalar.Scalar) val[ri] = "#" + Long.toHexString(((ghidra.program.model.scalar.Scalar) o1[0]).getUnsignedValue());
                                }
                            }
                        }
                    }
                    pw.println(f.getEntryPoint() + "\t" + ins.getAddress() + "\t" + tgt + "\t" + nz(val[0]) + "\t" + nz(val[1]) + "\t" + nz(val[2]) + "\t" + nz(val[3]));
                    cnt++;
                }
            }
        }
        println("CallSiteStrings: " + cnt + " sites -> " + a[0]);
    }
    String nz(String s) { return s == null ? "" : s; }
}

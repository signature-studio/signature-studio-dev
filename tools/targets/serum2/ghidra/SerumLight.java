// Light headless script (run with -noanalysis): create functions from .pdata, dump census CSV, decompile listed targets.
// args: <outdir> <targets.txt: one hex VA per line>
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
import java.io.*;
import java.util.*;

public class SerumLight extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        File out = new File(a[0]); out.mkdirs();
        Program p = currentProgram;
        Memory mem = p.getMemory();
        MemoryBlock pd = mem.getBlock(".pdata");
        long base = p.getImageBase().getOffset();
        int created = 0, failed = 0;
        byte[] buf = new byte[(int) pd.getSize()];
        pd.getBytes(pd.getStart(), buf);
        java.nio.ByteBuffer bb = java.nio.ByteBuffer.wrap(buf).order(java.nio.ByteOrder.LITTLE_ENDIAN);
        for (int i = 0; i + 12 <= buf.length; i += 12) {
            long b = bb.getInt(i) & 0xffffffffL;
            if (b == 0) continue;
            Address ad = toAddr(base + b);
            if (getFunctionAt(ad) != null) continue;
            if (disassemble(ad) && createFunction(ad, null) != null) created++; else failed++;
        }
        println("PDATA_FUNCS_CREATED=" + created + " FAILED=" + failed + " TOTAL_FUNCS=" + p.getFunctionManager().getFunctionCount());
        try (PrintWriter w = new PrintWriter(new File(out, "functions.csv"))) {
            w.println("addr,size");
            for (Function f : p.getFunctionManager().getFunctions(true))
                w.println(f.getEntryPoint() + "," + f.getBody().getNumAddresses());
        }
        DecompInterface di = new DecompInterface();
        di.openProgram(p);
        try (PrintWriter w = new PrintWriter(new File(out, "decomp_targets.c"));
             BufferedReader r = new BufferedReader(new FileReader(a[1]))) {
            String line;
            while ((line = r.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty() || line.startsWith("#")) continue;
                String[] parts = line.split("\\s+", 2);
                Address ad = toAddr(Long.parseLong(parts[0].replace("0x", ""), 16));
                Function f = getFunctionAt(ad);
                if (f == null) { disassemble(ad); f = createFunction(ad, null); }
                w.println("// ==== " + (parts.length > 1 ? parts[1] : "") + " @ " + ad);
                if (f == null) { w.println("// no function"); continue; }
                DecompileResults res = di.decompileFunction(f, 90, monitor);
                if (res != null && res.getDecompiledFunction() != null) w.println(res.getDecompiledFunction().getC());
                else w.println("// decompile failed");
            }
        }
        println("DONE light");
    }
}

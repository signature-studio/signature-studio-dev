// Ghidra headless postScript: 指定アドレス群への参照元 (関数, 種別) を列挙。 args: <out.tsv> <addr1,addr2,...>
//@category Analysis
import java.io.*;
import java.util.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class RefsTo extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        ReferenceManager rm = currentProgram.getReferenceManager();
        FunctionManager fm = currentProgram.getFunctionManager();
        try (PrintWriter pw = new PrintWriter(new FileWriter(a[0]))) {
            pw.println("target\tfrom\tfunc\tfunc_size\ttype");
            for (String s : a[1].split(",")) {
                Address t = toAddr(Long.parseUnsignedLong(s.replace("0x", ""), 16));
                ReferenceIterator ri = rm.getReferencesTo(t);
                while (ri.hasNext()) {
                    Reference r = ri.next();
                    Function f = fm.getFunctionContaining(r.getFromAddress());
                    pw.println(t + "\t" + r.getFromAddress() + "\t" + (f == null ? "-" : f.getEntryPoint().toString()) + "\t" + (f == null ? 0 : f.getBody().getNumAddresses()) + "\t" + r.getReferenceType());
                }
            }
        }
    }
}

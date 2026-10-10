// Ghidra headless postScript: 定義済み文字列のうち正規表現にマッチするものの参照元関数を列挙。
// args: <out.tsv> <regex>
//@category Analysis
import java.io.*;
import java.util.*;
import java.util.regex.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class StrRefs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        Pattern p = Pattern.compile(a[1], Pattern.CASE_INSENSITIVE);
        Listing l = currentProgram.getListing();
        ReferenceManager rm = currentProgram.getReferenceManager();
        FunctionManager fm = currentProgram.getFunctionManager();
        int n = 0;
        try (PrintWriter pw = new PrintWriter(new FileWriter(a[0]))) {
            pw.println("str_addr\tstring\tfunc\tfunc_size\tref_addr");
            DataIterator di = l.getDefinedData(true);
            while (di.hasNext()) {
                Data d = di.next();
                if (!d.hasStringValue()) continue;
                Object v = d.getValue();
                if (v == null) continue;
                String s = v.toString();
                if (!p.matcher(s).find()) continue;
                ReferenceIterator ri = rm.getReferencesTo(d.getAddress());
                boolean any = false;
                while (ri.hasNext()) {
                    Reference r = ri.next();
                    Function f = fm.getFunctionContaining(r.getFromAddress());
                    pw.println(d.getAddress() + "\t" + s.replaceAll("[\\p{Cntrl}]", " ") + "\t" + (f == null ? "-" : f.getEntryPoint() + ":" + f.getName()) + "\t" + (f == null ? 0 : f.getBody().getNumAddresses()) + "\t" + r.getFromAddress());
                    any = true; n++;
                }
                if (!any) { pw.println(d.getAddress() + "\t" + s.replaceAll("[\\p{Cntrl}]", " ") + "\t-\t0\t-"); }
            }
        }
        println("StrRefs: " + n + " refs -> " + a[0]);
    }
}

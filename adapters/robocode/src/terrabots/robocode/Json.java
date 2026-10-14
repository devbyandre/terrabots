package terrabots.robocode;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Just enough JSON for the engine protocol: objects, arrays, strings, numbers, booleans, null. */
public final class Json {
    private final String s;
    private int i;

    private Json(String s) { this.s = s; }

    public static Object parse(String text) {
        Json p = new Json(text);
        Object v = p.value();
        p.ws();
        if (p.i != text.length()) throw new IllegalArgumentException("trailing data at " + p.i);
        return v;
    }

    private void ws() { while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++; }

    private Object value() {
        ws();
        char c = s.charAt(i);
        switch (c) {
            case '{': return object();
            case '[': return array();
            case '"': return string();
            case 't': i += 4; return Boolean.TRUE;
            case 'f': i += 5; return Boolean.FALSE;
            case 'n': i += 4; return null;
            default: return number();
        }
    }

    private Map<String, Object> object() {
        Map<String, Object> m = new LinkedHashMap<>();
        i++;
        ws();
        if (s.charAt(i) == '}') { i++; return m; }
        while (true) {
            ws();
            String k = string();
            ws();
            i++;                                   // ':'
            m.put(k, value());
            ws();
            if (s.charAt(i++) == '}') return m;   // else ','
        }
    }

    private List<Object> array() {
        List<Object> a = new ArrayList<>();
        i++;
        ws();
        if (s.charAt(i) == ']') { i++; return a; }
        while (true) {
            a.add(value());
            ws();
            if (s.charAt(i++) == ']') return a;
        }
    }

    private String string() {
        StringBuilder b = new StringBuilder();
        i++;
        while (true) {
            char c = s.charAt(i++);
            if (c == '"') return b.toString();
            if (c != '\\') { b.append(c); continue; }
            char e = s.charAt(i++);
            switch (e) {
                case 'n': b.append('\n'); break;
                case 't': b.append('\t'); break;
                case 'r': b.append('\r'); break;
                case 'b': b.append('\b'); break;
                case 'f': b.append('\f'); break;
                case 'u': b.append((char) Integer.parseInt(s.substring(i, i + 4), 16)); i += 4; break;
                default: b.append(e);
            }
        }
    }

    private Object number() {
        int start = i;
        while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
        String t = s.substring(start, i);
        if (t.equals("NaN") || t.isEmpty()) throw new IllegalArgumentException("bad number at " + start);
        return Double.parseDouble(t);
    }

    // --- writing ---------------------------------------------------------

    public static String write(Object v) {
        StringBuilder b = new StringBuilder();
        write(b, v);
        return b.toString();
    }

    @SuppressWarnings("unchecked")
    private static void write(StringBuilder b, Object v) {
        if (v == null) b.append("null");
        else if (v instanceof String) quote(b, (String) v);
        else if (v instanceof Boolean) b.append(v);
        else if (v instanceof Number) {
            double d = ((Number) v).doubleValue();
            if (Double.isNaN(d) || Double.isInfinite(d)) b.append("0");   // the engine rejects non-finite numbers
            else if (d == Math.rint(d) && Math.abs(d) < 1e15) b.append((long) d);
            else b.append(d);
        } else if (v instanceof Map) {
            b.append('{');
            boolean first = true;
            for (Map.Entry<String, Object> e : ((Map<String, Object>) v).entrySet()) {
                if (!first) b.append(',');
                first = false;
                quote(b, e.getKey());
                b.append(':');
                write(b, e.getValue());
            }
            b.append('}');
        } else if (v instanceof List) {
            b.append('[');
            boolean first = true;
            for (Object o : (List<Object>) v) {
                if (!first) b.append(',');
                first = false;
                write(b, o);
            }
            b.append(']');
        } else quote(b, v.toString());
    }

    private static void quote(StringBuilder b, String s) {
        b.append('"');
        for (int k = 0; k < s.length(); k++) {
            char c = s.charAt(k);
            if (c == '"' || c == '\\') b.append('\\').append(c);
            else if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
            else b.append(c);
        }
        b.append('"');
    }

    // --- reading helpers ---------------------------------------------------

    public static double num(Map<String, Object> m, String k) {
        Object v = m.get(k);
        return v == null ? 0.0 : ((Number) v).doubleValue();
    }

    @SuppressWarnings("unchecked")
    public static List<Map<String, Object>> list(Map<String, Object> m, String k) {
        Object v = m.get(k);
        return v == null ? new ArrayList<>() : (List<Map<String, Object>>) v;
    }
}

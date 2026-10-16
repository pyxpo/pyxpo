using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Pyxpo;

/// Small readers over System.Text.Json nodes: the ops JSON is loosely typed (a number may be int or float, a
/// prop may be missing or null), like the NSNumber / Any casts in the iOS shell.
static class Js
{
    public static double? Num(JsonNode? n)
    {
        if (n is JsonValue v)
        {
            if (v.TryGetValue(out double d)) return d;
            if (v.TryGetValue(out long l)) return l;
            if (v.TryGetValue(out int i)) return i;
            if (v.TryGetValue(out JsonElement e) && e.ValueKind == JsonValueKind.Number) return e.GetDouble();
        }
        return null;
    }

    public static double D(JsonNode? n, double def = 0) => Num(n) ?? def;
    public static int I(JsonNode? n, int def = 0) => Num(n) is double d ? (int)d : def;

    public static bool? Bool(JsonNode? n)
    {
        if (n is JsonValue v)
        {
            if (v.TryGetValue(out bool b)) return b;
            if (v.TryGetValue(out JsonElement e) && (e.ValueKind == JsonValueKind.True || e.ValueKind == JsonValueKind.False))
                return e.GetBoolean();
        }
        return null;
    }

    public static bool B(JsonNode? n, bool def = false) => Bool(n) ?? def;

    public static string? Str(JsonNode? n)
    {
        if (n is JsonValue v)
        {
            if (v.TryGetValue(out string? s)) return s;
            if (v.TryGetValue(out JsonElement e) && e.ValueKind == JsonValueKind.String) return e.GetString();
        }
        return null;
    }

    public static JsonObject? Obj(JsonNode? n) => n as JsonObject;
    public static JsonArray? Arr(JsonNode? n) => n as JsonArray;

    public static List<double> Nums(JsonNode? n)
    {
        var out_ = new List<double>();
        if (n is JsonArray a) foreach (var x in a) out_.Add(D(x));
        return out_;
    }

    public static bool Truthy(JsonNode? n)
    {
        if (n == null) return false;
        if (Bool(n) is bool b) return b;
        if (Num(n) is double d) return d != 0;
        if (Str(n) is string s) return s.Length > 0;
        return true;
    }

    /// 0xAARRGGBB: styles arrive normalized to ARGB ints; a few props (placeholder_color) are "#rrggbb" strings.
    public static uint? Color(JsonNode? n)
    {
        if (Num(n) is double d) return (uint)(long)d;
        if (Str(n) is string s && s.Trim().StartsWith('#'))
        {
            var h = s.Trim()[1..];
            if (h.Length == 3) h = string.Concat(h[0], h[0], h[1], h[1], h[2], h[2]);
            if (h.Length == 6 && uint.TryParse(h, System.Globalization.NumberStyles.HexNumber, null, out var u))
                return 0xFF000000u | u;
            // #RRGGBBAA (CSS order, as in [tool.pyxpo] background_color) to ARGB.
            if (h.Length == 8 && uint.TryParse(h, System.Globalization.NumberStyles.HexNumber, null, out var v))
                return (v >> 8) | (v << 24);
        }
        return null;
    }

    public static JsonNode? Clone(JsonNode? n) => n?.DeepClone();

    public static string Dump(JsonNode n) => n.ToJsonString();
}

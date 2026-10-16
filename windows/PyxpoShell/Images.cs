using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net.Http;
using System.Threading.Tasks;

namespace Pyxpo;

/// Loads image bytes off the UI thread: files, `asset:name`, `data:` URIs and http(s) URLs. Same URI forms as
/// Images.swift / Images.kt. The caller decodes on the UI thread (BitmapImage needs it).
static class Images
{
    static readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(30) };
    static readonly ConcurrentDictionary<string, byte[]> cache = new();
    static readonly string exeDir = AppContext.BaseDirectory;

    public static async Task<byte[]> Load(string uri)
    {
        if (cache.TryGetValue(uri, out var hit)) return hit;
        byte[] data;
        if (uri.StartsWith("http://") || uri.StartsWith("https://"))
            data = await http.GetByteArrayAsync(uri).ConfigureAwait(false);
        else
            data = await Task.Run(() => Read(uri)).ConfigureAwait(false);
        if (data.Length < 8 * 1024 * 1024) cache[uri] = data;
        return data;
    }

    static byte[] Read(string uri)
    {
        if (uri.StartsWith("data:"))
        {
            int i = uri.IndexOf("base64,", StringComparison.Ordinal);
            if (i < 0) throw new IOException("only base64 data: URIs are supported");
            return Convert.FromBase64String(uri[(i + 7)..]);
        }
        if (uri.StartsWith("asset:"))
        {
            var name = uri[6..].Replace('/', Path.DirectorySeparatorChar);
            // Assets are staged with the app code (app\assets\...); the name may or may not carry that prefix.
            foreach (var dir in new[] { exeDir, Path.Combine(exeDir, "app"), Path.Combine(exeDir, "app", "assets") })
            {
                var p = Path.Combine(dir, name);
                if (File.Exists(p)) return File.ReadAllBytes(p);
            }
            throw new FileNotFoundException("no asset " + uri[6..]);
        }
        var path = uri.StartsWith("file://") ? new Uri(uri).LocalPath : uri;
        return File.ReadAllBytes(path);
    }
}

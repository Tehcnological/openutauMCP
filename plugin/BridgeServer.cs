using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Serilog;

namespace OpenUtauMcp.Plugin {
    /// <summary>
    /// Minimal HTTP/1.1 server on 127.0.0.1. POST /{op} with a JSON object body; replies
    /// {"ok":true,"result":...} or {"ok":false,"error":"Type: message"}.
    /// Requests must carry "X-OpenUtau-MCP: 1" and no Origin header (blocks browser pages).
    /// </summary>
    public static class BridgeServer {
        public const string HeaderName = "x-openutau-mcp";
        public static int Port { get; } = ReadPort();
        public static bool IsListening { get; private set; }
        public static string LastError { get; private set; } = "";

        static readonly object startLock = new object();
        static bool started;
        static TcpListener listener;
        const int MaxBody = 16 * 1024 * 1024;

        public static readonly JsonSerializerOptions Json = new JsonSerializerOptions {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        };

        static int ReadPort() {
            var env = Environment.GetEnvironmentVariable("OPENUTAU_MCP_PORT");
            return int.TryParse(env, out int p) && p > 0 && p < 65536 ? p : 51128;
        }

        public static void EnsureStarted() {
            lock (startLock) {
                if (started) {
                    return;
                }
                started = true;
            }
            try {
                listener = new TcpListener(IPAddress.Loopback, Port);
                listener.Start();
                IsListening = true;
                Log.Information($"OpenUtau MCP bridge listening on 127.0.0.1:{Port}");
                var thread = new Thread(AcceptLoop) { IsBackground = true, Name = "OpenUtauMcpBridge" };
                thread.Start();
            } catch (Exception e) {
                LastError = $"{e.GetType().Name}: {e.Message}";
                Log.Error(e, "OpenUtau MCP bridge failed to start");
            }
        }

        static void AcceptLoop() {
            while (true) {
                try {
                    var client = listener.AcceptTcpClient();
                    Task.Run(() => Handle(client));
                } catch (Exception e) {
                    Log.Error(e, "OpenUtau MCP bridge accept failed");
                    Thread.Sleep(500);
                }
            }
        }

        static async Task Handle(TcpClient client) {
            using (client) {
                try {
                    client.ReceiveTimeout = 30000;
                    var stream = client.GetStream();
                    var (method, path, headers, body) = ReadRequest(stream);
                    int status;
                    object payload;
                    if (headers.ContainsKey("origin") || !headers.TryGetValue(HeaderName, out var h) || h != "1") {
                        status = 403;
                        payload = new { ok = false, error = "Forbidden: missing X-OpenUtau-MCP header or Origin present" };
                    } else if (method != "POST") {
                        status = 405;
                        payload = new { ok = false, error = "Method not allowed: use POST" };
                    } else {
                        status = 200;
                        payload = await Dispatch(path.Trim('/'), body);
                    }
                    WriteResponse(stream, status, JsonSerializer.Serialize(payload, Json));
                } catch (Exception e) {
                    Log.Warning(e, "OpenUtau MCP bridge request failed");
                }
            }
        }

        static async Task<object> Dispatch(string op, string body) {
            try {
                JsonObject args = string.IsNullOrWhiteSpace(body)
                    ? new JsonObject()
                    : (JsonNode.Parse(body) as JsonObject ?? throw new ArgumentException("Body must be a JSON object"));
                var result = await Ops.Run(op, args);
                return new { ok = true, result };
            } catch (Exception e) {
                var inner = e is AggregateException ae && ae.InnerException != null ? ae.InnerException : e;
                if (inner is System.Reflection.TargetInvocationException tie && tie.InnerException != null) {
                    inner = tie.InnerException;
                }
                Log.Warning(inner, $"OpenUtau MCP op {op} failed");
                return new { ok = false, error = $"{inner.GetType().Name}: {inner.Message}" };
            }
        }

        static (string, string, Dictionary<string, string>, string) ReadRequest(Stream stream) {
            var headerBytes = new List<byte>();
            int b;
            while ((b = stream.ReadByte()) >= 0) {
                headerBytes.Add((byte)b);
                int n = headerBytes.Count;
                if (n >= 4 && headerBytes[n - 4] == '\r' && headerBytes[n - 3] == '\n' && headerBytes[n - 2] == '\r' && headerBytes[n - 1] == '\n') {
                    break;
                }
                if (n > 65536) {
                    throw new InvalidDataException("Header too large");
                }
            }
            var lines = Encoding.ASCII.GetString(headerBytes.ToArray()).Split("\r\n");
            var first = lines[0].Split(' ');
            if (first.Length < 2) {
                throw new InvalidDataException("Bad request line");
            }
            var headers = new Dictionary<string, string>();
            foreach (var line in lines[1..]) {
                int i = line.IndexOf(':');
                if (i > 0) {
                    headers[line[..i].Trim().ToLowerInvariant()] = line[(i + 1)..].Trim();
                }
            }
            int len = headers.TryGetValue("content-length", out var cl) && int.TryParse(cl, out int l) ? l : 0;
            if (len < 0 || len > MaxBody) {
                throw new InvalidDataException("Bad Content-Length");
            }
            var buf = new byte[len];
            int read = 0;
            while (read < len) {
                int r = stream.Read(buf, read, len - read);
                if (r <= 0) break;
                read += r;
            }
            return (first[0], first[1], headers, Encoding.UTF8.GetString(buf, 0, read));
        }

        static void WriteResponse(Stream stream, int status, string json) {
            var body = Encoding.UTF8.GetBytes(json);
            string reason = status == 200 ? "OK" : status == 403 ? "Forbidden" : "Method Not Allowed";
            var head = Encoding.ASCII.GetBytes(
                $"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: {body.Length}\r\nConnection: close\r\n\r\n");
            stream.Write(head);
            stream.Write(body);
            stream.Flush();
        }
    }
}

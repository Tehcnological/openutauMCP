using System;
using System.Collections.Generic;
using OpenUtau.Api;
using OpenUtau.Core;
using OpenUtau.Core.Editing;
using OpenUtau.Core.Ustx;

namespace OpenUtauMcp.Plugin {
    /// <summary>
    /// OpenUtau reads the PhonemizerAttribute of every exported Phonemizer subclass while it scans the
    /// Plugins folder at startup, which instantiates this attribute. Its constructor starts the bridge.
    /// Name and tag are null, so PhonemizerFactory.Get rejects the type and it never shows up in the
    /// phonemizer list.
    /// </summary>
    [AttributeUsage(AttributeTargets.Class, AllowMultiple = false, Inherited = false)]
    public sealed class BridgeStartupAttribute : PhonemizerAttribute {
        public BridgeStartupAttribute() : base(null, null) {
            BridgeServer.EnsureStarted();
        }
    }

    /// <summary>Carrier type for <see cref="BridgeStartupAttribute"/>. Never listed or used.</summary>
    [BridgeStartup]
    public sealed class BridgeStartupCarrier : Phonemizer {
        public override void SetSinger(USinger singer) { }
        public override Result Process(Note[] notes, Note? prev, Note? next, Note? prevNeighbour, Note? nextNeighbour, Note[] prevs)
            => new Result { phonemes = Array.Empty<Phoneme>() };
    }

    /// <summary>Piano roll → Batch Edit entry that reports the bridge status as a toast.</summary>
    public sealed class BridgeStatusBatchEdit : BatchEdit {
        public string Name => "OpenUtau MCP: bridge status / ブリッジ状態";

        public void Run(UProject project, UVoicePart part, List<UNote> selectedNotes, DocManager docManager) {
            BridgeServer.EnsureStarted();
            string msg = BridgeServer.IsListening
                ? $"OpenUtau MCP bridge is running on 127.0.0.1:{BridgeServer.Port} / ブリッジ稼働中"
                : $"OpenUtau MCP bridge is NOT running: {BridgeServer.LastError} / ブリッジ停止中";
            docManager.ExecuteCmd(new ToastNotification("Pianoroll", msg, msg));
        }
    }
}

// Dev tool: load .ustx files with OpenUtau.Core's own loader and print what it sees,
// or write a reference project ("--sample out.ustx"). Not shipped.
using System;
using System.Linq;
using OpenUtau.Core;
using OpenUtau.Core.Format;
using OpenUtau.Core.Ustx;

var ouDir = Environment.GetEnvironmentVariable("OPENUTAU_DIR") ?? @"C:\Program Files\OpenUtau";
System.Runtime.Loader.AssemblyLoadContext.Default.Resolving += (ctx, name) => {
    var f = System.IO.Path.Combine(ouDir, name.Name + ".dll");
    return System.IO.File.Exists(f) ? ctx.LoadFromAssemblyPath(f) : null;
};
return Run(args);

static int Run(string[] args) {

if (args.Length == 2 && args[0] == "--sample") {
    var p = Ustx.Create();
    p.tracks[0].singer = "x";
    var part = new UVoicePart { name = "P", trackNo = 0, position = 0, Duration = 1920 };
    var n = p.CreateNote(60, 0, 480);
    n.lyric = "la";
    part.notes.Add(n);
    p.parts.Add(part);
    p.ustxVersion = Ustx.kUstxVersion;
    p.BeforeSave();
    System.IO.File.WriteAllText(args[1], Yaml.DefaultSerializer.Serialize(p));
    return 0;
}
int rc = 0;
foreach (var f in args) {
    try {
        var p = Ustx.Load(f);
        Console.WriteLine($"OK {f}: tempos={string.Join(",", p.tempos)} tracks={p.tracks.Count} parts={p.parts.Count}");
        foreach (var t in p.tracks) Console.WriteLine($"  track {t.TrackNo} singer={t.singer} phonemizer={t.phonemizer}");
        foreach (var part in p.parts.OfType<UVoicePart>()) {
            Console.WriteLine($"  part {part.name} track={part.trackNo} pos={part.position} dur={part.Duration} notes={part.notes.Count}");
            foreach (var n in part.notes) Console.WriteLine($"    {n.position} {n.duration} {n.tone} '{n.lyric}' pitch={n.pitch.data.Count} vib={n.vibrato.length}");
        }
    } catch (Exception e) {
        Console.WriteLine($"FAIL {f}: {e}");
        rc = 1;
    }
}
return rc;
}

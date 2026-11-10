using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using OpenUtau.Api;
using OpenUtau.Core;
using OpenUtau.Core.Format;
using OpenUtau.Core.Render;
using OpenUtau.Core.Ustx;

namespace OpenUtauMcp.Plugin {
    /// <summary>
    /// Bridge operations. Document access runs on OpenUtau's UI thread; every mutation is one undo group.
    /// Indexing: part = index among voice parts in project order; track = track number;
    /// note = index in the part's sorted note set. Note positions are relative to the part. 480 ticks/quarter.
    /// </summary>
    public static class Ops {
        static readonly TimeSpan UiTimeout = TimeSpan.FromSeconds(30);

        static DocManager Doc => DocManager.Inst;
        static UProject Project => DocManager.Inst.Project;

        public static Task<object> Run(string op, JsonObject a) {
            switch (op) {
                case "status": return Ui(() => (object)new {
                    plugin = typeof(Ops).Assembly.GetName().Version?.ToString(),
                    openutau = typeof(DocManager).Assembly.GetName().Version?.ToString(),
                    port = BridgeServer.Port,
                    file_path = Project.FilePath,
                });
                case "project.get": return Ui(ProjectSummary);
                case "project.new": return Ui(() => NewProject(a));
                case "project.open": return Ui(() => OpenProject(a));
                case "project.save": return Ui(() => SaveProject(a));
                case "project.import": return Ui(() => ImportTracks(a));
                case "undo": return Ui(() => { Doc.Undo(); return ProjectSummary(); });
                case "redo": return Ui(() => { Doc.Redo(); return ProjectSummary(); });
                case "tempo.set": return Mutate("set tempo", () => SetTempo(a));
                case "tempo.remove": return Mutate("remove tempo", () => RemoveTempo(a));
                case "timesig.set": return Mutate("set time signature", () => SetTimeSig(a));
                case "key.set": return Mutate("set key", () => SetKey(a));
                case "singers.list": return Ui(ListSingers);
                case "singers.refresh": return Ui(() => {
                    Doc.ExecuteCmd(new SingersChangedNotification()); // rescans the Singers folder, like OpenUtau's refresh button
                    Doc.ExecuteCmd(new SingersRefreshedNotification());
                    return ListSingers();
                });
                case "phonemizers.list": return Ui(() => ListPhonemizers(a));
                case "expressions.list": return Ui(ListExpressions);
                case "track.add": return Mutate("add track", () => AddTrack(a));
                case "track.update": return Mutate("change track", () => UpdateTrack(a));
                case "track.remove": return Mutate("remove track", () => RemoveTrack(a));
                case "part.add": return Mutate("add part", () => AddPart(a));
                case "part.update": return Mutate("edit part", () => UpdatePart(a));
                case "part.remove": return Mutate("remove part", () => RemovePart(a));
                case "notes.list": return Ui(() => ListNotes(a));
                case "notes.add": return Mutate("add notes", () => AddNotes(a));
                case "notes.edit": return Mutate("edit notes", () => EditNotes(a));
                case "notes.lyrics": return Mutate("replace lyrics", () => ReplaceLyrics(a));
                case "notes.delete": return Mutate("delete notes", () => DeleteNotes(a));
                case "notes.expression": return Mutate("set expression", () => SetExpression(a));
                case "notes.pitch": return Mutate("set pitch points", () => SetPitch(a));
                case "curve.get": return Ui(() => GetCurve(a));
                case "curve.set": return Mutate("draw curve", () => SetCurve(a));
                case "curve.clear": return Mutate("clear curve", () => ClearCurve(a));
                case "phonemes.list": return ListPhonemes(a);
                case "phonemizers.rank": return Task.Run(() => RankPhonemizers(a)); // off the UI thread: can be slow
                case "playback.play": return Ui(() => Play(a));
                case "playback.pause": return Ui(() => { PlaybackManager.Inst.PausePlayback(); return PlayState(); });
                case "playback.stop": return Ui(() => { PlaybackManager.Inst.StopPlayback(); return PlayState(); });
                case "playback.seek": return Ui(() => { Doc.ExecuteCmd(new SeekPlayPosTickNotification(Math.Max(0, Int(a, "tick")))); return PlayState(); });
                case "export.wav": return ExportWav(a);
                case "export.midi": return Ui(() => ExportMidi(a));
                default: throw new ArgumentException($"Unknown operation '{op}'");
            }
        }

        // ---------- threading ----------

        static Task<object> Ui(Func<object> f) {
            var tcs = new TaskCompletionSource<object>(TaskCreationOptions.RunContinuationsAsynchronously);
            if (Doc.PostOnUIThread == null) {
                throw new InvalidOperationException("OpenUtau UI is not ready yet");
            }
            Doc.PostOnUIThread(() => {
                try {
                    tcs.TrySetResult(f());
                } catch (Exception e) {
                    tcs.TrySetException(e);
                }
            });
            return WithTimeout(tcs.Task, UiTimeout);
        }

        static async Task<object> WithTimeout(Task<object> task, TimeSpan timeout) {
            if (await Task.WhenAny(task, Task.Delay(timeout)) != task) {
                throw new TimeoutException($"OpenUtau UI thread did not respond within {timeout.TotalSeconds}s");
            }
            return await task;
        }

        /// <summary>Runs f on the UI thread inside one undo group; rolls back on error.</summary>
        static Task<object> Mutate(string name, Func<object> f) => Ui(() => {
            if (Doc.HasOpenUndoGroup) {
                throw new InvalidOperationException("OpenUtau is in the middle of an edit (open undo group); try again");
            }
            Doc.StartUndoGroup(name);
            object result;
            try {
                result = f();
            } catch {
                Doc.RollBackUndoGroup();
                Doc.EndUndoGroup();
                throw;
            }
            Doc.EndUndoGroup();
            return result;
        });

        // ---------- args ----------

        static bool Has(JsonObject a, string k) => a.TryGetPropertyValue(k, out var v) && v != null;
        static int Int(JsonObject a, string k) => Has(a, k) ? a[k]!.GetValue<int>() : throw new ArgumentException($"Missing '{k}'");
        static int? OptInt(JsonObject a, string k) => Has(a, k) ? a[k]!.GetValue<int>() : null;
        static double? OptNum(JsonObject a, string k) => Has(a, k) ? a[k]!.GetValue<double>() : null;
        static bool? OptBool(JsonObject a, string k) => Has(a, k) ? a[k]!.GetValue<bool>() : null;
        static string Str(JsonObject a, string k) => Has(a, k) ? a[k]!.GetValue<string>() : throw new ArgumentException($"Missing '{k}'");
        static string OptStr(JsonObject a, string k) => Has(a, k) ? a[k]!.GetValue<string>() : null;
        static List<int> Ints(JsonObject a, string k) => OptInts(a, k) ?? throw new ArgumentException($"Missing '{k}'");
        static List<int> OptInts(JsonObject a, string k) => Has(a, k) ? a[k]!.AsArray().Select(n => n!.GetValue<int>()).ToList() : null;

        static UTrack Track(int no) {
            if (no < 0 || no >= Project.tracks.Count) {
                throw new ArgumentOutOfRangeException("track", $"Track {no} does not exist (0..{Project.tracks.Count - 1})");
            }
            return Project.tracks[no];
        }

        static List<UVoicePart> VoiceParts() => Project.parts.OfType<UVoicePart>().ToList();

        static UVoicePart Part(JsonObject a) {
            int i = Int(a, "part");
            var parts = VoiceParts();
            if (i < 0 || i >= parts.Count) {
                throw new ArgumentOutOfRangeException("part", $"Voice part {i} does not exist ({parts.Count} voice parts)");
            }
            return parts[i];
        }

        static List<UNote> Notes(UVoicePart part, IEnumerable<int> indices) {
            var all = part.notes.ToList();
            return indices.Select(i => i >= 0 && i < all.Count
                ? all[i]
                : throw new ArgumentOutOfRangeException("index", $"Note {i} does not exist ({all.Count} notes)")).ToList();
        }

        // ---------- project ----------

        static object ProjectSummary() {
            Doc.FlushValidation(); // apply the edit's pending validation now, or the summary is one step stale
            var p = Project;
            var parts = VoiceParts();
            return new {
                file_path = p.FilePath,
                saved = Doc.ChangesSaved,
                key = p.key,
                resolution = p.resolution,
                end_tick = p.EndTick,
                tempos = p.tempos.Select(t => new { position = t.position, bpm = t.bpm }),
                time_signatures = p.timeSignatures.Select(t => new { bar = t.barPosition, beat_per_bar = t.beatPerBar, beat_unit = t.beatUnit }),
                tracks = p.tracks.Select(t => new {
                    track = t.TrackNo,
                    name = t.TrackName,
                    singer_id = t.Singer?.Id,
                    singer_name = t.Singer?.Name,
                    singer_found = t.Singer?.Found ?? false,
                    phonemizer = t.Phonemizer?.GetType().FullName,
                    phonemizer_tag = t.Phonemizer?.Tag,
                    renderer = t.RendererSettings?.renderer,
                    volume = t.Volume,
                    pan = t.Pan,
                    mute = t.Mute,
                    solo = t.Solo,
                    voice_colors = t.VoiceColorNames, // clr expression value = index in this list
                }),
                voice_parts = parts.Select((v, i) => new {
                    part = i,
                    name = v.name,
                    track = v.trackNo,
                    position = v.position,
                    duration = v.Duration,
                    note_count = v.notes.Count,
                }),
                wave_part_count = p.parts.Count - parts.Count,
            };
        }

        static void RequireSavedOrForce(JsonObject a) {
            if (!Doc.ChangesSaved && OptBool(a, "force") != true) {
                throw new InvalidOperationException("The open project has unsaved changes; save it first or pass force=true to discard them");
            }
        }

        static object NewProject(JsonObject a) {
            RequireSavedOrForce(a);
            Doc.ExecuteCmd(new LoadProjectNotification(Ustx.Create()));
            Doc.Recovered = false;
            return ProjectSummary();
        }

        static object OpenProject(JsonObject a) {
            RequireSavedOrForce(a);
            var path = Path.GetFullPath(Str(a, "path"));
            if (!File.Exists(path)) {
                throw new FileNotFoundException($"File not found: {path}");
            }
            Formats.LoadProject(new[] { path });
            Doc.ExecuteCmd(new VoiceColorRemappingNotification(-1, true));
            Doc.Recovered = false;
            return ProjectSummary();
        }

        static object SaveProject(JsonObject a) {
            var path = OptStr(a, "path");
            if (string.IsNullOrEmpty(path)) {
                if (string.IsNullOrEmpty(Project.FilePath)) {
                    throw new InvalidOperationException("Project has never been saved; give a path");
                }
                path = Project.FilePath;
            } else {
                path = Path.GetFullPath(path);
                if (!path.EndsWith(".ustx", StringComparison.OrdinalIgnoreCase)) {
                    throw new ArgumentException("Save path must end with .ustx");
                }
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            }
            var before = File.Exists(path) ? File.GetLastWriteTimeUtc(path) : DateTime.MinValue;
            Doc.ExecuteCmd(new SaveProjectNotification(path));
            if (!File.Exists(path) || File.GetLastWriteTimeUtc(path) == before && before != DateTime.MinValue && !Project.Saved) {
                throw new IOException($"Failed to save {path} (see OpenUtau log)");
            }
            return ProjectSummary();
        }

        static object ImportTracks(JsonObject a) {
            var path = Path.GetFullPath(Str(a, "path"));
            if (!File.Exists(path)) {
                throw new FileNotFoundException($"File not found: {path}");
            }
            bool importTempo = OptBool(a, "import_tempo") ?? Project.parts.Count == 0;
            Formats.ImportTracks(Project, new[] { path }, importTempo);
            Doc.ExecuteCmd(new VoiceColorRemappingNotification(-1, true));
            return ProjectSummary();
        }

        // ---------- tempo / time signature / key ----------

        static object SetTempo(JsonObject a) {
            double bpm = OptNum(a, "bpm") ?? throw new ArgumentException("Missing 'bpm'");
            if (bpm < 10 || bpm > 1000) throw new ArgumentOutOfRangeException("bpm", "BPM must be 10..1000");
            int tick = OptInt(a, "tick") ?? 0;
            if (tick < 0) throw new ArgumentOutOfRangeException("tick");
            if (tick == 0) {
                Doc.ExecuteCmd(new BpmCommand(Project, bpm));
            } else {
                if (Project.tempos.Any(t => t.position == tick)) {
                    Doc.ExecuteCmd(new DelTempoChangeCommand(Project, tick));
                }
                Doc.ExecuteCmd(new AddTempoChangeCommand(Project, tick, bpm));
            }
            return ProjectSummary();
        }

        static object RemoveTempo(JsonObject a) {
            int tick = Int(a, "tick");
            if (tick == 0) throw new ArgumentException("The tempo at tick 0 cannot be removed; set it instead");
            if (!Project.tempos.Any(t => t.position == tick)) throw new ArgumentException($"No tempo change at tick {tick}");
            Doc.ExecuteCmd(new DelTempoChangeCommand(Project, tick));
            return ProjectSummary();
        }

        static object SetTimeSig(JsonObject a) {
            int beatPerBar = Int(a, "beat_per_bar"), beatUnit = Int(a, "beat_unit");
            int bar = OptInt(a, "bar") ?? 0;
            if (beatPerBar < 1 || beatPerBar > 32) throw new ArgumentOutOfRangeException("beat_per_bar");
            if (!new[] { 1, 2, 4, 8, 16, 32 }.Contains(beatUnit)) throw new ArgumentOutOfRangeException("beat_unit", "beat_unit must be 1, 2, 4, 8, 16 or 32");
            if (bar < 0) throw new ArgumentOutOfRangeException("bar");
            if (bar == 0) {
                Doc.ExecuteCmd(new TimeSignatureCommand(Project, beatPerBar, beatUnit));
            } else {
                if (Project.timeSignatures.Any(t => t.barPosition == bar)) {
                    Doc.ExecuteCmd(new DelTimeSigCommand(Project, bar));
                }
                Doc.ExecuteCmd(new AddTimeSigCommand(Project, bar, beatPerBar, beatUnit));
            }
            return ProjectSummary();
        }

        static object SetKey(JsonObject a) {
            int key = Int(a, "key");
            if (key < 0 || key > 11) throw new ArgumentOutOfRangeException("key", "key must be 0 (C) .. 11 (B)");
            Doc.ExecuteCmd(new KeyCommand(Project, key));
            return ProjectSummary();
        }

        // ---------- catalog ----------

        static object ListSingers() => SingerManager.Inst.Singers.Values
            .OrderBy(s => s.Id)
            .Select(s => new {
                id = s.Id,
                name = s.Name,
                type = s.SingerType.ToString(),
                location = s.Location,
                author = s.Author,
                default_phonemizer = s.DefaultPhonemizer,
                renderers = Renderers.GetSupportedRenderers(s.SingerType),
            }).ToList();

        static object ListPhonemizers(JsonObject a) {
            var lang = OptStr(a, "language");
            return PhonemizerFactory.GetAll()
                .Where(f => string.IsNullOrEmpty(lang) || string.Equals(f.language, lang, StringComparison.OrdinalIgnoreCase))
                .Select(f => new { type = f.type.FullName, name = f.name, tag = f.tag, language = f.language, author = f.author })
                .ToList();
        }

        static object ListExpressions() => Project.expressions.Values.Select(e => new {
            abbr = e.abbr,
            name = e.name,
            type = e.type.ToString(),
            min = e.min,
            max = e.max,
            @default = e.defaultValue,
            options = e.options,
        }).ToList();

        // ---------- tracks ----------

        static USinger FindSinger(string q) {
            var singers = SingerManager.Inst.Singers;
            if (singers.TryGetValue(q, out var s)) return s;
            var match = singers.Values.FirstOrDefault(x => string.Equals(x.Id, q, StringComparison.OrdinalIgnoreCase))
                ?? singers.Values.FirstOrDefault(x => string.Equals(x.Name, q, StringComparison.OrdinalIgnoreCase))
                ?? singers.Values.FirstOrDefault(x => x.LocalizedNames != null && x.LocalizedNames.Values.Any(n => string.Equals(n, q, StringComparison.OrdinalIgnoreCase)));
            return match ?? throw new ArgumentException($"Singer '{q}' not found; use list_singers");
        }

        static PhonemizerFactory FindPhonemizer(string q) {
            var all = PhonemizerFactory.GetAll();
            return all.FirstOrDefault(f => f.type.FullName == q)
                ?? all.FirstOrDefault(f => string.Equals(f.type.Name, q, StringComparison.OrdinalIgnoreCase))
                ?? all.FirstOrDefault(f => string.Equals(f.tag, q, StringComparison.OrdinalIgnoreCase))
                ?? all.FirstOrDefault(f => string.Equals(f.name, q, StringComparison.OrdinalIgnoreCase))
                ?? throw new ArgumentException($"Phonemizer '{q}' is not installed in this OpenUtau. " + SimilarTags(q, all) +
                    "Use rank_phonemizers to find the best installed one for a singer.");
        }

        // Same-language tags first, so "EN CVVC" answers with the English phonemizers that do exist.
        static string SimilarTags(string q, PhonemizerFactory[] all) {
            var lang = q.Split(' ', '-')[0];
            var same = all.Where(f => f.tag.StartsWith(lang + " ", StringComparison.OrdinalIgnoreCase)).Select(f => f.tag).ToList();
            return same.Count > 0 ? $"Installed {lang.ToUpperInvariant()} phonemizers: {string.Join(", ", same)}. "
                                  : $"Installed tags: {string.Join(", ", all.Select(f => f.tag).Distinct())}. ";
        }

        /// <summary>
        /// Runs each candidate phonemizer on sample lyrics for a singer, the way OpenUtau's phonemizer runner does,
        /// and counts how many produced phonemes the voicebank has a sample for. Nothing in the project changes.
        /// </summary>
        static object RankPhonemizers(JsonObject a) {
            var singer = FindSinger(Str(a, "singer"));
            singer.EnsureLoaded(); // banks no track uses are not loaded yet, so every oto lookup would fail
            var words = a["words"]!.AsArray().Select(n => n!.GetValue<string>()).ToArray();
            int tone = OptInt(a, "tone") ?? 60;
            var langs = OptStr(a, "language")?.ToUpperInvariant().Split(',', StringSplitOptions.RemoveEmptyEntries);
            var candidates = PhonemizerFactory.GetAll().Where(f =>
                f.type.Namespace == "OpenUtau.Plugin.Builtin" // classic UTAU phonemizers; DiffSinger/ENUNU/etc. need their own singer types
                && (langs == null || langs.Contains(f.language?.ToUpperInvariant())));
            var groups = words.Select((w, i) => new[] { new Phonemizer.Note {
                lyric = w, tone = tone, position = i * 480, duration = 480, phonemeAttributes = new Phonemizer.PhonemeAttributes[0],
            } }).ToArray();
            var track = Project.tracks.FirstOrDefault() ?? new UTrack(Project);
            var results = new List<object>();
            foreach (var f in candidates) {
                int total = 0, found = 0;
                var missing = new List<string>();
                string error = null;
                try {
                    var p = f.Create();
                    p.SetSinger(singer);
                    p.SetTiming(Project.timeAxis);
                    p.SetUp(groups, Project, track);
                    for (int i = 0; i < groups.Length; i++) {
                        Phonemizer.Note? prev = i > 0 ? groups[i - 1][0] : null;
                        Phonemizer.Note? next = i < groups.Length - 1 ? groups[i + 1][0] : null;
                        var r = p.Process(groups[i], prev, next, prev, next, i > 0 ? groups[i - 1] : new Phonemizer.Note[0]);
                        foreach (var ph in r.phonemes ?? new Phonemizer.Phoneme[0]) {
                            if (string.IsNullOrEmpty(ph.phoneme)) continue;
                            total++;
                            if (singer.TryGetMappedOto(ph.phoneme, tone, out _)) found++;
                            else if (missing.Count < 12 && !missing.Contains(ph.phoneme)) missing.Add(ph.phoneme);
                        }
                    }
                    p.CleanUp();
                } catch (Exception e) {
                    error = $"{e.GetType().Name}: {e.Message}";
                }
                results.Add(new {
                    tag = f.tag, type = f.type.FullName, language = f.language,
                    score = total == 0 ? 0.0 : Math.Round((double)found / total, 3),
                    phonemes = total, with_sample = found, missing, error,
                });
            }
            return new {
                singer = singer.Id,
                words,
                ranking = results.OrderByDescending(r => ((dynamic)r).score).ThenByDescending(r => ((dynamic)r).phonemes).ToList(),
            };
        }

        /// <summary>Mirrors the track header: singer, then preferred/default phonemizer, then a suitable renderer.</summary>
        static void ApplyTrackSettings(UTrack track, JsonObject a) {
            var singerQ = OptStr(a, "singer");
            var phonemizerQ = OptStr(a, "phonemizer");
            var rendererQ = OptStr(a, "renderer");
            USinger singer = null;
            if (singerQ != null) {
                singer = FindSinger(singerQ);
                singer.EnsureLoaded();
                Doc.ExecuteCmd(new TrackChangeSingerCommand(Project, track, singer));
                if (phonemizerQ == null) {
                    string pref = null;
                    bool hasPref = !string.IsNullOrEmpty(singer.Id) &&
                        OpenUtau.Core.Util.Preferences.Default.SingerPhonemizers.TryGetValue(singer.Id, out pref);
                    var factory = hasPref ? PhonemizerFactory.Get(pref) : null;
                    factory ??= string.IsNullOrEmpty(singer.DefaultPhonemizer) ? null : PhonemizerFactory.Get(singer.DefaultPhonemizer);
                    if (factory != null) {
                        Doc.ExecuteCmd(new TrackChangePhonemizerCommand(Project, track, factory.Create()));
                    }
                }
                if (rendererQ == null && (!singer.Found || singer.SingerType != track.RendererSettings.Renderer?.SingerType)) {
                    var settings = singer.Found
                        ? new URenderSettings { renderer = Renderers.GetDefaultRenderer(singer.SingerType) }
                        : new URenderSettings();
                    Doc.ExecuteCmd(new TrackChangeRenderSettingCommand(Project, track, settings));
                }
            }
            if (phonemizerQ != null) {
                Doc.ExecuteCmd(new TrackChangePhonemizerCommand(Project, track, FindPhonemizer(phonemizerQ).Create()));
            }
            if (rendererQ != null) {
                var s = track.Singer;
                if (s == null || !s.Found) throw new InvalidOperationException("Set a singer before choosing a renderer");
                var supported = Renderers.GetSupportedRenderers(s.SingerType);
                var r = supported.FirstOrDefault(x => string.Equals(x, rendererQ, StringComparison.OrdinalIgnoreCase))
                    ?? throw new ArgumentException($"Renderer '{rendererQ}' not supported by this singer; supported: {string.Join(", ", supported)}");
                var settings = track.RendererSettings.Clone();
                settings.renderer = r;
                Doc.ExecuteCmd(new TrackChangeRenderSettingCommand(Project, track, settings));
            }
            var name = OptStr(a, "name");
            if (name != null) {
                Doc.ExecuteCmd(new RenameTrackCommand(Project, track, name));
            }
        }

        static object AddTrack(JsonObject a) {
            var track = new UTrack(Project) { TrackNo = Project.tracks.Count };
            Doc.ExecuteCmd(new AddTrackCommand(Project, track));
            ApplyTrackSettings(track, a);
            return new { track = track.TrackNo, summary = ProjectSummary() };
        }

        static object UpdateTrack(JsonObject a) {
            var track = Track(Int(a, "track"));
            ApplyTrackSettings(track, a);
            // Mixer values are not undoable in OpenUtau either; set them like the track header does.
            var vol = OptNum(a, "volume");
            if (vol != null) {
                track.Volume = Math.Clamp(vol.Value, -24, 12);
            }
            var pan = OptNum(a, "pan");
            if (pan != null) {
                track.Pan = Math.Clamp(pan.Value, -100, 100);
                Doc.ExecuteCmd(new PanChangeNotification(track.TrackNo, track.Pan));
            }
            var mute = OptBool(a, "mute");
            if (mute != null) track.Mute = mute.Value;
            var solo = OptBool(a, "solo");
            if (solo != null) {
                track.Solo = solo.Value;
                Doc.ExecuteCmd(new SoloTrackNotification(track.TrackNo, solo.Value));
            }
            if (vol != null || mute != null || solo != null) {
                bool anySolo = Project.SoloTrackExist;
                foreach (var t in Project.tracks) {
                    t.Muted = !t.Solo && (t.Mute || anySolo);
                    Doc.ExecuteCmd(new VolumeChangeNotification(t.TrackNo, t.Muted ? -24 : t.Volume));
                }
            }
            return ProjectSummary();
        }

        static object RemoveTrack(JsonObject a) {
            var track = Track(Int(a, "track"));
            Doc.ExecuteCmd(new RemoveTrackCommand(Project, track));
            return ProjectSummary();
        }

        // ---------- parts ----------

        static object AddPart(JsonObject a) {
            var track = Track(Int(a, "track"));
            int position = OptInt(a, "position") ?? 0;
            int duration = OptInt(a, "duration") ?? 1920 * 4;
            if (position < 0 || duration <= 0) throw new ArgumentOutOfRangeException("position/duration");
            var part = new UVoicePart {
                name = OptStr(a, "name") ?? "New Part",
                trackNo = track.TrackNo,
                position = position,
                Duration = duration,
            };
            Doc.ExecuteCmd(new AddPartCommand(Project, part));
            return new { part = VoiceParts().IndexOf(part), summary = ProjectSummary() };
        }

        static object UpdatePart(JsonObject a) {
            var part = Part(a);
            var name = OptStr(a, "name");
            if (name != null) Doc.ExecuteCmd(new RenamePartCommand(Project, part, name));
            int? pos = OptInt(a, "position"), trackNo = OptInt(a, "track");
            if (pos != null || trackNo != null) {
                if (pos < 0) throw new ArgumentOutOfRangeException("position");
                if (trackNo != null) Track(trackNo.Value);
                Doc.ExecuteCmd(new MovePartCommand(Project, part, pos ?? part.position, trackNo ?? part.trackNo));
            }
            var dur = OptInt(a, "duration");
            if (dur != null) {
                int min = part.notes.Count == 0 ? 1 : part.notes.Max(n => n.End);
                if (dur.Value < min) throw new ArgumentOutOfRangeException("duration", $"Duration must be at least {min} to keep all notes");
                Doc.ExecuteCmd(new ResizeVoicePartCommand(Project, part, dur.Value - part.Duration, false));
            }
            return new { part = VoiceParts().IndexOf(part), summary = ProjectSummary() };
        }

        static object RemovePart(JsonObject a) {
            Doc.ExecuteCmd(new RemovePartCommand(Project, Part(a)));
            return ProjectSummary();
        }

        // ---------- notes ----------

        static object NoteInfo(UNote n, int i) => new {
            index = i,
            position = n.position,
            duration = n.duration,
            tone = n.tone,
            lyric = n.lyric,
            tuning = n.tuning,
            vibrato = new {
                length = n.vibrato.length, period = n.vibrato.period, depth = n.vibrato.depth,
                @in = n.vibrato.@in, @out = n.vibrato.@out, shift = n.vibrato.shift, drift = n.vibrato.drift,
            },
            // Only values set on the note (defaults are omitted). index = phoneme index within the note.
            expressions = n.phonemeExpressions.Select(e => new { abbr = e.abbr, index = e.index, value = e.value }).ToList(),
            pitch = new { snap_first = n.pitch.snapFirst, points = n.pitch.data.Select(p => new { x = p.X, y = p.Y, shape = p.shape.ToString() }) },
        };

        // ---------- pitch points & curves ----------

        /// <summary>Replaces the pitch points of the given notes. x = ms from note start, y = tenths of a semitone.</summary>
        static object SetPitch(JsonObject a) {
            var part = Part(a);
            var pts = a["points"]!.AsArray().Select(n => {
                var o = n!.AsObject();
                var shape = OptStr(o, "shape") ?? "io";
                if (!Enum.TryParse<PitchPointShape>(shape, out var sh)) throw new ArgumentException($"Pitch shape '{shape}' must be io, i, o or l");
                return new PitchPoint((float)o["x"]!.GetValue<double>(), (float)o["y"]!.GetValue<double>(), sh);
            }).OrderBy(p => p.X).ToList();
            if (pts.Count < 2) throw new ArgumentException("Give at least 2 pitch points");
            var pitch = new UPitch { snapFirst = OptBool(a, "snap_first") ?? true };
            pts.ForEach(pitch.AddPoint);
            var notes = Notes(part, Ints(a, "indices"));
            Doc.ExecuteCmd(new SetPitchPointsCommand(part, notes, pitch));
            return new { notes = notes.Count, points = pts.Count };
        }

        static UExpressionDescriptor CurveDescriptor(UVoicePart part, string abbr) {
            if (!Track(part.trackNo).TryGetExpDescriptor(Project, abbr, out var desc)) {
                throw new ArgumentException($"Expression '{abbr}' not found; use list_expressions");
            }
            if (desc.type != UExpressionType.Curve) throw new ArgumentException($"Expression '{abbr}' is not a curve; use set_note_expression");
            return desc;
        }

        static object GetCurve(JsonObject a) {
            var part = Part(a);
            var abbr = Str(a, "abbr").ToLowerInvariant();
            var desc = CurveDescriptor(part, abbr);
            var c = part.curves.FirstOrDefault(x => x.abbr == abbr);
            return new { abbr, min = desc.min, max = desc.max, @default = desc.defaultValue,
                         points = c == null ? new List<int[]>() : c.xs.Zip(c.ys, (x, y) => new[] { x, y }).ToList() };
        }

        /// <summary>Draws straight segments through [tick, value] points (part-relative ticks), like the curve pen.</summary>
        static object SetCurve(JsonObject a) {
            var part = Part(a);
            var abbr = Str(a, "abbr").ToLowerInvariant();
            CurveDescriptor(part, abbr);
            var pts = a["points"]!.AsArray().Select(n => n!.AsArray().Select(v => (int)Math.Round(v!.GetValue<double>())).ToArray())
                .OrderBy(p => p[0]).ToList();
            if (pts.Count == 0 || pts.Any(p => p.Length != 2)) throw new ArgumentException("points must be [[tick, value], ...]");
            for (int i = 0; i < pts.Count; i++) {
                var prev = i == 0 ? pts[0] : pts[i - 1];
                Doc.ExecuteCmd(new SetCurveCommand(Project, part, abbr, pts[i][0], pts[i][1], prev[0], prev[1]));
            }
            return new { abbr, segments = Math.Max(0, pts.Count - 1) };
        }

        static object ClearCurve(JsonObject a) {
            var part = Part(a);
            var abbr = Str(a, "abbr").ToLowerInvariant();
            CurveDescriptor(part, abbr);
            Doc.ExecuteCmd(new ClearCurveCommand(part, abbr));
            return new { abbr, cleared = true };
        }

        static object ListNotes(JsonObject a) {
            var part = Part(a);
            return new {
                part = VoiceParts().IndexOf(part),
                position = part.position,
                duration = part.Duration,
                notes = part.notes.Select(NoteInfo).ToList(),
            };
        }

        static object AddNotes(JsonObject a) {
            var part = Part(a);
            var items = a["notes"]?.AsArray() ?? throw new ArgumentException("Missing 'notes'");
            var created = new List<UNote>();
            foreach (var node in items) {
                var o = node as JsonObject ?? throw new ArgumentException("Each note must be an object");
                int pos = Int(o, "position"), dur = Int(o, "duration"), tone = Int(o, "tone");
                if (pos < 0 || dur <= 0 || tone < 0 || tone > 127) {
                    throw new ArgumentOutOfRangeException("note", $"Bad note position={pos} duration={dur} tone={tone}");
                }
                var note = Project.CreateNote(tone, pos, dur);
                var lyric = OptStr(o, "lyric");
                if (lyric != null) note.lyric = lyric;
                created.Add(note);
            }
            if (created.Count == 0) throw new ArgumentException("'notes' is empty");
            int end = created.Max(n => n.End);
            if (end > part.Duration) {
                Doc.ExecuteCmd(new ResizeVoicePartCommand(Project, part, end - part.Duration, false));
            }
            Doc.ExecuteCmd(new AddNoteCommand(part, created));
            var all = part.notes.ToList();
            return new { added = created.Select(n => all.IndexOf(n)).ToList(), part_duration = part.Duration, note_count = all.Count };
        }

        static object EditNotes(JsonObject a) {
            var part = Part(a);
            var edits = a["edits"]?.AsArray() ?? throw new ArgumentException("Missing 'edits'");
            var all = part.notes.ToList();
            // Resolve every index against the original order before anything moves.
            var targets = edits.Select(e => {
                var o = e as JsonObject ?? throw new ArgumentException("Each edit must be an object");
                return (o, Notes(part, new[] { Int(o, "index") })[0]);
            }).ToList();
            foreach (var (o, note) in targets) {
                int? pos = OptInt(o, "position"), tone = OptInt(o, "tone"), dur = OptInt(o, "duration"), tuning = OptInt(o, "tuning");
                if (pos < 0 || tone < 0 || tone > 127 || dur <= 0) throw new ArgumentOutOfRangeException("edit", "Bad position/tone/duration");
                int dPos = pos != null ? pos.Value - note.position : 0;
                int dTone = tone != null ? tone.Value - note.tone : 0;
                if (dPos != 0 || dTone != 0) Doc.ExecuteCmd(new MoveNoteCommand(part, note, dPos, dTone));
                if (dur != null && dur.Value != note.duration) Doc.ExecuteCmd(new ResizeNoteCommand(part, note, dur.Value - note.duration));
                var lyric = OptStr(o, "lyric");
                if (lyric != null && lyric != note.lyric) Doc.ExecuteCmd(new ChangeNoteLyricCommand(part, note, lyric));
                if (tuning != null && tuning.Value != note.tuning) Doc.ExecuteCmd(new ChangeNoteTuningCommand(part, note, tuning.Value));
                if (o["vibrato"] is JsonObject v) {
                    void Vib(string k, Func<float, UCommand> make) {
                        var x = OptNum(v, k);
                        if (x != null) Doc.ExecuteCmd(make((float)x.Value));
                    }
                    Vib("length", x => new VibratoLengthCommand(part, note, x));
                    Vib("period", x => new VibratoPeriodCommand(part, note, x));
                    Vib("depth", x => new VibratoDepthCommand(part, note, x));
                    Vib("in", x => new VibratoFadeInCommand(part, note, x));
                    Vib("out", x => new VibratoFadeOutCommand(part, note, x));
                    Vib("shift", x => new VibratoShiftCommand(part, note, x));
                    Vib("drift", x => new VibratoDriftCommand(part, note, x));
                }
            }
            int end = part.notes.Count == 0 ? 0 : part.notes.Max(n => n.End);
            if (end > part.Duration) {
                Doc.ExecuteCmd(new ResizeVoicePartCommand(Project, part, end - part.Duration, false));
            }
            return ListNotes(a);
        }

        static object ReplaceLyrics(JsonObject a) {
            var part = Part(a);
            int start = OptInt(a, "start") ?? 0;
            var lyrics = a["lyrics"]?.AsArray().Select(n => n!.GetValue<string>()).ToArray() ?? throw new ArgumentException("Missing 'lyrics'");
            if (lyrics.Length == 0) throw new ArgumentException("'lyrics' is empty");
            var notes = Notes(part, Enumerable.Range(start, lyrics.Length));
            Doc.ExecuteCmd(new ChangeNoteLyricCommand(part, notes.ToArray(), lyrics));
            return new { changed = lyrics.Length, first = start };
        }

        static object DeleteNotes(JsonObject a) {
            var part = Part(a);
            var idx = OptInts(a, "indices");
            var notes = idx == null || idx.Count == 0 ? part.notes.ToList() : Notes(part, idx.Distinct());
            if (notes.Count > 0) Doc.ExecuteCmd(new RemoveNoteCommand(part, notes));
            return new { deleted = notes.Count, note_count = part.notes.Count };
        }

        static object SetExpression(JsonObject a) {
            var part = Part(a);
            var abbr = Str(a, "abbr").ToLowerInvariant();
            var track = Track(part.trackNo);
            if (!track.TryGetExpDescriptor(Project, abbr, out var desc)) {
                throw new ArgumentException($"Expression '{abbr}' not found; use list_expressions");
            }
            if (desc.type == UExpressionType.Curve || desc.type == UExpressionType.MaskedCurve) {
                throw new ArgumentException($"Expression '{abbr}' is a curve; only note expressions can be set");
            }
            float? value = Has(a, "value") ? (float)a["value"]!.GetValue<double>() : null;
            if (value != null) {
                float max = desc.type == UExpressionType.Options ? Math.Max(0, (desc.options?.Length ?? 1) - 1) : desc.max;
                float min = desc.type == UExpressionType.Options ? 0 : desc.min;
                if (value < min || value > max) throw new ArgumentOutOfRangeException("value", $"{abbr} must be {min}..{max}");
            }
            var idx = OptInts(a, "indices");
            var notes = idx == null || idx.Count == 0 ? part.notes.ToList() : Notes(part, idx.Distinct());
            if (notes.Count > 0) Doc.ExecuteCmd(new SetNotesSameExpressionCommand(Project, track, part, notes, abbr, value));
            return new { abbr, value, notes = notes.Count };
        }

        // ---------- phonemes ----------

        static async Task<object> ListPhonemes(JsonObject a) {
            // Phonemizing runs in the background; wait (off the UI thread) until it catches up.
            var deadline = DateTime.UtcNow.AddSeconds(OptNum(a, "wait_seconds") ?? 15);
            while (true) {
                bool ready = (bool)await Ui(() => Part(a).PhonemesUpToDate);
                if (ready || DateTime.UtcNow > deadline) break;
                await Task.Delay(200);
            }
            return await Ui(() => {
                var part = Part(a);
                var notes = part.notes.ToList();
                var index = new Dictionary<UNote, int>();
                for (int i = 0; i < notes.Count; i++) index[notes[i]] = i;
                return new {
                    up_to_date = part.PhonemesUpToDate,
                    phonemes = part.phonemes.Select(ph => new {
                        note = ph.Parent != null && index.TryGetValue(ph.Parent, out int ni) ? ni : -1,
                        lyric = ph.Parent?.lyric,
                        position = ph.position,
                        duration = ph.Duration,
                        phoneme = ph.phoneme,
                        alias = ph.phonemeMapped,
                        has_oto = ph.oto != null,
                    }).ToList(),
                };
            });
        }

        // ---------- playback ----------

        static object PlayState() => new {
            playing = PlaybackManager.Inst.PlayingMaster,
            position = Doc.playPosTick,
        };

        static object Play(JsonObject a) {
            var pm = PlaybackManager.Inst;
            if (pm.PlayingMaster) pm.StopPlayback();
            int? trackNo = OptInt(a, "track");
            if (trackNo != null) Track(trackNo.Value);
            int tick = OptInt(a, "tick") ?? -1;
            if (tick >= 0) Doc.ExecuteCmd(new SeekPlayPosTickNotification(tick));
            pm.PlayOrPause(tick: tick, endTick: OptInt(a, "end_tick") ?? -1, trackNo: trackNo ?? -1);
            return PlayState();
        }

        // ---------- export ----------

        static async Task<object> ExportWav(JsonObject a) {
            var path = Path.GetFullPath(Str(a, "path"));
            if (!path.EndsWith(".wav", StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("Path must end with .wav");
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            bool perTrack = OptBool(a, "per_track") ?? false;
            var start = DateTime.UtcNow.AddSeconds(-2);
            // Snapshot what we need on the UI thread; render off it (can take minutes).
            var (project, files) = ((UProject, List<string>))await Ui(() => {
                var p = Project;
                var f = perTrack
                    ? p.tracks.Where(t => !t.Muted).Select(t => OpenUtau.Core.PathManager.Inst.GetExportPath(path, t)).ToList()
                    : new List<string> { path };
                return (p, f);
            });
            if (perTrack) {
                await PlaybackManager.Inst.RenderToFiles(project, path);
            } else {
                await PlaybackManager.Inst.RenderMixdown(project, path);
            }
            var written = files.Where(f => File.Exists(f) && File.GetLastWriteTimeUtc(f) >= start)
                .Select(f => new { path = f, bytes = new FileInfo(f).Length }).ToList();
            if (written.Count == 0) {
                throw new IOException("Render produced no file (see OpenUtau log / error dialog)");
            }
            return new { files = written };
        }

        static object ExportMidi(JsonObject a) {
            var path = Path.GetFullPath(Str(a, "path"));
            if (!path.EndsWith(".mid", StringComparison.OrdinalIgnoreCase) && !path.EndsWith(".midi", StringComparison.OrdinalIgnoreCase)) {
                throw new ArgumentException("Path must end with .mid");
            }
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            MidiWriter.Save(path, Project);
            return new { path, bytes = new FileInfo(path).Length };
        }
    }
}

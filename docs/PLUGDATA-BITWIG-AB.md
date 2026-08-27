# PlugData macOS and Bitwig A/B record

## Decision

The current macOS workbench uses the official PlugData `0.9.4` Universal
package from GitHub Actions run
[`27418767000`](https://github.com/plugdata-team/plugdata/actions/runs/27418767000),
commit
[`98ae0f78ba43d17f4aa6d5409eca3bbf818b4e74`](https://github.com/plugdata-team/plugdata/commit/98ae0f78ba43d17f4aa6d5409eca3bbf818b4e74),
built on 2026-06-12. It is the first tested candidate in this workbench that
passes both the native discovery-menu smoke and the Bitwig editor lifecycle
smoke.

This is a bounded host-compatibility decision. It does not transfer the later
standalone physical-device acceptance to this earlier binary, and it does not
complete the remaining Bitwig patch, hardware, or contention gates.

## Why the moving nightly was rejected

The A side was the official `0.9.4` nightly installed on 2026-08-27, commit
`6dad7af1`. Its preserved installer and installed binaries were identified by:

| Artifact | SHA-256 |
| --- | --- |
| macOS Universal package | `e6ebdd1ef0b600a558b8e7801aa12900c84f45b6f0d8f9546aa601cc865b023a` |
| standalone executable | `1fa223de1b3b0c08f54d364f55a952d1dc8d758cb2cc812511c0a760849e694f` |
| CLAP executable | `227e24a0f3068c0ea22cd7cedb938c13617fb139a3c0ba4939b57b5a7735803d` |
| VST3 executable | `0283a994882ac3e24847f4b143f3d730af5f7f6c4ebb6a33d77f9888085db41e` |

Closing the PlugData CLAP editor in Bitwig repeatedly aborted its isolated
plug-in host. The reports show `EXC_CRASH (SIGABRT)`, `__cxa_pure_virtual`, and
`juce::MessageQueue::deliverNextMessage()` on the main thread. The same reports
identify a `JUCE v9.0.1` timer thread. Bitwig itself survived because the
plug-in was hosted in a separate process.

This evidence rejects that exact moving-nightly build for the Bitwig lane. It
does not establish that every build after June fails or identify the upstream
source commit that introduced the defect.

## Candidate custody

The B package was downloaded directly from the official PlugData Actions run,
then verified before installation:

- package SHA-256:
  `99a6471ed187d68d7c9fc6f704216d52cb638567891ed58320fac41b21fb159f`;
- signed by Developer ID Installer Timothy Schoen (`7SV7JPRR2L`);
- standalone, CLAP, and VST3 bundles pass strict deep code-signing checks;
- every executable contains native `arm64` and `x86_64` slices; and
- the package reports PlugData `0.9.4`.

The fully installed files were then matched to the expanded signed package:

| Artifact | SHA-256 |
| --- | --- |
| standalone executable | `86179a37e58e7a0f0436fc555f56ce41892e3f32ed19b4a3ba8f1cfe3c17476e` |
| CLAP executable | `2cae8ed877ea5da09fcd4dd50ddae486d8f17462b4311f6cd970343e0c62f715` |
| VST3 executable | `b6d91aa0314934d9e583bba91a41e299b393c9fa647473bd9e6a796e0fbf0019` |
| shared `plugdata-resources.bin` | `cfde68a35cc22fadf9c04879177c6fc7ae7832b16988a2b5eeff7a0ebb99f7ce` |

The installer copies that exact shared resource into the standalone app and
each plug-in. Running only the extracted app beside another installation is
not a valid A/B: the extracted app lacks the installed shared resource and
failed in `Fonts::getDefaultFont()` before loading any patch. Only the complete
signed package was accepted as a candidate.

## Acceptance performed on 2026-08-27

Host:

- Apple-silicon Mac;
- macOS `26.4.1` (`25E253`); and
- Bitwig Studio `6.1`, revision
  `94a90411037fa337883222813b7372a3ace9dbd7`.

Standalone discovery-menu smoke:

1. A fake SerialOSC server advertised `m100` and `m200` on isolated loopback
   port `12012`.
2. `monome-discovery-smoke.pd` populated the native `else/popmenu` with both
   devices.
3. The automated patch selected index `1`, returned to index `0`, and emitted
   snapshots for both stable IDs.
4. PlugData quit normally and produced no new crash report.

Bitwig CLAP editor lifecycle:

1. Bitwig loaded
   `/Library/Audio/Plug-Ins/CLAP/plugdata.clap/Contents/MacOS/plugdata` in an
   isolated host; the loaded path was verified from the live process.
2. The floating PlugData editor opened and rendered normally.
3. Five close/reopen cycles retained the same plug-in-host PID.
4. No new `BitwigPluginHost` crash report appeared.

Bitwig VST3 editor lifecycle:

1. Bitwig's format view was temporarily changed from `Preferred Formats` to
   `All plug-ins` because its normal `Prefer CLAP over VST` rule correctly
   hides the redundant VST3 entry.
2. Bitwig loaded
   `/Library/Audio/Plug-Ins/VST3/plugdata.vst3/Contents/MacOS/plugdata`; the
   loaded path was verified from the live process.
3. Three close/reopen cycles retained the same plug-in-host PID.
4. No new `BitwigPluginHost` crash report appeared.
5. `Preferred Formats` with `Prefer CLAP over VST` was restored.

Final cleanup was explicit: the disposable Bitwig project was closed without
saving, Bitwig and both plug-in hosts exited, the fake server stopped, and an
independent live SerialOSC readback found the zero Grid, legacy 128, and Arc
all released at destination port `0`.

## Remaining gates

This pass accepts only startup, native-menu behavior, and editor-window
lifecycle for the pinned candidate. The following remain open:

- load the Monome session patch inside Bitwig CLAP;
- transport-stopped behavior and bypass;
- project save/reload and an intentional plug-in-process restart;
- one-device, pair, and three-device hardware runs in Bitwig; and
- verified displacement and release between standalone PlugData and Bitwig.

Do not describe the project as Bitwig-accepted until those gates pass.

# PlugData macOS and Bitwig A/B record

## Decision

The current macOS workbench uses the official PlugData `0.9.4` Universal
package from GitHub Actions run
[`27418767000`](https://github.com/plugdata-team/plugdata/actions/runs/27418767000),
commit
[`98ae0f78ba43d17f4aa6d5409eca3bbf818b4e74`](https://github.com/plugdata-team/plugdata/commit/98ae0f78ba43d17f4aa6d5409eca3bbf818b4e74),
built on 2026-06-12. It is the first tested candidate in this workbench that
passes both the native discovery-menu smoke and the Bitwig editor lifecycle
smoke. It subsequently completed the bounded Bitwig Monome hardware and
standalone-contention run recorded below.

This is a bounded host-compatibility decision. The hardware run is direct
evidence for this candidate rather than an inference from the later standalone
nightly. One lifecycle gate still fails: fully deactivating the Bitwig device
terminates the isolated plug-in host without releasing its SerialOSC
destination. Ordinary bypass is accepted; intentional plug-in-process restart
is not.

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

## Bitwig Monome hardware run on 2026-08-27

The pinned CLAP loaded `monome-grid-live.pd` and `monome-arc-live.pd` in one
Bitwig project. Device identity and callback routing were:

| Device | Stable ID | Bitwig route |
| --- | --- | --- |
| legacy 128 Grid | `m1000853` | Grid slot A, callback `17780` |
| zero Grid | `m23215901` | Grid slot B, callback `17781` |
| four-ring Arc | `m1001113` | Arc session, callback `17782` |

The following behavior passed with physical output/input observation plus
independent `/sys/info` destination readback:

1. The legacy 128 completed explicit selection, non-mutating probe, verified
   claim, distinguishable LED output, and key press/release while Bitwig's
   transport was stopped.
2. Ordinary Bitwig bypass retained the same isolated plug-in-host process and
   the Grid remained responsive to hardware input and output after bypass was
   removed.
3. Project save/reload failed closed rather than declaring a remembered device
   connected. A fresh selection, probe, and claim restored the route, followed
   by fresh physical output and input.
4. The legacy and zero Grids held simultaneous verified callbacks `17780` and
   `17781`, displayed different level patterns, and independently reported key
   press/release coordinates.
5. Both Grids and the Arc then held all three callbacks simultaneously. All
   four Arc rings had distinct position markers; Grid key events and Arc
   encoder deltas remained isolated to their own capability routes.
6. Arc, legacy, and zero were actively unplugged and reconnected one at a time.
   Each removal detached only that device. Both survivors kept their visible
   state and exact callback destination. Each returning device kept its stable
   ID and SerialOSC's prior self callback; recovery required a fresh exact
   probe, guarded release to port `0`, explicit reclaim, restored output, and
   fresh physical input.
7. The final standalone-versus-Bitwig displacement test used
   `monome-grid-contender-live.pd` on isolated discovery/session/control ports
   `18779`, `18780`, and `18900`. The standalone patch claimed the legacy Grid,
   displayed a new pattern, and received `key 8 3 1/0`.
8. Bitwig's next ownership check reported `displaced destination_changed`,
   detached the Grid, and read back the rival `127.0.0.1:18780` destination.
   A Bitwig LED command failed with `grid_not_attached`; its release path
   reported `darken_skipped grid_not_attached` and `release_skipped`. Direct
   readback remained on `18780` throughout, so Bitwig never overwrote the
   standalone owner.
9. The standalone owner darkened and released the legacy Grid to port `0`.
   After the standalone patch and all three isolated sockets closed, Bitwig
   freshly selected, probed the free device, reclaimed `17780`, restored its
   original pattern, and received `key 0 0 1/0`.
10. Cleanup checked ownership, darkened, and released legacy, zero, then Arc.
    Final direct readback reported destination port `0` for all three devices,
    and both Grids plus all four Arc rings were physically confirmed dark.

## Known failing lifecycle gate

Fully deactivating the Bitwig device terminated the isolated PlugData host.
SerialOSC retained the legacy Grid's `17780` destination and the Grid retained
its LEDs because the dead process could not run `prepare_release`. This is a
real stale-claim lifecycle failure, not a successful restart. Guarded manual
recovery through exact readback, release to port `0`, and explicit reclaim
worked, but it does not make unexpected or intentional process death safe.

The accepted ordinary bypass and editor close/reopen paths do not terminate
the plug-in host and must not be conflated with this failure.

## Current boundary

The pinned candidate is accepted for the Monome patch in Bitwig across stopped
transport, ordinary bypass, save/reload, one device, two Grids, all three
devices, active hot-swap in every direction, and deliberate displacement by
standalone PlugData. The project is not yet accepted for full Bitwig device
deactivation or plug-in-process restart. Packaging must not claim crash-safe
or restart-safe SerialOSC cleanup until that lifecycle gap is closed.

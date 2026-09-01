# PlugData macOS and Steam Deck Bitwig A/B record

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
nightly. Under stable pre-lease SerialOSC, fully deactivating the Bitwig device
terminated the isolated plug-in host without releasing its destination. The
opt-in lease candidate subsequently closed that exact process-death gate on
2026-08-31; ordinary bypass and intentional plug-in-process restart are both
accepted within the pinned macOS lane described below.

The same source revision is also the bounded Steam Deck x64 host/runtime
reference after the 2026-09-01 Linux A/B below. That Linux result does not make
the build user-ready: the real Grid and Arc paths work through the machine
control inlet, but visible `else/popmenu` selections do not reach the session
layer.

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

## Historical pre-lease lifecycle failure

Fully deactivating the Bitwig device terminated the isolated PlugData host.
SerialOSC retained the legacy Grid's `17780` destination and the Grid retained
its LEDs because the dead process could not run `prepare_release`. This is a
real stale-claim lifecycle failure, not a successful restart. Guarded manual
recovery through exact readback, release to port `0`, and explicit reclaim
worked, but it does not make unexpected or intentional process death safe.

The accepted ordinary bypass and editor close/reopen paths did not terminate
the plug-in host and must not be conflated with this historical failure.

## Lease-candidate process-death acceptance on 2026-08-31

The same pinned PlugData CLAP executable was loaded from
`/Library/Audio/Plug-Ins/CLAP/plugdata.clap/Contents/MacOS/plugdata` against
SerialOSC lease candidate `7187832`. Bitwig placed both live workbench patches
in isolated plug-in host PID `77986`. Opening the patches did not claim any
device. Non-mutating probes established the actual menu projection before use:
index `0` was legacy 128, index `1` was Arc, and index `2` was zero.

Explicit selection, probe, and claim produced these simultaneous routes:

| Device | Callback |
| --- | --- |
| legacy 128 `m1000853` | `17780` |
| zero `m23215901` | `17781` |
| Arc `m1001113` | `17782` |

Independent readback after more than one six-second TTL proved all three
leases were renewing. The legacy Grid displayed a dim surface with a bright
bottom-right position, the zero displayed a brighter surface with a bright
top-left position, and all four Arc rings displayed distinct bright markers.
The operator physically confirmed that exact layout. Legacy top-left input
reached only Grid slot A.

Bitwig's full device `Active` control then terminated PID `77986`; the process
ran no darkening or release path. The candidate daemon recorded three
`lease expired` events rather than releases. Independent readback found legacy,
zero, and Arc free at `127.0.0.1:0`, and the operator confirmed both Grids and
all four Arc rings went completely dark by themselves.

Reactivation created fresh isolated host PID `13845`. Both patches restored,
but every selection remained empty and all devices remained free: restart was
fail-closed. After fresh explicit selection, probe, and claim, all three leases
again renewed beyond the TTL. Successful heartbeat acknowledgements emitted no
console status, so the console remained unchanged across the renewal window;
state changes and failures remain visible. Zero bottom-right input reached only
slot B as `key 15 15 1/0`, and clockwise motion on Arc ring `1` produced only
positive ring-`1` deltas. Final orderly releases returned all three devices to
free port `0`.

## Current boundary

The pinned PlugData candidate plus SerialOSC lease candidate `7187832` is
accepted on this Mac across stopped transport, ordinary bypass, save/reload,
one device, two Grids, all three devices, active hot-swap in every direction,
standalone displacement, full Bitwig device deactivation, daemon expiry, and
fail-closed plug-in-host restart. This evidence does not transfer to arbitrary
PlugData or SerialOSC builds, and it does not satisfy any Steam Deck lease
gate. Cross-platform packaging remains blocked on the Steam Deck run.

## Steam Deck Linux A/B benchmark on 2026-09-01

### Scope and custody

This was an isolated compatibility benchmark before the full Steam Deck
SerialOSC/Bitwig acceptance gate. SteamOS stayed read-only. The host was an
x86_64 Steam Deck in Desktop Mode running Bitwig Studio `6.0.11` from Flatpak:

- Bitwig app commit
  `7b66aed37386ffff99e40bbd486f90ceee7ac1d5c59508c7952094122cebf50e`;
- runtime `org.freedesktop.Platform/x86_64/25.08`.

The rejected A side was the then-current official Debian x64 PlugData `0.9.4`
nightly from Actions run `33424892153`, source commit
`1c83c0c08c5a3d8d33f27b632e9772726ef56098`. Its installed CLAP and resource
hashes were:

| Artifact | SHA-256 |
| --- | --- |
| CLAP | `5fd30fc64eeea1c5b2ea9cf37b73975600a3a6da67daed4e46b32ab913b3362b` |
| `plugdata-resources.bin` | `4781125eb3d421adb35e906e404e78a3e29283dbc496387ce4fa3acf31facce6` |

The two Bitwig browser entries were duplicate copies of those same bytes, not
two builds. Each exact path loaded and then aborted its isolated plug-in host
with `pure virtual method called`, `terminate called without an active
exception`, and exit code `134`. Bitwig itself restarted the isolated host.

The B side was the official Debian x64 artifact from successful Actions run
[`27418767000`](https://github.com/plugdata-team/plugdata/actions/runs/27418767000),
source commit `98ae0f78ba43d17f4aa6d5409eca3bbf818b4e74`. It was downloaded and
expanded beside the installed build without replacing it:

- archive SHA-256:
  `963b078e52ad5a181fc46c3edefc574f19f3ffb02fd6c21c3dd331ab0f77abf2`;
- CLAP SHA-256:
  `ac564454f57f5944549ab5c37035dccd1acf9f8339d4b0c13be42a99beddfa15`;
- resource SHA-256:
  `ea250c71886d61a96aad2189b8227b6dd98bddd897f3270d5384b66104cc32c2`;
- staged CLAP:
  `/home/deck/Plug-ins/plugdata-ab/98ae0f78/plugdata/CLAP/plugdata.clap`.

Host and Flatpak dependency checks found no missing libraries before launch.

### Bounded stability and hardware result

Bitwig loaded the exact staged CLAP into isolated host PID `484843`; the module
path was verified from the live process. Instance creation printed one JUCE
assertion at `clap-juce-wrapper.cpp:1801`, which remains a warning, but it did
not terminate the host. The same PID survived five editor close/reopen cycles,
both live patch loads, and the complete bounded device run. No `pure virtual`,
plug-in-crash, abort, host-death, or exit-code-134 marker appeared in the
preserved B-side logs.

`monome-grid-live.pd` and `monome-arc-live.pd` opened in that one host. It alone
owned all seven expected local sockets: `17778`, `17779`, `17780`, `17781`,
`17782`, `17900`, and `17901`. Opening the patches did not claim hardware;
independent readback found all three devices free at destination port `0`.

All three graphical device menus exposed a Linux-specific acceptance blocker:

1. Arc `m1001113` was the second item, legacy Grid `m1000853` the first, and
   zero Grid `m2321590` the third.
2. Selecting each visible entry changed its menu label.
3. The Arc session reported `error no_device_selected`; Grid probe/claim
   attempts likewise left both routes independently verified free at port `0`.
4. Sending the same exact zero-based indexes through the patches' loopback-only
   machine control inlet (`select 1`, `a_select 0`, and `b_select 2`) made probe
   and claim work immediately.

This is not a SerialOSC or lease failure. It is a gap at the graphical
`else/popmenu`-to-session selection boundary on this exact Linux build.

With that boundary explicitly bypassed, every single-device lane passed:

| Device | Verified callback | Physical output | Exact input | Cleanup |
| --- | --- | --- | --- | --- |
| Arc `m1001113` | `17782` | all four rings level `4`; bright ring `0` position `0` and ring `3` position `63` | `arc_delta 0 1` | all four rings dark; port `0` |
| legacy Grid `m1000853` | `17780` | full 16-by-8 surface level `4`; bright `(15,7)` | `a_key 0 0 1/0` | full surface dark; port `0` |
| zero Grid `m2321590` | `17781` | full 16-by-16 surface level `6`; bright `(0,0)` | `b_key 15 15 1/0` | full surface dark; port `0` |

Each lease was independently observed renewing beyond its initial six-second
TTL. The two non-target devices stayed free and dark in every lane. After the
final release, all three devices independently reported destination port `0`,
the operator confirmed every surface dark, Bitwig remained alive, and the same
plug-in host still owned all seven patch sockets.

The preserved successful-run logs are:

| File | SHA-256 |
| --- | --- |
| `/home/deck/.local/state/serialosc-acceptance/2026-09-01-bitwig-98ae0f78-benchmark/engine.log` | `91fd1d43968688524e989f6f4810b05314bd4ec2466726e84e19d551fb7f00b3` |
| `/home/deck/.local/state/serialosc-acceptance/2026-09-01-bitwig-98ae0f78-benchmark/BitwigStudio.log` | `f36f81f8c6e46ddf00f797bc96a3e620eb1ba261fa8d07188361c217ff235339` |

### Linux eligibility decision

The pinned `98ae0f78` Debian x64 build is accepted as the stable Linux
host/runtime reference for continued workbench and transport investigation. It
is **not** accepted as a user-facing Steam Deck PlugData build because every
graphical device selection required a test-only terminal injection. The moving
`1c83c0c0` build is rejected for this lane because it aborts the isolated
plug-in host.

This benchmark did not run simultaneous three-device claims, bypass,
save/reload, hot-unplug, full Bitwig device deactivation, or plug-in-host death.
Those remain separate gates. Resolve or replace the graphical selection
boundary first; then run the full Steam Deck SerialOSC/Bitwig matrix without
using the terminal selection bypass.

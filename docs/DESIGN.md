# PlugData Monome Device Layer

## Product boundary

This is a PlugData-first project. Vanilla Pure Data compatibility is explicitly
out of scope.

PlugData patches provide OSC transport and visible UI. Pd-Lua is the preferred
tool for stateful logic such as device registries and LED framebuffers because
it is bundled with PlugData and works in its standalone and plugin builds.
Native third-party externals are not part of the design.

The stable device ID reported by SerialOSC is identity. Discovery order, USB
path, device-server port, and menu index are not identity.

## Non-negotiable behavior

- Discovery never claims a device.
- A device is claimed only after explicit user selection and `claim`.
- No device is silently replaced because another device was added or removed.
- Connection truth comes from SerialOSC readback, not a button or menu label.
- Legacy SerialOSC has one last-writer application destination per device.
  Lease-capable SerialOSC adds cooperative callback ownership and expiry, not
  authentication or a hardware ACL. The UI therefore says **claimed** or
  **displaced**, never **locked**.
- Every internal Pd send/receive is instance-scoped; global names are forbidden.
- Grid and Arc capabilities have separate output paths.
- Demos consume the public device API and never manage SerialOSC themselves.

## Architecture

```text
SerialOSC discovery :12002
          |
    monome.discovery
          |
    monome-registry ------> PlugData popmenu + status
          |
     explicit select
          |
     monome.session
       /        \
monome.grid   monome.arc
       \        /
      applications and demos
```

### `monome.discovery`

Owns the discovery callback, sends `/serialosc/list` and
`/serialosc/notify`, re-arms the one-shot notification after every add/remove,
and forwards records to the registry. It does not send `/sys/host`,
`/sys/port`, or `/sys/prefix`.

Because `/serialosc/list` has no end marker, a rescan is a bounded collection
window: `scan_begin`, zero or more device replies, then `scan_end`. Only
`scan_end` may sweep records that were not seen.

### `monome-registry`

Maintains deterministic records keyed by serial ID. It preserves selection by
ID across scan order changes and emits menu projection data. It does not open
ports, infer ownership, or communicate with hardware.

### `monome.session`

Implements one selected device lifecycle:

```text
absent -> available -> probing -> available
             |
             +------> claiming -> connected
                                   |       |
                    check mismatch|       |verified release
                                   v       v
                              displaced  available
                                   |
                          release intent -> available
```

It supports an accepted legacy policy and an opt-in lease policy. Both probe
before claiming and require exact readback. Lease mode fails closed when the
daemon extension is absent, renews a verified token, requires explicit
takeover of a legacy destination, and independently verifies free state after
release. Legacy mode retains verified `/sys/port 0` release. Grid and Arc
capability owners still darken their valid surfaces before requesting release;
daemon expiry supplies the crash path when client cleanup cannot run.

### `monome.grid`

Normalizes key events and `/sys/size`. LED state is buffered as a maximum
16-by-16 surface and dirty 8-by-8 level maps are flushed at a bounded frame
rate. A 128 and a 256 use the same API.

### `monome.arc`

Normalizes encoder delta/key events and owns one 64-level framebuffer per
ring. Dirty rings are emitted with `/ring/map` at a bounded frame rate.

## Public message contract

The final `monome-device` abstraction will accept:

```text
rescan
select <serial-id>
deselect
probe
claim
check
release
prefix <osc-prefix>
rotation <0|90|180|270>
```

It will produce three streams:

1. normalized Grid or Arc input events;
2. status and lifecycle events;
3. selected-device metadata.

The status projection must show state, serial ID, model, capability, device
server port, local callback port, prefix, dimensions/ring count, last event,
and any displacement reason.

## Stepped delivery

### Step 0 — Workbench and state core

- Use a supported native SerialOSC on the development Mac.
- Quarantine the inherited first-device patches.
- Implement and unit-test the identity-based registry.

Acceptance: registry tests pass; no code in this step sends a claim.

### Step 1 — Discovery tracer bullet

- Build a configurable fake SerialOSC discovery server.
- Bind a real callback port and surface bind failure.
- Populate a PlugData `popmenu` from registry projection events.
- Re-arm notifications and preserve selection through add/remove/rescan.

Acceptance: simulated two-device discovery, reordering, duplicate replies,
unrelated removal, selected removal, and callback collision all have explicit
deterministic results.

Status on 2026-08-25: complete on the accepted official PlugData 0.9.4 nightly
at commit `6bb2b60c8`. Discovery transport, notification re-arm, registry
behavior, selected removal, hot-add, callback collision, and dynamic
`else/popmenu` population/output pass. Stable 0.9.3 retains a known menu
failure and is not the current workbench basis. Real SerialOSC's full
add/remove tuples are represented by the fake server and normalized before
registry mutation. See `docs/DISCOVERY-WORKBENCH.md`.

### Step 2 — Explicit session lifecycle

- Probe with `/sys/info` without claiming.
- Implement `claim`, verified readback, displacement detection, and release.
- Prevent two sessions in one PlugData process from claiming the same serial.

Acceptance: a second app can displace the first, and the first reports
`displaced` rather than claiming it remains connected.

Status through 2026-08-27: complete against isolated fake device servers and the
accepted PlugData nightly standalone. Non-mutating probe, verified claim,
periodic readback, simulated external displacement, release refusal after
displacement, verified `/sys/port 0` release, callback collision, and
process-local duplicate claim refusal pass. The same probe, exact claim
readback, and verified release also pass on a physical legacy 128, modern
16-by-16 zero Grid, and four-ring Arc. The three devices then passed
simultaneous standalone session acceptance, active removal/recovery in every
direction, and independent release. The same session boundary later passed in
Bitwig for one device, both Grids, all three devices, active hot-swap, and
deliberate standalone displacement: Bitwig detected the rival callback,
detached capability output, and refused unsafe release. Full plug-in-process
death remains a separate host lifecycle gap. See `docs/SESSION-WORKBENCH.md`.

### Step 3 — Grid capability

- Normalize key input and dynamic dimensions.
- Add a level framebuffer and bounded map flushing.
- Validate legacy 128 and modern 256 hardware.

Status on 2026-08-25: the Grid core, Pd-Lua bridge, session composition, fake
device framebuffer, and 128/256/dual smoke patches are implemented. Unit and
loopback acceptance cover dynamic 16-by-8 and 16-by-16 surfaces, 0-15 levels,
dirty 8-by-8 map batching, duplicate-key suppression, synthetic held-key
release, capability routing only through a verified session, and
dark-before-release ordering.

The physical legacy 128 passed discovery, explicit selection, 16-by-8
`/sys/info`, verified claim, full-surface and corner brightness, corner key
press/release, all-dark cleanup, verified `/sys/port 0` release, hot-remove,
hot-add, released-state probe, re-claim, and claimed hot-unplug cleanup. The
apparent CalDigit continuity failure was a reproducible upstream SerialOSC
null-port crash after release; the project now carries a narrow source patch
and pinned Apple-silicon service installer. The installed production service
also passed claimed unplug with a physically held key and emitted the required
synthetic release before detach.

The physical modern zero Grid then passed discovery, explicit selection,
16-by-16 `/sys/info`, verified claim, full-surface and opposite-corner
brightness, top-left key press/release, all-dark cleanup, verified release,
released-port readback, held-key claimed unplug with synthetic release,
same-ID hot-add, re-probe, re-claim, bottom-right output, and final orderly
release. This completes Step 3's single-Grid physical acceptance. Grid-pair
removal tests remain part of Step 5. See `docs/GRID-WORKBENCH.md`.

### Step 4 — Arc capability

- Normalize encoder delta/key input.
- Add bounded ring-map flushing and reliable all-dark cleanup.
- Validate the four-ring Arc.

Status on 2026-08-26: the Arc core, Pd-Lua bridge, verified-session
composition, fake device server, automated smoke patch, and dedicated live
workbench are implemented. Unit and loopback acceptance cover explicit two- or
four-ring attachment, 64-position level maps, dirty-ring batching, bounds
validation, delta and optional key normalization, duplicate-key suppression,
synthetic held-key release, stale-buffer clearing, and four all-dark maps
before verified `/sys/port 0` release. The accepted PlugData nightly completed
the fake four-ring lifecycle and input-routing pass with independent all-dark
and port-`0` simulator readback. The physical four-ring Arc then passed stable
identity and zero-by-zero `/sys/info`, explicit claim, all-ring and isolated
position output, signed encoder input, orderly dark/release, released
reconnect, and active-claim hot-unplug recovery. The active reconnect exposed
a retained self callback; the repaired session requires a fresh exact probe
and a second ownership readback before clearing it to port `0`, while a rival
destination remains untouched.

### Step 5 — Host and hot-swap acceptance

- Run the same patch in PlugData standalone and Bitwig CLAP.
- Test UI close/reopen, transport stopped, bypass, save/reload, and plugin
  process restart.
- Test one device, pairs, all three devices, removal in each direction, and
  contention between standalone and Bitwig.

Status on 2026-08-27: the physical legacy 128 and zero Grid passed the Grid-pair
slice in PlugData standalone. Both devices held simultaneous verified claims
on separate callback ports, routed distinct LED and key traffic, survived
removal of the other device, restored the removed stable identity in both
directions, and released independently to port `0`. Both Grids and the Arc then
passed the all-three standalone slice: distinct claims and input/output routes,
fresh ownership checks, active removal and same-ID recovery of each device,
unchanged verified survivors in every direction, and independent dark release
to port `0`. See `docs/THREE-DEVICE-ACCEPTANCE.md`.

The pinned PlugData candidate at commit `98ae0f78` then passed the bounded
Bitwig 6.1 hardware lane: stopped transport, ordinary bypass with a stable host
process, fail-closed save/reload followed by explicit reclaim, one device,
both Grids, all three devices, active removal/recovery of each device with
unchanged survivors, and deliberate displacement by an isolated standalone
patch. The displaced Bitwig session detached output and skipped release rather
than overwrite the standalone owner. After standalone released to port `0`,
Bitwig freshly probed, reclaimed, restored output, and received input. Final
cleanup left all three devices dark at port `0`.

The pre-lease Step 5 run failed full Bitwig device deactivation because the
isolated host died before it could darken or release. On 2026-08-31, lease
candidate `7187832` closed that macOS gate: the daemon expired all three
abandoned leases, auto-darkened every surface, returned every destination to
port `0`, and a fresh host started fail-closed before explicit reclaim. See
`docs/PLUGDATA-BITWIG-AB.md`.

### Step 5A — Preserve the pre-lease workbench

- Emit the complete committed source, tests, physical workbench, and evidence
  as a checksum-addressed development bundle.
- Keep the failed process-death gate explicit in that bundle.
- Do not call the development bundle an end-user PlugData package.

Status on 2026-08-27: implemented by
`tools/build_workbench_bundle.sh`. See `docs/WORKBENCH-BUNDLE.md` and
`docs/PROJECT-MAP.md`.

### Step 5B — Opt-in SerialOSC lease

- Specify lease claim, renewal, expiry, release, displacement, and readback in
  the fake-server contract first.
- Implement the protocol in a dedicated upstream-oriented SerialOSC fork
  without changing legacy `/sys/port` behavior.
- Align `monome.session` with the opt-in lease.
- Repeat deterministic, macOS Bitwig, and Steam Deck physical acceptance,
  including actual client-process death.

Acceptance: a terminated PlugData host causes SerialOSC itself to darken the
device and clear the expired runtime destination, while legacy clients retain
their existing behavior. See `docs/PROJECT-MAP.md`.

### Step 6 — Demos and end-user package

- Grid demo: dynamic 128/256 layout with momentary and latch modes.
- Arc demo: encoder-following animation with bounded refresh.
- Add help patches, release metadata, installation documentation, and a
  user-facing archive that matches the accepted PlugData distribution format.

End-user packaging starts only after Step 5B is accepted on macOS and
SteamOS. The macOS full-device-deactivation gate now passes. SteamOS has passed
bounded single-device standalone slices for the legacy 128, Zero/256, and
four-ring Arc, including hotplug and host death, but its simultaneous matrix,
Bitwig, and remaining lifecycle lanes still block packaging. The Step 5A
development bundle does not soften or bypass those remaining gates.

## Current workbench boundary

As of 2026-08-27, this Mac uses the pinned official SerialOSC source at
`ff53885` with the project's two null-port guards, built as native arm64 and
run as a user LaunchAgent. Homebrew supplies the native libraries but its stock
SerialOSC job remains stopped. The older 1.4.1 Intel launch job is preserved
but disabled. Service verification and physical Grid results remain separate
acceptance layers.

The physical standalone record was produced with the official 0.9.4 nightly
from run `32892289806`, commit `6bb2b60c8`. The currently installed host
candidate is the official 0.9.4 package from run `27418767000`, commit
`98ae0f78`; it passes the standalone dynamic-menu smoke, the bounded Bitwig
CLAP/VST3 editor-lifecycle preflight, the Bitwig Monome hardware/contention
surface listed in Step 5, and full host-death/restart acceptance against
SerialOSC lease candidate `7187832`. Bounded Steam Deck single-device slices
for the legacy 128, Zero/256, and four-ring Arc now pass against the exact
x86-64 candidate, including hotplug and host death, while the simultaneous,
Bitwig, and remaining lifecycle matrix stays open. See
`docs/PLUGDATA-MACOS.md`,
`docs/PLUGDATA-BITWIG-AB.md`, and
`docs/STEAMOS-LEASE-CANDIDATE.md`.

Fake-server acceptance remains the deterministic regression layer. It exposes
the same `/sys/info`, `/sys/host`, `/sys/port`, `/sys/prefix`,
`/sys/rotation`, Grid key, and Grid level-map surfaces without opening USB
hardware or touching live SerialOSC port `12002`.

## Deferred decisions

- Repository license.
- Final PlugData archive/store metadata after inspecting the schema used by
  the release version of PlugData.
- Whether the legacy patches remain in release archives after the new Grid and
  Arc demos replace their educational value.

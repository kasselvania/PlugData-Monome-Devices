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
- SerialOSC has one outgoing application destination per device but no atomic
  lock. The UI therefore says **claimed** or **displaced**, never **locked**.
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

It probes `/sys/info` before claiming, changes host/port/prefix only during an
explicit claim, verifies readback, detects displacement, and releases only if
it is still the current destination. A verified release sends `/sys/port 0`;
it does not delete SerialOSC preferences. Grid and Arc capability owners must
darken their valid surfaces before requesting release rather than making the
generic session layer guess an LED protocol.

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

Status on 2026-08-25: discovery transport, notification re-arm, registry
behavior, selected removal, hot-add, and callback collision pass. The stable
PlugData `else/popmenu` remains empty under both registry-driven and direct
`clear`/`add`/`set` probes, so Step 1 is not complete. A direct-selection
fallback exists only to continue testing discovery state without hiding this
gap. See `docs/DISCOVERY-WORKBENCH.md`.

### Step 2 — Explicit session lifecycle

- Probe with `/sys/info` without claiming.
- Implement `claim`, verified readback, displacement detection, and release.
- Prevent two sessions in one PlugData process from claiming the same serial.

Acceptance: a second app can displace the first, and the first reports
`displaced` rather than claiming it remains connected.

Status on 2026-08-25: complete against isolated fake device servers and the
stable PlugData standalone. Non-mutating probe, verified claim, periodic
readback, simulated external displacement, release refusal after displacement,
verified `/sys/port 0` release, callback collision, and process-local duplicate
claim refusal pass. This is not physical Grid/Arc or Bitwig acceptance. See
`docs/SESSION-WORKBENCH.md`.

### Step 3 — Grid capability

- Normalize key input and dynamic dimensions.
- Add a level framebuffer and bounded map flushing.
- Validate legacy 128 and modern 256 hardware.

### Step 4 — Arc capability

- Normalize encoder delta/key input.
- Add bounded ring-map flushing and reliable all-dark cleanup.
- Validate the four-ring Arc.

### Step 5 — Host and hot-swap acceptance

- Run the same patch in PlugData standalone and Bitwig CLAP.
- Test UI close/reopen, transport stopped, bypass, save/reload, and plugin
  process restart.
- Test one device, pairs, all three devices, removal in each direction, and
  contention between standalone and Bitwig.

### Step 6 — Demos and package

- Grid demo: dynamic 128/256 layout with momentary and latch modes.
- Arc demo: encoder-following animation with bounded refresh.
- Add help patches, release metadata, installation documentation, and a
  `.plugdata` package.

Packaging starts only after standalone and Bitwig physical acceptance pass.

## Current workbench boundary

As of 2026-08-25, this Mac runs Homebrew SerialOSC 1.4.7 from arm64 binaries.
The older 1.4.1 Intel launch job is preserved but disabled for rollback. No
Monome was connected during the service migration, so physical-device
acceptance is still pending.

The installed PlugData standalone and CLAP plugin are 0.9.3 from the official
`v0.9.3-2` package. The installed VST3 is 0.9.2 and is not an equivalent
acceptance lane until it is upgraded. The current 0.9.4 nightly was tested from
a temporary copy and crashed during font initialization, so it is not an
accepted replacement. See `docs/PLUGDATA-MACOS.md`.

Step 2 session acceptance currently uses only fake per-device servers on
loopback. The fake server exposes the same `/sys/info`, `/sys/host`,
`/sys/port`, `/sys/prefix`, and `/sys/rotation` surface needed for the lifecycle
without opening USB hardware or touching live SerialOSC port `12002`.

## Deferred decisions

- Repository license.
- Final `.plugdata` package metadata after inspecting the schema used by the
  release version of PlugData.
- Whether the legacy patches remain in release archives after the new Grid and
  Arc demos replace their educational value.

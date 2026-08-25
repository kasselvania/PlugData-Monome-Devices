# PlugData Monome Devices

A PlugData-first device layer for Monome Grid and Arc hardware through
[SerialOSC](https://monome.org/docs/serialosc/).

The project is being rebuilt around explicit device selection, observable
connection state, safe hot swapping, and the same patch behavior in PlugData
standalone and its DAW plugins. Vanilla Pure Data compatibility is not a
project goal.

## Current status

The original proof-of-concept patches are preserved under [`legacy/`](legacy/)
for reference, but they are not the architecture of the rebuilt object.

The first new component is `monome-registry`, a discovery-state core which:

- keys devices by stable SerialOSC ID;
- never auto-selects or claims the first device;
- preserves an explicit selection across rescans;
- removes devices missed by a completed scan;
- produces deterministic menu data for a future PlugData `popmenu` adapter.

See [`docs/DESIGN.md`](docs/DESIGN.md) for the stepped implementation and
acceptance plan.

## Requirements

- PlugData 0.9.3 or newer
- SerialOSC
- Monome Grid and/or Arc hardware for physical acceptance

On macOS, use the current Homebrew service rather than the retired Intel-only
installer. See [`docs/MACOS-SERIALOSC.md`](docs/MACOS-SERIALOSC.md).

## Run the current tests

The registry core has no external Lua dependencies:

```sh
lua tests/registry_spec.lua
```

These tests validate discovery state only. They do not claim to validate OSC
transport, PlugData UI behavior, Bitwig hosting, or physical hardware.

Open [`monome-registry-help.pd`](monome-registry-help.pd) in PlugData to inspect
the Pd-Lua event and menu-projection interface interactively.

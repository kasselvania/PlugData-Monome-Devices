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

The first workbench slice now contains `monome-discovery` and
`monome-registry`. Together they:

- use an isolated fake discovery server on loopback port `12012`;
- bind and self-test a real callback before declaring it ready;
- speak the documented SerialOSC list/notify protocol;
- keys devices by stable SerialOSC ID;
- never auto-selects or claims the first device;
- preserves an explicit selection across rescans;
- removes devices missed by a completed scan;
- emit the documented `clear`/`add`/`set` protocol for PlugData's
  `else/popmenu` object.

Discovery, registry selection, hot-remove/hot-add, and callback collision have
been exercised in PlugData. Dynamic `popmenu` population remains an explicit
stable-build gap; the help patch includes a direct-selection fallback and does
not claim that Step 1 is complete.

See [`docs/DESIGN.md`](docs/DESIGN.md) for the stepped implementation and
acceptance plan and [`docs/DISCOVERY-WORKBENCH.md`](docs/DISCOVERY-WORKBENCH.md)
for the runnable workbench.

## Requirements

- PlugData stable `v0.9.3-2` (internal version `0.9.3`)
- SerialOSC
- Monome Grid and/or Arc hardware for physical acceptance

On macOS, use the current Homebrew service rather than the retired Intel-only
installer. See [`docs/MACOS-SERIALOSC.md`](docs/MACOS-SERIALOSC.md). Launch
PlugData as an application, not by executing its inner Mach-O binary; see
[`docs/PLUGDATA-MACOS.md`](docs/PLUGDATA-MACOS.md).

## Run the current tests

The registry core and fake discovery server have no external dependencies:

```sh
lua tests/registry_spec.lua
python3 -m unittest -v tests/fake_serialosc_spec.py
luac -p monome_registry.lua monome-registry.pd_lua
```

The Python tests bind only ephemeral loopback UDP ports. The simulator itself
refuses live SerialOSC port `12002`.

Run `python3 tools/fake_serialosc.py`, then open
[`monome-discovery-help.pd`](monome-discovery-help.pd) in PlugData for the
interactive workbench. [`monome-discovery-smoke.pd`](monome-discovery-smoke.pd)
runs the same discovery automatically and exposes the current native-menu gate.

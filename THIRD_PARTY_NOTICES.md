# Third-party notices

Project-owned PlugData Monome Devices source is licensed under the MIT License,
copyright 2025-2026 Peter Kassel. See `LICENSE`.

## SerialOSC

The project installers fetch source from
[`monome/serialosc`](https://github.com/monome/serialosc) or the separately
identified `kasselvania/serialosc` lease fork. SerialOSC is a separate project
copyright William Light and contributors under the permissive terms recorded in
its upstream [`COPYRIGHT`](https://github.com/monome/serialosc/blob/main/COPYRIGHT)
file. `patches/serialosc-null-port.patch` is a narrow patch against that source;
the project MIT grant does not replace the upstream notice for SerialOSC code.

The installer also builds or links separately supplied libmonome, liblo, libuv,
and their transitive components. Their notices travel with those projects and
must be retained in any binary redistribution. This repository does not contain
their source or prebuilt binaries.

## PlugData and Pure Data libraries

PlugData, Pure Data, Pd-Lua, ELSE, and Cyclone are separately supplied runtime
projects under their own terms. This repository does not redistribute the
PlugData application or those bundled libraries.

See `docs/PROJECT-MAP.md` for the boundary between this device layer, the
SerialOSC protocol fork, and platform installers.

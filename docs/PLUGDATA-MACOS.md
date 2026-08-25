# PlugData on this macOS workbench

## Launch rule

Launch PlugData through Finder, Spotlight, the Dock, or LaunchServices:

```sh
open -a plugdata
```

Do not execute this file directly:

```text
/Applications/plugdata.app/Contents/MacOS/plugdata
```

On this Mac, direct execution aborts during macOS application registration,
before PlugData loads Pd, Pd-Lua, a patch, or SerialOSC. Those crash reports are
therefore launcher failures, not evidence that a Monome patch crashed.

The identifying report signature is:

- `EXC_CRASH (SIGABRT)` / abort trap 6;
- main thread in `HIServices` `_RegisterApplication`;
- launch lifetime under one second;
- shell/Codex/ChatGPT shown as parent, responsible process, or coalition.

## Version decision (2026-08-25)

Keep the official stable `v0.9.3-2` package. Its app bundle reports internal
version `0.9.3`, is universal arm64/x86_64, and the installed executable was
verified byte-for-byte against the official package.

The current official macOS Universal nightly from successful run
`32880948901` (commit `28cd449b1555e01dec705999856af0ab867654b4`,
bundle version `0.9.4`) was tested from a temporary extracted copy without
installing it. It crashed before opening a window with `EXC_BAD_ACCESS` in
`Fonts::Fonts()` / `juce::Typeface::createSystemTypefaceFor`. It is not a safe
replacement for the stable build on this machine.

## Separate `popmenu` gap

The stable app launches normally, but its native `else/popmenu` did not pass
the dynamic-menu smoke test:

- the registry emitted the documented `clear`, `add`, and `set` protocol;
- a direct message-box version of the same protocol was also exercised;
- the widget remained on its empty label;
- float and bang probes emitted no menu value.

This is separate from the launch crash. The registry and discovery transport
remain usable through explicit `select_index` messages. Step 1 is not complete
until a supported PlugData build passes the native menu gate.

References:

- <https://plugdata.org/download>
- <https://github.com/plugdata-team/plugdata/releases/tag/v0.9.3-2>
- <https://github.com/plugdata-team/plugdata/actions/runs/32880948901>
- <https://github.com/porres/pd-else/blob/master/Documentation/Help-files/popmenu-help.pd>

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

Use the installed official macOS Universal nightly from successful run
`32892289806`, commit
`6bb2b60c82a20c869712b1803f490faec4a2abc6`. The app bundle reports version
`0.9.4`, contains both arm64 and x86_64 slices, launches normally through
LaunchServices, loads the Pd-Lua workbench, and passes the native dynamic-menu
gate below.

This exact build is the known-good development basis. A moving nightly should
not be treated as equivalent merely because it also reports `0.9.4`; re-run
the menu and workbench smoke gates after updating.

An earlier nightly from run `32880948901`, commit `28cd449b1555e01d`, crashed
in `Fonts::Fonts()` before opening a window. That failure is historical and
does not apply to the installed `6bb2b60c8` build. Stable `v0.9.3-2` launches,
but it failed the required dynamic-menu behavior and is no longer the accepted
workbench target.

## `popmenu` acceptance

The accepted nightly's native `else/popmenu` passed both required paths:

- registry-driven `clear`, `add`, and `set` populated two device entries;
- selecting an entry updated the visible device label; and
- the widget emitted index `0`, which selected the matching stable serial ID.

The same probe remains a documented failure on stable 0.9.3. That distinction
is why the repository records an exact known-good nightly rather than a bare
version number.

References:

- <https://plugdata.org/download>
- <https://github.com/plugdata-team/plugdata/releases/tag/v0.9.3-2>
- <https://github.com/plugdata-team/plugdata/actions/runs/32892289806>
- <https://github.com/porres/pd-else/blob/master/Documentation/Help-files/popmenu-help.pd>

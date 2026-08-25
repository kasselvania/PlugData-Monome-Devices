# Legacy proof of concept

These patches are preserved as source archaeology only:

- `monome-object.pd` is a PlugData OSC port of the 2023 Monome Pure Data
  abstraction. It automatically claims the first discovered device.
- `grid-howto.pd` demonstrates Grid messages but relies on global send/receive
  names and a fixed `/monome` prefix.

They are not supported entry points for the rebuilt project. New work belongs
under the explicit discovery, registry, session, Grid, and Arc boundaries in
[`docs/DESIGN.md`](../docs/DESIGN.md).

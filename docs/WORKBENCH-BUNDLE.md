# Development workbench bundle

The repository can produce a checksum-addressed ZIP containing the complete
committed PlugData device layer, fake server, live workbench, tests,
documentation, macOS SerialOSC provisioning tools, and preserved legacy
reference.

The provisioning tools include both the accepted null-port-safe stable
installer and a separately rooted lease-candidate manager. The latter can
prepare a pinned candidate without changing the running service and requires
an explicit, rollback-guarded activation.

From a clean checkout:

```sh
./tools/build_workbench_bundle.sh
```

The default output is:

```text
dist/plugdata-monome-workbench-<commit>.zip
dist/plugdata-monome-workbench-<commit>.zip.sha256
```

The archive is built from `HEAD`, not uncommitted working-tree files. Its
top-level directory and filename carry the exact abbreviated Git object ID.
The builder verifies the ZIP before reporting success.

To package another committed ref or choose another output directory:

```sh
./tools/build_workbench_bundle.sh --ref <git-ref> --output <directory>
```

## What this bundle means

It is a reproducible development baseline for continuing the SerialOSC lease
and PlugData integration work. It retains the evidence and tooling required to
reproduce the current standalone and Bitwig behavior.

It is not yet:

- a one-click PlugData installation;
- a PlugData Store submission;
- a promise that arbitrary PlugData builds are compatible;
- a cross-platform crash-safety claim before Steam Deck acceptance; or
- the later collection of musical Grid and Arc examples.

Those claims remain blocked by Steam Deck and cross-platform physical
acceptance, an explicit project license, and the final PlugData package format
decision. See [PROJECT-MAP.md](PROJECT-MAP.md).

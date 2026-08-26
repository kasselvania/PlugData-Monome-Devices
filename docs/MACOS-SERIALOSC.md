# SerialOSC on Apple-silicon macOS

Homebrew provides native Apple-silicon SerialOSC 1.4.7 binaries and the
required libraries. Stock 1.4.7 also contains a reproducible crash when an
application safely releases a device to destination port `0` and later asks
for `/sys/info`. This project builds the pinned official source with only the
two null-port guards required to make that state safe.

Sources:

- <https://monome.org/docs/serialosc/setup/>
- <https://formulae.brew.sh/formula/serialosc>

## Project installation

Install Homebrew and Apple's Command Line Tools first. From this repository:

```sh
./tools/install_macos_serialosc.sh install
./tools/install_macos_serialosc.sh verify
```

The installer:

- fetches official SerialOSC revision
  `ff53885cb227546d0f29f42f223ecf7a984df0e9`;
- applies only [`patches/serialosc-null-port.patch`](../patches/serialosc-null-port.patch);
- builds native `arm64` binaries against Homebrew `liblo`, `libmonome`, and
  `libuv`;
- installs them below
  `~/Library/Application Support/PlugData Monome Devices/serialosc`;
- preserves `~/Library/Preferences/org.monome.serialosc`;
- stops the stock Homebrew job and disables the retired Monome job; and
- starts one user LaunchAgent on UDP port `12002`.

Expected service label:

```text
com.kasselvania.plugdata-monome.serialosc
```

The installer needs no `sudo` and does not replace files in Homebrew's Cellar.

## Verify the active service

```sh
./tools/install_macos_serialosc.sh verify
file "$HOME/Library/Application Support/PlugData Monome Devices/serialosc/bin/serialoscd"
launchctl print gui/$(id -u)/com.kasselvania.plugdata-monome.serialosc
lsof -nP -iUDP:12002
```

On Apple silicon, `file` must report `arm64`. Exactly one SerialOSC daemon
should own UDP port 12002.

## Why the stock build fails

`/sys/port 0` is SerialOSC's valid released state. In that state, liblo can
return a null pointer when SerialOSC asks for the outgoing port as text. Stock
SerialOSC passes that pointer directly to `atoi()` in the `/sys/info` reply and
to `strtol()` while saving configuration. The observed crash report ended in:

```text
strtol_l -> atoi -> info_reply_all -> info_prop_handler
```

The patch reports port `0` when the text pointer is absent and writes `0` to
configuration by the same rule. It does not change discovery, USB detection,
device I/O, supervision, or OSC ownership semantics.

Physical readback after the patch proved this sequence:

1. release the legacy 128 with `/sys/port 0`;
2. probe it again with `/sys/info` and read back port `0`;
3. claim it at the workbench callback and light all 128 LEDs;
4. unplug while claimed; and
5. observe clean device, registry, and selection teardown with no new crash.

After installing the clean production LaunchAgent, the same legacy 128 passed
discovery, released-state probe, verified claim, full-surface output, and
unplug while the top-left key was physically held. PlugData emitted
`key 0 0 0 synthetic` before detach, the per-device worker exited normally,
and no new crash report appeared.

## Migrating an older Monome installer

Do not start both launch jobs. Preserve device preferences before changing the
service:

```sh
cp -pR "$HOME/Library/Preferences/org.monome.serialosc" /path/to/backup/
```

The historical installer normally used the label `org.monome.serialosc` and
the plist `/Library/LaunchAgents/org.monome.serialosc.plist`.

The project installer stops known conflicting jobs and disables the historical
per-user label before starting its own service. The equivalent manual commands
are:

```sh
launchctl bootout gui/$(id -u)/org.monome.serialosc
launchctl disable gui/$(id -u)/org.monome.serialosc
brew services stop serialosc
```

The old files do not need to be deleted to prove the migration. Keeping them
in place provides a rollback while the new service is tested.

## Rollback to stock Homebrew

The rollback keeps the patched binaries and preferences in place:

```sh
./tools/install_macos_serialosc.sh restore-homebrew
```

Then confirm that exactly one process owns UDP 12002. This restores the known
null-port crash as well, so it is a service rollback rather than an accepted
workbench configuration. Do not run project, Homebrew, and historical services
together.

## Acceptance levels

Service acceptance proves the daemon is running, native, and owns discovery
port 12002. It does not prove that a Grid or Arc has been detected. Physical
acceptance additionally requires discovery, `/sys/info` readback, input,
LED/ring output, disconnect, reconnect, and destination release.

## USB and reconnect diagnosis

A Grid lighting briefly at plug-in proves bus power, not SerialOSC attachment.
Check the layers separately:

```sh
ioreg -p IOUSB -l -w 0
find /dev -maxdepth 1 \( -name 'cu.usbserial*' -o -name 'tty.usbserial*' \) -print
pgrep -fl 'serialosc|serialosc-device'
lsof /dev/tty.usbserial-mXXXX /dev/cu.usbserial-mXXXX
tail -n 50 "$HOME/Library/Logs/PlugData Monome Devices/serialoscd.log"
```

On the 2026-08-25/26 CalDigit run, macOS kept the legacy Grid's serial nodes
while SerialOSC's per-device process exited. Instrumentation and the macOS
crash report later proved that the deterministic trigger was PlugData's
`/sys/info` probe after an earlier release to port `0`; the dock did not drop
the USB connection.

Do not loop service restarts or launch `serialosc-device` by hand. Its standard
input/output are private supervisor IPC pipes, so a standalone child can open
the serial port without becoming a valid discoverable SerialOSC server. If the
patched service fails, inspect all layers and retain the crash/log evidence
before changing the connection topology.

Implementation reference:

- <https://github.com/monome/serialosc/blob/main/src/serialosc-device/osc/sys_methods.c>
- <https://github.com/monome/serialosc/blob/main/src/serialosc-device/config.c>

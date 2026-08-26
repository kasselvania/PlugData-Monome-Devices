# SerialOSC on Apple-silicon macOS

Monome's supported macOS setup uses Homebrew. Homebrew currently provides
SerialOSC 1.4.7 and its dependencies as native Apple-silicon bottles.

Sources:

- <https://monome.org/docs/serialosc/setup/>
- <https://formulae.brew.sh/formula/serialosc>

## New installation

```sh
brew install serialosc
brew services start serialosc
brew services list
```

Expected service label:

```text
homebrew.mxcl.serialosc
```

## Verify the active service

```sh
file /opt/homebrew/opt/serialosc/bin/serialoscd
launchctl print gui/$(id -u)/homebrew.mxcl.serialosc
lsof -nP -iUDP:12002
```

On Apple silicon, `file` must report `arm64`. Exactly one SerialOSC daemon
should own UDP port 12002.

## Migrating an older Monome installer

Do not start both launch jobs. Preserve device preferences before changing the
service:

```sh
cp -pR "$HOME/Library/Preferences/org.monome.serialosc" /path/to/backup/
```

The historical installer normally used the label `org.monome.serialosc` and
the plist `/Library/LaunchAgents/org.monome.serialosc.plist`.

Stop and disable that per-user job before starting the Homebrew service:

```sh
launchctl bootout gui/$(id -u)/org.monome.serialosc
launchctl disable gui/$(id -u)/org.monome.serialosc
brew services start serialosc
```

The old files do not need to be deleted to prove the migration. Keeping them
in place provides a rollback while the new service is tested.

## Rollback

Only use this when the historical plist and application bundle still exist:

```sh
brew services stop serialosc
launchctl enable gui/$(id -u)/org.monome.serialosc
launchctl bootstrap gui/$(id -u) /Library/LaunchAgents/org.monome.serialosc.plist
```

Then confirm that exactly one process owns UDP 12002. Do not run the Homebrew
and historical services together.

## Acceptance levels

Service acceptance proves the daemon is running, native, and owns discovery
port 12002. It does not prove that a Grid or Arc has been detected. Physical
acceptance additionally requires discovery, `/sys/info` readback, input,
LED/ring output, disconnect, reconnect, and destination release.

## Dock and reconnect diagnosis

A Grid lighting briefly at plug-in proves bus power, not SerialOSC attachment.
Check the layers separately:

```sh
ioreg -p IOUSB -l -w 0
find /dev -maxdepth 1 \( -name 'cu.usbserial*' -o -name 'tty.usbserial*' \) -print
pgrep -fl 'serialosc|serialosc-device'
lsof /dev/tty.usbserial-mXXXX /dev/cu.usbserial-mXXXX
tail -n 50 /opt/homebrew/var/log/serialoscd.log
```

On the 2026-08-25 CalDigit-dock run, macOS still exposed the legacy Grid's
serial nodes while no process held the port and SerialOSC's per-device process
had exited. Restarting the existing user service with the Grid still connected
temporarily recovered it:

```sh
brew services restart serialosc
```

SerialOSC's macOS detector reports devices during its initial scan and when
IOKit reports a newly matched serial device. The supervisor reports a
per-device child exit but does not respawn that child while the existing device
node remains matched. Do not launch `serialosc-device` by hand: its standard
input/output are private supervisor IPC pipes, so a standalone child can open
the serial port without becoming a discoverable SerialOSC server.

In the observed dock run, repeated service restarts created a valid device
server only briefly before it exited again. That is a USB/dock-to-SerialOSC
continuity failure, not proof that the PlugData Grid layer failed. Do not loop
restarts and call the hardware accepted. Re-seat the cable or use a direct Mac
port when an operator is present, then repeat discovery, claim, input, output,
and release readback.

Implementation reference:

- <https://github.com/monome/serialosc/blob/main/src/serialosc-detector/iokitlib.c>
- <https://github.com/monome/serialosc/blob/main/src/serialoscd/uv.c>

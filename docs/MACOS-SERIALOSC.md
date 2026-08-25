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

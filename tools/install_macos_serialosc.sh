#!/bin/bash

set -euo pipefail

SERIALOSC_REPOSITORY="${SERIALOSC_REPOSITORY:-https://github.com/monome/serialosc.git}"
SERIALOSC_REVISION="ff53885cb227546d0f29f42f223ecf7a984df0e9"
SERIALOSC_SHORT_REVISION="ff53885"
SERVICE_LABEL="com.kasselvania.plugdata-monome.serialosc"
LEGACY_SERVICE_LABEL="org.monome.serialosc"
DISCOVERY_PORT="12002"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PATCH_FILE="$PROJECT_ROOT/patches/serialosc-null-port.patch"
INSTALL_ROOT="$HOME/Library/Application Support/PlugData Monome Devices/serialosc"
BIN_DIR="$INSTALL_ROOT/bin"
METADATA_FILE="$INSTALL_ROOT/BUILD"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/$SERVICE_LABEL.plist"
LOG_DIR="$HOME/Library/Logs/PlugData Monome Devices"
LOG_FILE="$LOG_DIR/serialoscd.log"
USER_DOMAIN="gui/$(id -u)"

say() {
	printf '%s\n' "$*"
}

fail() {
	printf 'ERROR: %s\n' "$*" >&2
	exit 1
}

usage() {
	cat <<'EOF'
Usage: tools/install_macos_serialosc.sh [install|verify|restore-homebrew]

  install           Build the pinned patched source and activate its user service.
  verify            Verify the installed binary, service, and UDP ownership.
  restore-homebrew  Stop this service and reactivate Homebrew SerialOSC.
EOF
}

require_command() {
	command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

service_loaded() {
	launchctl print "$USER_DOMAIN/$1" >/dev/null 2>&1
}

stop_project_service() {
	launchctl bootout "$USER_DOMAIN/$SERVICE_LABEL" >/dev/null 2>&1 || true
}

stop_homebrew_service() {
	if brew list --versions serialosc >/dev/null 2>&1; then
		brew services stop serialosc >/dev/null 2>&1
	fi
}

wait_for_discovery_port() {
	tries=0
	while [ "$tries" -lt 10 ]; do
		if lsof -nP -t -iUDP:"$DISCOVERY_PORT" 2>/dev/null | grep -q .; then
			return 0
		fi
		tries=$((tries + 1))
		sleep 1
	done
	return 1
}

verify_installation() {
	require_command file
	require_command launchctl
	require_command lsof

	[ -x "$BIN_DIR/serialoscd" ] || fail "Patched serialoscd is not installed."
	[ -x "$BIN_DIR/serialosc-device" ] || fail "Patched serialosc-device is not installed."
	[ -x "$BIN_DIR/serialosc-detector" ] || fail "Patched serialosc-detector is not installed."
	grep -q "revision=$SERIALOSC_REVISION" "$METADATA_FILE" || \
		fail "Installed build metadata does not match the pinned revision."
	file "$BIN_DIR/serialoscd" | grep -q 'arm64' || \
		fail "Installed serialoscd is not native arm64."
	"$BIN_DIR/serialoscd" -v | grep -q "($SERIALOSC_SHORT_REVISION)" || \
		fail "Installed serialoscd does not report the pinned revision."
	service_state="$(launchctl print "$USER_DOMAIN/$SERVICE_LABEL" 2>/dev/null)" || \
		fail "Patched SerialOSC service is not loaded."
	printf '%s\n' "$service_state" | grep -Fq "program = $BIN_DIR/serialoscd" || \
		fail "Loaded service does not point to the patched serialoscd."
	service_pid="$(printf '%s\n' "$service_state" | \
		awk '/^[[:space:]]*pid = [0-9]+$/ { print $3; exit }')"
	[ -n "$service_pid" ] || fail "Loaded service has no running process."
	wait_for_discovery_port || fail "SerialOSC did not bind UDP port $DISCOVERY_PORT."

	owners="$(lsof -nP -t -iUDP:"$DISCOVERY_PORT" 2>/dev/null | sort -u)"
	owner_count="$(printf '%s\n' "$owners" | awk 'NF { count++ } END { print count + 0 }')"
	[ "$owner_count" -eq 1 ] || \
		fail "Expected one owner of UDP port $DISCOVERY_PORT; found $owner_count."
	owner_pid="$(printf '%s\n' "$owners" | awk 'NF { print; exit }')"
	[ "$owner_pid" = "$service_pid" ] || \
		fail "UDP port $DISCOVERY_PORT is not owned by the loaded patched service."

	if service_loaded homebrew.mxcl.serialosc; then
		fail "Homebrew SerialOSC is also loaded; only one service may run."
	fi

	say "SerialOSC fix verified."
	say "  revision: $SERIALOSC_REVISION"
	say "  service:  $SERVICE_LABEL"
	say "  UDP owner: $owner_pid ($BIN_DIR/serialoscd)"
}

ensure_build_requirements() {
	[ "$(uname -s)" = "Darwin" ] || fail "This installer is for macOS only."
	[ "$(uname -m)" = "arm64" ] || fail "This installer currently supports Apple-silicon Macs only."
	require_command brew
	require_command git
	require_command patch
	require_command xcrun
	xcrun --find clang >/dev/null 2>&1 || \
		fail "Apple Command Line Tools are required. Run: xcode-select --install"

	if ! command -v python3 >/dev/null 2>&1; then
		say "Installing Python build support with Homebrew..."
		brew install python
	fi

	for dependency in liblo libmonome libuv; do
		if ! brew list --versions "$dependency" >/dev/null 2>&1; then
			say "Installing Homebrew dependency: $dependency"
			brew install "$dependency"
		fi
	done
}

write_launch_agent() {
	mkdir -p "$(dirname "$LAUNCH_AGENT")" "$LOG_DIR"
	python3 - "$LAUNCH_AGENT" "$SERVICE_LABEL" "$BIN_DIR/serialoscd" "$LOG_FILE" <<'PY'
import pathlib
import plistlib
import sys

path, label, executable, log = sys.argv[1:]
payload = {
    "Label": label,
    "ProgramArguments": [executable],
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": log,
    "StandardErrorPath": log,
}
with pathlib.Path(path).open("wb") as handle:
    plistlib.dump(payload, handle, sort_keys=False)
PY
}

install_serialosc() {
	ensure_build_requirements
	[ -f "$PATCH_FILE" ] || fail "Patch not found: $PATCH_FILE"

	work_root="$(mktemp -d "${TMPDIR:-/tmp}/plugdata-serialosc.XXXXXX")"
	trap 'rm -rf "$work_root"' EXIT
	source_dir="$work_root/serialosc"

	say "Fetching pinned SerialOSC source..."
	git clone --quiet --no-checkout "$SERIALOSC_REPOSITORY" "$source_dir"
	git -C "$source_dir" checkout --quiet --detach "$SERIALOSC_REVISION"
	actual_revision="$(git -C "$source_dir" rev-parse HEAD)"
	[ "$actual_revision" = "$SERIALOSC_REVISION" ] || \
		fail "Source revision mismatch: $actual_revision"
	git -C "$source_dir" submodule update --quiet --init --depth 1 third-party/optparse

	say "Applying the null-port safety patch..."
	patch --quiet -d "$source_dir" -p1 -i "$PATCH_FILE"

	brew_prefix="$(brew --prefix)"
	export CPATH="$brew_prefix/include${CPATH:+:$CPATH}"
	export LIBRARY_PATH="$brew_prefix/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
	export PKG_CONFIG_PATH="$brew_prefix/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"

	say "Building native arm64 SerialOSC..."
	(
		cd "$source_dir"
		python3 ./waf configure
		python3 ./waf build
	)

	for executable in serialoscd serialosc-device serialosc-detector; do
		file "$source_dir/build/bin/$executable" | grep -q 'arm64' || \
			fail "Build output is not native arm64: $executable"
	done

	say "Activating one user-owned SerialOSC service..."
	stop_project_service
	stop_homebrew_service
	launchctl disable "$USER_DOMAIN/$LEGACY_SERVICE_LABEL" >/dev/null 2>&1 || true

	if lsof -nP -t -iUDP:"$DISCOVERY_PORT" 2>/dev/null | grep -q .; then
		lsof -nP -iUDP:"$DISCOVERY_PORT" >&2 || true
		fail "UDP port $DISCOVERY_PORT is still occupied after stopping known services."
	fi

	mkdir -p "$BIN_DIR"
	for executable in serialoscd serialosc-device serialosc-detector; do
		install -m 755 "$source_dir/build/bin/$executable" "$BIN_DIR/$executable"
	done
	printf 'revision=%s\npatch=serialosc-null-port.patch\n' \
		"$SERIALOSC_REVISION" > "$METADATA_FILE"
	write_launch_agent
	launchctl enable "$USER_DOMAIN/$SERVICE_LABEL"
	launchctl bootstrap "$USER_DOMAIN" "$LAUNCH_AGENT"
	launchctl kickstart -k "$USER_DOMAIN/$SERVICE_LABEL"

	verify_installation
}

restore_homebrew() {
	require_command brew
	require_command launchctl
	brew list --versions serialosc >/dev/null 2>&1 || \
		fail "Homebrew SerialOSC is not installed."
	stop_project_service
	launchctl disable "$USER_DOMAIN/$SERVICE_LABEL"
	brew services start serialosc
	say "Homebrew SerialOSC restored. Patched files were preserved for rollback."
}

mode="${1:-install}"
case "$mode" in
	install) install_serialosc ;;
	verify) verify_installation ;;
	restore-homebrew) restore_homebrew ;;
	-h|--help|help) usage ;;
	*) usage >&2; exit 2 ;;
esac

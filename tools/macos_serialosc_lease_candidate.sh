#!/bin/bash

set -euo pipefail

FORK_REPOSITORY="https://github.com/kasselvania/serialosc.git"
FORK_REVISION="65ca6c2ff4d8589c5e75d5e8b4e9cd38bec96bec"
FORK_SHORT_REVISION="65ca6c2"
STABLE_SERVICE_LABEL="com.kasselvania.plugdata-monome.serialosc"
CANDIDATE_SERVICE_LABEL="com.kasselvania.plugdata-monome.serialosc-lease-candidate"
DISCOVERY_PORT="12002"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SUPPORT_ROOT="$HOME/Library/Application Support/PlugData Monome Devices"
STABLE_ROOT="$SUPPORT_ROOT/serialosc"
CANDIDATE_ROOT="$SUPPORT_ROOT/serialosc-lease-candidate/$FORK_SHORT_REVISION"
CANDIDATE_BIN_DIR="$CANDIDATE_ROOT/bin"
CANDIDATE_METADATA="$CANDIDATE_ROOT/BUILD"
CANDIDATE_CHECKSUMS="$CANDIDATE_ROOT/SHA256SUMS"
STABLE_AGENT="$HOME/Library/LaunchAgents/$STABLE_SERVICE_LABEL.plist"
CANDIDATE_AGENT="$HOME/Library/LaunchAgents/$CANDIDATE_SERVICE_LABEL.plist"
LOG_DIR="$HOME/Library/Logs/PlugData Monome Devices"
CANDIDATE_LOG="$LOG_DIR/serialoscd-lease-candidate.log"
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
Usage: tools/macos_serialosc_lease_candidate.sh MODE [SOURCE_DIR]

  prepare [SOURCE_DIR]  Build and install the pinned candidate without activating it.
                        SOURCE_DIR may be an exact clean local fork checkout.
  activate              Switch from the accepted stable service to the candidate.
  verify                Verify the active candidate and sole UDP ownership.
  restore-stable        Stop the candidate and restore the accepted stable service.
  status                Report installed revisions, loaded jobs, and UDP ownership.

The stable binaries and LaunchAgent are never overwritten or deleted.
EOF
}

require_command() {
	command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

service_loaded() {
	launchctl print "$USER_DOMAIN/$1" >/dev/null 2>&1
}

service_state() {
	launchctl print "$USER_DOMAIN/$1" 2>/dev/null
}

service_pid() {
	service_state "$1" | awk \
		'/^[[:space:]]*pid = [0-9]+$/ { print $3; exit }'
}

port_owners() {
	lsof -nP -t -iUDP:"$DISCOVERY_PORT" 2>/dev/null | sort -u
}

wait_for_port_owner() {
	expected_pid="$1"
	tries=0
	while [ "$tries" -lt 20 ]; do
		owners="$(port_owners || true)"
		if [ "$owners" = "$expected_pid" ]; then
			return 0
		fi
		tries=$((tries + 1))
		sleep 0.25
	done
	return 1
}

wait_for_free_port() {
	tries=0
	while [ "$tries" -lt 20 ]; do
		if [ -z "$(port_owners || true)" ]; then
			return 0
		fi
		tries=$((tries + 1))
		sleep 0.25
	done
	return 1
}

verify_candidate_files() {
	require_command file
	require_command shasum

	[ -x "$CANDIDATE_BIN_DIR/serialoscd" ] || \
		fail "Candidate serialoscd is not prepared."
	[ -x "$CANDIDATE_BIN_DIR/serialosc-device" ] || \
		fail "Candidate serialosc-device is not prepared."
	[ -x "$CANDIDATE_BIN_DIR/serialosc-detector" ] || \
		fail "Candidate serialosc-detector is not prepared."
	grep -Fqx "repository=$FORK_REPOSITORY" "$CANDIDATE_METADATA" || \
		fail "Candidate repository metadata does not match."
	grep -Fqx "revision=$FORK_REVISION" "$CANDIDATE_METADATA" || \
		fail "Candidate revision metadata does not match."
	file "$CANDIDATE_BIN_DIR/serialoscd" | grep -q 'arm64' || \
		fail "Candidate serialoscd is not native arm64."
	"$CANDIDATE_BIN_DIR/serialoscd" -v | \
		grep -Fq "($FORK_SHORT_REVISION)" || \
		fail "Candidate serialoscd does not report the pinned revision."
	(
		cd "$CANDIDATE_BIN_DIR"
		shasum -a 256 -c "$CANDIDATE_CHECKSUMS" >/dev/null
	) || fail "Candidate binary checksum verification failed."
}

verify_service() {
	label="$1"
	program="$2"
	state="$(service_state "$label")" || \
		fail "Service is not loaded: $label"
	printf '%s\n' "$state" | grep -Fq "program = $program" || \
		fail "Loaded service does not point to $program"
	pid="$(printf '%s\n' "$state" | awk \
		'/^[[:space:]]*pid = [0-9]+$/ { print $3; exit }')"
	[ -n "$pid" ] || fail "Loaded service has no running process: $label"
	wait_for_port_owner "$pid" || \
		fail "UDP $DISCOVERY_PORT is not solely owned by $label (PID $pid)."
}

verify_candidate_active() {
	verify_candidate_files
	verify_service "$CANDIDATE_SERVICE_LABEL" \
		"$CANDIDATE_BIN_DIR/serialoscd"
	if service_loaded "$STABLE_SERVICE_LABEL"; then
		fail "Stable SerialOSC is also loaded."
	fi
	if service_loaded homebrew.mxcl.serialosc; then
		fail "Homebrew SerialOSC is also loaded."
	fi
	say "SerialOSC lease candidate verified."
	say "  revision: $FORK_REVISION"
	say "  service:  $CANDIDATE_SERVICE_LABEL"
	say "  binary:   $CANDIDATE_BIN_DIR/serialoscd"
}

ensure_build_requirements() {
	[ "$(uname -s)" = "Darwin" ] || fail "This candidate is for macOS only."
	[ "$(uname -m)" = "arm64" ] || \
		fail "This candidate currently supports Apple-silicon Macs only."
	for command_name in brew git file launchctl python3 shasum xcrun; do
		require_command "$command_name"
	done
	xcrun --find clang >/dev/null 2>&1 || \
		fail "Apple Command Line Tools are required."
	for dependency in liblo libmonome libuv; do
		brew list --versions "$dependency" >/dev/null 2>&1 || \
			fail "Missing Homebrew dependency: $dependency"
	done
}

verify_source() {
	source_dir="$1"
	[ -d "$source_dir/.git" ] || fail "Not a Git checkout: $source_dir"
	actual_revision="$(git -C "$source_dir" rev-parse HEAD)"
	[ "$actual_revision" = "$FORK_REVISION" ] || \
		fail "Source revision mismatch: $actual_revision"
	[ -z "$(git -C "$source_dir" status --porcelain --untracked-files=no)" ] || \
		fail "Source checkout has tracked changes: $source_dir"
	optparse_state="$(git -C "$source_dir" submodule status third-party/optparse)"
	case "$optparse_state" in
		" "*) ;;
		*) fail "Pinned optparse submodule is not checked out exactly." ;;
	esac
}

write_candidate_agent() {
	mkdir -p "$(dirname "$CANDIDATE_AGENT")" "$LOG_DIR"
	python3 - "$CANDIDATE_AGENT" "$CANDIDATE_SERVICE_LABEL" \
		"$CANDIDATE_BIN_DIR/serialoscd" "$CANDIDATE_LOG" <<'PY'
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

install_built_candidate() {
	source_dir="$1"
	mkdir -p "$CANDIDATE_BIN_DIR"
	for executable in serialoscd serialosc-device serialosc-detector; do
		file "$source_dir/build/bin/$executable" | grep -q 'arm64' || \
			fail "Build output is not native arm64: $executable"
		install -m 755 "$source_dir/build/bin/$executable" \
			"$CANDIDATE_BIN_DIR/$executable"
	done
	printf 'repository=%s\nrevision=%s\nchannel=lease-candidate\n' \
		"$FORK_REPOSITORY" "$FORK_REVISION" > "$CANDIDATE_METADATA"
	(
		cd "$CANDIDATE_BIN_DIR"
		shasum -a 256 serialoscd serialosc-device serialosc-detector > \
			"$CANDIDATE_CHECKSUMS"
	)
	write_candidate_agent
	verify_candidate_files
}

build_source() {
	source_dir="$1"
	brew_prefix="$(brew --prefix)"
	export CPATH="$brew_prefix/include${CPATH:+:$CPATH}"
	export LIBRARY_PATH="$brew_prefix/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
	export PKG_CONFIG_PATH="$brew_prefix/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
	(
		cd "$source_dir"
		python3 ./waf configure
		python3 ./waf build
	)
	"$source_dir/build/bin/serialoscd" -v | \
		grep -Fq "($FORK_SHORT_REVISION)" || \
		fail "Built serialoscd does not report the pinned revision."
}

prepare_candidate() {
	ensure_build_requirements
	service_loaded "$CANDIDATE_SERVICE_LABEL" && \
		fail "Restore the stable service before replacing candidate files."
	requested_source="${1:-}"
	work_root=""

	if [ -n "$requested_source" ]; then
		source_dir="$(cd "$requested_source" && pwd)"
		verify_source "$source_dir"
	else
		work_root="$(mktemp -d "${TMPDIR:-/tmp}/serialosc-lease.XXXXXX")"
		source_dir="$work_root/serialosc"
		trap 'if [ -n "${work_root:-}" ] && [ -d "$work_root" ]; then rm -rf "$work_root"; fi' EXIT
		say "Fetching pinned SerialOSC lease fork..."
		git clone --quiet --no-checkout "$FORK_REPOSITORY" "$source_dir"
		git -C "$source_dir" checkout --quiet --detach "$FORK_REVISION"
		git -C "$source_dir" submodule update --quiet --init --depth 1 \
			third-party/optparse
		verify_source "$source_dir"
	fi

	say "Building pinned native ARM64 lease candidate..."
	build_source "$source_dir"
	say "Installing candidate beside the accepted stable build..."
	install_built_candidate "$source_dir"
	say "Candidate prepared but not activated."
	say "  candidate: $CANDIDATE_ROOT"
	say "  stable:    $STABLE_ROOT"
	say "Run '$0 activate' only when physical acceptance is ready."
}

stop_candidate() {
	launchctl bootout "$USER_DOMAIN/$CANDIDATE_SERVICE_LABEL" \
		>/dev/null 2>&1 || true
}

restore_stable_service() {
	require_command launchctl
	require_command lsof
	[ -f "$STABLE_AGENT" ] || fail "Stable LaunchAgent is missing: $STABLE_AGENT"
	[ -x "$STABLE_ROOT/bin/serialoscd" ] || \
		fail "Stable serialoscd is missing: $STABLE_ROOT/bin/serialoscd"

	stop_candidate
	launchctl disable "$USER_DOMAIN/$CANDIDATE_SERVICE_LABEL" \
		>/dev/null 2>&1 || true
	if service_loaded "$STABLE_SERVICE_LABEL"; then
		verify_service "$STABLE_SERVICE_LABEL" "$STABLE_ROOT/bin/serialoscd"
		say "Accepted stable SerialOSC is already active."
		return
	fi
	wait_for_free_port || fail "UDP $DISCOVERY_PORT remained occupied after stopping candidate."
	launchctl enable "$USER_DOMAIN/$STABLE_SERVICE_LABEL"
	if ! service_loaded "$STABLE_SERVICE_LABEL"; then
		launchctl bootstrap "$USER_DOMAIN" "$STABLE_AGENT"
	fi
	launchctl kickstart -k "$USER_DOMAIN/$STABLE_SERVICE_LABEL"
	verify_service "$STABLE_SERVICE_LABEL" "$STABLE_ROOT/bin/serialoscd"
	say "Accepted stable SerialOSC restored."
}

switch_to_candidate() {
	launchctl bootout "$USER_DOMAIN/$STABLE_SERVICE_LABEL" \
		>/dev/null 2>&1 || return 1
	launchctl disable "$USER_DOMAIN/$STABLE_SERVICE_LABEL" \
		>/dev/null 2>&1 || return 1
	wait_for_free_port || return 1
	launchctl enable "$USER_DOMAIN/$CANDIDATE_SERVICE_LABEL" || return 1
	launchctl bootstrap "$USER_DOMAIN" "$CANDIDATE_AGENT" || return 1
	launchctl kickstart -k "$USER_DOMAIN/$CANDIDATE_SERVICE_LABEL" || return 1
	(verify_candidate_active) || return 1
}

activate_candidate() {
	require_command launchctl
	require_command lsof
	verify_candidate_files
	[ -f "$STABLE_AGENT" ] || fail "Stable LaunchAgent is unavailable for rollback."
	[ -x "$STABLE_ROOT/bin/serialoscd" ] || fail "Stable binary is unavailable for rollback."
	if service_loaded "$CANDIDATE_SERVICE_LABEL"; then
		verify_candidate_active
		return
	fi
	service_loaded "$STABLE_SERVICE_LABEL" || \
		fail "The accepted stable service must be running before candidate activation."
	verify_service "$STABLE_SERVICE_LABEL" "$STABLE_ROOT/bin/serialoscd"

	say "Switching from accepted stable SerialOSC to the lease candidate..."
	if ! switch_to_candidate; then
		printf 'Candidate activation failed; restoring stable service.\n' >&2
		restore_stable_service
		fail "Candidate activation did not pass verification."
	fi
}

show_status() {
	say "SerialOSC service status"
	if [ -f "$STABLE_ROOT/BUILD" ]; then
		say "  stable metadata:"
		sed 's/^/    /' "$STABLE_ROOT/BUILD"
	else
		say "  stable metadata: missing"
	fi
	if [ -f "$CANDIDATE_METADATA" ]; then
		say "  candidate metadata:"
		sed 's/^/    /' "$CANDIDATE_METADATA"
	else
		say "  candidate metadata: not prepared"
	fi
	for label in "$STABLE_SERVICE_LABEL" "$CANDIDATE_SERVICE_LABEL" \
		homebrew.mxcl.serialosc; do
		if service_loaded "$label"; then
			say "  loaded: $label (PID $(service_pid "$label"))"
		else
			say "  stopped: $label"
		fi
	done
	owners="$(port_owners || true)"
	if [ -n "$owners" ]; then
		say "  UDP $DISCOVERY_PORT owner PID(s): $owners"
	else
		say "  UDP $DISCOVERY_PORT: unowned"
	fi
}

mode="${1:-help}"
case "$mode" in
	prepare) prepare_candidate "${2:-}" ;;
	activate) activate_candidate ;;
	verify) verify_candidate_active ;;
	restore-stable) restore_stable_service ;;
	status) show_status ;;
	-h|--help|help) usage ;;
	*) usage >&2; exit 2 ;;
esac

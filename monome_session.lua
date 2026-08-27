local ClaimRegistry = {}
ClaimRegistry.__index = ClaimRegistry

function ClaimRegistry.new()
    return setmetatable({ owners = {} }, ClaimRegistry)
end

function ClaimRegistry:acquire(serial, owner)
    local current = self.owners[serial]
    if current and current ~= owner then
        return nil, "claimed_in_process"
    end
    self.owners[serial] = owner
    return true
end

function ClaimRegistry:release(serial, owner)
    if self.owners[serial] ~= owner then
        return false
    end
    self.owners[serial] = nil
    return true
end

function ClaimRegistry:owner(serial)
    return self.owners[serial]
end

local Session = {}
Session.__index = Session

local function is_integer(value)
    return type(value) == "number" and value == math.floor(value)
end

local function valid_port(value, allow_zero)
    local minimum = allow_zero and 0 or 1
    return is_integer(value) and value >= minimum and value <= 65535
end

local function valid_string(value)
    return type(value) == "string" and value ~= "" and not value:find("\0", 1, true)
end

local function valid_prefix(value)
    return valid_string(value) and value:sub(1, 1) == "/"
        and value:sub(-1) ~= "/"
end

local function valid_protocol(value)
    return value == "legacy" or value == "lease"
end

local function valid_token(value)
    return valid_string(value) and #value <= 128
end

local function valid_ttl(value)
    return is_integer(value) and value >= 1000 and value <= 60000
end

local function valid_size(width, height)
    return is_integer(width) and is_integer(height)
        and ((width == 0 and height == 0) or (width >= 1 and height >= 1))
end

local function copy_info(info)
    if not info then
        return nil
    end
    return {
        id = info.id,
        host = info.host,
        port = info.port,
        prefix = info.prefix,
        rotation = info.rotation,
        width = info.width,
        height = info.height,
    }
end

local function copy_lease(info)
    if not info then
        return nil
    end
    return {
        version = info.version,
        serial = info.serial,
        mode = info.mode,
        host = info.host,
        port = info.port,
        prefix = info.prefix,
        remaining_ms = info.remaining_ms,
        owner = info.owner,
    }
end

local function default_lease_token(owner, callback_port)
    local identity = tostring({}):gsub("^table: ", "")
    return string.format("%s:%d:%s:%d", owner, callback_port, identity, os.time())
end

local function loopback_name(host)
    return host == "127.0.0.1" or host == "localhost" or host == "::1"
end

local function hosts_equal(left, right)
    return left == right or (loopback_name(left) and loopback_name(right))
end

local function append(destination, values)
    for _, value in ipairs(values) do
        table.insert(destination, value)
    end
end

function Session.new(options)
    options = options or {}
    assert(valid_string(options.owner), "session owner is required")
    assert(valid_port(options.callback_port, false), "callback port is required")

    local callback_host = options.callback_host or "127.0.0.1"
    local device_host = options.device_host or "127.0.0.1"
    local prefix = options.prefix or "/monome"
    local info_window_ms = options.info_window_ms or 120
    local protocol = options.protocol or "legacy"
    local lease_ttl_ms = options.lease_ttl_ms or 6000
    local lease_renew_ms = options.lease_renew_ms or 2000
    local lease_token = options.lease_token
        or default_lease_token(options.owner, options.callback_port)

    assert(valid_string(callback_host), "invalid callback host")
    assert(valid_string(device_host), "invalid device host")
    assert(valid_prefix(prefix), "invalid prefix")
    assert(valid_protocol(protocol), "invalid protocol")
    assert(is_integer(info_window_ms) and info_window_ms > 0,
        "invalid info window")
    assert(valid_ttl(lease_ttl_ms), "invalid lease TTL")
    assert(is_integer(lease_renew_ms) and lease_renew_ms > 0
        and lease_renew_ms < lease_ttl_ms, "invalid lease renewal interval")
    assert(valid_token(lease_token), "invalid lease token")

    return setmetatable({
        owner = options.owner,
        claims = options.claims or ClaimRegistry.new(),
        callback_host = callback_host,
        callback_port = options.callback_port,
        device_host = device_host,
        prefix = prefix,
        info_window_ms = info_window_ms,
        protocol = protocol,
        lease_token = lease_token,
        lease_ttl_ms = lease_ttl_ms,
        lease_renew_ms = lease_renew_ms,
        lease_supported = nil,
        lease_observed = nil,
        lease_active = false,
        renew_pending = false,
        transport = "stopped",
        state = "absent",
        selected = nil,
        observed = nil,
        request = nil,
        info_fields = nil,
        acquired = false,
        outputs = {},
    }, Session)
end

function Session:_emit(channel, selector, atoms)
    table.insert(self.outputs, {
        channel = channel,
        selector = selector,
        atoms = atoms or {},
    })
end

function Session:drain()
    local outputs = self.outputs
    self.outputs = {}
    return outputs
end

function Session:_error(code, atoms)
    local output = { code }
    append(output, atoms or {})
    self:_emit("status", "error", output)
    return nil, code
end

function Session:_set_state(state, reason)
    self.state = state
    local atoms = { state }
    if reason then
        table.insert(atoms, reason)
    end
    self:_emit("status", "state", atoms)
end

function Session:_release_local_claim()
    if self.acquired and self.selected then
        self.claims:release(self.selected.serial, self.owner)
    end
    self.acquired = false
end

function Session:_cancel_lease_liveness()
    if self.lease_active or self.renew_pending then
        self:_emit("control", "cancel_lease_timer", {})
    end
    self.lease_active = false
    self.renew_pending = false
end

function Session:_clear_remote_observation()
    self.observed = nil
    self.lease_supported = nil
    self.lease_observed = nil
end

function Session:start()
    if self.transport ~= "stopped" then
        return self:_error("transport_already_started")
    end
    self.transport = "starting"
    self:_emit("status", "transport", {
        "starting", self.callback_host, self.callback_port,
    })
    self:_emit("control", "bind", {
        self.callback_host, self.callback_port,
    })
    return true
end

function Session:transport_ready()
    if self.transport ~= "starting" then
        return self:_error("unexpected_transport_ready")
    end
    self.transport = "ready"
    self:_emit("status", "transport", {
        "ready", self.callback_host, self.callback_port,
    })
    return true
end

function Session:transport_error(code)
    if self.transport ~= "starting" then
        return self:_error("unexpected_transport_error")
    end
    self.transport = "stopped"
    self:_emit("control", "close", {})
    return self:_error(code or "transport_unavailable", {
        self.callback_host, self.callback_port,
    })
end

function Session:stop()
    if self.transport == "stopped" then
        self:_emit("status", "transport", { "stopped" })
        return true
    end
    if self.state == "connected" or self.state == "claiming"
        or self.state == "releasing" then
        return self:_error("release_required")
    end

    if self.state == "probing" then
        self:_set_state("available", "probe_cancelled")
    end
    self.request = nil
    self.info_fields = nil
    self.transport = "stopped"
    self:_emit("control", "cancel_info_timer", {})
    self:_cancel_lease_liveness()
    self:_emit("control", "close", {})
    self:_emit("status", "transport", { "stopped" })
    return true
end

function Session:select(serial, model, port)
    if not valid_string(serial) then
        return self:_error("invalid_serial")
    end
    if not valid_string(model) then
        return self:_error("invalid_model")
    end
    if not valid_port(port, false) then
        return self:_error("invalid_device_port")
    end
    if self.request then
        return self:_error("request_in_progress")
    end

    local previous = self.selected
    local endpoint_changed = previous ~= nil
        and (previous.serial ~= serial or previous.port ~= port)

    if self.selected and self.selected.serial ~= serial
        and (self.state == "connected" or self.state == "claiming"
            or self.state == "releasing") then
        return self:_error("release_required")
    end

    if self.selected and self.selected.serial == serial
        and self.acquired and self.selected.port ~= port then
        self:_release_local_claim()
        self:_cancel_lease_liveness()
        self:_set_state("displaced", "device_server_changed")
    end

    self.selected = {
        serial = serial,
        model = model,
        port = port,
    }
    self:_clear_remote_observation()
    self.request = nil
    self.info_fields = nil

    if self.state ~= "connected" and self.state ~= "claiming"
        and self.state ~= "releasing" then
        self:_set_state("available", "selected")
    end
    if endpoint_changed then
        self:_emit("control", "disconnect", {})
    end
    if previous == nil or endpoint_changed then
        self:_emit("control", "connect", { self.device_host, port })
    end
    self:_emit("status", "selected", { serial, model, port })
    return true
end

function Session:deselect()
    if self.state == "connected" or self.state == "claiming"
        or self.state == "releasing" then
        return self:_error("release_required")
    end
    local serial = self.selected and self.selected.serial or "none"
    if self.request then
        self:_emit("control", "cancel_info_timer", {})
    end
    self.selected = nil
    self:_clear_remote_observation()
    self.request = nil
    self.info_fields = nil
    self:_cancel_lease_liveness()
    self:_set_state("absent", "deselected")
    self:_emit("status", "deselected", { serial })
    self:_emit("control", "disconnect", {})
    return true
end

function Session:device_removed(serial)
    if not self.selected or self.selected.serial ~= serial then
        self:_emit("status", "ignored", { "remove", serial })
        return true
    end

    self:_release_local_claim()
    self.selected = nil
    self:_clear_remote_observation()
    self.request = nil
    self.info_fields = nil
    self:_emit("control", "cancel_info_timer", {})
    self:_cancel_lease_liveness()
    self:_emit("control", "disconnect", {})
    self:_set_state("absent", "device_removed")
    self:_emit("status", "device_removed", { serial })
    return true
end

function Session:set_prefix(prefix)
    if not valid_prefix(prefix) then
        return self:_error("invalid_prefix")
    end
    if self.state == "connected" or self.state == "claiming"
        or self.state == "releasing" then
        return self:_error("release_required")
    end
    self.prefix = prefix
    self:_emit("status", "prefix", { prefix })
    return true
end

function Session:set_protocol(protocol)
    if not valid_protocol(protocol) then
        return self:_error("invalid_protocol")
    end
    if self.state == "connected" or self.state == "claiming"
        or self.state == "releasing" or self.request then
        return self:_error("release_required")
    end
    self.protocol = protocol
    self.lease_supported = nil
    self.lease_observed = nil
    self:_emit("status", "protocol", { protocol })
    return true
end

function Session:_ready_for_request()
    if self.transport ~= "ready" then
        return nil, "transport_not_ready"
    end
    if not self.selected then
        return nil, "no_device_selected"
    end
    if self.request then
        return nil, "request_in_progress"
    end
    return true
end

function Session:_request_info(kind)
    self.request = kind
    self.lease_observed = nil
    if self.protocol == "lease" then
        if kind == "probe" then
            self.info_fields = {}
            self:_emit("osc", "/sys/info", {
                self.callback_host, self.callback_port,
            })
        else
            self.info_fields = nil
        end
        self:_emit("osc", "/sys/lease/info", {
            self.lease_token, self.callback_host, self.callback_port,
        })
    else
        self.info_fields = {}
        self:_emit("osc", "/sys/info", {
            self.callback_host, self.callback_port,
        })
    end
    self:_emit("control", "info_timer", { self.info_window_ms })
end

function Session:probe()
    local ready, err = self:_ready_for_request()
    if not ready then
        return self:_error(err)
    end
    if self.state ~= "available" and self.state ~= "displaced" then
        return self:_error("probe_not_allowed", { self.state })
    end

    self:_set_state("probing")
    self:_emit("status", "probe", {
        "begin", self.selected.serial, self.selected.port,
    })
    self:_request_info("probe")
    return true
end

function Session:_claim(takeover)
    local ready, err = self:_ready_for_request()
    if not ready then
        return self:_error(err)
    end
    if self.state ~= "available" then
        return self:_error("claim_not_allowed", { self.state })
    end
    if not self.observed or self.observed.id ~= self.selected.serial then
        return self:_error("probe_required")
    end

    if self.protocol == "lease" then
        if not self.lease_supported or not self.lease_observed then
            return self:_error("lease_unsupported")
        end
        if self.lease_observed.serial ~= self.selected.serial then
            return self:_error("lease_device_mismatch")
        end
        if self.lease_observed.mode == "legacy" and not takeover then
            return self:_error("takeover_required", {
                self.lease_observed.host,
                self.lease_observed.port,
                self.lease_observed.prefix,
            })
        end
        if self.lease_observed.mode == "leased"
            and self.lease_observed.owner ~= 1 then
            return self:_error("lease_busy")
        end
    end

    local acquired, claim_err = self.claims:acquire(
        self.selected.serial, self.owner
    )
    if not acquired then
        return self:_error(claim_err, { self.selected.serial })
    end
    self.acquired = true

    self:_set_state("claiming")
    self:_emit("status", "claim", { "begin", self.selected.serial })

    if self.protocol == "lease" then
        local path = self.lease_observed.mode == "legacy"
            and "/sys/lease/takeover" or "/sys/lease/acquire"
        self.request = "lease_grant"
        self.info_fields = nil
        self:_emit("osc", path, {
            self.lease_token,
            self.callback_host,
            self.callback_port,
            self.prefix,
            self.lease_ttl_ms,
        })
        self:_emit("control", "info_timer", { self.info_window_ms })
        return true
    end

    self:_emit("osc", "/sys/prefix", { self.prefix })
    self:_emit("osc", "/sys/host", { self.callback_host })
    self:_emit("osc", "/sys/port", { self.callback_port })
    self:_request_info("claim")
    return true
end

function Session:claim()
    return self:_claim(false)
end

function Session:takeover()
    if self.protocol ~= "lease" then
        return self:_error("takeover_requires_lease_protocol")
    end
    return self:_claim(true)
end

function Session:check()
    local ready, err = self:_ready_for_request()
    if not ready then
        return self:_error(err)
    end
    if self.state ~= "connected" then
        return self:_error("check_not_allowed", { self.state })
    end
    self:_emit("status", "check", { "begin", self.selected.serial })
    self:_request_info("verify")
    return true
end

function Session:renew()
    if self.protocol ~= "lease" then
        return self:_error("renew_requires_lease_protocol")
    end
    if self.state ~= "connected" or not self.lease_active then
        return self:_error("renew_not_connected", { self.state })
    end
    if self.renew_pending then
        self:_mark_displaced("renew_timeout", self.lease_observed or {})
        return nil, "renew_timeout"
    end

    self.renew_pending = true
    self:_emit("osc", "/sys/lease/renew", {
        self.lease_token,
        self.lease_ttl_ms,
        self.callback_host,
        self.callback_port,
    })
    self:_emit("control", "lease_timer", { self.lease_renew_ms })
    return true
end

function Session:device_osc(address, atoms)
    if self.state ~= "connected" then
        return self:_error("capability_requires_connected", { self.state })
    end
    if not valid_string(address)
        or address:sub(1, #self.prefix + 1) ~= self.prefix .. "/" then
        return self:_error("capability_prefix_mismatch", {
            address or "invalid", self.prefix,
        })
    end

    atoms = atoms or {}
    for _, atom in ipairs(atoms) do
        if type(atom) ~= "string" and type(atom) ~= "number" then
            return self:_error("unsupported_capability_atom")
        end
    end
    self:_emit("osc", address, atoms)
    return true
end

function Session:release()
    if not self.selected then
        return self:_error("no_device_selected")
    end
    if self.request then
        return self:_error("request_in_progress")
    end

    if self.protocol == "lease" then
        if self.state == "available" then
            if not self.lease_observed then
                return self:_error("probe_required")
            end
            if self.lease_observed.mode == "free"
                and self.lease_observed.port == 0 then
                self:_emit("status", "released", {
                    self.selected.serial, "verified_already_zero",
                })
            else
                self:_emit("status", "release_skipped", {
                    self.selected.serial,
                    "destination_not_owned",
                    self.lease_observed.host,
                    self.lease_observed.port,
                    self.lease_observed.prefix,
                })
            end
            return true
        end
        if self.state == "displaced" then
            self:_release_local_claim()
            self:_cancel_lease_liveness()
            self:_set_state("available", "release_skipped")
            self:_emit("status", "release_skipped", {
                self.selected.serial, "displaced",
            })
            return true
        end
        local ready, err = self:_ready_for_request()
        if not ready then
            return self:_error(err)
        end
        if self.state ~= "connected" or not self.lease_active then
            return self:_error("release_not_allowed", { self.state })
        end

        self:_cancel_lease_liveness()
        self:_set_state("releasing")
        self:_emit("status", "release", { "begin", self.selected.serial })
        self.request = "lease_release"
        self:_emit("osc", "/sys/lease/release", {
            self.lease_token, self.callback_host, self.callback_port,
        })
        self:_emit("control", "info_timer", { self.info_window_ms })
        return true
    end

    if self.state == "available" then
        if not self.observed then
            return self:_error("probe_required")
        end

        if self:_matches_claim(self.observed) then
            local ready, err = self:_ready_for_request()
            if not ready then
                return self:_error(err)
            end
            local acquired, claim_err = self.claims:acquire(
                self.selected.serial, self.owner
            )
            if not acquired then
                return self:_error(claim_err, { self.selected.serial })
            end
            self.acquired = true
            self:_set_state("releasing", "stale_self_destination")
            self:_emit("status", "release", {
                "begin", self.selected.serial, "stale_self_destination",
            })
            self:_request_info("release")
            return true
        end

        if self.observed.port == 0 then
            self:_emit("status", "released", {
                self.selected.serial, "verified_already_zero",
            })
        else
            self:_emit("status", "release_skipped", {
                self.selected.serial,
                "destination_not_owned",
                self.observed.host,
                self.observed.port,
                self.observed.prefix,
            })
        end
        return true
    end
    if self.state == "displaced" then
        self:_release_local_claim()
        self:_set_state("available", "release_skipped")
        self:_emit("status", "release_skipped", {
            self.selected.serial, "displaced",
        })
        return true
    end

    local ready, err = self:_ready_for_request()
    if not ready then
        return self:_error(err)
    end
    if self.state ~= "connected" then
        return self:_error("release_not_allowed", { self.state })
    end

    self:_set_state("releasing")
    self:_emit("status", "release", { "begin", self.selected.serial })
    self:_request_info("release")
    return true
end

function Session:info(field, atoms)
    if not self.request then
        self:_emit("status", "ignored", { "unsolicited_info", field })
        return true
    end
    if not self.info_fields then
        self:_emit("status", "ignored", { "legacy_info_during_lease", field })
        return true
    end
    atoms = atoms or {}

    if field == "id" or field == "host" or field == "prefix" then
        if #atoms ~= 1 or not valid_string(atoms[1]) then
            return self:_error("invalid_info_" .. field)
        end
        self.info_fields[field] = atoms[1]
    elseif field == "port" then
        if #atoms ~= 1 or not valid_port(atoms[1], true) then
            return self:_error("invalid_info_port")
        end
        self.info_fields.port = atoms[1]
    elseif field == "rotation" then
        if #atoms ~= 1 or not is_integer(atoms[1]) then
            return self:_error("invalid_info_rotation")
        end
        self.info_fields.rotation = atoms[1]
    elseif field == "size" then
        if #atoms ~= 2 or not valid_size(atoms[1], atoms[2]) then
            return self:_error("invalid_info_size")
        end
        self.info_fields.width = atoms[1]
        self.info_fields.height = atoms[2]
    else
        return self:_error("unknown_info_field", { field })
    end
    return true
end

function Session:lease_state(atoms)
    if self.protocol ~= "lease" then
        self:_emit("status", "ignored", { "lease_state_in_legacy_mode" })
        return true
    end
    if not self.request then
        self:_emit("status", "ignored", { "unsolicited_lease_state" })
        return true
    end
    atoms = atoms or {}
    if #atoms ~= 8
        or not is_integer(atoms[1])
        or not valid_string(atoms[2])
        or (atoms[3] ~= "free" and atoms[3] ~= "legacy"
            and atoms[3] ~= "leased")
        or not valid_string(atoms[4])
        or not valid_port(atoms[5], true)
        or not valid_prefix(atoms[6])
        or not is_integer(atoms[7]) or atoms[7] < 0
        or (atoms[8] ~= 0 and atoms[8] ~= 1) then
        return self:_error("invalid_lease_state")
    end
    if atoms[1] ~= 1 then
        self.lease_supported = false
        return self:_error("unsupported_lease_version", { atoms[1] })
    end
    if (atoms[3] == "free" and atoms[5] ~= 0)
        or (atoms[3] ~= "free" and atoms[5] == 0)
        or (atoms[3] ~= "leased" and atoms[8] ~= 0) then
        return self:_error("inconsistent_lease_state")
    end

    self.lease_supported = true
    self.lease_observed = {
        version = atoms[1],
        serial = atoms[2],
        mode = atoms[3],
        host = atoms[4],
        port = atoms[5],
        prefix = atoms[6],
        remaining_ms = atoms[7],
        owner = atoms[8],
    }
    return true
end

function Session:lease_granted(token, ttl_ms)
    if self.protocol ~= "lease" or self.request ~= "lease_grant" then
        self:_emit("status", "ignored", { "unsolicited_lease_granted" })
        return true
    end
    if token ~= self.lease_token or not valid_ttl(ttl_ms) then
        return self:_error("invalid_lease_grant")
    end

    self:_emit("control", "cancel_info_timer", {})
    self.request = nil
    self.lease_active = true
    self.renew_pending = false
    self:_request_info("claim")
    return true
end

function Session:lease_renewed(token, ttl_ms)
    if self.protocol ~= "lease" or token ~= self.lease_token
        or not self.lease_active or self.state ~= "connected" then
        self:_emit("status", "ignored", { "unsolicited_lease_renewed" })
        return true
    end
    if not valid_ttl(ttl_ms) then
        return self:_error("invalid_lease_renewal")
    end
    self.renew_pending = false
    self:_emit("status", "lease", { "renewed", ttl_ms })
    return true
end

function Session:lease_released(token)
    if self.protocol ~= "lease" or self.request ~= "lease_release" then
        self:_emit("status", "ignored", { "unsolicited_lease_released" })
        return true
    end
    if token ~= self.lease_token then
        return self:_error("invalid_lease_release")
    end

    self:_emit("control", "cancel_info_timer", {})
    self.request = nil
    self:_request_info("release_verify")
    return true
end

function Session:lease_rejected(token, reason)
    if self.protocol ~= "lease" or token ~= self.lease_token
        or not valid_string(reason) then
        self:_emit("status", "ignored", { "unrelated_lease_rejection" })
        return true
    end

    if self.request == "lease_grant" then
        self:_emit("control", "cancel_info_timer", {})
        self.request = nil
        self:_release_local_claim()
        self:_cancel_lease_liveness()
        self:_set_state("available", "lease_rejected")
        return self:_error("lease_rejected", { reason })
    end
    if self.request == "lease_release" then
        self:_emit("control", "cancel_info_timer", {})
        self.request = nil
        self:_request_info("release_verify")
        return true
    end
    if self.renew_pending then
        self.renew_pending = false
        self:_mark_displaced("renew_rejected_" .. reason,
            self.lease_observed or {})
        return nil, reason
    end

    self:_emit("status", "ignored", { "unsolicited_lease_rejected", reason })
    return true
end

function Session:lease_lost(token, reason)
    if self.protocol ~= "lease" or token ~= self.lease_token
        or not valid_string(reason) then
        self:_emit("status", "ignored", { "unrelated_lease_lost" })
        return true
    end
    if not self.selected or (not self.lease_active
        and self.state ~= "claiming" and self.state ~= "releasing") then
        self:_emit("status", "ignored", { "stale_lease_lost" })
        return true
    end
    if self.request then
        self:_emit("control", "cancel_info_timer", {})
        self.request = nil
        self.info_fields = nil
    end
    self:_mark_displaced("lease_lost_" .. reason,
        self.lease_observed or {})
    return true
end

function Session:_info_atoms(info)
    return {
        info.id,
        info.host,
        info.port,
        info.prefix,
        info.rotation or -1,
        info.width or 0,
        info.height or 0,
    }
end

function Session:_info_complete(info)
    return valid_string(info.id)
        and valid_string(info.host)
        and valid_port(info.port, true)
        and valid_prefix(info.prefix)
end

function Session:_matches_claim(info)
    return info.id == self.selected.serial
        and hosts_equal(info.host, self.callback_host)
        and info.port == self.callback_port
        and info.prefix == self.prefix
end

function Session:_matches_lease(info)
    return info and info.version == 1
        and info.serial == self.selected.serial
        and info.mode == "leased"
        and info.owner == 1
        and hosts_equal(info.host, self.callback_host)
        and info.port == self.callback_port
        and info.prefix == self.prefix
end

function Session:_mark_displaced(reason, info)
    if self.request then
        self:_emit("control", "cancel_info_timer", {})
        self.request = nil
        self.info_fields = nil
    end
    self:_release_local_claim()
    self:_cancel_lease_liveness()
    if self.protocol == "lease" then
        self.lease_observed = copy_lease(info)
        if self.observed then
            self.observed.host = info.host or self.observed.host
            self.observed.port = info.port or self.observed.port
            self.observed.prefix = info.prefix or self.observed.prefix
        end
    else
        self.observed = copy_info(info)
    end
    self:_set_state("displaced", reason)
    self:_emit("status", "displaced", {
        self.selected.serial,
        reason,
        self.callback_host,
        self.callback_port,
        self.prefix,
        info.host or "unknown",
        info.port or -1,
        info.prefix or "unknown",
    })
end

function Session:info_end()
    if not self.request then
        return self:_error("no_info_request")
    end

    local request = self.request
    local info = self.info_fields
    local lease = self.lease_observed
    self.request = nil
    self.info_fields = nil
    self:_emit("control", "cancel_info_timer", {})

    if request == "lease_grant" then
        self:_mark_displaced("lease_grant_timeout", lease or {})
        return self:_error("lease_grant_timeout")
    end

    if request == "lease_release" then
        self:_request_info("release_verify")
        return true
    end

    if self.protocol == "lease" and request ~= "probe" then
        if not lease then
            self:_mark_displaced(request .. "_unverified", {})
            return self:_error("lease_state_incomplete", { request })
        end
        if lease.serial ~= self.selected.serial then
            self:_mark_displaced(request .. "_id_mismatch", lease)
            return self:_error("lease_id_mismatch", {
                self.selected.serial, lease.serial,
            })
        end

        if request == "claim" then
            if self:_matches_lease(lease) then
                self.lease_active = true
                self.renew_pending = false
                self.observed.host = lease.host
                self.observed.port = lease.port
                self.observed.prefix = lease.prefix
                self:_set_state("connected", "verified_lease")
                self:_emit("status", "connected", self:_info_atoms(self.observed))
                self:_emit("control", "lease_timer", {
                    self.lease_renew_ms,
                })
                return true
            end
            self:_mark_displaced("lease_claim_verification_failed", lease)
            return nil, "lease_claim_verification_failed"
        end

        if request == "verify" then
            if self:_matches_lease(lease) then
                self.lease_observed = copy_lease(lease)
                self.observed.host = lease.host
                self.observed.port = lease.port
                self.observed.prefix = lease.prefix
                self:_set_state("connected", "verified_lease")
                self:_emit("status", "verified", self:_info_atoms(self.observed))
                return true
            end
            self:_mark_displaced("lease_changed", lease)
            return nil, "lease_changed"
        end

        if request == "release_verify" then
            if lease.mode == "free" and lease.port == 0 then
                self:_release_local_claim()
                self:_cancel_lease_liveness()
                self.lease_observed = copy_lease(lease)
                if self.observed then
                    self.observed.host = lease.host
                    self.observed.port = 0
                    self.observed.prefix = lease.prefix
                end
                self:_set_state("available", "released")
                self:_emit("status", "released", {
                    self.selected.serial, "verified_lease_free",
                })
                return true
            end
            self:_mark_displaced("release_not_free", lease)
            self:_emit("status", "release_skipped", {
                self.selected.serial, "lease_state_changed",
            })
            return nil, "release_not_free"
        end

        return self:_error("unknown_lease_info_request", { request })
    end

    if not self:_info_complete(info) then
        if request == "probe" then
            self:_set_state("available", "probe_incomplete")
        else
            self:_mark_displaced(request .. "_unverified", info)
        end
        return self:_error("info_incomplete", { request })
    end

    if info.id ~= self.selected.serial then
        if request == "probe" then
            self:_set_state("available", "probe_id_mismatch")
        else
            self:_mark_displaced(request .. "_id_mismatch", info)
        end
        return self:_error("info_id_mismatch", {
            self.selected.serial, info.id,
        })
    end

    self.observed = copy_info(info)

    if request == "probe" then
        if self.protocol == "lease" then
            if lease and lease.serial ~= self.selected.serial then
                self.lease_supported = false
                self.lease_observed = nil
                self:_set_state("available", "lease_id_mismatch")
                return self:_error("lease_id_mismatch", {
                    self.selected.serial, lease.serial,
                })
            end
            self.lease_supported = lease ~= nil
            self:_emit("status", "lease", {
                lease and "supported" or "unsupported",
                lease and lease.mode or "none",
            })
        end
        self:_set_state("available", "probed")
        self:_emit("status", "probed", self:_info_atoms(info))
        return true
    end

    if request == "claim" then
        if self:_matches_claim(info) then
            self:_set_state("connected", "verified_claim")
            self:_emit("status", "connected", self:_info_atoms(info))
            return true
        end
        self:_mark_displaced("claim_verification_failed", info)
        return nil, "claim_verification_failed"
    end

    if request == "verify" then
        if self:_matches_claim(info) then
            self:_set_state("connected", "verified")
            self:_emit("status", "verified", self:_info_atoms(info))
            return true
        end
        self:_mark_displaced("destination_changed", info)
        return nil, "destination_changed"
    end

    if request == "release" then
        if self:_matches_claim(info) then
            self:_emit("osc", "/sys/port", { 0 })
            self:_release_local_claim()
            self.observed.port = 0
            self:_set_state("available", "released")
            self:_emit("status", "released", {
                self.selected.serial, "verified",
            })
            return true
        end
        self:_mark_displaced("release_ownership_lost", info)
        self:_emit("status", "release_skipped", {
            self.selected.serial, "destination_changed",
        })
        return nil, "release_ownership_lost"
    end

    return self:_error("unknown_info_request", { request })
end

function Session:snapshot()
    self:_emit("status", "snapshot", {
        self.state,
        self.transport,
        self.selected and self.selected.serial or "none",
        self.selected and self.selected.model or "none",
        self.selected and self.selected.port or 0,
        self.prefix,
        self.acquired and 1 or 0,
        self.protocol,
        self.lease_active and 1 or 0,
        self.lease_supported and 1 or 0,
    })
    return true
end

function Session:abandon()
    self:_release_local_claim()
    self.lease_active = false
    self.renew_pending = false
    self.request = nil
    self.info_fields = nil
end

return {
    ClaimRegistry = ClaimRegistry,
    Session = Session,
}

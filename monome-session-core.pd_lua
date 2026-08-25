local MonomeSessionCore = pd.Class:new():register("monome-session-core")

local Core = nil
local process_claims = nil
local next_owner = 0

local outlet_for_channel = {
    status = 1,
    osc = 2,
    control = 3,
}

function MonomeSessionCore:initialize(_, atoms)
    if not Core then
        Core = dofile(self._loadpath .. "monome_session.lua")
        process_claims = Core.ClaimRegistry.new()
    end

    local callback_port = atoms[1]
    local info_window_ms = atoms[2] or 120
    local prefix = atoms[3] or "/monome"
    if type(callback_port) ~= "number" then
        self:error("monome-session-core: callback port is required")
        return false
    end

    next_owner = next_owner + 1
    self.owner = "pd-session-" .. tostring(next_owner)
    self.session = Core.Session.new({
        owner = self.owner,
        claims = process_claims,
        callback_port = callback_port,
        info_window_ms = info_window_ms,
        prefix = prefix,
    })
    self.inlets = 1
    self.outlets = 3
    return true
end

function MonomeSessionCore:_dispatch()
    for _, output in ipairs(self.session:drain()) do
        local outlet = outlet_for_channel[output.channel]
        if outlet then
            self:outlet(outlet, output.selector, output.atoms)
        else
            self:error("monome-session-core: unknown output channel")
        end
    end
end

function MonomeSessionCore:_call(method, ...)
    self.session[method](self.session, ...)
    self:_dispatch()
end

function MonomeSessionCore:in_1_start()
    self:_call("start")
end

function MonomeSessionCore:in_1_stop()
    self:_call("stop")
end

function MonomeSessionCore:in_1_select(atoms)
    if #atoms ~= 3 then
        self.session:_error("select_requires_serial_model_port")
        self:_dispatch()
        return
    end
    self:_call("select", atoms[1], atoms[2], atoms[3])
end

function MonomeSessionCore:in_1_deselect()
    self:_call("deselect")
end

function MonomeSessionCore:in_1_remove(atoms)
    if #atoms ~= 1 then
        self.session:_error("remove_requires_serial")
        self:_dispatch()
        return
    end
    self:_call("device_removed", atoms[1])
end

function MonomeSessionCore:in_1_prefix(atoms)
    if #atoms ~= 1 then
        self.session:_error("prefix_requires_value")
        self:_dispatch()
        return
    end
    self:_call("set_prefix", atoms[1])
end

function MonomeSessionCore:in_1_probe()
    self:_call("probe")
end

function MonomeSessionCore:in_1_claim()
    self:_call("claim")
end

function MonomeSessionCore:in_1_check()
    self:_call("check")
end

function MonomeSessionCore:in_1_release()
    self:_call("release")
end

function MonomeSessionCore:in_1_transport_ready()
    self:_call("transport_ready")
end

function MonomeSessionCore:in_1_transport_error(atoms)
    self:_call("transport_error", atoms[1] or "transport_unavailable")
end

function MonomeSessionCore:in_1_info_id(atoms)
    self:_call("info", "id", atoms)
end

function MonomeSessionCore:in_1_info_size(atoms)
    self:_call("info", "size", atoms)
end

function MonomeSessionCore:in_1_info_host(atoms)
    self:_call("info", "host", atoms)
end

function MonomeSessionCore:in_1_info_port(atoms)
    self:_call("info", "port", atoms)
end

function MonomeSessionCore:in_1_info_prefix(atoms)
    self:_call("info", "prefix", atoms)
end

function MonomeSessionCore:in_1_info_rotation(atoms)
    self:_call("info", "rotation", atoms)
end

function MonomeSessionCore:in_1_info_end()
    self:_call("info_end")
end

function MonomeSessionCore:in_1_bang()
    self:_call("snapshot")
end

function MonomeSessionCore:finalize()
    if self.session then
        local state = self.session.state
        self.session:abandon()
        if state == "connected" or state == "claiming" or state == "releasing" then
            pd.post(
                "monome-session-core: destroyed without verified release; "
                .. "remote destination is unknown"
            )
        end
    end
end

local MonomeArcCore = pd.Class:new():register("monome-arc-core")

local Core = nil

local outlet_for_channel = {
    event = 1,
    status = 2,
    osc = 3,
    control = 4,
    passthrough = 5,
}

function MonomeArcCore:initialize(_, atoms)
    if not Core then
        Core = dofile(self._loadpath .. "monome_arc.lua")
    end

    local rings = atoms[1]
    if rings ~= 2 and rings ~= 4 then
        self:error("monome-arc-core: explicit ring count must be 2 or 4")
        return false
    end

    self.rings = rings
    self.arc = Core.Arc.new(rings)
    self.inlets = 3
    self.outlets = 5
    return true
end

function MonomeArcCore:_dispatch()
    for _, output in ipairs(self.arc:drain()) do
        local outlet = outlet_for_channel[output.channel]
        if outlet then
            self:outlet(outlet, output.selector, output.atoms)
        else
            self:error("monome-arc-core: unknown output channel")
        end
    end
end

function MonomeArcCore:_call(method, ...)
    self.arc[method](self.arc, ...)
    self:_dispatch()
end

function MonomeArcCore:in_1(sel, atoms)
    atoms = atoms or {}
    if sel == "attach" then
        if #atoms ~= 2 then
            self.arc:_error("attach_requires_serial_prefix")
        else
            self.arc:attach(atoms[1], atoms[2], self.rings)
        end
    elseif sel == "detach" then
        self.arc:detach(atoms[1] or "manual")
    elseif sel == "led" or sel == "level" then
        if #atoms ~= 3 then
            self.arc:_error("led_requires_ring_position_level")
        else
            self.arc:level(atoms[1], atoms[2], atoms[3])
        end
    elseif sel == "map" then
        if #atoms ~= 65 then
            self.arc:_error("map_requires_ring_and_64_levels")
        else
            local levels = {}
            for index = 2, #atoms do
                table.insert(levels, atoms[index])
            end
            self.arc:map(atoms[1], levels)
        end
    elseif sel == "all" then
        if #atoms ~= 1 then
            self.arc:_error("all_requires_level")
        else
            self.arc:all(atoms[1])
        end
    elseif sel == "clear" then
        self.arc:clear()
    elseif sel == "flush" then
        self.arc:flush()
    elseif sel == "prepare_release" then
        self.arc:prepare_release()
    elseif sel == "bang" or sel == "snapshot" then
        self.arc:snapshot()
    else
        self.arc:_error("unknown_arc_command", { sel })
    end
    self:_dispatch()
end

function MonomeArcCore:in_2(sel, atoms)
    self:_call("input", sel, atoms)
end

function MonomeArcCore:in_3(sel, atoms)
    self:_call("session", sel, atoms)
end

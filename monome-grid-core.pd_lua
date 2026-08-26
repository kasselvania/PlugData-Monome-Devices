local MonomeGridCore = pd.Class:new():register("monome-grid-core")

local Core = nil

local outlet_for_channel = {
    event = 1,
    status = 2,
    osc = 3,
    control = 4,
    passthrough = 5,
}

function MonomeGridCore:initialize(_, _)
    if not Core then
        Core = dofile(self._loadpath .. "monome_grid.lua")
    end
    self.grid = Core.Grid.new()
    self.inlets = 3
    self.outlets = 5
    return true
end

function MonomeGridCore:_dispatch()
    for _, output in ipairs(self.grid:drain()) do
        local outlet = outlet_for_channel[output.channel]
        if outlet then
            self:outlet(outlet, output.selector, output.atoms)
        else
            self:error("monome-grid-core: unknown output channel")
        end
    end
end

function MonomeGridCore:_call(method, ...)
    self.grid[method](self.grid, ...)
    self:_dispatch()
end

function MonomeGridCore:in_1(sel, atoms)
    atoms = atoms or {}
    if sel == "attach" then
        if #atoms ~= 4 then
            self.grid:_error("attach_requires_serial_prefix_width_height")
        else
            self.grid:attach(atoms[1], atoms[2], atoms[3], atoms[4])
        end
    elseif sel == "detach" then
        self.grid:detach(atoms[1] or "manual")
    elseif sel == "led" or sel == "level" then
        if #atoms ~= 3 then
            self.grid:_error("led_requires_x_y_level")
        else
            self.grid:level(atoms[1], atoms[2], atoms[3])
        end
    elseif sel == "all" then
        if #atoms ~= 1 then
            self.grid:_error("all_requires_level")
        else
            self.grid:all(atoms[1])
        end
    elseif sel == "clear" then
        self.grid:all(0)
    elseif sel == "map" then
        if #atoms ~= 66 then
            self.grid:_error("map_requires_offsets_and_64_levels")
        else
            local levels = {}
            for index = 3, #atoms do
                table.insert(levels, atoms[index])
            end
            self.grid:map(atoms[1], atoms[2], levels)
        end
    elseif sel == "flush" then
        self.grid:flush()
    elseif sel == "prepare_release" then
        self.grid:prepare_release()
    elseif sel == "bang" or sel == "snapshot" then
        self.grid:snapshot()
    else
        self.grid:_error("unknown_grid_command", { sel })
    end
    self:_dispatch()
end

function MonomeGridCore:in_2(sel, atoms)
    self:_call("input", sel, atoms)
end

function MonomeGridCore:in_3(sel, atoms)
    self:_call("session", sel, atoms)
end

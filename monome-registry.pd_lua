local MonomeRegistry = pd.Class:new():register("monome-registry")

local function device_atoms(device)
    return { device.serial, device.model, device.port }
end

function MonomeRegistry:initialize(_, _)
    local Registry = dofile(self._loadpath .. "monome_registry.lua")
    self.registry = Registry.new()
    self.inlets = 1
    self.outlets = 2
    return true
end

function MonomeRegistry:_error(code)
    self:error("monome-registry: " .. code)
    self:outlet(1, "error", { code })
end

function MonomeRegistry:_emit_menu()
    self:outlet(2, "clear", {})

    local selected = self.registry:selection()
    for index, device in ipairs(self.registry:snapshot()) do
        self:outlet(2, "append", {
            index - 1,
            device.serial,
            device.model,
            device.port,
        })

        if selected and selected.serial == device.serial then
            self:outlet(2, "select", { index - 1 })
        end
    end

    if not selected then
        self:outlet(2, "select", { -1 })
    end
end

function MonomeRegistry:in_1_scan_begin(_)
    self.registry:begin_scan()
    self:outlet(1, "scan", { "begin" })
end

function MonomeRegistry:in_1_device(atoms)
    if #atoms ~= 3 then
        self:_error("device_requires_serial_model_port")
        return
    end

    local change, device_or_error = self.registry:upsert(
        atoms[1], atoms[2], atoms[3]
    )
    if not change then
        self:_error(device_or_error)
        return
    end

    local atoms_out = { change }
    for _, atom in ipairs(device_atoms(device_or_error)) do
        table.insert(atoms_out, atom)
    end
    self:outlet(1, "device", atoms_out)
    self:_emit_menu()
end

function MonomeRegistry:in_1_scan_end(_)
    local result, err = self.registry:end_scan()
    if not result then
        self:_error(err)
        return
    end

    for _, serial in ipairs(result.removed) do
        self:outlet(1, "removed", { serial, "scan" })
    end
    if result.selection_lost then
        self:outlet(1, "selection_lost", {
            result.selection_lost,
            "scan",
        })
    end

    self:outlet(1, "scan", { "end" })
    self:_emit_menu()
end

function MonomeRegistry:in_1_remove(atoms)
    if #atoms ~= 1 then
        self:_error("remove_requires_serial")
        return
    end

    local result, err = self.registry:remove(atoms[1])
    if not result then
        self:_error(err)
        return
    end

    if result.removed then
        self:outlet(1, "removed", { result.removed.serial, "notify" })
    end
    if result.selection_lost then
        self:outlet(1, "selection_lost", {
            result.selection_lost,
            "notify",
        })
    end

    self:_emit_menu()
end

function MonomeRegistry:in_1_select(atoms)
    if #atoms ~= 1 then
        self:_error("select_requires_serial")
        return
    end

    if atoms[1] == "none" then
        local previous = self.registry:deselect()
        self:outlet(1, "deselected", { previous or "none" })
        self:_emit_menu()
        return
    end

    local selected, err = self.registry:select(atoms[1])
    if not selected then
        self:_error(err)
        return
    end

    self:outlet(1, "selected", device_atoms(selected))
    self:_emit_menu()
end

function MonomeRegistry:in_1_select_index(atoms)
    if #atoms ~= 1 then
        self:_error("select_index_requires_index")
        return
    end

    local selected, err = self.registry:select_index(atoms[1])
    if not selected then
        self:_error(err)
        return
    end

    self:outlet(1, "selected", device_atoms(selected))
    self:_emit_menu()
end

function MonomeRegistry:in_1_clear(_)
    local previous = self.registry:clear()
    if previous then
        self:outlet(1, "selection_lost", { previous, "clear" })
    end
    self:outlet(1, "cleared", {})
    self:_emit_menu()
end

function MonomeRegistry:in_1_bang()
    self:outlet(1, "snapshot", { "begin" })
    for _, device in ipairs(self.registry:snapshot()) do
        local atoms_out = { "snapshot" }
        for _, atom in ipairs(device_atoms(device)) do
            table.insert(atoms_out, atom)
        end
        self:outlet(1, "device", atoms_out)
    end

    local selected = self.registry:selection()
    if selected then
        self:outlet(1, "selected", device_atoms(selected))
    else
        self:outlet(1, "selected", { "none" })
    end
    self:outlet(1, "snapshot", { "end" })
end

local Registry = {}
Registry.__index = Registry

local function copy_device(device)
    if not device then
        return nil
    end

    return {
        serial = device.serial,
        model = device.model,
        port = device.port,
    }
end

local function validate_device(serial, model, port)
    if type(serial) ~= "string" or serial == "" then
        return nil, "invalid_serial"
    end

    if type(model) ~= "string" or model == "" then
        return nil, "invalid_model"
    end

    if type(port) ~= "number" or port ~= math.floor(port)
        or port < 1 or port > 65535 then
        return nil, "invalid_port"
    end

    return true
end

function Registry.new()
    return setmetatable({
        devices = {},
        selected_serial = nil,
        scanning = false,
        seen = {},
    }, Registry)
end

function Registry:begin_scan()
    self.scanning = true
    self.seen = {}
end

function Registry:upsert(serial, model, port)
    local valid, err = validate_device(serial, model, port)
    if not valid then
        return nil, err
    end

    local previous = self.devices[serial]
    local change = "added"

    if previous then
        if previous.model == model and previous.port == port then
            change = "unchanged"
        else
            change = "updated"
        end
    end

    self.devices[serial] = {
        serial = serial,
        model = model,
        port = port,
    }

    if self.scanning then
        self.seen[serial] = true
    end

    return change, copy_device(self.devices[serial])
end

function Registry:end_scan()
    if not self.scanning then
        return nil, "scan_not_active"
    end

    local removed = {}
    for serial in pairs(self.devices) do
        if not self.seen[serial] then
            table.insert(removed, serial)
        end
    end
    table.sort(removed)

    for _, serial in ipairs(removed) do
        self.devices[serial] = nil
    end

    local selection_lost = nil
    if self.selected_serial and not self.devices[self.selected_serial] then
        selection_lost = self.selected_serial
        self.selected_serial = nil
    end

    self.scanning = false
    self.seen = {}

    return {
        removed = removed,
        selection_lost = selection_lost,
    }
end

function Registry:remove(serial)
    if type(serial) ~= "string" or serial == "" then
        return nil, "invalid_serial"
    end

    local removed = self.devices[serial]
    if not removed then
        return {
            removed = nil,
            selection_lost = nil,
        }
    end

    self.devices[serial] = nil
    self.seen[serial] = nil

    local selection_lost = nil
    if self.selected_serial == serial then
        selection_lost = serial
        self.selected_serial = nil
    end

    return {
        removed = copy_device(removed),
        selection_lost = selection_lost,
    }
end

function Registry:select(serial)
    if type(serial) ~= "string" or serial == "" then
        return nil, "invalid_serial"
    end

    local device = self.devices[serial]
    if not device then
        return nil, "unknown_device"
    end

    self.selected_serial = serial
    return copy_device(device)
end

function Registry:deselect()
    local previous = self.selected_serial
    self.selected_serial = nil
    return previous
end

function Registry:select_index(index)
    if type(index) ~= "number" or index ~= math.floor(index) or index < 0 then
        return nil, "invalid_index"
    end

    local devices = self:snapshot()
    local device = devices[index + 1]
    if not device then
        return nil, "unknown_index"
    end

    return self:select(device.serial)
end

function Registry:selection()
    if not self.selected_serial then
        return nil
    end
    return copy_device(self.devices[self.selected_serial])
end

function Registry:snapshot()
    local devices = {}
    for _, device in pairs(self.devices) do
        table.insert(devices, copy_device(device))
    end

    table.sort(devices, function(left, right)
        return left.serial < right.serial
    end)

    return devices
end

function Registry:menu_projection()
    local projection = {
        items = {},
        selected_index = -1,
    }

    for index, device in ipairs(self:snapshot()) do
        local display_model = device.model:gsub("%s+", "-")
        table.insert(
            projection.items,
            device.serial .. "__" .. display_model
        )
        if device.serial == self.selected_serial then
            projection.selected_index = index - 1
        end
    end

    return projection
end

function Registry:clear()
    local previous_selection = self.selected_serial
    self.devices = {}
    self.selected_serial = nil
    self.scanning = false
    self.seen = {}
    return previous_selection
end

return Registry

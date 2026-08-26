local Grid = {}
Grid.__index = Grid

local MAX_WIDTH = 16
local MAX_HEIGHT = 16
local QUAD_SIZE = 8

local function is_integer(value)
    return type(value) == "number" and value == math.floor(value)
end

local function valid_string(value)
    return type(value) == "string" and value ~= ""
        and not value:find("\0", 1, true)
end

local function valid_prefix(value)
    return valid_string(value) and value:sub(1, 1) == "/"
        and value:sub(-1) ~= "/"
end

local function valid_dimension(value, maximum)
    return is_integer(value) and value >= QUAD_SIZE and value <= maximum
        and value % QUAD_SIZE == 0
end

local function append(destination, values)
    for _, value in ipairs(values) do
        table.insert(destination, value)
    end
end

function Grid.new()
    local levels = {}
    local keys = {}
    for index = 1, MAX_WIDTH * MAX_HEIGHT do
        levels[index] = 0
        keys[index] = 0
    end

    return setmetatable({
        active = false,
        serial = nil,
        prefix = nil,
        width = nil,
        height = nil,
        levels = levels,
        keys = keys,
        dirty = {},
        outputs = {},
    }, Grid)
end

function Grid:_emit(channel, selector, atoms)
    table.insert(self.outputs, {
        channel = channel,
        selector = selector,
        atoms = atoms or {},
    })
end

function Grid:drain()
    local outputs = self.outputs
    self.outputs = {}
    return outputs
end

function Grid:_error(code, atoms)
    local output = { code }
    append(output, atoms or {})
    self:_emit("status", "error", output)
    return nil, code
end

function Grid:_index(x, y)
    return (y * MAX_WIDTH) + x + 1
end

function Grid:_reset_buffers()
    for index = 1, MAX_WIDTH * MAX_HEIGHT do
        self.levels[index] = 0
        self.keys[index] = 0
    end
    self.dirty = {}
end

function Grid:_mark_dirty(x, y)
    local x_offset = math.floor(x / QUAD_SIZE) * QUAD_SIZE
    local y_offset = math.floor(y / QUAD_SIZE) * QUAD_SIZE
    self.dirty[y_offset * MAX_WIDTH + x_offset] = true
end

function Grid:_mark_all_dirty()
    for y_offset = 0, self.height - 1, QUAD_SIZE do
        for x_offset = 0, self.width - 1, QUAD_SIZE do
            self.dirty[y_offset * MAX_WIDTH + x_offset] = true
        end
    end
end

function Grid:_ready()
    if not self.active then
        return nil, "grid_not_attached"
    end
    return true
end

function Grid:_valid_coordinate(x, y)
    return is_integer(x) and is_integer(y)
        and x >= 0 and y >= 0 and x < self.width and y < self.height
end

function Grid:_release_held_keys(reason)
    local released = 0
    if self.width and self.height then
        for y = 0, self.height - 1 do
            for x = 0, self.width - 1 do
                local index = self:_index(x, y)
                if self.keys[index] == 1 then
                    self.keys[index] = 0
                    self:_emit("event", "key", { x, y, 0, "synthetic", reason })
                    released = released + 1
                end
            end
        end
    end
    return released
end

function Grid:attach(serial, prefix, width, height)
    if not valid_string(serial) then
        return self:_error("invalid_serial")
    end
    if not valid_prefix(prefix) then
        return self:_error("invalid_prefix")
    end
    if not valid_dimension(width, MAX_WIDTH)
        or not valid_dimension(height, MAX_HEIGHT) then
        return self:_error("unsupported_grid_size", { width or -1, height or -1 })
    end

    if self.active then
        self:_release_held_keys("reattach")
    end
    self:_reset_buffers()
    self.active = true
    self.serial = serial
    self.prefix = prefix
    self.width = width
    self.height = height
    self:_mark_all_dirty()
    self:_emit("status", "attached", { serial, prefix, width, height })
    return true
end

function Grid:detach(reason)
    reason = reason or "detached"
    if not self.active then
        self:_emit("status", "detached", { "none", reason, 0 })
        return true
    end

    local serial = self.serial
    local released = self:_release_held_keys(reason)
    self.active = false
    self.serial = nil
    self.prefix = nil
    self.width = nil
    self.height = nil
    self:_reset_buffers()
    self:_emit("status", "detached", { serial, reason, released })
    return true
end

function Grid:session(selector, atoms)
    atoms = atoms or {}
    if selector == "connected" or selector == "verified" then
        if #atoms ~= 7 then
            return self:_error("invalid_session_info", { selector })
        end
        if selector == "connected" then
            return self:attach(atoms[1], atoms[4], atoms[6], atoms[7])
        end
        if self.active and (atoms[1] ~= self.serial or atoms[4] ~= self.prefix
            or atoms[6] ~= self.width or atoms[7] ~= self.height) then
            return self:_error("verified_session_changed")
        end
        return true
    end

    if selector == "displaced" or selector == "device_removed"
        or selector == "deselected" or selector == "released" then
        return self:detach(selector)
    end

    return true
end

function Grid:input(address, atoms)
    atoms = atoms or {}
    if not self.active then
        self:_emit("passthrough", address, atoms)
        return true
    end

    local expected = self.prefix .. "/grid/key"
    if address ~= expected then
        self:_emit("passthrough", address, atoms)
        return true
    end
    if #atoms ~= 3 or not self:_valid_coordinate(atoms[1], atoms[2])
        or not is_integer(atoms[3]) or (atoms[3] ~= 0 and atoms[3] ~= 1) then
        return self:_error("invalid_key_event")
    end

    local x, y, state = atoms[1], atoms[2], atoms[3]
    local index = self:_index(x, y)
    if self.keys[index] == state then
        self:_emit("status", "ignored", { "duplicate_key", x, y, state })
        return true
    end
    self.keys[index] = state
    self:_emit("event", "key", { x, y, state })
    return true
end

function Grid:level(x, y, level)
    local ready, err = self:_ready()
    if not ready then
        return self:_error(err)
    end
    if not self:_valid_coordinate(x, y) then
        return self:_error("coordinate_out_of_bounds", { x or -1, y or -1 })
    end
    if not is_integer(level) or level < 0 or level > 15 then
        return self:_error("invalid_led_level", { level or -1 })
    end

    local index = self:_index(x, y)
    if self.levels[index] == level then
        return true
    end
    self.levels[index] = level
    self:_mark_dirty(x, y)
    return true
end

function Grid:all(level)
    local ready, err = self:_ready()
    if not ready then
        return self:_error(err)
    end
    if not is_integer(level) or level < 0 or level > 15 then
        return self:_error("invalid_led_level", { level or -1 })
    end

    for y = 0, self.height - 1 do
        for x = 0, self.width - 1 do
            local index = self:_index(x, y)
            if self.levels[index] ~= level then
                self.levels[index] = level
                self:_mark_dirty(x, y)
            end
        end
    end
    return true
end

function Grid:map(x_offset, y_offset, levels)
    local ready, err = self:_ready()
    if not ready then
        return self:_error(err)
    end
    if not is_integer(x_offset) or not is_integer(y_offset)
        or x_offset < 0 or y_offset < 0
        or x_offset % QUAD_SIZE ~= 0 or y_offset % QUAD_SIZE ~= 0
        or x_offset + QUAD_SIZE > self.width
        or y_offset + QUAD_SIZE > self.height then
        return self:_error("invalid_map_offset", {
            x_offset or -1, y_offset or -1,
        })
    end
    if type(levels) ~= "table" or #levels ~= QUAD_SIZE * QUAD_SIZE then
        return self:_error("map_requires_64_levels")
    end
    for _, level in ipairs(levels) do
        if not is_integer(level) or level < 0 or level > 15 then
            return self:_error("invalid_led_level", { level or -1 })
        end
    end

    local source = 1
    for y = y_offset, y_offset + QUAD_SIZE - 1 do
        for x = x_offset, x_offset + QUAD_SIZE - 1 do
            local index = self:_index(x, y)
            local level = levels[source]
            if self.levels[index] ~= level then
                self.levels[index] = level
                self:_mark_dirty(x, y)
            end
            source = source + 1
        end
    end
    return true
end

function Grid:_quad_atoms(x_offset, y_offset)
    local atoms = { x_offset, y_offset }
    for y = y_offset, y_offset + QUAD_SIZE - 1 do
        for x = x_offset, x_offset + QUAD_SIZE - 1 do
            table.insert(atoms, self.levels[self:_index(x, y)])
        end
    end
    return atoms
end

function Grid:flush()
    local ready = self:_ready()
    if not ready then
        return true
    end

    local flushed = 0
    for y_offset = 0, self.height - 1, QUAD_SIZE do
        for x_offset = 0, self.width - 1, QUAD_SIZE do
            local key = y_offset * MAX_WIDTH + x_offset
            if self.dirty[key] then
                self.dirty[key] = nil
                self:_emit(
                    "osc",
                    self.prefix .. "/grid/led/level/map",
                    self:_quad_atoms(x_offset, y_offset)
                )
                flushed = flushed + 1
            end
        end
    end
    if flushed > 0 then
        self:_emit("status", "flushed", { flushed })
    end
    return true
end

function Grid:prepare_release()
    if self.active then
        self:all(0)
        self:_mark_all_dirty()
        self:flush()
        self:_emit("status", "darkened", {
            self.serial, self.width, self.height,
        })
    else
        self:_emit("status", "darken_skipped", { "grid_not_attached" })
    end
    self:_emit("control", "release", {})
    return true
end

function Grid:snapshot()
    self:_emit("status", "snapshot", {
        self.active and "attached" or "detached",
        self.serial or "none",
        self.prefix or "none",
        self.width or 0,
        self.height or 0,
    })
    return true
end

return {
    Grid = Grid,
    MAX_WIDTH = MAX_WIDTH,
    MAX_HEIGHT = MAX_HEIGHT,
    QUAD_SIZE = QUAD_SIZE,
}

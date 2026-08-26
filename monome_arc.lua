local Arc = {}
Arc.__index = Arc

local MAX_RINGS = 4
local LEDS_PER_RING = 64

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

local function valid_ring_count(value)
    return is_integer(value) and (value == 2 or value == 4)
end

local function append(destination, values)
    for _, value in ipairs(values) do
        table.insert(destination, value)
    end
end

function Arc.new(configured_rings)
    assert(configured_rings == nil or valid_ring_count(configured_rings),
        "unsupported ring count")
    local levels = {}
    local keys = {}
    for ring = 1, MAX_RINGS do
        levels[ring] = {}
        keys[ring] = 0
        for position = 1, LEDS_PER_RING do
            levels[ring][position] = 0
        end
    end

    return setmetatable({
        active = false,
        serial = nil,
        prefix = nil,
        rings = nil,
        configured_rings = configured_rings,
        levels = levels,
        keys = keys,
        dirty = {},
        outputs = {},
    }, Arc)
end

function Arc:_emit(channel, selector, atoms)
    table.insert(self.outputs, {
        channel = channel,
        selector = selector,
        atoms = atoms or {},
    })
end

function Arc:drain()
    local outputs = self.outputs
    self.outputs = {}
    return outputs
end

function Arc:_error(code, atoms)
    local output = { code }
    append(output, atoms or {})
    self:_emit("status", "error", output)
    return nil, code
end

function Arc:_reset_levels()
    for ring = 1, MAX_RINGS do
        self.keys[ring] = 0
        for position = 1, LEDS_PER_RING do
            self.levels[ring][position] = 0
        end
    end
    self.dirty = {}
end

function Arc:_mark_all_dirty()
    if self.rings then
        for ring = 1, self.rings do
            self.dirty[ring] = true
        end
    end
end

function Arc:_ready()
    if not self.active then
        return nil, "arc_not_attached"
    end
    return true
end

function Arc:_valid_ring(ring)
    return is_integer(ring) and ring >= 0 and ring < self.rings
end

local function valid_position(position)
    return is_integer(position) and position >= 0
        and position < LEDS_PER_RING
end

function Arc:_release_held_keys(reason)
    local released = 0
    if self.rings then
        for ring = 1, self.rings do
            if self.keys[ring] == 1 then
                self.keys[ring] = 0
                self:_emit("event", "key", {
                    ring - 1, 0, "synthetic", reason,
                })
                released = released + 1
            end
        end
    end
    return released
end

function Arc:attach(serial, prefix, rings)
    if not valid_string(serial) then
        return self:_error("invalid_serial")
    end
    if not valid_prefix(prefix) then
        return self:_error("invalid_prefix")
    end
    if not valid_ring_count(rings) then
        return self:_error("unsupported_ring_count", { rings or -1 })
    end

    if self.active then
        self:_release_held_keys("reattach")
    end
    self:_reset_levels()
    self.active = true
    self.serial = serial
    self.prefix = prefix
    self.rings = rings
    for ring = 1, rings do
        self.dirty[ring] = true
    end
    self:_emit("status", "attached", { serial, prefix, rings })
    return true
end

function Arc:detach(reason)
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
    self.rings = nil
    self:_reset_levels()
    self:_emit("status", "detached", { serial, reason, released })
    return true
end

function Arc:session(selector, atoms)
    atoms = atoms or {}
    if selector == "connected" or selector == "verified" then
        if #atoms ~= 7 then
            return self:_error("invalid_session_info", { selector })
        end
        if not self.configured_rings then
            return self:_error("ring_count_required")
        end
        if selector == "connected" then
            return self:attach(atoms[1], atoms[4], self.configured_rings)
        end
        if self.active and (atoms[1] ~= self.serial
            or atoms[4] ~= self.prefix or self.rings ~= self.configured_rings) then
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

function Arc:_ring_atoms(ring)
    local atoms = { ring - 1 }
    for position = 1, LEDS_PER_RING do
        table.insert(atoms, self.levels[ring][position])
    end
    return atoms
end

function Arc:level(ring, position, level)
    local ready, err = self:_ready()
    if not ready then
        return self:_error(err)
    end
    if not self:_valid_ring(ring) then
        return self:_error("ring_out_of_bounds", { ring or -1 })
    end
    if not valid_position(position) then
        return self:_error("position_out_of_bounds", { position or -1 })
    end
    if not is_integer(level) or level < 0 or level > 15 then
        return self:_error("invalid_led_level", { level or -1 })
    end

    local internal_ring = ring + 1
    local internal_position = position + 1
    if self.levels[internal_ring][internal_position] == level then
        return true
    end
    self.levels[internal_ring][internal_position] = level
    self.dirty[internal_ring] = true
    return true
end

function Arc:map(ring, levels)
    local ready, err = self:_ready()
    if not ready then
        return self:_error(err)
    end
    if not self:_valid_ring(ring) then
        return self:_error("ring_out_of_bounds", { ring or -1 })
    end
    if type(levels) ~= "table" or #levels ~= LEDS_PER_RING then
        return self:_error("map_requires_64_levels")
    end
    for _, level in ipairs(levels) do
        if not is_integer(level) or level < 0 or level > 15 then
            return self:_error("invalid_led_level", { level or -1 })
        end
    end

    local internal_ring = ring + 1
    local changed = false
    for position = 1, LEDS_PER_RING do
        if self.levels[internal_ring][position] ~= levels[position] then
            self.levels[internal_ring][position] = levels[position]
            changed = true
        end
    end
    if changed then
        self.dirty[internal_ring] = true
    end
    return true
end

function Arc:all(level)
    local ready, err = self:_ready()
    if not ready then
        return self:_error(err)
    end
    if not is_integer(level) or level < 0 or level > 15 then
        return self:_error("invalid_led_level", { level or -1 })
    end

    for ring = 1, self.rings do
        local changed = false
        for position = 1, LEDS_PER_RING do
            if self.levels[ring][position] ~= level then
                self.levels[ring][position] = level
                changed = true
            end
        end
        if changed then
            self.dirty[ring] = true
        end
    end
    return true
end

function Arc:clear()
    return self:all(0)
end

function Arc:input(address, atoms)
    atoms = atoms or {}
    if not self.active then
        self:_emit("passthrough", address, atoms)
        return true
    end

    local delta_address = self.prefix .. "/enc/delta"
    local key_address = self.prefix .. "/enc/key"
    if address ~= delta_address and address ~= key_address then
        self:_emit("passthrough", address, atoms)
        return true
    end
    if address == delta_address then
        if #atoms ~= 2 or not self:_valid_ring(atoms[1])
            or not is_integer(atoms[2]) then
            return self:_error("invalid_delta_event")
        end
        self:_emit("event", "delta", { atoms[1], atoms[2] })
        return true
    end

    if #atoms ~= 2 or not self:_valid_ring(atoms[1])
        or not is_integer(atoms[2])
        or (atoms[2] ~= 0 and atoms[2] ~= 1) then
        return self:_error("invalid_key_event")
    end
    local internal_ring = atoms[1] + 1
    if self.keys[internal_ring] == atoms[2] then
        self:_emit("status", "ignored", {
            "duplicate_key", atoms[1], atoms[2],
        })
        return true
    end
    self.keys[internal_ring] = atoms[2]
    self:_emit("event", "key", { atoms[1], atoms[2] })
    return true
end

function Arc:flush()
    if not self.active then
        return true
    end

    local flushed = 0
    for ring = 1, self.rings do
        if self.dirty[ring] then
            self.dirty[ring] = nil
            self:_emit(
                "osc",
                self.prefix .. "/ring/map",
                self:_ring_atoms(ring)
            )
            flushed = flushed + 1
        end
    end
    if flushed > 0 then
        self:_emit("status", "flushed", { flushed })
    end
    return true
end

function Arc:prepare_release()
    if self.active then
        self:clear()
        self:_mark_all_dirty()
        self:flush()
        self:_emit("status", "darkened", { self.serial, self.rings })
    else
        self:_emit("status", "darken_skipped", { "arc_not_attached" })
    end
    self:_emit("control", "release", {})
    return true
end

function Arc:snapshot()
    self:_emit("status", "snapshot", {
        self.active and "attached" or "detached",
        self.serial or "none",
        self.prefix or "none",
        self.rings or self.configured_rings or 0,
    })
    return true
end

return {
    Arc = Arc,
    MAX_RINGS = MAX_RINGS,
    LEDS_PER_RING = LEDS_PER_RING,
}

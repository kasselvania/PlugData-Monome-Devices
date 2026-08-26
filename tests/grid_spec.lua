local script_path = debug.getinfo(1, "S").source:sub(2)
local project_root = script_path:match("^(.*)/tests/grid_spec.lua$")
if script_path == "tests/grid_spec.lua" then
    project_root = "."
end
assert(project_root, "run this test from its checked-out project path")

local Core = dofile(project_root .. "/monome_grid.lua")

local passed = 0

local function test(name, body)
    local ok, err = pcall(body)
    if not ok then
        io.stderr:write("FAIL: " .. name .. "\n" .. tostring(err) .. "\n")
        os.exit(1)
    end
    passed = passed + 1
    io.stdout:write("PASS: " .. name .. "\n")
end

local function equal(actual, expected, message)
    if actual ~= expected then
        error((message or "values differ")
            .. ": expected " .. tostring(expected)
            .. ", got " .. tostring(actual), 2)
    end
end

local function find(outputs, channel, selector)
    for _, output in ipairs(outputs) do
        if output.channel == channel and output.selector == selector then
            return output
        end
    end
end

local function collect(outputs, channel, selector)
    local matches = {}
    for _, output in ipairs(outputs) do
        if output.channel == channel and output.selector == selector then
            table.insert(matches, output)
        end
    end
    return matches
end

local function attach(width, height, serial, prefix)
    local grid = Core.Grid.new()
    assert(grid:attach(
        serial or "m100", prefix or "/monome", width or 16, height or 8
    ))
    grid:drain()
    return grid
end

local function initial_flush(width, height)
    local grid = attach(width, height)
    assert(grid:flush())
    return grid, grid:drain()
end

test("only supported 8-aligned surfaces can attach", function()
    local grid = Core.Grid.new()
    local ok, err = grid:attach("m100", "/monome", 17, 8)
    equal(ok, nil)
    equal(err, "unsupported_grid_size")
    ok, err = grid:attach("m100", "/monome", 8, 12)
    equal(ok, nil)
    equal(err, "unsupported_grid_size")
    equal(grid.active, false)
end)

test("128 attach flushes two deterministic dark quads", function()
    local _, outputs = initial_flush(16, 8)
    local maps = collect(
        outputs, "osc", "/monome/grid/led/level/map"
    )
    equal(#maps, 2)
    equal(maps[1].atoms[1], 0)
    equal(maps[1].atoms[2], 0)
    equal(maps[2].atoms[1], 8)
    equal(maps[2].atoms[2], 0)
    equal(#maps[1].atoms, 66)
    for index = 3, 66 do
        equal(maps[1].atoms[index], 0)
        equal(maps[2].atoms[index], 0)
    end
end)

test("256 attach flushes four quads in row-major order", function()
    local _, outputs = initial_flush(16, 16)
    local maps = collect(
        outputs, "osc", "/monome/grid/led/level/map"
    )
    equal(#maps, 4)
    equal(maps[1].atoms[1] .. "," .. maps[1].atoms[2], "0,0")
    equal(maps[2].atoms[1] .. "," .. maps[2].atoms[2], "8,0")
    equal(maps[3].atoms[1] .. "," .. maps[3].atoms[2], "0,8")
    equal(maps[4].atoms[1] .. "," .. maps[4].atoms[2], "8,8")
end)

test("level changes coalesce and duplicates do not redraw", function()
    local grid = initial_flush(16, 8)
    grid:drain()
    assert(grid:level(2, 3, 7))
    assert(grid:level(2, 3, 12))
    assert(grid:level(2, 3, 12))
    assert(grid:flush())
    local outputs = grid:drain()
    local maps = collect(
        outputs, "osc", "/monome/grid/led/level/map"
    )
    equal(#maps, 1)
    equal(maps[1].atoms[3 + (3 * 8) + 2], 12)

    assert(grid:flush())
    equal(#grid:drain(), 0)
end)

test("8 by 8 maps are row-major and validate the whole update", function()
    local grid = initial_flush(16, 8)
    grid:drain()
    local levels = {}
    for index = 1, 64 do
        levels[index] = (index - 1) % 16
    end
    assert(grid:map(8, 0, levels))
    assert(grid:flush())
    local map = assert(find(
        grid:drain(), "osc", "/monome/grid/led/level/map"
    ))
    equal(map.atoms[1], 8)
    equal(map.atoms[2], 0)
    for index = 1, 64 do
        equal(map.atoms[index + 2], levels[index])
    end

    levels[64] = 16
    local ok, err = grid:map(0, 0, levels)
    equal(ok, nil)
    equal(err, "invalid_led_level")
end)

test("coordinates and levels fail closed", function()
    local grid = attach(16, 8)
    local ok, err = grid:level(16, 0, 1)
    equal(ok, nil)
    equal(err, "coordinate_out_of_bounds")
    ok, err = grid:level(0, -1, 1)
    equal(ok, nil)
    equal(err, "coordinate_out_of_bounds")
    ok, err = grid:level(0, 0, 15.5)
    equal(ok, nil)
    equal(err, "invalid_led_level")
    ok, err = grid:map(4, 0, {})
    equal(ok, nil)
    equal(err, "invalid_map_offset")
end)

test("key events are normalized against prefix and dimensions", function()
    local grid = attach(16, 8, "m100", "/plugdata")
    assert(grid:input("/plugdata/grid/key", { 15, 7, 1 }))
    local event = assert(find(grid:drain(), "event", "key"))
    equal(table.concat(event.atoms, ","), "15,7,1")

    assert(grid:input("/plugdata/grid/key", { 15, 7, 0 }))
    event = assert(find(grid:drain(), "event", "key"))
    equal(table.concat(event.atoms, ","), "15,7,0")
end)

test("duplicate key state is suppressed", function()
    local grid = attach(16, 8)
    assert(grid:input("/monome/grid/key", { 3, 4, 1 }))
    grid:drain()
    assert(grid:input("/monome/grid/key", { 3, 4, 1 }))
    local outputs = grid:drain()
    equal(find(outputs, "event", "key"), nil)
    local ignored = assert(find(outputs, "status", "ignored"))
    equal(ignored.atoms[1], "duplicate_key")
end)

test("invalid key events do not mutate key state", function()
    local grid = attach(16, 8)
    local ok, err = grid:input("/monome/grid/key", { 16, 0, 1 })
    equal(ok, nil)
    equal(err, "invalid_key_event")
    ok, err = grid:input("/monome/grid/key", { 0, 0, 2 })
    equal(ok, nil)
    equal(err, "invalid_key_event")
    equal(grid.keys[1], 0)
end)

test("non-grid OSC is preserved for another capability", function()
    local grid = attach(16, 8)
    assert(grid:input("/monome/enc/delta", { 0, 3 }))
    local output = assert(find(
        grid:drain(), "passthrough", "/monome/enc/delta"
    ))
    equal(table.concat(output.atoms, ","), "0,3")
end)

test("detach releases held keys synthetically", function()
    local grid = attach(16, 8)
    assert(grid:input("/monome/grid/key", { 1, 2, 1 }))
    grid:drain()
    assert(grid:detach("device_removed"))
    local outputs = grid:drain()
    local event = assert(find(outputs, "event", "key"))
    equal(table.concat(event.atoms, ","), "1,2,0,synthetic,device_removed")
    local detached = assert(find(outputs, "status", "detached"))
    equal(detached.atoms[3], 1)
end)

test("reconnect clears stale LEDs and key state", function()
    local grid = initial_flush(16, 8)
    grid:drain()
    assert(grid:level(0, 0, 15))
    assert(grid:input("/monome/grid/key", { 0, 0, 1 }))
    grid:drain()
    assert(grid:attach("m200", "/next", 16, 16))
    local attach_outputs = grid:drain()
    assert(find(attach_outputs, "event", "key"))
    assert(grid:flush())
    local maps = collect(grid:drain(), "osc", "/next/grid/led/level/map")
    equal(#maps, 4)
    for _, map in ipairs(maps) do
        for index = 3, 66 do
            equal(map.atoms[index], 0)
        end
    end
end)

test("release darkens every valid quad before delegating release", function()
    local grid = initial_flush(16, 16)
    grid:drain()
    assert(grid:all(15))
    assert(grid:prepare_release())
    local outputs = grid:drain()
    equal(#outputs, 7)
    for index = 1, 4 do
        equal(outputs[index].channel, "osc")
        for atom = 3, 66 do
            equal(outputs[index].atoms[atom], 0)
        end
    end
    equal(outputs[5].selector, "flushed")
    equal(outputs[6].selector, "darkened")
    equal(outputs[7].channel, "control")
    equal(outputs[7].selector, "release")
end)

test("release still delegates when no Grid surface is attached", function()
    local grid = Core.Grid.new()
    assert(grid:prepare_release())
    local outputs = grid:drain()
    equal(outputs[1].selector, "darken_skipped")
    equal(outputs[2].channel, "control")
    equal(outputs[2].selector, "release")
end)

test("session events attach and detach the capability", function()
    local grid = Core.Grid.new()
    assert(grid:session("connected", {
        "m100", "127.0.0.1", 17780, "/monome", 0, 16, 8,
    }))
    equal(grid.active, true)
    grid:drain()
    assert(grid:session("displaced", {}))
    equal(grid.active, false)
    assert(find(grid:drain(), "status", "detached"))
end)

io.stdout:write(string.format("grid_spec: %d tests passed\n", passed))

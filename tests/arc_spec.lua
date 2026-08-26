local script_path = debug.getinfo(1, "S").source:sub(2)
local project_root = script_path:match("^(.*)/tests/arc_spec.lua$")
if script_path == "tests/arc_spec.lua" then
    project_root = "."
end
assert(project_root, "run this test from its checked-out project path")

local Core = dofile(project_root .. "/monome_arc.lua")

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

local function collect(outputs, channel, selector)
    local matches = {}
    for _, output in ipairs(outputs) do
        if output.channel == channel and output.selector == selector then
            table.insert(matches, output)
        end
    end
    return matches
end

local function find(outputs, channel, selector)
    local matches = collect(outputs, channel, selector)
    return matches[1]
end

test("four-ring attach flushes four deterministic dark maps", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/monome", 4))
    arc:drain()
    assert(arc:flush())

    local maps = collect(arc:drain(), "osc", "/monome/ring/map")
    equal(#maps, 4)
    for ring = 0, 3 do
        equal(maps[ring + 1].atoms[1], ring)
        equal(#maps[ring + 1].atoms, 65)
        for index = 2, 65 do
            equal(maps[ring + 1].atoms[index], 0)
        end
    end
end)

test("only explicit two- or four-ring surfaces can attach", function()
    local arc = Core.Arc.new()
    local ok, err = arc:attach("a100", "/monome", 1)
    equal(ok, nil)
    equal(err, "unsupported_ring_count")
    ok, err = arc:attach("a100", "/monome", 3)
    equal(ok, nil)
    equal(err, "unsupported_ring_count")
    equal(arc.active, false)
end)

test("level changes coalesce and only redraw the dirty ring", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/monome", 4))
    arc:drain()
    assert(arc:flush())
    arc:drain()

    assert(arc:level(2, 17, 7))
    assert(arc:level(2, 17, 12))
    assert(arc:level(2, 17, 12))
    assert(arc:flush())
    local maps = collect(arc:drain(), "osc", "/monome/ring/map")
    equal(#maps, 1)
    equal(maps[1].atoms[1], 2)
    equal(maps[1].atoms[19], 12)

    assert(arc:flush())
    equal(#arc:drain(), 0)
end)

test("ring maps validate the whole update before changing output", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/monome", 2))
    arc:drain()
    assert(arc:flush())
    arc:drain()

    local levels = {}
    for index = 1, 64 do
        levels[index] = (index - 1) % 16
    end
    assert(arc:map(1, levels))
    assert(arc:flush())
    local maps = collect(arc:drain(), "osc", "/monome/ring/map")
    equal(#maps, 1)
    equal(maps[1].atoms[1], 1)
    for index = 1, 64 do
        equal(maps[1].atoms[index + 1], levels[index])
    end

    levels[64] = 16
    local ok, err = arc:map(0, levels)
    equal(ok, nil)
    equal(err, "invalid_led_level")
    assert(arc:flush())
    equal(#collect(arc:drain(), "osc", "/monome/ring/map"), 0)
end)

test("all sets every active ring and suppresses duplicate frames", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/monome", 2))
    arc:drain()
    assert(arc:flush())
    arc:drain()

    assert(arc:all(15))
    assert(arc:flush())
    local maps = collect(arc:drain(), "osc", "/monome/ring/map")
    equal(#maps, 2)
    for ring = 1, 2 do
        for index = 2, 65 do
            equal(maps[ring].atoms[index], 15)
        end
    end

    assert(arc:all(15))
    assert(arc:flush())
    equal(#arc:drain(), 0)
end)

test("clear produces an all-dark frame for every active ring", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/monome", 4))
    arc:drain()
    assert(arc:flush())
    arc:drain()
    assert(arc:all(15))
    assert(arc:flush())
    arc:drain()

    assert(arc:clear())
    assert(arc:flush())
    local maps = collect(arc:drain(), "osc", "/monome/ring/map")
    equal(#maps, 4)
    for _, map in ipairs(maps) do
        for index = 2, 65 do
            equal(map.atoms[index], 0)
        end
    end
end)

test("ring positions and LED levels fail closed", function()
    local arc = Core.Arc.new()
    local ok, err = arc:level(0, 0, 1)
    equal(ok, nil)
    equal(err, "arc_not_attached")
    assert(arc:attach("a100", "/monome", 2))
    arc:drain()

    ok, err = arc:level(2, 0, 1)
    equal(ok, nil)
    equal(err, "ring_out_of_bounds")
    ok, err = arc:level(0, 64, 1)
    equal(ok, nil)
    equal(err, "position_out_of_bounds")
    ok, err = arc:level(0, 0, 15.5)
    equal(ok, nil)
    equal(err, "invalid_led_level")
    ok, err = arc:map(0, {})
    equal(ok, nil)
    equal(err, "map_requires_64_levels")
end)

test("encoder deltas are normalized against the attached prefix", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/plugdata", 4))
    arc:drain()

    assert(arc:input("/plugdata/enc/delta", { 3, -12 }))
    local event = assert(find(arc:drain(), "event", "delta"))
    equal(table.concat(event.atoms, ","), "3,-12")
end)

test("encoder key events are normalized when hardware provides them", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/monome", 2))
    arc:drain()

    assert(arc:input("/monome/enc/key", { 1, 1 }))
    local event = assert(find(arc:drain(), "event", "key"))
    equal(table.concat(event.atoms, ","), "1,1")

    assert(arc:input("/monome/enc/key", { 1, 0 }))
    event = assert(find(arc:drain(), "event", "key"))
    equal(table.concat(event.atoms, ","), "1,0")
end)

test("duplicate encoder key state is suppressed", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/monome", 2))
    arc:drain()
    assert(arc:input("/monome/enc/key", { 0, 1 }))
    arc:drain()

    assert(arc:input("/monome/enc/key", { 0, 1 }))
    local outputs = arc:drain()
    equal(find(outputs, "event", "key"), nil)
    local ignored = assert(find(outputs, "status", "ignored"))
    equal(ignored.atoms[1], "duplicate_key")
end)

test("invalid encoder events fail closed without mutating key state", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/monome", 2))
    arc:drain()

    local ok, err = arc:input("/monome/enc/delta", { 2, 1 })
    equal(ok, nil)
    equal(err, "invalid_delta_event")
    ok, err = arc:input("/monome/enc/key", { 0, 2 })
    equal(ok, nil)
    equal(err, "invalid_key_event")
    equal(arc.keys[1], 0)
end)

test("non-Arc OSC is preserved for another capability", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/monome", 4))
    arc:drain()

    assert(arc:input("/monome/grid/key", { 1, 2, 1 }))
    local output = assert(find(
        arc:drain(), "passthrough", "/monome/grid/key"
    ))
    equal(table.concat(output.atoms, ","), "1,2,1")
end)

test("detach releases held encoder keys synthetically", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/monome", 4))
    arc:drain()
    assert(arc:input("/monome/enc/key", { 1, 1 }))
    arc:drain()

    assert(arc:detach("device_removed"))
    local outputs = arc:drain()
    local event = assert(find(outputs, "event", "key"))
    equal(
        table.concat(event.atoms, ","),
        "1,0,synthetic,device_removed"
    )
    local detached = assert(find(outputs, "status", "detached"))
    equal(detached.atoms[3], 1)
end)

test("reconnect releases held keys and clears stale LED buffers", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/monome", 4))
    arc:drain()
    assert(arc:flush())
    arc:drain()
    assert(arc:level(0, 0, 15))
    assert(arc:input("/monome/enc/key", { 0, 1 }))
    arc:drain()

    assert(arc:attach("a200", "/next", 2))
    local attach_outputs = arc:drain()
    local release = assert(find(attach_outputs, "event", "key"))
    equal(table.concat(release.atoms, ","), "0,0,synthetic,reattach")
    assert(arc:flush())
    local maps = collect(arc:drain(), "osc", "/next/ring/map")
    equal(#maps, 2)
    for _, map in ipairs(maps) do
        for index = 2, 65 do
            equal(map.atoms[index], 0)
        end
    end
end)

test("session attachment uses the explicitly configured ring count", function()
    local arc = Core.Arc.new(4)
    assert(arc:session("connected", {
        "a100", "127.0.0.1", 17780, "/monome", 0, 0, 0,
    }))
    equal(arc.active, true)
    equal(arc.rings, 4)
    assert(arc:flush())
    equal(#collect(arc:drain(), "osc", "/monome/ring/map"), 4)
end)

test("session attachment refuses to guess an Arc ring count", function()
    local arc = Core.Arc.new()
    local ok, err = arc:session("connected", {
        "a100", "127.0.0.1", 17780, "/monome", 0, 0, 0,
    })
    equal(ok, nil)
    equal(err, "ring_count_required")
    equal(arc.active, false)
end)

test("session removal detaches the Arc capability", function()
    local arc = Core.Arc.new(4)
    assert(arc:session("connected", {
        "a100", "127.0.0.1", 17780, "/monome", 0, 0, 0,
    }))
    arc:drain()

    assert(arc:session("device_removed", {}))
    equal(arc.active, false)
    assert(find(arc:drain(), "status", "detached"))
end)

test("verified session metadata cannot silently change Arc identity", function()
    local arc = Core.Arc.new(4)
    assert(arc:session("connected", {
        "a100", "127.0.0.1", 17780, "/monome", 0, 0, 0,
    }))
    arc:drain()
    assert(arc:session("verified", {
        "a100", "127.0.0.1", 17780, "/monome", 0, 0, 0,
    }))

    local ok, err = arc:session("verified", {
        "a100", "127.0.0.1", 17780, "/other", 0, 0, 0,
    })
    equal(ok, nil)
    equal(err, "verified_session_changed")
end)

test("release darkens every ring before delegating release", function()
    local arc = Core.Arc.new()
    assert(arc:attach("a100", "/monome", 4))
    arc:drain()
    assert(arc:flush())
    arc:drain()
    assert(arc:all(15))
    assert(arc:flush())
    arc:drain()

    assert(arc:prepare_release())
    local outputs = arc:drain()
    equal(#outputs, 7)
    for index = 1, 4 do
        equal(outputs[index].channel, "osc")
        for atom = 2, 65 do
            equal(outputs[index].atoms[atom], 0)
        end
    end
    equal(outputs[5].selector, "flushed")
    equal(outputs[6].selector, "darkened")
    equal(outputs[7].channel, "control")
    equal(outputs[7].selector, "release")
end)

test("release still delegates when no Arc surface is attached", function()
    local arc = Core.Arc.new(4)
    assert(arc:prepare_release())
    local outputs = arc:drain()
    equal(outputs[1].selector, "darken_skipped")
    equal(outputs[2].channel, "control")
    equal(outputs[2].selector, "release")
end)

test("snapshot reports explicit Arc attachment state", function()
    local arc = Core.Arc.new(4)
    assert(arc:snapshot())
    local output = assert(find(arc:drain(), "status", "snapshot"))
    equal(table.concat(output.atoms, ","), "detached,none,none,4")

    assert(arc:attach("a100", "/monome", 4))
    arc:drain()
    assert(arc:snapshot())
    output = assert(find(arc:drain(), "status", "snapshot"))
    equal(table.concat(output.atoms, ","), "attached,a100,/monome,4")
end)

io.stdout:write(string.format("arc_spec: %d tests passed\n", passed))

local script_path = debug.getinfo(1, "S").source:sub(2)
local project_root = script_path:match("^(.*)/tests/session_spec.lua$")
if script_path == "tests/session_spec.lua" then
    project_root = "."
end
assert(project_root, "run this test from its checked-out project path")

local Core = dofile(project_root .. "/monome_session.lua")

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

local function session(owner, claims)
    return Core.Session.new({
        owner = owner,
        claims = claims,
        callback_port = 17780,
        info_window_ms = 100,
    })
end

local function find(outputs, channel, selector)
    for _, output in ipairs(outputs) do
        if output.channel == channel and output.selector == selector then
            return output
        end
    end
    return nil
end

local function osc_addresses(outputs)
    local addresses = {}
    for _, output in ipairs(outputs) do
        if output.channel == "osc" then
            table.insert(addresses, output.selector)
        end
    end
    return table.concat(addresses, " ")
end

local function ready_and_select(target, serial, port)
    assert(target:start())
    target:drain()
    assert(target:transport_ready())
    target:drain()
    assert(target:select(serial or "m100", "monome 128", port or 17001))
    target:drain()
end

local function feed_info(target, values)
    values = values or {}
    assert(target:info("id", { values.id or "m100" }))
    if values.size ~= false then
        assert(target:info("size", values.size or { 16, 8 }))
    end
    assert(target:info("host", { values.host or "127.0.0.1" }))
    assert(target:info("port", { values.port or 0 }))
    assert(target:info("prefix", { values.prefix or "/monome" }))
    assert(target:info("rotation", { values.rotation or 0 }))
end

local function complete_probe(target, values)
    assert(target:probe())
    target:drain()
    feed_info(target, values)
    assert(target:info_end())
    target:drain()
end

local function complete_claim(target)
    assert(target:claim())
    local claim_outputs = target:drain()
    equal(
        osc_addresses(claim_outputs),
        "/sys/prefix /sys/host /sys/port /sys/info"
    )
    feed_info(target, { port = 17780 })
    assert(target:info_end())
    target:drain()
end

test("probe is non-mutating and records observed destination", function()
    local target = session("one")
    ready_and_select(target)

    assert(target:probe())
    local outputs = target:drain()
    equal(osc_addresses(outputs), "/sys/info")

    feed_info(target, { host = "localhost", port = 9000, prefix = "/other" })
    assert(target:info_end())
    outputs = target:drain()
    equal(target.state, "available")
    equal(target.observed.port, 9000)
    assert(find(outputs, "status", "probed"))
end)

test("claim requires a completed probe", function()
    local target = session("one")
    ready_and_select(target)
    local ok, err = target:claim()
    equal(ok, nil)
    equal(err, "probe_required")
    equal(osc_addresses(target:drain()), "")
end)

test("claim changes settings then requires matching readback", function()
    local claims = Core.ClaimRegistry.new()
    local target = session("one", claims)
    ready_and_select(target)
    complete_probe(target)

    assert(target:claim())
    local outputs = target:drain()
    equal(
        osc_addresses(outputs),
        "/sys/prefix /sys/host /sys/port /sys/info"
    )
    equal(claims:owner("m100"), "one")

    feed_info(target, { host = "localhost", port = 17780 })
    assert(target:info_end())
    outputs = target:drain()
    equal(target.state, "connected")
    assert(find(outputs, "status", "connected"))
end)

test("claim mismatch refuses a connected claim", function()
    local claims = Core.ClaimRegistry.new()
    local target = session("one", claims)
    ready_and_select(target)
    complete_probe(target)

    assert(target:claim())
    target:drain()
    feed_info(target, { port = 19999 })
    local ok, err = target:info_end()
    equal(ok, nil)
    equal(err, "claim_verification_failed")
    equal(target.state, "displaced")
    equal(claims:owner("m100"), nil)
    assert(find(target:drain(), "status", "displaced"))
end)

test("periodic check detects another application displacement", function()
    local claims = Core.ClaimRegistry.new()
    local target = session("one", claims)
    ready_and_select(target)
    complete_probe(target)
    complete_claim(target)

    assert(target:check())
    target:drain()
    feed_info(target, { host = "127.0.0.1", port = 19000, prefix = "/rival" })
    local ok, err = target:info_end()
    equal(ok, nil)
    equal(err, "destination_changed")
    equal(target.state, "displaced")
    equal(claims:owner("m100"), nil)
end)

test("verified release sends port zero and clears local ownership", function()
    local claims = Core.ClaimRegistry.new()
    local target = session("one", claims)
    ready_and_select(target)
    complete_probe(target)
    complete_claim(target)

    assert(target:release())
    equal(osc_addresses(target:drain()), "/sys/info")
    feed_info(target, { port = 17780 })
    assert(target:info_end())
    local outputs = target:drain()
    equal(osc_addresses(outputs), "/sys/port")
    equal(find(outputs, "osc", "/sys/port").atoms[1], 0)
    equal(target.state, "available")
    equal(claims:owner("m100"), nil)
end)

test("release after displacement never overwrites the other destination", function()
    local claims = Core.ClaimRegistry.new()
    local target = session("one", claims)
    ready_and_select(target)
    complete_probe(target)
    complete_claim(target)

    assert(target:release())
    target:drain()
    feed_info(target, { port = 19000, prefix = "/rival" })
    local ok, err = target:info_end()
    equal(ok, nil)
    equal(err, "release_ownership_lost")
    local outputs = target:drain()
    equal(osc_addresses(outputs), "")
    equal(target.state, "displaced")
    equal(claims:owner("m100"), nil)
    assert(find(outputs, "status", "release_skipped"))
end)

test("one process refuses two claims for the same serial", function()
    local claims = Core.ClaimRegistry.new()
    local first = session("one", claims)
    local second = session("two", claims)
    ready_and_select(first)
    ready_and_select(second)
    complete_probe(first)
    complete_probe(second)

    assert(first:claim())
    first:drain()
    local ok, err = second:claim()
    equal(ok, nil)
    equal(err, "claimed_in_process")
    equal(osc_addresses(second:drain()), "")
end)

test("device removal clears process ownership and selected identity", function()
    local claims = Core.ClaimRegistry.new()
    local target = session("one", claims)
    ready_and_select(target)
    complete_probe(target)
    complete_claim(target)

    assert(target:device_removed("m100"))
    equal(target.state, "absent")
    equal(target.selected, nil)
    equal(claims:owner("m100"), nil)
end)

test("transport readiness and stop are fail closed", function()
    local target = session("one")
    assert(target:select("m100", "monome 128", 17001))
    target:drain()
    local ok, err = target:probe()
    equal(ok, nil)
    equal(err, "transport_not_ready")
    target:drain()

    assert(target:start())
    target:drain()
    assert(target:transport_ready())
    target:drain()
    complete_probe(target)
    complete_claim(target)
    ok, err = target:stop()
    equal(ok, nil)
    equal(err, "release_required")
end)

test("stopping a probe cancels the request and restores availability", function()
    local target = session("one")
    ready_and_select(target)
    assert(target:probe())
    target:drain()

    local ok, err = target:select("m200", "monome 256", 17002)
    equal(ok, nil)
    equal(err, "request_in_progress")
    target:drain()

    assert(target:stop())
    local outputs = target:drain()
    equal(target.state, "available")
    equal(target.transport, "stopped")
    assert(find(outputs, "control", "cancel_info_timer"))

    assert(target:start())
    target:drain()
    assert(target:transport_ready())
end)

test("displaced intent can be released after transport stops", function()
    local claims = Core.ClaimRegistry.new()
    local target = session("one", claims)
    ready_and_select(target)
    complete_probe(target)
    complete_claim(target)

    assert(target:check())
    target:drain()
    feed_info(target, { port = 19000, prefix = "/rival" })
    target:info_end()
    target:drain()
    equal(target.state, "displaced")

    assert(target:stop())
    target:drain()
    assert(target:release())
    local outputs = target:drain()
    equal(target.state, "available")
    assert(find(outputs, "status", "release_skipped"))
end)

test("incomplete claim readback cannot become connected", function()
    local claims = Core.ClaimRegistry.new()
    local target = session("one", claims)
    ready_and_select(target)
    complete_probe(target)
    assert(target:claim())
    target:drain()
    assert(target:info("id", { "m100" }))
    local ok, err = target:info_end()
    equal(ok, nil)
    equal(err, "info_incomplete")
    equal(target.state, "displaced")
    equal(claims:owner("m100"), nil)
end)

io.stdout:write(string.format("session_spec: %d tests passed\n", passed))

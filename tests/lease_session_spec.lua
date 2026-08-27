local script_path = debug.getinfo(1, "S").source:sub(2)
local project_root = script_path:match("^(.*)/tests/lease_session_spec.lua$")
if script_path == "tests/lease_session_spec.lua" then
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

local function session(owner, claims)
    return Core.Session.new({
        owner = owner,
        claims = claims,
        callback_port = 17780,
        info_window_ms = 100,
        protocol = "lease",
        lease_token = owner .. "-token",
        lease_ttl_ms = 6000,
        lease_renew_ms = 2000,
    })
end

local function ready_and_select(target)
    assert(target:start())
    target:drain()
    assert(target:transport_ready())
    target:drain()
    assert(target:select("m100", "monome 128", 17001))
    target:drain()
end

local function feed_device_info(target, port, prefix)
    assert(target:info("id", { "m100" }))
    assert(target:info("size", { 16, 8 }))
    assert(target:info("host", { "127.0.0.1" }))
    assert(target:info("port", { port or 0 }))
    assert(target:info("prefix", { prefix or "/monome" }))
    assert(target:info("rotation", { 0 }))
end

local function feed_lease_state(target, mode, port, owner, prefix)
    assert(target:lease_state({
        1,
        "m100",
        mode,
        "127.0.0.1",
        port,
        prefix or "/monome",
        mode == "leased" and 5900 or 0,
        owner or 0,
    }))
end

local function complete_probe(target, mode, port, owner, prefix)
    assert(target:probe())
    local outputs = target:drain()
    equal(osc_addresses(outputs), "/sys/info /sys/lease/info")
    local lease_info = find(outputs, "osc", "/sys/lease/info")
    equal(lease_info.atoms[1], target.lease_token)
    equal(lease_info.atoms[2], "127.0.0.1")
    equal(lease_info.atoms[3], 17780)
    feed_device_info(target, port, prefix)
    feed_lease_state(target, mode, port, owner, prefix)
    assert(target:info_end())
    target:drain()
end

local function complete_claim(target, takeover)
    if takeover then
        assert(target:takeover())
    else
        assert(target:claim())
    end
    local outputs = target:drain()
    equal(osc_addresses(outputs), takeover and "/sys/lease/takeover"
        or "/sys/lease/acquire")
    local claim = find(outputs, "osc", takeover and "/sys/lease/takeover"
        or "/sys/lease/acquire")
    equal(claim.atoms[1], target.lease_token)
    equal(claim.atoms[2], "127.0.0.1")
    equal(claim.atoms[3], 17780)
    equal(claim.atoms[4], "/monome")
    equal(claim.atoms[5], 6000)
    assert(target:lease_granted(target.lease_token, 6000))
    outputs = target:drain()
    equal(osc_addresses(outputs), "/sys/lease/info")
    feed_lease_state(target, "leased", 17780, 1, "/monome")
    assert(target:info_end())
    outputs = target:drain()
    equal(target.state, "connected")
    assert(find(outputs, "control", "lease_timer"))
end

test("lease probe is non-mutating and discovers support", function()
    local target = session("one")
    ready_and_select(target)
    complete_probe(target, "free", 0, 0)
    equal(target.lease_supported, true)
    equal(target.lease_observed.mode, "free")
    equal(target.state, "available")
end)

test("missing capability response fails closed", function()
    local target = session("one")
    ready_and_select(target)
    assert(target:probe())
    target:drain()
    feed_device_info(target, 0)
    assert(target:info_end())
    target:drain()
    equal(target.lease_supported, false)
    local ok, err = target:claim()
    equal(ok, nil)
    equal(err, "lease_unsupported")
    equal(osc_addresses(target:drain()), "")
end)

test("free destination grants and verifies a renewable lease", function()
    local target = session("one")
    ready_and_select(target)
    complete_probe(target, "free", 0, 0)
    complete_claim(target, false)

    assert(target:renew())
    local outputs = target:drain()
    equal(osc_addresses(outputs), "/sys/lease/renew")
    local renew = find(outputs, "osc", "/sys/lease/renew")
    equal(renew.atoms[1], target.lease_token)
    equal(renew.atoms[2], 6000)
    equal(renew.atoms[3], "127.0.0.1")
    equal(renew.atoms[4], 17780)
    assert(find(outputs, "control", "lease_timer"))
    equal(target.renew_pending, true)
    assert(target:lease_renewed(target.lease_token, 6000))
    target:drain()
    equal(target.renew_pending, false)

    assert(target:check())
    outputs = target:drain()
    equal(osc_addresses(outputs), "/sys/lease/info")
    feed_lease_state(target, "leased", 17780, 1)
    assert(target:info_end())
    equal(target.state, "connected")
end)

test("legacy destination requires explicit takeover", function()
    local target = session("one")
    ready_and_select(target)
    complete_probe(target, "legacy", 8000, 0)
    local ok, err = target:claim()
    equal(ok, nil)
    equal(err, "takeover_required")
    equal(osc_addresses(target:drain()), "")
    complete_claim(target, true)
end)

test("another lease owner is never taken over", function()
    local target = session("one")
    ready_and_select(target)
    complete_probe(target, "leased", 19000, 0, "/rival")
    local ok, err = target:takeover()
    equal(ok, nil)
    equal(err, "lease_busy")
    equal(osc_addresses(target:drain()), "")
end)

test("release requires explicit free-state readback", function()
    local claims = Core.ClaimRegistry.new()
    local target = session("one", claims)
    ready_and_select(target)
    complete_probe(target, "free", 0, 0)
    complete_claim(target, false)
    equal(claims:owner("m100"), "one")

    assert(target:release())
    local outputs = target:drain()
    equal(osc_addresses(outputs), "/sys/lease/release")
    local release = find(outputs, "osc", "/sys/lease/release")
    equal(release.atoms[1], target.lease_token)
    equal(release.atoms[2], "127.0.0.1")
    equal(release.atoms[3], 17780)
    assert(find(outputs, "control", "cancel_lease_timer"))
    assert(target:lease_released(target.lease_token))
    outputs = target:drain()
    equal(osc_addresses(outputs), "/sys/lease/info")
    feed_lease_state(target, "free", 0, 0)
    assert(target:info_end())
    outputs = target:drain()
    equal(target.state, "available")
    equal(claims:owner("m100"), nil)
    assert(find(outputs, "status", "released"))
end)

test("no-lease release reply is verified idempotently", function()
    local target = session("one")
    ready_and_select(target)
    complete_probe(target, "free", 0, 0)
    complete_claim(target, false)
    assert(target:release())
    target:drain()
    assert(target:lease_rejected(target.lease_token, "no_lease"))
    equal(osc_addresses(target:drain()), "/sys/lease/info")
    feed_lease_state(target, "free", 0, 0)
    assert(target:info_end())
    equal(target.state, "available")
end)

test("renew rejection drops the ownership assertion", function()
    local target = session("one")
    ready_and_select(target)
    complete_probe(target, "free", 0, 0)
    complete_claim(target, false)
    assert(target:renew())
    target:drain()
    local ok, err = target:lease_rejected(target.lease_token, "not_owner")
    equal(ok, nil)
    equal(err, "not_owner")
    equal(target.state, "displaced")
    equal(target.lease_active, false)
end)

test("missing renewal reply fails before the daemon TTL", function()
    local target = session("one")
    ready_and_select(target)
    complete_probe(target, "free", 0, 0)
    complete_claim(target, false)
    assert(target:renew())
    target:drain()
    local ok, err = target:renew()
    equal(ok, nil)
    equal(err, "renew_timeout")
    equal(target.state, "displaced")
end)

test("renew failure cancels an overlapping readback", function()
    local target = session("one")
    ready_and_select(target)
    complete_probe(target, "free", 0, 0)
    complete_claim(target, false)

    assert(target:check())
    target:drain()
    equal(target.request, "verify")
    assert(target:renew())
    target:drain()

    local ok, err = target:lease_rejected(target.lease_token, "not_owner")
    equal(ok, nil)
    equal(err, "not_owner")
    equal(target.state, "displaced")
    equal(target.request, nil)
    local outputs = target:drain()
    assert(find(outputs, "control", "cancel_info_timer"))
    assert(find(outputs, "control", "cancel_lease_timer"))
end)

test("lost notification drops capability ownership", function()
    local target = session("one")
    ready_and_select(target)
    complete_probe(target, "free", 0, 0)
    complete_claim(target, false)
    assert(target:lease_lost(target.lease_token, "expired"))
    local outputs = target:drain()
    equal(target.state, "displaced")
    equal(target.lease_active, false)
    assert(find(outputs, "status", "displaced"))
end)

test("late lost notification after removal is harmless", function()
    local target = session("one")
    ready_and_select(target)
    complete_probe(target, "free", 0, 0)
    complete_claim(target, false)
    assert(target:device_removed("m100"))
    target:drain()
    assert(target:lease_lost(target.lease_token, "expired"))
    equal(target.state, "absent")
    assert(find(target:drain(), "status", "ignored"))
end)

test("grant timeout never becomes connected", function()
    local target = session("one")
    ready_and_select(target)
    complete_probe(target, "free", 0, 0)
    assert(target:claim())
    target:drain()
    local ok, err = target:info_end()
    equal(ok, nil)
    equal(err, "lease_grant_timeout")
    equal(target.state, "displaced")
end)

io.stdout:write(string.format("lease_session_spec: %d tests passed\n", passed))

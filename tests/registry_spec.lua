local script_path = debug.getinfo(1, "S").source:sub(2)
local project_root = script_path:match("^(.*)/tests/registry_spec.lua$")
if script_path == "tests/registry_spec.lua" then
    project_root = "."
end
assert(project_root, "run this test from its checked-out project path")

local Registry = dofile(project_root .. "/monome_registry.lua")

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

test("devices are ordered by stable serial ID", function()
    local registry = Registry.new()
    registry:upsert("m200", "monome 256", 12002)
    registry:upsert("m100", "monome 128", 12001)

    local snapshot = registry:snapshot()
    equal(snapshot[1].serial, "m100")
    equal(snapshot[2].serial, "m200")
end)

test("discovery never auto-selects", function()
    local registry = Registry.new()
    registry:upsert("m100", "monome 128", 12001)
    equal(registry:selection(), nil)
end)

test("duplicate replies update one record", function()
    local registry = Registry.new()
    equal(registry:upsert("m100", "monome 128", 12001), "added")
    equal(registry:upsert("m100", "monome 128", 12001), "unchanged")
    equal(registry:upsert("m100", "monome 128", 13001), "updated")
    equal(#registry:snapshot(), 1)
    equal(registry:snapshot()[1].port, 13001)
end)

test("selection survives a reordered complete scan", function()
    local registry = Registry.new()
    registry:upsert("m100", "monome 128", 12001)
    registry:upsert("m200", "monome 256", 12002)
    assert(registry:select("m200"))

    registry:begin_scan()
    registry:upsert("m200", "monome 256", 12002)
    registry:upsert("m100", "monome 128", 12001)
    local result = assert(registry:end_scan())

    equal(#result.removed, 0)
    equal(result.selection_lost, nil)
    equal(registry:selection().serial, "m200")
end)

test("scan end removes stale records and reports lost selection", function()
    local registry = Registry.new()
    registry:upsert("m100", "monome 128", 12001)
    registry:upsert("m200", "monome 256", 12002)
    registry:select("m200")

    registry:begin_scan()
    registry:upsert("m100", "monome 128", 12001)
    local result = assert(registry:end_scan())

    equal(#result.removed, 1)
    equal(result.removed[1], "m200")
    equal(result.selection_lost, "m200")
    equal(registry:selection(), nil)
end)

test("removing another device preserves selection", function()
    local registry = Registry.new()
    registry:upsert("m100", "monome 128", 12001)
    registry:upsert("m200", "monome 256", 12002)
    registry:select("m100")

    local result = assert(registry:remove("m200"))
    equal(result.selection_lost, nil)
    equal(registry:selection().serial, "m100")
end)

test("menu index is a projection rather than identity", function()
    local registry = Registry.new()
    registry:upsert("m200", "monome 256", 12002)
    registry:upsert("m100", "monome 128", 12001)

    local selected = assert(registry:select_index(1))
    equal(selected.serial, "m200")
    equal(registry:selection().serial, "m200")
end)

test("invalid records fail closed", function()
    local registry = Registry.new()
    local change, err = registry:upsert("m100", "monome 128", 0)
    equal(change, nil)
    equal(err, "invalid_port")
    equal(#registry:snapshot(), 0)

    local ended, scan_err = registry:end_scan()
    equal(ended, nil)
    equal(scan_err, "scan_not_active")
end)

io.stdout:write(string.format("registry_spec: %d tests passed\n", passed))

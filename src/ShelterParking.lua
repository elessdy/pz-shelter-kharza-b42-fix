-- Original compatibility hook for the private Shelter2238B42Local prototype.
-- Keep vanilla zones intact: a map-level objects.lua would clear a larger legacy grid area.
require "metazones/metazoneHandler"

local function shelterMapIsLoaded()
    local directories = getLotDirectories()
    for i = 0, directories:size() - 1 do
        if directories:get(i) == "Shelter2238B42Local" then
            return true
        end
    end
    return false
end

local function registerShelterParking()
    if not shelterMapIsLoaded() then return end

    local world = getWorld()
    local grid = world:getMetaGrid()
    local existing = grid:getVehicleZoneAt(6694, 11597, 0)
    if existing and existing:getType() == "ParkingStall"
        and existing:getX() == 6692 and existing:getY() == 11596
        and existing:getWidth() == 5 and existing:getHeight() == 3 then
        print("SHELTER_PARKING|REGISTERED|x=6692|y=11596|z=0|width=5|height=3|existing=true")
        return
    end

    -- Coordinates are world tiles from the original shelter's single parking rectangle.
    local zone = world:registerVehiclesZone("", "ParkingStall", 6692, 11596, 0, 5, 3, nil)
    world:checkVehiclesZones()
    if zone and zone:getX() == 6692 and zone:getY() == 11596
        and zone:getWidth() == 5 and zone:getHeight() == 3 then
        print("SHELTER_PARKING|REGISTERED|x=6692|y=11596|z=0|width=5|height=3|existing=false")
    else
        print("SHELTER_PARKING|FAILED|x=6692|y=11596|z=0|width=5|height=3")
    end
end

-- The require above registers normal map-zone loading before this callback.
Events.OnLoadMapZones.Add(registerShelterParking)

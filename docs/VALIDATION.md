# Accepted reference and validation

## Shelter 22 38 — October 2, 2026

The accepted local visual package is `prototype-v003`. A clean converter rebuild
(`prototype-v004`) reproduced **all 183 packaged files byte for byte**, with no
added, missing, or changed files. The converter now includes these fixes directly;
the prototype does not depend on replaying manual edits.
The source-cell generalization also passed this exact comparison (`prototype-v005`).
The published reference manifest uses those identical payload bytes plus the
builder's 18 required directory declarations; it contains no game or mod assets.
The final generalized build (`prototype-v009`) passed again after the second
shelter's polygon handling was added, including the published release fingerprint.

### Included compatibility work

- Convert the original 300 × 300 map cell into four B42 256 × 256 cells at its
  original world position; preserve the surrounding vanilla terrain.
- Correct density-chunk coordinates and room-object metadata after stock conversion.
- Regenerate the map overlay binary, preserving polygon holes and edge features.
- Convert spawn coordinates and register only the original parking rectangle.
- Create empty `common/media/maps` directories required by B42 map discovery.
- Apply `Translucent` to the 17 custom reed sprites.
- Assign canonical depth maps to five Melos roof slopes and the front eave.
- Apply `OpaquePixelsOnly` to the front eave. No window or roof tiles were moved.

The small original declarations under `templates/shelter2238-v003/` reference
separately installed assets. They do not contain textures or copied game geometry.

### Evidence

- 3,932,160 tile/layer comparisons and 262,144 ground-flag comparisons passed.
- 4,096 density chunks, five rooms, two buildings, and 13 room objects validated.
- The installed game's map-overlay parser accepted the converted binary.
- A private server loaded nine real chunks around the spawn point.
- The client spawned at the intended shelter floor.
- The user's manual playtest confirmed doors, stairs, improved plants, and the
  final appearance. The user accepted the existing rooftop barrel appearance.
- Actual client logs confirmed resuming the existing character in the same save
  after fixing map discovery. No extra automated graphical reload test was run.

### Remaining limits

An actual multiplayer join and traversal with matching converted packages have
not been tested. The complete server mod stack is also untested. Legacy B41
foraging zones are not migrated: the prototype retains current vanilla zones and
biomes, with the shelter's parking rectangle registered separately. New clipping
intersections use integer rounding, bounded by the overlay validator.

Visual acceptance applies to Shelter 22 38 on the pinned build. Each additional
shelter needs its own conversion validation and manual walkthrough.

## Regression method

Keep accepted generated assets and their receipts locally, outside Git. Build into
a fresh output directory and compare the complete file manifest against the
accepted package. Retain failures and diagnostics rather than overwriting them.
The portable manifest fingerprints required directory declarations alongside the
files and verifies their existence, so missing empty discovery folders also fail.

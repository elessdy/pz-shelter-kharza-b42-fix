# Shelter 22 28 candidate

**Conversion validated; manual gameplay and multiplayer are not yet tested.**

- Source: Kharza's [Shelter 22 28](https://steamcommunity.com/sharedfiles/filedetails/?id=3221271772).
- Dependency: [SHELTERS TileSet](https://steamcommunity.com/sharedfiles/filedetails/?id=3221270060).
- Original cell: `22_28`, at its original world coordinates.
- B42 output cells: `25_32`, `25_33`, `26_32`, `26_33`.
- Local mod/map ID: `Shelter2228B42Local`.
- Spawn: `6641,8416,0`.
- Map order: `Shelter2228B42Local;Muldraugh, KY`.

Build with `src/build_prototype.py --shelter 22-28` and the same pinned B42.21
runtime and local path arguments described in the README. Use a fresh output tag.
The converter emits no Melos dependency or Shelter 22 38 parking hook for this map.

## Evidence from the first completed build

The private `prototype-v008` build passed stock conversion, vanilla-edge merge,
tile comparisons, independent metadata validation, spawn migration, and game map
overlay parsing. It produced a portable file/directory manifest. Its candidate
reference is committed as hashes only:
[`reference/shelter-22-28-b42.21-candidate.json`](reference/shelter-22-28-b42.21-candidate.json).

This map revealed a polygon hole whose first vertex touches the containing outer
boundary. Ownership is now determined using the whole hole area. The emitted XML
and decoded binary are checked for exact feature, property, ring and coordinate
agreement.

Clipping required rounding 95 vertices by at most 0.5 tile. The measured map-overlay
area difference was 83.331 square tiles, within the calculated swept-edge rounding
bound of 83.450. The difference occurs in forest and river polygons; building and
road areas are unchanged. This map has an explicit 84-square-tile cap. Shelter
22 38 retains its existing 64-square-tile cap and exact reference file hashes.

## Next manual check

Use a separate profile and disposable world. Confirm appearance, the spawn floor,
doors, stairs at approximately `6648,8429..8431`, and crossing the shelter's edges.
Then save, exit, and resume the same character. Successful file conversion alone
does not establish collision behavior, lighting, biome equivalence, or multiplayer.

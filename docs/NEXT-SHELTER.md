# Shelter 22 28 candidate

**Conversion validated; an initial manual visit found missing grass artwork.
The texture-restoration candidate still needs visual validation. Multiplayer is
not yet tested.**

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
overlay parsing. The current `prototype-v010` candidate adds the narrow texture
restoration below and passed the same conversion checks. Its manifest records
23 payload files and 12 required directories, with fingerprint
`5cb745c13bb40ab11796f34fb90333156327b2440f40e9299e9a8a69ca5f84c9`.
The candidate reference is committed as hashes only:
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

## Missing grass restoration candidate

The initial manual visit exposed missing `e_newgrass_1_87` artwork. The map contains
35 instances of that sprite. Its tile definition still exists, but its texture
is absent from the loaded 2x pack; the original artwork remains in the installed
`Tiles1x.pack`.

`RestoreLegacyGrass.java` reads that local pack and writes one sprite under the
same name into a small private 2x pack. It replicates every RGBA pixel exactly
twice in each dimension and doubles the offsets and original canvas dimensions.
The only additional rendering property is `Translucent=true`. No map objects,
tile names, saved objects or save files are rewritten by this restoration.
The pack round-trip verified all 6,032 replicated pixels and 2,160 transparent
padding pixels. These file checks do not establish the final visual result.
Compared with the first completed build, 20 payload files are identical; only
`mod.info` changed and the restoration pack and property template were added.
The stock geometry parser accepted the template's sole `Translucent` property.

The dark lattice roof slopes match the original author's poster and source
artwork. An independent comparison found all 274 roof-square coordinates and
complete ordered tile stacks unchanged. The candidate preserves those slopes;
it does not replace them with a different roof material.

## Next manual check

Use a separate profile and disposable world. Confirm restored grass appearance,
including transparency and placement, then the spawn floor,
doors, stairs at approximately `6648,8429..8431`, and crossing the shelter's edges.
Then save, exit, and resume the same character. Successful file conversion alone
does not establish collision behavior, lighting, biome equivalence, or multiplayer.

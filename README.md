# Kharza shelter compatibility tooling for Project Zomboid B42

Build local B42 shelter mods from your own installed B41 Workshop originals.
The repository contains the converter and validation tools; it does not contain
the game, original maps, texture packs, or converted map downloads.

This is an experimental, version-pinned project. **Shelter 22 38 is the accepted
single-player reference. Multiplayer joining has not yet been validated.**

## Current scope

| Shelter | Status |
| --- | --- |
| 22 38 | Conversion and server chunk loading validated; user accepted visuals, doors and stairs; existing character resumed successfully. Fresh rebuild reproduces all 183 accepted payload files. |
| 22 28 | Converted; map, metadata and overlay validations passed. Separate manual playtest pending. |
| Other shelters | Not supported yet. |

The tested game is **B42.21**, with this `projectzomboid.jar` SHA-256:

```text
e1a69eb743ede60b213a0fe7f8b83d4fcab773036d256cc4543a336f3b058a33
```

The builder refuses a different game JAR. Compatibility with a future build must
be assessed before changing this pin.

## Requirements

- Python 3.11 or newer and a JDK 25 with both `java` and `javac`.
- A local installation of the pinned Project Zomboid build, including its `media`
  directory. The builder reads it without installing anything into it.
- Original Workshop files for the selected shelter and its dependencies:
  [Shelter 22 38](https://steamcommunity.com/sharedfiles/filedetails/?id=3259059290),
  [SHELTERS TileSet](https://steamcommunity.com/sharedfiles/filedetails/?id=3221270060),
  and [Melos Tiles for Miles](https://steamcommunity.com/sharedfiles/filedetails/?id=2879745353).

## Build the reference shelter

From the repository directory, with paths appropriate for your machine:

```powershell
python src/build_prototype.py --tag prototype-v001 `
  --runtime 'C:/Program Files (x86)/Steam/steamapps/common/ProjectZomboid' `
  --workshop-root 'C:/Program Files (x86)/Steam/steamapps/workshop/content/108600' `
  --jdk-bin 'C:/path/to/jdk-25/bin'
```

The default selection is `--shelter 22-38`. To build the next candidate, use
`--shelter 22-28` with a new tag and the original
[Shelter 22 28](https://steamcommunity.com/sharedfiles/filedetails/?id=3221271772)
and SHELTERS TileSet subscriptions. That map does not require Melos.
See [Shelter 22 28 status](docs/NEXT-SHELTER.md) before playtesting it.

Use a new tag for each build; the builder never overwrites an existing build.
Output goes under `private/<tag>/mods`. Inputs, diagnostics, and local provenance
receipts remain under `private/`, which is excluded from Git.
Each successful build also writes a portable `package-manifest.json` beside the
mods, with file hashes and required empty-directory checks.

The build converts the old 300-tile cell into intersecting B42 256-tile cells,
restores unaffected vanilla edges, corrects density and room-object metadata,
migrates the map overlay and spawn points, validates the result, and includes the
accepted visual fixes. No game, server, or player profile is launched or changed.

To compare a later build with a previous local accepted package, add
`--reference-build private/<accepted-tag>`. This requires every payload file to
match, as well as the map-discovery directory to exist.

## Testing and installation

Use an isolated profile and a new disposable world for each new map conversion.
Keep original B41 versions disabled when enabling generated B42 replacements.
The ordinary player profile and multiplayer server are not configured by this
tool. Do not add an untested conversion to an existing shared world.

The generated folders are normal local mods. Empty `common/media/maps` directories
are required by this game build's map discovery and must survive installation.
The map order for the accepted reference is
`Shelter2238B42Local;Muldraugh, KY`.

See [validation evidence](docs/VALIDATION.md) for what has and has not passed,
[multiplayer matching](docs/MULTIPLAYER.md) for the planned join workflow, and
[attribution](NOTICE.md) for asset boundaries.

The accepted reference's file fingerprints are preserved in
[`docs/reference/shelter-22-38-b42.21.json`](docs/reference/shelter-22-38-b42.21.json).
Verify future builds against that file before treating them as equivalent to the
accepted reference; the manifest produced by a new build alone is not approval.

Run the asset-free verifier tests with:

```sh
python -B -m unittest discover -s tests -v
```

CI runs those tests on Windows and Linux. Full conversion tests need separately
installed game and Workshop files and are not run by public CI.

## Repository contents

- `src/`: original converter adapters and validation tools.
- `templates/`: original rendering-property and depth-alias declarations.
- `tests/`: synthetic tests that require no game or Workshop assets.
- `docs/`: accepted behavior, limitations, and multiplayer matching design.

The repository uses an explicit file allowlist. Generated maps, runtime copies,
credentials, and unreviewed research helpers are not part of the public source.

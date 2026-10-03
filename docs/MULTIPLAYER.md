# Matching local mods for multiplayer

## What the game checks

Inspection of the pinned B42.21 runtime shows that joining checks required mod IDs
and compares Lua, script, and animation checksums. This is not a digest of every
map, tileset, texture pack, or metadata file in a mod folder. Matching identifiers
and a successful checksum check do not certify that a converted map works.

Keep the game's normal checksum checks enabled. Local generated mods need to be
installed on both the server and every player's computer; they are not downloaded
automatically through Workshop merely because a server requires their mod IDs.

## File verification

`src/package_manifest.py` creates and verifies a portable manifest containing
SHA-256 fingerprints for payload files and explicit game/converter/mod metadata.
A release manifest must come from an accepted reference build. Players verify
their generated output against that reference, not against a manifest freshly
created from their own potentially different files.

The verifier detects missing, changed, and extra files and rejects unsafe paths.
Required empty directories are declared in the fingerprint too, including the
`common/media/maps` scaffolding that fixed the missing-map dialog. A full manifest
is an integrity check against a trusted release; it is not a signature or an
anti-cheat boundary.

The builder writes `package-manifest.json` beside each generated `mods` directory.
The accepted Shelter 22 38 reference is committed as hashes only under
`docs/reference/shelter-22-38-b42.21.json`: 183 files and 18 required directories.
Its fingerprint is:

```text
fca05c7449b64e9d1f400364f3f441864c783c7449f578d72e1fb15d524b1e94
```

After building, verify against that accepted reference:

```powershell
python src/package_manifest.py verify private/prototype-v001/mods `
  --manifest docs/reference/shelter-22-38-b42.21.json `
  --expected-fingerprint fca05c7449b64e9d1f400364f3f441864c783c7449f578d72e1fb15d524b1e94
```

`READY` means the declared package files and directories match. `MISMATCH` lists
the differences. If an original Workshop dependency has updated, do not create a
new reference merely to suppress the mismatch: inspect and test that update first.

## Intended player workflow

1. Subscribe to the required original Workshop items.
2. Build local B42 replacements using the pinned converter and game version.
3. Verify the output against the server's accepted release manifest.
4. Install the generated local mods and join normally.

The fingerprint CLI is implemented. A friendly installer, update coordination,
and actual Steam multiplayer join are still outstanding. No converted assets are
published in this repository.

## Multiplayer validation before deployment

Use isolated server and client profiles with the same validated package, required
mod IDs, dependencies, and map order. Confirm joining, appearance, door and stair
movement, saving/reconnecting, and server-authoritative position around the shelter.
Record game and package versions. Test the final combined mod stack separately.

Prepared local probe helpers are research artifacts; no multiplayer pass is
claimed from their existence or from the earlier server chunk-loading check.

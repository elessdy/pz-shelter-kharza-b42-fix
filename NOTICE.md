# Attribution and repository boundaries

This repository contains original conversion adapters, validation tools, and small
compatibility metadata templates. Its MIT license covers that original tooling
only. It does not grant rights to Project Zomboid, Workshop mods, or generated
packages containing those assets.

Obtain the game and each required Workshop item separately. Game JARs, texture
packs, tilesets, map files, screenshots, saved worlds, downloaded tools, credentials,
and generated converted mods are excluded from this repository.

## Upstream work

- **The Indie Stone — Project Zomboid.** The converter calls the locally installed
  game's `zombie.pot.POT` converter and map readers. No game implementation or JAR
  is bundled. [Project Zomboid](https://projectzomboid.com/)
- **Kharza — SHELTERS and SHELTERS TileSet.** Original map and artwork authorship
  stays with the upstream creators. This project is an independent compatibility
  effort and is not an official Kharza release.
  [TileSet](https://steamcommunity.com/sharedfiles/filedetails/?id=3221270060),
  [Shelter 22 38](https://steamcommunity.com/sharedfiles/filedetails/?id=3259059290),
  [Shelter 22 28](https://steamcommunity.com/sharedfiles/filedetails/?id=3221271772).
- **melos_tiles and credited contributors — Melos Tiles for Miles.** Used locally
  by Shelter 22 38; neither its artwork nor its packs are redistributed here.
  [Workshop page](https://steamcommunity.com/sharedfiles/filedetails/?id=2879745353)
- **Unjammer — PZ_B41toB42-Converter.** Reference for invoking the stock converter;
  its implementation and game JAR are not vendored or relicensed here.
  [Reference repository](https://github.com/Unjammer/PZ_B41toB42-Converter)

Review upstream terms before distributing any converted assets. A locally generated
package remains subject to its original assets' terms. See the
[Project Zomboid modding policy](https://projectzomboid.com/blog/modding-policy/).

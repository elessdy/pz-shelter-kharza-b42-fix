"""Apply scoped, original rendering metadata for the two shelter presets.

Only sprite names and properties are included. Game depth images and the mod
authors' artwork remain separate, locally supplied dependencies.
"""
from pathlib import Path
import hashlib

TEMPLATES = Path(__file__).resolve().parents[1] / "templates/shelter2238-v003"
MAP_MEDIA = Path("Shelter2238B42Local/common/media")
ACCEPTED_SHA256 = {
    "tileGeometry.txt": "6fc8f10555a53a73280da20111d1bfca42314b5cd127881171638df3260e1079",
    "tileDepthTextureAssignments.txt": "ae206107cdecdec02c7680db21664c3776308f23d558b70f511d4fb7422f228a",
}


def apply_2228_grass_metadata(mods_root):
    """Mark restored legacy grass translucent without borrowing depth/behavior."""
    template = TEMPLATES.parent / "shelter2228-grass/tileGeometry.txt"
    relative = Path("Shelter2228B42Local/common/media/tileGeometry.txt")
    payload = template.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
    target = Path(mods_root) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(payload)
    return {"profile": "shelter2228-grass", "sprite": "e_newgrass_1_87",
            "property": "Translucent=true", "depth_alias": None,
            "metadata_sha256": {relative.as_posix(): hashlib.sha256(payload).hexdigest()},
            "reference_visuals_accepted_by_user": False, "this_build_launched": False}


def apply_shelter_visual_fixes(mods_root):
    """Write the two accepted files; refuse different existing metadata."""
    target = Path(mods_root) / MAP_MEDIA
    payloads = {}
    for name, expected in ACCEPTED_SHA256.items():
        # Normalize Git checkout endings, then emit the accepted Windows bytes.
        payload = (TEMPLATES / name).read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError("Visual template changed; revalidate before use: " + name)
        destination = target / name
        if destination.exists() and destination.read_bytes() != payload:
            raise ValueError("Refusing to replace different metadata: " + str(destination))
        payloads[name] = payload
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (target / name).write_bytes(payload)
    # B42.21 MapGroups skips the version branch when this directory is absent.
    (target / "maps").mkdir(exist_ok=True)
    return {
        "profile": "shelter2238-v003",
        "roof_slope_depth_aliases": 5,
        "roof_slope_property": "Translucent=true",
        "front_eave_alias": "melos_tiles_roofs_08a_70=roofs_01_7",
        "front_eave_property": "OpaquePixelsOnly=true",
        "reed_sprites": "dl_reed_0 through dl_reed_16",
        "reed_property": "Translucent=true",
        "metadata_sha256": {(MAP_MEDIA / name).as_posix(): value
                            for name, value in ACCEPTED_SHA256.items()},
        "reference_visuals_accepted_by_user": True,
        "this_build_launched": False,
    }

"""Build private Shelter 22 38 or 22 28 B42 prototypes from local inputs.
Does not install, enable, publish, or launch anything. Supports only the pinned
42.21 game JAR and the two explicit source-map presets, not arbitrary maps.
"""
from pathlib import Path
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, sys
from shelter_visual_fixes import apply_shelter_visual_fixes
from package_manifest import create_manifest, verify_manifest
ROOT=Path(__file__).resolve().parents[1]
PRESETS={
    "22-38":{"source":"3259059290/mods/Shelter 22 38/media/maps/Shelter 22 38",
             "cell":(22,38),"name":"Shelter 22 38","id":"Shelter2238B42Local",
             "spawn":[6687,11587,1],"melos":True,"visual_fixes":True},
    "22-28":{"source":"3221271772/mods/Shelter 22 28/media/maps/Shelter 22 28",
             "cell":(22,28),"name":"Shelter 22 28","id":"Shelter2228B42Local",
             "spawn":[6641,8416,0],"melos":False,"visual_fixes":False},
}
def configured_path(variable, default): return Path(os.environ.get(variable) or default)
P=argparse.ArgumentParser(description=__doc__)
P.add_argument("--tag",required=True,help="New private build folder, e.g. prototype-v001")
P.add_argument("--shelter",choices=tuple(PRESETS),default="22-38",help="Explicit source-map preset (default:22-38)")
P.add_argument("--runtime",type=Path,default=configured_path("PZ_SHELTERS_RUNTIME",ROOT/"private/runtime"),
               help="Local B42.21 directory containing projectzomboid.jar and media")
P.add_argument("--workshop-root",type=Path,default=configured_path("PZ_SHELTERS_WORKSHOP_ROOT",r"C:\Program Files (x86)\Steam\steamapps\workshop\content\108600"),
               help="Local Project Zomboid Workshop content/108600 directory")
P.add_argument("--jdk-bin",type=Path,default=configured_path("PZ_SHELTERS_JDK_BIN",ROOT/"tools/jdk-25.0.4.1+1/bin"),
               help="JDK 25 bin directory containing java and javac")
P.add_argument("--output-root",type=Path,default=configured_path("PZ_SHELTERS_OUTPUT_ROOT",ROOT/"private"),
               help="Output parent, restricted to this checkout's private directory")
P.add_argument("--reference-build",type=Path,help="Optional prior local build whose complete mods payload must match")
P.add_argument("--converter-version",default="0.1.0",help="Converter release label included in portable package fingerprint")
args=P.parse_args()
if not re.fullmatch(r"(?:prototype|shelter2228|shelter2238)-v[0-9]{3}",args.tag): P.error("Use prototype-vNNN, shelter2228-vNNN or shelter2238-vNNN")
PRESET=PRESETS[args.shelter]
CELL=PRESET["cell"]
CELL_NAME="_".join(map(str,CELL))
MAP_ID=PRESET["id"]
MAP_NAME=PRESET["name"]
DEPENDENCIES=(["melos_tiles_for_miles_pack"] if PRESET["melos"] else [])+["SheltersTilesB42Local"]
REQUIRES=",".join("\\"+name for name in DEPENDENCIES)
OUTPUT_ROOT=args.output_root.expanduser().resolve()
if not OUTPUT_ROOT.is_relative_to((ROOT/"private").resolve()): P.error("Output root must stay inside this checkout's private directory")
OUT=OUTPUT_ROOT/args.tag
if OUT.exists(): raise SystemExit("Output already exists; select a new tag. Previous results are preserved.")
RUNTIME=args.runtime.expanduser().resolve(strict=True)
JAR=RUNTIME/"projectzomboid.jar"
EXPECTED_JAR="e1a69eb743ede60b213a0fe7f8b83d4fcab773036d256cc4543a336f3b058a33"
def sha(p):
    with p.open("rb") as stream: return hashlib.file_digest(stream,"sha256").hexdigest()
def file_manifest(directory):
    return {p.relative_to(directory).as_posix():sha(p) for p in sorted(directory.rglob("*")) if p.is_file()}
if sha(JAR)!=EXPECTED_JAR: raise SystemExit("Unvalidated game JAR. Reassess conversion against the new game build.")
W=args.workshop_root.expanduser().resolve(strict=True)
SOURCE=W/PRESET["source"]
TILES=W/"3221270060/mods/Shelters Tileset"
MELOS=W/"2879745353/mods/Melos Tiles for Miles"
VANILLA=RUNTIME/"media/maps/Muldraugh, KY"
JDK=args.jdk_bin.expanduser().resolve(strict=True)
EXE=".exe" if os.name=="nt" else ""
JAVA=JDK/("java"+EXE); JAVAC=JDK/("javac"+EXE)
if not JAVA.is_file() or not JAVAC.is_file(): raise SystemExit("Both java and javac are required in --jdk-bin")
REFERENCE=args.reference_build.expanduser().resolve(strict=True) if args.reference_build else None
expected_payload=None
if REFERENCE:
    expected_payload=json.loads((REFERENCE/"build-receipt.json").read_text(encoding="utf-8"))["package_file_sha256"]
    if file_manifest(REFERENCE/"mods")!=expected_payload: raise SystemExit("Reference files differ from their receipt")
CLASSES=OUT/"classes"
OUT.mkdir(parents=True); (OUT/"input-b41").mkdir(); CLASSES.mkdir(); (OUT/"runtime-home").mkdir()
sources={}
def copied(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst)
    sources[str(src)]={"size":src.stat().st_size,"sha256":sha(src)}
for name in (CELL_NAME+".lotheader","world_"+CELL_NAME+".lotpack","chunkdata_"+CELL_NAME+".bin"):
    copied(SOURCE/name,OUT/"input-b41"/name)
env=os.environ.copy()
for key in ("_JAVA_OPTIONS","JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS"): env.pop(key,None)
cp=os.pathsep.join((str(CLASSES),str(JAR)))
# Build only the conversion dependencies, never unrelated unfinished diagnostics.
java_sources=("ConvertShelterMap.java","ShelterCell.java","MergeShelterEdges.java","ValidateShelterMap.java","ConvertShelterAncillary.java")
compilation=subprocess.run([str(JAVAC),"-cp",str(JAR),"-d",str(CLASSES)]+
 [str(ROOT/"src"/name) for name in java_sources],env=env,capture_output=True,text=True,encoding="utf-8",errors="replace")
(OUT/"javac.log").write_text(compilation.stdout+compilation.stderr,encoding="utf-8")
if compilation.returncode: raise SystemExit("Compilation failed; inspect javac.log. Incomplete output preserved.")
def run(name,*parameters):
    result=subprocess.run([str(JAVA),"-Xmx1536m","-Duser.home="+str(OUT/"runtime-home"),
        "-cp",cp,name]+[str(p) for p in parameters],cwd=ROOT,env=env,capture_output=True,text=True,encoding="utf-8",errors="replace")
    (OUT/(name.rsplit(".",1)[-1]+".log")).write_text(result.stdout+result.stderr,encoding="utf-8")
    if result.returncode: raise SystemExit("Failed "+name+"; inspect its log. Incomplete output preserved.")
    print("PASS",name,flush=True)
run("ConvertShelterMap",ROOT,OUT/"input-b41",OUT/"converted")
run("zombie.pot.MergeShelterEdges",ROOT,OUT/"input-b41",OUT/"converted",VANILLA,OUT/"merged",*CELL)
run("zombie.pot.ValidateShelterMap",OUT/"input-b41",OUT/"merged",*CELL)
subprocess.run([sys.executable,"-B",str(ROOT/"src/ValidateShelterMetadata.py"),str(OUT/"input-b41"),str(VANILLA),str(OUT/"merged"),"--source-cell",*map(str,CELL),"--report",str(OUT/"metadata-validation.json")],env=env,check=True)

run("ConvertShelterAncillary",ROOT,SOURCE,VANILLA,OUT/"ancillary",*CELL)
mods=OUT/"mods"
tilemod=mods/"SheltersTilesB42Local"
for rel in ("media/shelters-tileset.tiles","media/texturepacks/shelters-tileset.pack"):
    copied(TILES/rel,tilemod/"42"/rel)
(tilemod/"42/mod.info").write_text("""name=SHELTERS Tiles B42 Local Prototype
id=SheltersTilesB42Local
versionMin=42.21
pack=shelters-tileset
tiledef=shelters-tileset 2024
description=Private local compatibility prototype; requires original assets.
""",encoding="utf-8",newline="\r\n")
mapmod=mods/MAP_ID
mapdir=mapmod/"42/media/maps"/MAP_ID
mapdir.mkdir(parents=True)
for f in (OUT/"merged").iterdir():
    if f.suffix in (".lotheader",".lotpack",".bin"): shutil.copy2(f,mapdir/f.name)
for name in ("spawnpoints.lua","worldmap.xml","worldmap.xml.bin"):
    shutil.copy2(OUT/"ancillary"/name,mapdir/name)
parking=OUT/"ancillary/ShelterParking.lua"
if parking.exists():
    target=mapmod/"42/media/lua/server/ShelterParking.lua"
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(parking,target)
copied(SOURCE/"thumb.png",mapdir/"thumb.png")
(mapdir/"map.info").write_text(f"""title={MAP_NAME} B42 Local Prototype
lots=Muldraugh, KY
description=Private compatibility playtest at original world location.
""",encoding="utf-8",newline="\r\n")
(mapmod/"42/mod.info").write_text(f"""name={MAP_NAME} B42 Local Prototype
id={MAP_ID}
versionMin=42.21
require={REQUIRES}
description=Private local conversion. Visual and multiplayer playtesting required.
""",encoding="utf-8",newline="\r\n")
if PRESET["melos"]:
    for branch in ("42","common"): shutil.copytree(MELOS/branch,mods/"MelosTiles"/branch)
required_directories=[]
for mod in mods.iterdir():
    for branch in ("42","common"):
        # MapGroups checks common/media/maps before it looks at 42/media/maps.
        for folder in ("AnimSets","actiongroups","maps"):
            directory=mod/branch/"media"/folder
            directory.mkdir(parents=True,exist_ok=True)
            required_directories.append(directory.relative_to(mods).as_posix())
visual_fixes=apply_shelter_visual_fixes(mods) if PRESET["visual_fixes"] else None
for name in ("objects.lua","spawnpoints.lua","worldmap.xml"):
    sources[str(SOURCE/name)]={"size":(SOURCE/name).stat().st_size,"sha256":sha(SOURCE/name)}
manifest=file_manifest(mods)
portable=create_manifest(mods,OUT/"package-manifest.json",game_version="42.21",
    converter_version=args.converter_version,mod_ids=DEPENDENCIES+[MAP_ID],
    required_directories=required_directories)
verified=verify_manifest(mods,OUT/"package-manifest.json",expected_fingerprint=portable["fingerprint"])
if not verified.ready: raise SystemExit("Generated package failed its portable manifest verification")
receipt={"created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "game_jar_sha256":EXPECTED_JAR,"input_sources":sources,"package_file_sha256":manifest,
 "installed":False,"published":False,"shelter":args.shelter,"source_cell":list(CELL),
 "scope":("private Shelter 22 38 build with accepted v003 rendering metadata; multiplayer and biome limitations remain" if PRESET["visual_fixes"] else "private Shelter 22 28 conversion; visual, traversal and gameplay validation pending"),
 "visual_fixes":visual_fixes,
 "package_fingerprint":portable["fingerprint"],"package_manifest":"package-manifest.json",
 "required_map_discovery_directory":MAP_ID+"/common/media/maps",
 "build_configuration":{"runtime":str(RUNTIME),"workshop_root":str(W),"jdk_bin":str(JDK),"java_sources":list(java_sources),"converter_version":args.converter_version},
 "spawn":PRESET["spawn"],"map_order":[MAP_ID,"Muldraugh, KY"],
 "mods":["\\"+name for name in DEPENDENCIES+[MAP_ID]]}
(OUT/"build-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
if REFERENCE:
    comparison={"reference":str(REFERENCE),"build":str(OUT),
        "reference_file_count":len(expected_payload),"built_file_count":len(manifest),
        "changed":sorted(rel for rel in expected_payload.keys() & manifest.keys() if expected_payload[rel]!=manifest[rel]),
        "missing":sorted(expected_payload.keys()-manifest.keys()),"added":sorted(manifest.keys()-expected_payload.keys()),
        "reference_unchanged":file_manifest(REFERENCE/"mods")==expected_payload,
        "map_discovery_directory_exists":(mapmod/"common/media/maps").is_dir()}
    comparison["pass"]=not any(comparison[k] for k in ("changed","missing","added")) and comparison["reference_unchanged"] and comparison["map_discovery_directory_exists"]
    (OUT/"reference-comparison.json").write_text(json.dumps(comparison,indent=2)+"\n",encoding="utf-8")
    if not comparison["pass"]: raise SystemExit("Reference comparison failed; inspect reference-comparison.json")
    print("PASS exact reference payload:",len(manifest),"files",flush=True)
print("Private prototype:",OUT)
print("Package fingerprint:",portable["fingerprint"])

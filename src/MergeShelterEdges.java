package zombie.pot;
import java.nio.file.*;
import java.util.*;
import zombie.iso.BuildingDef;
import zombie.iso.RoomDef;
import zombie.iso.MetaObject;
import zombie.core.random.RandStandard;
import zombie.core.random.RandLua;

/** Private merge: converted tiles, original B41 metadata, vanilla outside the source footprint. */
public final class MergeShelterEdges {
    static int upper(POTLotPack p) { return p.lotHeader.maxLevel-(p.version==0?1:0); }

    /** POT's writer writes MetaObject.getX/Y directly, although its reader makes them room-relative.
     * Prepare a copy with cell-relative coordinates solely for that writer; never mutate source rooms.
     */
    static void addBuildingForStockWriter(POTLotHeader target, BuildingDef source) {
        target.addBuilding(source);
        BuildingDef copy=target.buildings.get(target.buildings.size()-1);
        for(int i=0;i<source.rooms.size();i++) {
            RoomDef original=source.rooms.get(i), room=copy.rooms.get(i);
            room.objects.clear();
            for(MetaObject object:original.objects) {
                room.objects.add(new MetaObject(object.getType(),
                  original.x+object.getX()-target.getMinSquareX(),
                  original.y+object.getY()-target.getMinSquareY(),room));
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ShelterCell cell=ShelterCell.fromArgs(args,5,"workspace original-b41 converted vanilla new-output");
        Path root=Path.of(args[0]).toRealPath(), originalDir=Path.of(args[1]).toRealPath();
        Path converted=Path.of(args[2]).toRealPath(), vanilla=Path.of(args[3]).toRealPath();
        Path output=Path.of(args[4]).toAbsolutePath().normalize();
        if(!originalDir.startsWith(root) || !converted.startsWith(root) || !output.startsWith(root) || output.equals(root))
            throw new IllegalArgumentException("Outside private workspace");
        Files.createDirectories(output);
        if(!output.toRealPath().startsWith(root)) throw new IllegalArgumentException("Output symlink escapes workspace");
        try(var ls=Files.list(output)) { if(ls.findAny().isPresent()) throw new IllegalArgumentException("Output must be empty"); }
        RandStandard.INSTANCE.init(); RandLua.INSTANCE.init();
        POTLotPack original=ValidateShelterMap.read(originalDir,cell.x,cell.y,false);
        POTChunkData originalBits=new POTChunkData(cell.x,cell.y,false);
        originalBits.load(originalDir.resolve("chunkdata_"+cell.name()+".bin").toFile());
        for(BuildingDef b:original.lotHeader.buildings)
            if(!cell.contained(b.x,b.y,b.x2,b.y2)) throw new IllegalStateException("Original building crosses source footprint");
        long checked=0,nonempty=0,bitsChecked=0;
        for(int cx=cell.firstX;cx<=cell.lastX;cx++) for(int cy=cell.firstY;cy<=cell.lastY;cy++) {
            POTLotPack shelter=ValidateShelterMap.read(converted,cx,cy,true);
            POTLotPack base=ValidateShelterMap.read(vanilla,cx,cy,true);
            POTLotHeader h=new POTLotHeader(cx,cy,true);
            POTLotPack merged=new POTLotPack(h);
            POTChunkData bc=new POTChunkData(cx,cy,true),mc=new POTChunkData(cx,cy,true);
            bc.load(vanilla.resolve("chunkdata_"+cx+"_"+cy+".bin").toFile());
            // Buildings are owned by the cell containing their top-left bound, matching POT.
            for(BuildingDef b:original.lotHeader.buildings)
                if(h.containsSquare(b.x,b.y)) addBuildingForStockWriter(h,b);
            for(BuildingDef b:base.lotHeader.buildings) {
                if(cell.overlaps(b.x,b.y,b.x2,b.y2)) {
                    if(!cell.contained(b.x,b.y,b.x2,b.y2)) throw new IllegalStateException("Vanilla building crosses footprint: "+b.x+","+b.y+".."+b.x2+","+b.y2);
                } else addBuildingForStockWriter(h,b);
            }
            for(int y=cy*256;y<(cy+1)*256;y++) for(int x=cx*256;x<(cx+1)*256;x++) {
                POTLotPack source=cell.inside(x,y)?shelter:base;
                for(int z=source.lotHeader.minLevel;z<=upper(source);z++) {
                    String[] tiles=ValidateShelterMap.square(source,x,y,z);
                    if(tiles!=null && tiles.length>0) { merged.setSquareData(x,y,z,tiles); nonempty++; }
                }
                mc.setSquareBits(x,y,(cell.inside(x,y)?originalBits:bc).getSquareBits(x,y));
            }
            // The stock converter indexes density from the old cell origin for each new cell.
            // Recompute at world coordinates directly, treating stored density bytes as unsigned.
            for(int chy=0;chy<32;chy++) for(int chx=0;chx<32;chx++) {
                int sum=0;
                for(int dy=0;dy<8;dy++) for(int dx=0;dx<8;dx++) {
                    int x=cx*256+chx*8+dx,y=cy*256+chy*8+dy;
                    sum+=(cell.inside(x,y)?original:base).lotHeader.getZombieDensityForSquare(x,y)&0xff;
                }
                h.zombieDensity[chx+chy*32]=(byte)(sum/64);
            }
            merged.save(output.resolve("world_"+cx+"_"+cy+".lotpack").toString());
            mc.save(output.resolve("chunkdata_"+cx+"_"+cy+".bin").toString());
            h.save(output.resolve(cx+"_"+cy+".lotheader").toString());
            POTLotPack reread=ValidateShelterMap.read(output,cx,cy,true);
            POTChunkData rc=new POTChunkData(cx,cy,true);
            rc.load(output.resolve("chunkdata_"+cx+"_"+cy+".bin").toFile());
            int zmin=Math.min(base.lotHeader.minLevel,original.lotHeader.minLevel);
            int zmax=Math.max(upper(base),upper(original));
            for(int y=cy*256;y<(cy+1)*256;y++) for(int x=cx*256;x<(cx+1)*256;x++) {
                POTLotPack expected=cell.inside(x,y)?original:base;
                for(int z=zmin;z<=zmax;z++) {
                    if(!Arrays.equals(ValidateShelterMap.square(expected,x,y,z),ValidateShelterMap.square(reread,x,y,z)))
                        throw new IllegalStateException("Tile mismatch "+x+","+y+","+z);
                    checked++;
                }
                if(rc.getSquareBits(x,y)!=(cell.inside(x,y)?originalBits:bc).getSquareBits(x,y))
                    throw new IllegalStateException("Ground bits mismatch "+x+","+y);
                bitsChecked++;
            }
            System.out.printf("Cell %d,%d merged and reread: z=%d..%d rooms=%d buildings=%d%n",
              cx,cy,reread.lotHeader.minLevel,reread.lotHeader.maxLevel,reread.lotHeader.roomList.size(),reread.lotHeader.buildings.size());
        }
        System.out.printf("PASS: %d direct-original/vanilla square-layer comparisons; %d ground-bit comparisons; %d populated squares.%n",checked,bitsChecked,nonempty);
        System.out.println("Run ValidateShelterMetadata.py independently for header geometry, metaobjects, density and header bounds.");
    }
}

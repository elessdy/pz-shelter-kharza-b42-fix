package zombie.pot;
import java.nio.file.*;
import java.util.*;
import zombie.core.random.RandStandard;
import zombie.core.random.RandLua;

public final class ValidateShelterMap {
    static POTLotPack read(Path dir, int x, int y, boolean modern) throws Exception {
        POTLotHeader h = new POTLotHeader(x, y, modern);
        h.load(dir.resolve(x+"_"+y+".lotheader").toFile());
        POTLotPack p = new POTLotPack(h);
        p.load(dir.resolve("world_"+x+"_"+y+".lotpack").toFile());
        return p;
    }
    static String[] square(POTLotPack p, int x, int y, int z) {
        int upper = p.lotHeader.maxLevel - (p.version == 0 ? 1 : 0);
        if (z < p.lotHeader.minLevel || z > upper) return null;
        return p.getSquareData(x,y,z);
    }
    public static void main(String[] args) throws Exception {
        ShelterCell cell=ShelterCell.fromArgs(args,2,"old-input converted-output");
        RandStandard.INSTANCE.init(); RandLua.INSTANCE.init();
        POTLotPack old=read(Path.of(args[0]),cell.x,cell.y,false);
        Map<String,POTLotPack> out=new HashMap<>();
        for(int x=cell.firstX;x<=cell.lastX;x++) for(int y=cell.firstY;y<=cell.lastY;y++) {
            POTLotPack p=read(Path.of(args[1]),x,y,true);
            out.put(x+"_"+y,p);
            System.out.printf("Cell %d,%d: format=%d, z=%d..%d, rooms=%d, buildings=%d, tileNames=%d%n",
                x,y,p.version,p.lotHeader.minLevel,p.lotHeader.maxLevel,
                p.lotHeader.roomList.size(),p.lotHeader.buildings.size(),p.lotHeader.tilesUsed.size());
        }
        long checked=0,nonempty=0,tiles=0,mismatches=0;
        int zmax=old.lotHeader.maxLevel-(old.version==0?1:0);
        for(int z=old.lotHeader.minLevel;z<=zmax;z++)
        for(int y=cell.minY;y<cell.maxY;y++) for(int x=cell.minX;x<cell.maxX;x++) {
            String[] a=square(old,x,y,z);
            String[] b=square(out.get((x/256)+"_"+(y/256)),x,y,z);
            checked++;
            if(a!=null) { nonempty++; tiles+=a.length; }
            if(!Arrays.equals(a,b)) {
                if(mismatches<5) System.out.println("DIFF "+x+","+y+","+z+" "+Arrays.toString(a)+" -> "+Arrays.toString(b));
                mismatches++;
            }
        }
        // Preserve the original diagnostic when using the established 22/38 default.
        // Other maps are checked over every source tile/layer by the same comparison above.
        if(cell.isShelter2238()) {
            POTLotPack spawn=out.get("26_45");
            System.out.println("Spawn z0: "+Arrays.toString(square(spawn,6687,11587,0)));
            System.out.println("Spawn z1: "+Arrays.toString(square(spawn,6687,11587,1)));
            System.out.println("Outside source footprint example: "+Arrays.toString(square(out.get("25_44"),6400,11264,0)));
        }
        System.out.printf("RESULT checked=%d nonempty=%d tileInstances=%d mismatches=%d%n",checked,nonempty,tiles,mismatches);
        if(mismatches!=0) throw new IllegalStateException("Tile content changed during conversion");
    }
}

import java.awt.geom.*;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.*;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.*;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.*;
import zombie.asset.AssetPath;
import zombie.pot.ShelterCell;
import zombie.worldMap.*;

/** Original local-only migration adapter; reads game/mod assets from separately obtained inputs. */
public final class ConvertShelterAncillary {
    static final int CELL=ShelterCell.MODERN_SIZE;
    static ShelterCell sourceCell;
    static Rectangle2D FOOTPRINT;
    record Feature(Area area, SortedMap<String,String> properties, String origin) {}
    record Ring(List<Point2D.Double> points, double signedArea, Area area) {}
    static final List<Feature> features=new ArrayList<>();
    static int sourceCount, vanillaCount, emittedCount, roundedVertices;
    static double maxVertexShift, sweptAreaBound;

    public static void main(String[] args) throws Exception {
        sourceCell=ShelterCell.fromArgs(args,4,"workspace original-map vanilla-map output required");
        FOOTPRINT=new Rectangle2D.Double(sourceCell.minX,sourceCell.minY,ShelterCell.LEGACY_SIZE,ShelterCell.LEGACY_SIZE);
        features.clear(); sourceCount=vanillaCount=emittedCount=roundedVertices=0; maxVertexShift=sweptAreaBound=0;
        Path workspace=Path.of(args[0]).toRealPath();
        Path original=Path.of(args[1]).toRealPath(), vanilla=Path.of(args[2]).toRealPath();
        Path output=Path.of(args[3]).toAbsolutePath().normalize();
        if(!output.startsWith(workspace.resolve("private"))) throw new IllegalArgumentException("Output must be private inside workspace");
        if(Files.exists(output)) {
            try(var entries=Files.list(output)) { if(entries.findAny().isPresent()) throw new IllegalArgumentException("Output must be empty"); }
        } else Files.createDirectories(output);
        if(!output.toRealPath().startsWith(workspace.resolve("private").toRealPath())) throw new IllegalArgumentException("Output resolves outside private");

        // Installed vanilla XML retains an obsolete 300-cell layout; its v2 binary is authoritative.
        loadBinary(vanilla.resolve("worldmap-forest.xml.bin"));
        loadBinary(vanilla.resolve("worldmap.xml.bin"));
        loadLegacyXml(original.resolve("worldmap.xml"));
        Document document=DocumentBuilderFactory.newInstance().newDocumentBuilder().newDocument();
        Element world=document.createElement("world"); world.setAttribute("version","1.0"); document.appendChild(world);
        for(int cx=sourceCell.firstX;cx<=sourceCell.lastX;cx++) for(int cy=sourceCell.firstY;cy<=sourceCell.lastY;cy++) {
            Element cell=document.createElement("cell"); cell.setAttribute("x",Integer.toString(cx)); cell.setAttribute("y",Integer.toString(cy)); world.appendChild(cell);
            Area cellArea=new Area(new Rectangle2D.Double(cx*CELL,cy*CELL,CELL,CELL));
            for(Feature feature:features) {
                Area clipped=new Area(feature.area); clipped.intersect(cellArea);
                if(!clipped.isEmpty()) emitFeature(document,cell,clipped,feature.properties,cx,cy);
            }
        }
        Path xml=output.resolve("worldmap.xml");
        Transformer transformer=TransformerFactory.newInstance().newTransformer();
        transformer.setOutputProperty(OutputKeys.INDENT,"yes"); transformer.setOutputProperty(OutputKeys.ENCODING,"UTF-8");
        transformer.transform(new DOMSource(document),new StreamResult(xml.toFile()));
        Path binary=output.resolve("worldmap.xml.bin");
        writeBinary(document,binary);
        WorldMapData parsed=data(binary);
        if(!new WorldMapBinary().read(binary.toString(),parsed)) throw new IllegalStateException("Game binary parser rejected output");
        int[] exactCounts=compareRoundedDocument(document,parsed);
        int parsedFeatures=parsed.cells.stream().mapToInt(c->c.features.size()).sum();
        if(parsed.cells.size()!=sourceCell.outputCount() || parsedFeatures!=emittedCount) throw new IllegalStateException("Game parser output count differs");
        Map<String,Area> expected=unionByProperties(features);
        List<Feature> roundtrip=new ArrayList<>();
        for(WorldMapCell c:parsed.cells) for(WorldMapFeature f:c.features) roundtrip.add(feature(f,c.x*CELL,c.y*CELL,"roundtrip"));
        Map<String,Area> actual=unionByProperties(roundtrip);
        if(!expected.keySet().equals(actual.keySet())) throw new IllegalStateException("Properties differ after roundtrip");
        double differenceArea=0;
        List<String> propertyDifferences=new ArrayList<>();
        for(String key:expected.keySet()) {
            Area diff=new Area(expected.get(key)); diff.exclusiveOr(actual.get(key));
            double amount=areaSize(diff); differenceArea+=amount;
            propertyDifferences.add(key+"="+amount);
        }
        // Integer-only world-map coordinates require rounding newly introduced clipping intersections.
        if(maxVertexShift>Math.sqrt(0.5)+1e-7) throw new IllegalStateException("Unexpected overlay rounding error");
        // Every edge moves through two triangles when its endpoints round. Their summed
        // areas conservatively bound the polygon change, including hole boundaries.
        if(differenceArea>sweptAreaBound+1e-5)
            throw new IllegalStateException("Overlay difference exceeds measured quantization bound: "+differenceArea+" > "+sweptAreaBound);
        // The source-specific cap supplements exact serialization and geometric checks.
        // 22/38 stays at 64; 22/28 has measured error83.33117 within swept bound83.45022.
        if(differenceArea>sourceCell.overlayAreaLimit()) throw new IllegalStateException("Overlay area mismatch exceeds "+sourceCell.overlayAreaLimit()+"-square-tile bound: "+differenceArea);

        String spawn=Files.readString(original.resolve("spawnpoints.lua"));
        Pattern legacy=Pattern.compile("worldX\\s*=\\s*(-?\\d+)\\s*,\\s*worldY\\s*=\\s*(-?\\d+)\\s*,\\s*posX\\s*=\\s*(-?\\d+)\\s*,\\s*posY\\s*=\\s*(-?\\d+)(?=\\s*,\\s*posZ\\s*=\\s*(-?\\d+))");
        Matcher matcher=legacy.matcher(spawn); StringBuilder migrated=new StringBuilder(); int spawnCount=0;
        Set<String> spawnTiles=new LinkedHashSet<>();
        while(matcher.find()) {
            int worldX=Integer.parseInt(matcher.group(1)),worldY=Integer.parseInt(matcher.group(2));
            int localX=Integer.parseInt(matcher.group(3)),localY=Integer.parseInt(matcher.group(4));
            int z=Integer.parseInt(matcher.group(5));
            if(worldX!=sourceCell.x || worldY!=sourceCell.y || localX<0 || localX>=ShelterCell.LEGACY_SIZE
                || localY<0 || localY>=ShelterCell.LEGACY_SIZE || z<0 || z>31)
                throw new IllegalStateException("Spawn entry outside source cell or supported level range");
            int x=Math.addExact(sourceCell.minX,localX),y=Math.addExact(sourceCell.minY,localY);
            if(!sourceCell.inside(x,y)) throw new IllegalStateException("Spawn outside source footprint");
            matcher.appendReplacement(migrated,"posX = "+x+", posY = "+y); spawnCount++;
            spawnTiles.add(x+","+y+","+z);
        }
        matcher.appendTail(migrated);
        if(spawnCount==0 || migrated.toString().contains("worldX") || migrated.toString().contains("worldY")) throw new IllegalStateException("Unexpected spawnpoint format");
        Files.writeString(output.resolve("spawnpoints.lua"),migrated,StandardCharsets.UTF_8);
        // Preserve as a non-loadable reference: B42 ignores its old biome types and an active
        // objects.lua triggers over-broad legacy300-cell zone clearing for this converted map.
        Files.copy(original.resolve("objects.lua"),output.resolve("objects.b41.lua.reference.txt"));
        if(Files.mismatch(original.resolve("objects.lua"),output.resolve("objects.b41.lua.reference.txt"))!=-1) throw new IllegalStateException("Zone reference copy differs");
        if(sourceCell.isShelter2238()) Files.copy(workspace.resolve("src/ShelterParking.lua"),output.resolve("ShelterParking.lua"));
        String report="Ancillary conversion, local private prototype only\n"
            +"Legacy shelter overlay features: "+sourceCount+"\n"
            +"Vanilla edge overlay features retained before cell splitting: "+vanillaCount+"\n"
            +"Output cells: "+sourceCell.outputNames()+"; parsed output features: "+parsedFeatures+"\n"
            +"Spawn entries migrated: "+spawnCount+"; absolute tile: "+String.join("; ",spawnTiles)+"\n"
            +"objects.b41.lua.reference.txt byte-identical; reference ONLY, do not rename to objects.lua\n"
            +"B42 skips legacy Nav/Forest/DeepForest/FarmLand zones; biome migration is outstanding.\n"
            +(sourceCell.isShelter2238()?"Active map objects.lua would clear zones in old300 cells22_38,23_38,22_39,23_39 (600x600), exceeding shelter footprint.\n":"Active map objects.lua uses legacy300-cell clearing that may exceed the selected source footprint.\n")
            +"No active objects.lua emitted: retain vanilla zones as explicit prototype default.\n"
            +(sourceCell.isShelter2238()?"Original ShelterParking.lua registers only the one custom parking rectangle after normal map zones; runtime validation required.\n":"No parking hook emitted; retain vanilla zones for this source cell.\n")
            +"New clipping vertices rounded to integer XML: "+roundedVertices+"; maximum Euclidean shift: "+maxVertexShift+" tiles\n"
            +"Symmetric difference of property-grouped output vs pre-rounding polygons: "+differenceArea+" square tiles\n"
            +"Geometry acceptance bound: at most "+sourceCell.overlayAreaLimit()+" square tiles across "+(sourceCell.outputCount()*CELL*CELL)+" square tiles; PASS\n"
            +"Conservative swept-edge quantization bound: "+sweptAreaBound+" square tiles; PASS\n"
            +"Property-grouped symmetric differences: "+String.join("; ",propertyDifferences)+"\n"
            +"Exact rounded XML vs decoded binary: "+exactCounts[0]+" features, "+exactCounts[1]+" rings, "+(exactCounts[1]-exactCounts[0])+" holes, "+exactCounts[2]+" vertices; properties and coordinates identical; PASS\n"
            +"Generated v2/256-cell binary re-read by installed game's WorldMapBinary parser. No old worldmap.xml.bin copied.\n"
            +"XML companion retained for review; current installed XML reader counts coordinate shorts as points, so binary is required.\n"
            +"Foraging/biome behavior, render appearance, traversal and multiplayer remain untested in-game.\n";
        Files.writeString(output.resolve("validation.txt"),report); System.out.print(report);
    }

    static WorldMapData data(Path p) { return new WorldMapData(new AssetPath(p.toString()),WorldMapDataAssetManager.instance); }
    static void loadBinary(Path p) throws Exception {
        WorldMapData d=data(p); if(!new WorldMapBinary().read(p.toString(),d)) throw new IllegalStateException("Binary rejected: "+p);
        for(WorldMapCell c:d.cells) if(sourceCell.containsOutputCell(c.x,c.y)) for(WorldMapFeature f:c.features) {
            Feature feature=feature(f,c.x*CELL,c.y*CELL,p.getFileName().toString());
            // Binary features can extend beyond their owning cell; preserve only this cell's visible region.
            feature.area.intersect(new Area(new Rectangle2D.Double(c.x*CELL,c.y*CELL,CELL,CELL)));
            feature.area.subtract(new Area(FOOTPRINT));
            if(!feature.area.isEmpty()) { features.add(feature); vanillaCount++; }
        }
    }
    static void loadLegacyXml(Path p) throws Exception {
        DocumentBuilderFactory factory=DocumentBuilderFactory.newInstance();
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl",true);
        Document d=factory.newDocumentBuilder().parse(p.toFile());
        List<Element> cells=children(d.getDocumentElement(),"cell");
        if(cells.size()!=1 || !cells.getFirst().getAttribute("x").equals(Integer.toString(sourceCell.x)) || !cells.getFirst().getAttribute("y").equals(Integer.toString(sourceCell.y))) throw new IllegalStateException("Unexpected source map");
        for(Element cell:cells) for(Element f:children(cell,"feature")) {
            Element geometry=children(f,"geometry").getFirst();
            if(!geometry.getAttribute("type").equals("Polygon")) throw new IllegalStateException("Unsupported source geometry");
            Path2D.Double path=new Path2D.Double(Path2D.WIND_EVEN_ODD);
            for(Element ring:children(geometry,"coordinates")) {
                List<Element> points=children(ring,"point");
                if(points.size()<3) throw new IllegalStateException("Invalid source ring");
                for(int i=0;i<points.size();i++) {
                    Element point=points.get(i); int x=Math.addExact(sourceCell.minX,Integer.parseInt(point.getAttribute("x"))),y=Math.addExact(sourceCell.minY,Integer.parseInt(point.getAttribute("y")));
                    if(i==0) path.moveTo(x,y); else path.lineTo(x,y);
                }
                path.closePath();
            }
            SortedMap<String,String> properties=new TreeMap<>();
            for(Element props:children(f,"properties")) for(Element prop:children(props,"property")) properties.put(prop.getAttribute("name"),prop.getAttribute("value"));
            Feature feature=new Feature(new Area(path),properties,"shelter");
            Area outside=new Area(feature.area); outside.subtract(new Area(FOOTPRINT));
            if(!outside.isEmpty()) throw new IllegalStateException("Source polygon exceeds footprint");
            features.add(feature); sourceCount++;
        }
    }
    static Feature feature(WorldMapFeature f,int ox,int oy,String origin) {
        if(f.geometry.type!=WorldMapGeometry.Type.Polygon) throw new IllegalArgumentException("Only polygon overlay migration supported: "+f.geometry.type);
        Path2D.Double path=new Path2D.Double(Path2D.WIND_EVEN_ODD);
        for(WorldMapPoints ring:f.geometry.points) {
            if(ring.numPoints()<3) throw new IllegalStateException("Degenerate source polygon");
            path.moveTo(ox+ring.getX(0),oy+ring.getY(0));
            for(int i=1;i<ring.numPoints();i++) path.lineTo(ox+ring.getX(i),oy+ring.getY(i));
            path.closePath();
        }
        return new Feature(new Area(path),new TreeMap<>(f.properties),origin);
    }
    static List<Ring> rings(Area area,boolean round) {
        List<Ring> rings=new ArrayList<>(); List<Point2D.Double> points=null; double[] coords=new double[6];
        for(PathIterator iterator=area.getPathIterator(null);!iterator.isDone();iterator.next()) {
            int kind=iterator.currentSegment(coords);
            if(kind==PathIterator.SEG_MOVETO) points=new ArrayList<>();
            if(kind==PathIterator.SEG_MOVETO || kind==PathIterator.SEG_LINETO) {
                double x=coords[0],y=coords[1];
                if(round) { double shift=Point2D.distance(x,y,Math.rint(x),Math.rint(y)); if(shift>1e-7) roundedVertices++; maxVertexShift=Math.max(maxVertexShift,shift); x=Math.rint(x); y=Math.rint(y); }
                Point2D.Double point=new Point2D.Double(x,y);
                if(points.isEmpty() || !points.getLast().equals(point)) points.add(point);
            } else if(kind==PathIterator.SEG_CLOSE) {
                if(points.size()>1 && points.getFirst().equals(points.getLast())) points.removeLast();
                double signed=0; Path2D.Double path=new Path2D.Double();
                for(int i=0;i<points.size();i++) { Point2D.Double a=points.get(i),b=points.get((i+1)%points.size()); signed+=a.x*b.y-b.x*a.y; if(i==0) path.moveTo(a.x,a.y); else path.lineTo(a.x,a.y); }
                path.closePath(); if(points.size()>=3 && Math.abs(signed)>1e-8) rings.add(new Ring(points,signed/2,new Area(path)));
            } else if(kind!=PathIterator.SEG_MOVETO && kind!=PathIterator.SEG_LINETO) throw new IllegalStateException("Nonlinear polygon");
        }
        return rings;
    }
    static void emitFeature(Document d,Element cell,Area area,Map<String,String> props,int cx,int cy) {
        sweptAreaBound+=quantizationBound(area);
        List<Ring> rings=rings(area,true), outers=rings.stream().filter(r->r.signedArea<0).toList(), holes=rings.stream().filter(r->r.signedArea>0).toList();
        if(outers.isEmpty() && !rings.isEmpty()) throw new IllegalStateException("Unexpected Area contour winding");
        Map<Ring,Ring> parents=new HashMap<>();
        for(Ring hole:holes) {
            // Area.contains(point) excludes boundary points. A valid hole may touch its
            // outer ring at the first vertex, so classify the entire area instead.
            Ring owner=outers.stream().filter(o->{
                Area remainder=new Area(hole.area); remainder.subtract(o.area);
                return remainder.isEmpty();
            }).min(Comparator.comparingDouble(o->Math.abs(o.signedArea))).orElseThrow(()->new IllegalStateException("Unattached polygon hole"));
            parents.put(hole,owner);
        }
        for(Ring outer:outers) {
            Element feature=d.createElement("feature"), geometry=d.createElement("geometry"); geometry.setAttribute("type","Polygon"); feature.appendChild(geometry); cell.appendChild(feature);
            emitRing(d,geometry,outer,cx,cy);
            for(Ring hole:holes) if(parents.get(hole)==outer) emitRing(d,geometry,hole,cx,cy);
            Element properties=d.createElement("properties"); feature.appendChild(properties);
            for(var entry:props.entrySet()) { Element property=d.createElement("property"); property.setAttribute("name",entry.getKey()); property.setAttribute("value",entry.getValue()); properties.appendChild(property); }
            emittedCount++;
        }
    }
    static void emitRing(Document d,Element geometry,Ring ring,int cx,int cy) {
        Element coordinates=d.createElement("coordinates"); geometry.appendChild(coordinates);
        for(Point2D.Double point:ring.points) {
            int x=(int)point.x-cx*CELL,y=(int)point.y-cy*CELL;
            if(x<0 || x>CELL || y<0 || y>CELL) throw new IllegalStateException("Point outside output cell");
            Element p=d.createElement("point"); p.setAttribute("x",Integer.toString(x)); p.setAttribute("y",Integer.toString(y)); coordinates.appendChild(p);
        }
    }
    static double triangleArea(Point2D.Double a,Point2D.Double b,Point2D.Double c) {
        return Math.abs((b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x))/2;
    }
    static double quantizationBound(Area area) {
        double sum=0;
        for(Ring ring:rings(area,false)) {
            List<Point2D.Double> points=ring.points;
            for(int i=0;i<points.size();i++) {
                Point2D.Double a=points.get(i),b=points.get((i+1)%points.size());
                Point2D.Double qa=new Point2D.Double(Math.rint(a.x),Math.rint(a.y));
                Point2D.Double qb=new Point2D.Double(Math.rint(b.x),Math.rint(b.y));
                sum+=triangleArea(a,b,qb)+triangleArea(a,qb,qa);
            }
        }
        return sum;
    }
    /** Check the serialized geometry exactly, independently of the permitted integer rounding. */
    static int[] compareRoundedDocument(Document document,WorldMapData parsed) {
        int features=0,rings=0,points=0;
        List<Element> cells=children(document.getDocumentElement(),"cell");
        if(cells.size()!=parsed.cells.size()) throw new IllegalStateException("Cell count changed in binary");
        for(int ci=0;ci<cells.size();ci++) {
            Element cell=cells.get(ci); WorldMapCell binaryCell=parsed.cells.get(ci);
            if(binaryCell.x!=Integer.parseInt(cell.getAttribute("x")) || binaryCell.y!=Integer.parseInt(cell.getAttribute("y")))
                throw new IllegalStateException("Cell coordinates changed in binary");
            List<Element> cellFeatures=children(cell,"feature");
            if(cellFeatures.size()!=binaryCell.features.size()) throw new IllegalStateException("Feature count changed in binary");
            for(int fi=0;fi<cellFeatures.size();fi++) {
                Element feature=cellFeatures.get(fi); WorldMapFeature binaryFeature=binaryCell.features.get(fi);
                Element geometry=children(feature,"geometry").getFirst();
                if(!geometry.getAttribute("type").equals(binaryFeature.geometry.type.toString())) throw new IllegalStateException("Geometry type changed in binary");
                List<Element> ringList=children(geometry,"coordinates");
                if(ringList.size()!=binaryFeature.geometry.points.size()) throw new IllegalStateException("Ring/hole count changed in binary");
                for(int ri=0;ri<ringList.size();ri++) {
                    List<Element> pointList=children(ringList.get(ri),"point"); WorldMapPoints binaryPoints=binaryFeature.geometry.points.get(ri);
                    if(pointList.size()!=binaryPoints.numPoints()) throw new IllegalStateException("Vertex count changed in binary");
                    for(int pi=0;pi<pointList.size();pi++) {
                        Element point=pointList.get(pi);
                        if(Integer.parseInt(point.getAttribute("x"))!=binaryPoints.getX(pi) || Integer.parseInt(point.getAttribute("y"))!=binaryPoints.getY(pi))
                            throw new IllegalStateException("Vertex coordinates changed in binary");
                    }
                    points+=pointList.size(); rings++;
                }
                Map<String,String> properties=new TreeMap<>();
                for(Element p:children(children(feature,"properties").getFirst(),"property")) properties.put(p.getAttribute("name"),p.getAttribute("value"));
                if(!properties.equals(binaryFeature.properties)) throw new IllegalStateException("Properties changed in binary");
                features++;
            }
        }
        return new int[]{features,rings,points};
    }
    static Map<String,Area> unionByProperties(List<Feature> input) {
        Map<String,Area> result=new TreeMap<>();
        for(Feature f:input) result.computeIfAbsent(f.properties.toString(),key->new Area()).add(new Area(f.area));
        return result;
    }
    static double areaSize(Area area) { double signed=0; for(Ring ring:rings(area,false)) signed+=ring.signedArea; return Math.abs(signed); }
    static List<Element> children(Element parent,String name) {
        List<Element> result=new ArrayList<>();
        for(Node node=parent.getFirstChild();node!=null;node=node.getNextSibling()) if(node instanceof Element e && e.getTagName().equals(name)) result.add(e);
        return result;
    }
    static void intLE(OutputStream out,int value) throws IOException { for(int shift=0;shift<32;shift+=8) out.write(value>>>shift & 255); }
    static void shortLE(OutputStream out,int value) throws IOException { out.write(value & 255); out.write(value>>>8 & 255); }
    static void writeBinary(Document document,Path path) throws IOException {
        Map<String,Integer> strings=new LinkedHashMap<>(); strings.put("Polygon",0);
        List<Element> cells=children(document.getDocumentElement(),"cell");
        for(Element cell:cells) for(Element feature:children(cell,"feature")) for(Element props:children(feature,"properties")) for(Element p:children(props,"property")) {
            for(String value:List.of(p.getAttribute("name"),p.getAttribute("value"))) strings.computeIfAbsent(value,key->strings.size());
        }
        try(OutputStream out=new BufferedOutputStream(Files.newOutputStream(path))) {
            out.write("IGMB".getBytes(StandardCharsets.US_ASCII)); intLE(out,2); intLE(out,CELL); intLE(out,sourceCell.outputWidth()); intLE(out,sourceCell.outputHeight()); intLE(out,strings.size());
            for(String s:strings.keySet()) { byte[] bytes=s.getBytes(StandardCharsets.UTF_8); if(bytes.length>1022) throw new IllegalStateException("Oversize string"); shortLE(out,bytes.length); out.write(bytes); }
            for(Element cell:cells) {
                intLE(out,Integer.parseInt(cell.getAttribute("x"))); intLE(out,Integer.parseInt(cell.getAttribute("y")));
                List<Element> cellFeatures=children(cell,"feature"); intLE(out,cellFeatures.size());
                int totalPointShorts=0;
                for(Element feature:cellFeatures) {
                    Element geometry=children(feature,"geometry").getFirst(); shortLE(out,strings.get("Polygon"));
                    List<Element> rings=children(geometry,"coordinates"); if(rings.size()>255) throw new IllegalStateException("Too many rings"); out.write(rings.size());
                    for(Element ring:rings) {
                        List<Element> points=children(ring,"point"); totalPointShorts+=points.size()*2;
                        if(points.size()>32767 || totalPointShorts>32767) throw new IllegalStateException("Game short-buffer indexing limit exceeded");
                        shortLE(out,points.size());
                        for(Element p:points) { shortLE(out,Integer.parseInt(p.getAttribute("x"))); shortLE(out,Integer.parseInt(p.getAttribute("y"))); }
                    }
                    List<Element> props=children(children(feature,"properties").getFirst(),"property"); if(props.size()>255) throw new IllegalStateException("Too many properties"); out.write(props.size());
                    for(Element p:props) { shortLE(out,strings.get(p.getAttribute("name"))); shortLE(out,strings.get(p.getAttribute("value"))); }
                }
            }
        }
    }
}

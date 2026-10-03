package zombie.pot;

import java.util.StringJoiner;

/** One legacy 300-tile source cell and the B42 cells intersecting its footprint. */
public final class ShelterCell {
    public static final int LEGACY_SIZE = 300, MODERN_SIZE = 256;
    public final int x, y, minX, minY, maxX, maxY;
    public final int firstX, firstY, lastX, lastY;

    public ShelterCell(int x, int y) {
        if (x < 0 || y < 0) throw new IllegalArgumentException("Negative source cells are not supported");
        this.x = x;
        this.y = y;
        minX = Math.multiplyExact(x, LEGACY_SIZE);
        minY = Math.multiplyExact(y, LEGACY_SIZE);
        maxX = Math.addExact(minX, LEGACY_SIZE);
        maxY = Math.addExact(minY, LEGACY_SIZE);
        firstX = Math.floorDiv(minX, MODERN_SIZE);
        firstY = Math.floorDiv(minY, MODERN_SIZE);
        lastX = Math.floorDiv(maxX - 1, MODERN_SIZE);
        lastY = Math.floorDiv(maxY - 1, MODERN_SIZE);
    }

    public static ShelterCell fromArgs(String[] args, int required, String usage) {
        if (args.length != required && args.length != required + 2)
            throw new IllegalArgumentException(usage + " [source-cell-x source-cell-y]");
        return args.length == required ? new ShelterCell(22, 38)
            : new ShelterCell(Integer.parseInt(args[required]), Integer.parseInt(args[required + 1]));
    }

    public boolean inside(int wx, int wy) {
        return wx >= minX && wx < maxX && wy >= minY && wy < maxY;
    }
    public boolean overlaps(int x1, int y1, int x2, int y2) {
        return x1 < maxX && x2 > minX && y1 < maxY && y2 > minY;
    }
    public boolean contained(int x1, int y1, int x2, int y2) {
        return x1 >= minX && x2 <= maxX && y1 >= minY && y2 <= maxY;
    }
    public boolean containsOutputCell(int cx, int cy) {
        return cx >= firstX && cx <= lastX && cy >= firstY && cy <= lastY;
    }
    public int outputWidth() { return lastX - firstX + 1; }
    public int outputHeight() { return lastY - firstY + 1; }
    public int outputCount() { return outputWidth() * outputHeight(); }
    public boolean isShelter2238() { return x == 22 && y == 38; }
    // Measured nearest-integer clipping: 22/28 is bounded by 83.45022 swept tile area.
    // Keep the established 22/38 limit unchanged; other cells retain the conservative default.
    public int overlayAreaLimit() { return x == 22 && y == 28 ? 84 : 64; }
    public String name() { return x + "_" + y; }
    public String outputNames() {
        StringJoiner names = new StringJoiner(",");
        for (int cx = firstX; cx <= lastX; cx++)
            for (int cy = firstY; cy <= lastY; cy++) names.add(cx + "_" + cy);
        return names.toString();
    }
}

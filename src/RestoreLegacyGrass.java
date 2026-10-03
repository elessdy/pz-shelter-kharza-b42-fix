import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;
import javax.imageio.ImageIO;

/** Original local format adapter. No game artwork is embedded in this source.
 * Run from the repository root: RestoreLegacyGrass input.pack output.pack report.json
 * The two new outputs must remain inside that root's private directory.
 */
public final class RestoreLegacyGrass {
    static final String SPRITE = "e_newgrass_1_87";
    static final String SOURCE_PAGE = "Tiles1x5";
    static final String OUTPUT_PAGE = "shelter2228_legacy_grass_2x_page0";
    static final int[] SOURCE_RECT = {384, 538, 58, 26, 3, 96, 64, 128};
    static final int[] OUTPUT_RECT = {0, 0, 116, 52, 6, 192, 128, 256};
    static final String SOURCE_PNG_SHA = "353c92373bc19b66267db0e4c924881b48a37b5f596a5cc84a6cc139c2646123";
    static final String SOURCE_RGBA_SHA = "bc933061a591cb6fa96ea97660b739e4c31fb6d7dbf2dde0904f4a7a38730da8";
    record Entry(String page, int alpha, int[] rect, byte[] png, int pageCount, long entryCount) {}

    public static void main(String[] args) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException("input.pack output.pack report.json; run from repository root");
        Path workspace = Path.of("").toRealPath();
        Path privateRoot = workspace.resolve("private").toRealPath();
        require(privateRoot.startsWith(workspace), "Private directory resolves outside workspace");
        Path input = Path.of(args[0]).toRealPath();
        Path output = privateOutput(args[1], privateRoot);
        Path report = privateOutput(args[2], privateRoot);
        require(!output.equals(report) && !output.equals(input) && !report.equals(input), "Input/output paths must differ");
        require(Files.isRegularFile(input), "Input must be an existing local pack file");
        String sourcePackSha = sha(input);
        Entry original = findSprite(input);
        require(original.page.equals(SOURCE_PAGE), "Unexpected source page");
        require(original.alpha == 1 && Arrays.equals(original.rect, SOURCE_RECT), "Unexpected source sprite rectangle/alpha flag");
        require(sha(original.png).equals(SOURCE_PNG_SHA), "Source PNG changed; inspect before updating the pin");
        ImageIO.setUseCache(false);
        BufferedImage source = decode(original.png);
        require(source.getWidth() == 1024 && source.getHeight() == 1022, "Unexpected source atlas dimensions");
        byte[] sourceRgba = rgba(source, SOURCE_RECT[0], SOURCE_RECT[1], 58, 26);
        require(sha(sourceRgba).equals(SOURCE_RGBA_SHA), "Decoded source crop differs from inspected RGBA pixels");

        // Copy packed ARGB integers, including transparent RGB and every alpha bit.
        // This is exact nearest-neighbor replication; no filtering or color drawing.
        BufferedImage atlas = new BufferedImage(128, 64, BufferedImage.TYPE_INT_ARGB);
        for (int y = 0; y < 52; y++) for (int x = 0; x < 116; x++)
            atlas.setRGB(x, y, source.getRGB(384 + x / 2, 538 + y / 2));
        ByteArrayOutputStream pngBuffer = new ByteArrayOutputStream();
        require(ImageIO.write(atlas, "png", pngBuffer), "No PNG encoder available");
        byte[] png = pngBuffer.toByteArray();
        BufferedImage decodedPng = decode(png);
        verifyPixels(source, decodedPng);
        byte[] pack = writePack(png);

        // All input/pixel checks precede creation. Existing outputs are never replaced.
        Files.createDirectories(output.getParent());
        Files.createDirectories(report.getParent());
        require(output.getParent().toRealPath().startsWith(privateRoot), "Output parent escaped private directory");
        require(report.getParent().toRealPath().startsWith(privateRoot), "Report parent escaped private directory");
        Files.write(output, pack, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        Entry reread = findSprite(output);
        require(reread.pageCount == 1 && reread.entryCount == 1, "Generated pack contains unexpected entries");
        require(reread.page.equals(OUTPUT_PAGE) && reread.alpha == 1, "Generated page metadata differs");
        require(Arrays.equals(reread.rect, OUTPUT_RECT), "Generated sprite rectangle differs");
        require(Arrays.equals(reread.png, png), "Generated PNG payload differs");
        BufferedImage rereadImage = decode(reread.png);
        verifyPixels(source, rereadImage);
        require(sha(input).equals(sourcePackSha), "Input pack changed during conversion");
        int transparent = 0, opaque = 0;
        for (int i = 3; i < sourceRgba.length; i += 4) {
            int alpha = sourceRgba[i] & 255;
            if (alpha == 0) transparent++;
            if (alpha == 255) opaque++;
        }
        String outputHash = sha(output);
        String json = """
            {
              "status": "pass",
              "scope": "Private texture restoration candidate; not visually validated",
              "sprite": %s,
              "source_pack": %s,
              "source_pack_sha256": %s,
              "source_page": %s,
              "source_png_sha256": %s,
              "source_crop_rgba_sha256": %s,
              "source_rect_xywh_offsets_canvas": [384,538,58,26,3,96,64,128],
              "source_alpha_counts": {"zero": %d, "opaque": %d, "intermediate": %d},
              "output_pack": %s,
              "output_pack_sha256": %s,
              "output_page": %s,
              "output_png_sha256": %s,
              "output_atlas_rgba_sha256": %s,
              "output_sprite_rgba_sha256": %s,
              "output_rect_xywh_offsets_canvas": [0,0,116,52,6,192,128,256],
              "output_atlas_dimensions": [128,64],
              "pack_version": 1,
              "page_count": 1,
              "sprite_count": 1,
              "source_pixels": 1508,
              "replicated_pixels_checked": 6032,
              "transparent_padding_pixels_checked": 2160,
              "pack_metadata_roundtrip_exact": true,
              "rgba_pixel_roundtrip_exact": true,
              "input_unchanged": true,
              "java_runtime_version": %s,
              "java_vendor": %s,
              "rendering_test_performed": false
            }
            """.formatted(quote(SPRITE), quote(input.toString()), quote(sourcePackSha), quote(SOURCE_PAGE),
                quote(SOURCE_PNG_SHA), quote(SOURCE_RGBA_SHA), transparent, opaque, 1508-transparent-opaque,
                quote(output.toString()), quote(outputHash), quote(OUTPUT_PAGE), quote(sha(png)),
                quote(sha(rgba(rereadImage, 0, 0, 128, 64))), quote(sha(rgba(rereadImage, 0, 0, 116, 52))),
                quote(System.getProperty("java.runtime.version")), quote(System.getProperty("java.vendor")));
        Files.writeString(report, json, StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        System.out.println("PASS RestoreLegacyGrass: one legacy sprite, 6032 exact replicated RGBA pixels, 2160 transparent padding pixels");
        System.out.println("Output pack SHA256 " + outputHash);
    }

    static Path privateOutput(String value, Path privateRoot) throws IOException {
        Path path = Path.of(value).toAbsolutePath().normalize();
        require(path.startsWith(privateRoot) && !path.equals(privateRoot), "Output must be inside workspace/private");
        require(!Files.exists(path, LinkOption.NOFOLLOW_LINKS), "Output already exists: " + path);
        Path ancestor = path.getParent();
        while (!Files.exists(ancestor)) ancestor = ancestor.getParent();
        require(ancestor.toRealPath().startsWith(privateRoot), "Output ancestor resolves outside private");
        return path;
    }

    static Entry findSprite(Path file) throws IOException {
        Entry selected = null;
        long totalEntries = 0;
        try (DataInputStream in = new DataInputStream(new BufferedInputStream(Files.newInputStream(file)))) {
            require(Arrays.equals(in.readNBytes(4), new byte[]{'P','Z','P','K'}), "Expected PZPK header");
            require(readInt(in) == 1, "Only PZPK version 1 is supported");
            int pages = bounded(readInt(in), 1, 4096, "page count");
            for (int pageIndex = 0; pageIndex < pages; pageIndex++) {
                String page = readString(in);
                int count = bounded(readInt(in), 0, 100000, "sprite count");
                int alpha = bounded(readInt(in), 0, 1, "alpha flag");
                totalEntries += count;
                int[] found = null;
                for (int i = 0; i < count; i++) {
                    String name = readString(in);
                    int[] rect = new int[8];
                    for (int n = 0; n < rect.length; n++) rect[n] = readInt(in);
                    if (name.equals(SPRITE)) {
                        require(found == null && selected == null, "Duplicate legacy sprite entries");
                        found = rect;
                    }
                }
                int length = bounded(readInt(in), 1, 64*1024*1024, "PNG byte length");
                if (found == null) in.skipNBytes(length);
                else {
                    byte[] png = in.readNBytes(length);
                    require(png.length == length, "Truncated PNG payload");
                    selected = new Entry(page, alpha, found, png, pages, 0);
                }
            }
            require(in.read() == -1, "Unexpected trailing pack bytes");
        }
        require(selected != null, "Legacy grass sprite not found");
        return new Entry(selected.page, selected.alpha, selected.rect, selected.png, selected.pageCount, totalEntries);
    }

    static byte[] writePack(byte[] png) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(new byte[]{'P','Z','P','K'});
        writeInt(out, 1); writeInt(out, 1);
        writeString(out, OUTPUT_PAGE); writeInt(out, 1); writeInt(out, 1);
        writeString(out, SPRITE);
        for (int value : OUTPUT_RECT) writeInt(out, value);
        writeInt(out, png.length); out.write(png);
        return out.toByteArray();
    }

    static BufferedImage decode(byte[] png) throws IOException {
        BufferedImage image = ImageIO.read(new ByteArrayInputStream(png));
        require(image != null, "PNG decoder rejected image");
        return image;
    }

    static void verifyPixels(BufferedImage source, BufferedImage output) {
        require(output.getWidth() == 128 && output.getHeight() == 64, "Generated atlas dimensions differ");
        for (int y = 0; y < 64; y++) for (int x = 0; x < 128; x++) {
            int expected = x < 116 && y < 52 ? source.getRGB(384 + x/2, 538 + y/2) : 0;
            require(output.getRGB(x,y) == expected, "RGBA pixel changed at " + x + "," + y);
        }
    }

    static byte[] rgba(BufferedImage image, int x, int y, int width, int height) {
        byte[] bytes = new byte[width*height*4];
        int index = 0;
        for (int cy = y; cy < y+height; cy++) for (int cx = x; cx < x+width; cx++) {
            int pixel = image.getRGB(cx,cy);
            bytes[index++] = (byte)(pixel >>> 16); bytes[index++] = (byte)(pixel >>> 8);
            bytes[index++] = (byte)pixel; bytes[index++] = (byte)(pixel >>> 24);
        }
        return bytes;
    }

    static int readInt(DataInputStream in) throws IOException { return Integer.reverseBytes(in.readInt()); }
    static void writeInt(OutputStream out, int value) throws IOException {
        for (int shift = 0; shift < 32; shift += 8) out.write(value >>> shift & 255);
    }
    static String readString(DataInputStream in) throws IOException {
        int length = bounded(readInt(in), 1, 4096, "string length");
        byte[] bytes = in.readNBytes(length);
        require(bytes.length == length, "Truncated string");
        return new String(bytes, StandardCharsets.UTF_8);
    }
    static void writeString(OutputStream out, String value) throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        writeInt(out, bytes.length); out.write(bytes);
    }
    static int bounded(int value, int min, int max, String label) {
        require(value >= min && value <= max, "Invalid " + label + ": " + value);
        return value;
    }
    static String sha(Path path) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = Files.newInputStream(path)) {
            byte[] block = new byte[1024*1024];
            for (int size; (size = in.read(block)) >= 0;) digest.update(block, 0, size);
        }
        return HexFormat.of().formatHex(digest.digest());
    }
    static String sha(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }
    static String quote(String text) {
        StringBuilder result = new StringBuilder("\"");
        for (char c : text.toCharArray()) {
            if (c == '\\' || c == '"') result.append('\\').append(c);
            else if (c < 32) result.append(String.format("\\u%04x", (int)c));
            else result.append(c);
        }
        return result.append('"').toString();
    }
    static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }
}

import java.nio.file.*;
import java.util.*;
import zombie.core.random.RandStandard;
import zombie.core.random.RandLua;
import zombie.pot.POT;

/** Local-only adapter to the user's installed game's map converter. No game/map assets included. */
public final class ConvertShelterMap {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException("workspace input output required");
        Path workspace = Path.of(args[0]).toRealPath();
        Path input = Path.of(args[1]).toRealPath();
        Path output = Path.of(args[2]).toAbsolutePath().normalize();
        if (!input.startsWith(workspace) || !output.startsWith(workspace) || input.equals(output))
            throw new IllegalArgumentException("Input and output must be different paths inside prototype workspace");
        if (Files.exists(output)) {
            try (var entries = Files.list(output)) {
                if (entries.findAny().isPresent()) throw new IllegalArgumentException("Output must be empty");
            }
        } else Files.createDirectories(output);
        if (!output.toRealPath().startsWith(workspace)) throw new IllegalArgumentException("Output resolves outside workspace");
        try (var entries = Files.list(input)) {
            if (entries.noneMatch(p -> p.getFileName().toString().endsWith(".lotheader")))
                throw new IllegalArgumentException("No source lot headers");
        }
        RandStandard.INSTANCE.init();
        RandLua.INSTANCE.init();
        long start = System.nanoTime();
        new POT().convertMapDirectory(input.toString(), output.toString());
        try (var entries = Files.list(output)) {
            long headers = entries.filter(p -> p.getFileName().toString().endsWith(".lotheader")).count();
            if (headers == 0) throw new IllegalStateException("Converter produced no lot headers");
            System.out.println("Converted map: " + headers + " output headers in " +
                ((System.nanoTime()-start)/1_000_000) + " ms");
        }
    }
}

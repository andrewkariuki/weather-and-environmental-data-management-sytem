
package jkuat.weather.utils;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

/**
 * WeatherLogger — thread-safe, file-backed logger.
 *
 * Keeps the last 500 entries in memory for the System Log panel,
 * and appends every entry to LOG_FILE on disk.
 *
 * Log levels: INFO | WARNING | ERROR | EVENT
 *
 * Why a dedicated class?
 *   Every service (dataset, sensor feed, file handler, API) needs logging.
 *   A single shared instance is injected via constructor — no statics,
 *   easy to test, easy to swap.
 */
public class WeatherLogger {

    private static final DateTimeFormatter FMT =
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final String       path;
    private final List<String> mem = new ArrayList<>();

    public WeatherLogger() {
        this.path = Cfg.LOG_FILE;
        new File(Cfg.DATA_DIR).mkdirs();
    }

    // ── Core write (synchronized — safe to call from any thread) ────────────
    private synchronized void write(String level, String msg) {
        String entry = "[" + LocalDateTime.now().format(FMT) + "] "
                     + "[" + String.format("%-7s", level) + "] " + msg;
        mem.add(entry);
        if (mem.size() > 500) mem.remove(0);

        try (var w = new FileWriter(path, true)) {
            w.write(entry + "\n");
        } catch (IOException ignored) { /* log failure should never crash app */ }
    }

    // ── Public API ───────────────────────────────────────────────────────────
    public void info   (String m) { write("INFO",    m); }
    public void warning(String m) { write("WARNING", m); }
    public void error  (String m) { write("ERROR",   m); }
    public void event  (String m) { write("EVENT",   m); }

    /** Returns the most recent {@code n} log entries (newest last). */
    public synchronized List<String> recent(int n) {
        int from = Math.max(0, mem.size() - n);
        return new ArrayList<>(mem.subList(from, mem.size()));
    }

    /** Reads the full log file from disk (for the log panel "Refresh" button). */
    public String readAll() {
        try { return Files.readString(java.nio.file.Path.of(path)); }
        catch (IOException e) { return "(No log file yet)"; }
    }
}
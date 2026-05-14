
package jkuat.weather.utils;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;

//weather logger class for time-stamped log entries of events, errors, and info messages
public class WeatherLogger {

    private static final DateTimeFormatter FMT =
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final String       path;
    private final List<String> mem = new ArrayList<>();

    public WeatherLogger() {
        this.path = Cfg.LOG_FILE;
        new File(Cfg.DATA_DIR).mkdirs();
    }
//synchronization to ensure thread safety
    private synchronized void write(String level, String msg) {
        String entry = "[" + LocalDateTime.now().format(FMT) + "] "
                     + "[" + String.format("%-7s", level) + "] " + msg;
        mem.add(entry);
        if (mem.size() > 500) mem.remove(0);

        try (var w = new FileWriter(path, true)) {
            w.write(entry + "\n");
        } catch (IOException ignored) { /* log failure should never crash app */ }
    }

//public methods for logging different levels of messages
    public void info   (String m) { write("INFO",    m); }
    public void warning(String m) { write("WARNING", m); }
    public void error  (String m) { write("ERROR",   m); }
    public void event  (String m) { write("EVENT",   m); }

//returns the most recent n log entries from memory
    public synchronized List<String> recent(int n) {
        int from = Math.max(0, mem.size() - n);
        return new ArrayList<>(mem.subList(from, mem.size()));
    }

//reads the entire log file content as a string
    public String readAll() {
        try { return Files.readString(java.nio.file.Path.of(path)); }
        catch (IOException e) { return "(No log file yet)"; }
    }
}
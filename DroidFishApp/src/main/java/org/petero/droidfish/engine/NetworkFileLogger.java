/*
    DroidFish - An Android chess program.
    Copyright (C) 2012-2014  Peter Österlund, peterosterlund2@gmail.com

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

package org.petero.droidfish.engine;

import android.os.Environment;
import android.util.Log;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * Thread-safe file logger for NetworkEngine connection debugging.
 * Writes timestamped entries to DroidFish/logs/network.log on external storage.
 * Auto-rotates at 1MB (keeps one backup as network.log.1).
 */
public class NetworkFileLogger {
    private static final String TAG = "NetworkFileLogger";
    private static final long MAX_SIZE = 1024 * 1024; // 1MB
    private static final String LOG_DIR = "DroidFish/logs";
    private static final String LOG_FILE = "network.log";
    private static final String BACKUP_FILE = "network.log.1";

    private static NetworkFileLogger instance;
    private File logFile;
    private File backupFile;
    private boolean initialized;

    private final SimpleDateFormat dateFormat =
            new SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US);

    private NetworkFileLogger() {
        initialized = false;
        try {
            File baseDir = new File(Environment.getExternalStorageDirectory(), LOG_DIR);
            if (!baseDir.exists() && !baseDir.mkdirs()) {
                Log.w(TAG, "Cannot create log directory: " + baseDir);
                return;
            }
            logFile = new File(baseDir, LOG_FILE);
            backupFile = new File(baseDir, BACKUP_FILE);
            initialized = true;
        } catch (Exception e) {
            Log.w(TAG, "Failed to initialize file logger", e);
        }
    }

    /** Get singleton instance. */
    public static synchronized NetworkFileLogger getInstance() {
        if (instance == null) {
            instance = new NetworkFileLogger();
        }
        return instance;
    }

    /** Info-level log. */
    public void i(String tag, String msg) {
        write("I", tag, msg);
    }

    /** Warning-level log. */
    public void w(String tag, String msg) {
        write("W", tag, msg);
    }

    /** Error-level log. */
    public void e(String tag, String msg) {
        write("E", tag, msg);
    }

    /** Error-level log with throwable. */
    public void e(String tag, String msg, Throwable t) {
        StringWriter sw = new StringWriter();
        t.printStackTrace(new PrintWriter(sw));
        write("E", tag, msg + "\n" + sw.toString());
    }

    /** Write a formatted log line, rotating if needed. */
    private synchronized void write(String level, String tag, String msg) {
        if (!initialized || logFile == null)
            return;

        try {
            // Rotate if over size limit
            if (logFile.exists() && logFile.length() > MAX_SIZE) {
                if (backupFile.exists()) {
                    backupFile.delete();
                }
                logFile.renameTo(backupFile);
                // logFile reference still points to the original path
                logFile = new File(logFile.getParentFile(), LOG_FILE);
            }

            String timestamp = dateFormat.format(new Date());
            String line = timestamp + " [" + level + "] " + tag + ": " + msg + "\n";

            FileWriter fw = new FileWriter(logFile, true);
            fw.write(line);
            fw.close();
        } catch (IOException e) {
            Log.w(TAG, "Failed to write to network log", e);
        }
    }
}

/*
    DroidFish - An Android chess program.
    Copyright (C) 2011-2014  Peter Österlund, peterosterlund2@gmail.com

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

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.channels.FileChannel;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

import org.petero.droidfish.DroidFishApp;
import org.petero.droidfish.EngineOptions;
import org.petero.droidfish.R;
import android.content.Context;
import android.util.Log;

/** Engine running as a process started from an external resource. */
public class ExternalEngine extends UCIEngineBase {
    private static final String TAG = "ExternalEngine";
    protected final Context context;

    private File engineFileName;
    private File engineWorkDir;
    private final Report report;
    private Process engineProc;
    private Thread startupThread;
    private Thread exitThread;
    private Thread stdInThread;
    private Thread stdErrThread;
    private Thread stdOutThread;
    private final LocalPipe inLines;
    private final LocalPipe outLines;
    private boolean startedOk;
    private boolean isRunning;

    public ExternalEngine(String engine, String workDir, Report report) {
        context = DroidFishApp.getContext();
        this.report = report;
        engineFileName = new File(engine);
        engineWorkDir = new File(workDir);
        engineProc = null;
        startupThread = null;
        exitThread = null;
        stdInThread = null;
        stdErrThread = null;
        stdOutThread = null;
        inLines = new LocalPipe();
        outLines = new LocalPipe();
        startedOk = false;
        isRunning = false;
    }

    protected String internalSFPath() {
        return context.getFilesDir().getAbsolutePath() + "/internal_sf";
    }

    /** Override to configure ProcessBuilder before the engine process starts.
     *  Subclasses can use this to set environment variables or other options. */
    protected void configureProcessBuilder(ProcessBuilder pb) {
        // Default: no-op
    }

    /** Return log file for engine stderr output. Tries external storage first,
     *  falls back to app-internal storage. Returns null if neither works. */
    private File getEngineLogFile() {
        String engineName = engineFileName.getName();
        if (engineName.startsWith("lib") && engineName.endsWith(".so"))
            engineName = engineName.substring(3, engineName.length() - 3);
        String logName = engineName + ".log";

        // Try external storage: DroidFish/uci/logs/
        try {
            File extDir = android.os.Environment.getExternalStorageDirectory();
            File logDir = new File(extDir, "DroidFish/uci/logs");
            if (logDir.isDirectory() || logDir.mkdirs()) {
                File logFile = new File(logDir, logName);
                return logFile;
            }
        } catch (Exception ignore) {
        }

        // Fallback: app-internal storage
        try {
            File logDir = new File(context.getFilesDir(), "engine-logs");
            logDir.mkdirs();
            return new File(logDir, logName);
        } catch (Exception ignore) {
        }
        return null;
    }

    @Override
    protected void startProcess() {
        try {
            File exeDir = new File(context.getFilesDir(), "engine");
            exeDir.mkdir();
            Log.d(TAG, "Engine exeDir: " + exeDir.getAbsolutePath());
            String exePath = copyFile(engineFileName, exeDir);
            File exeFile = new File(exePath);
            Log.d(TAG, "Engine exe path: " + exePath);
            Log.d(TAG, "Engine exe exists: " + exeFile.exists() +
                       ", size: " + exeFile.length() +
                       ", canRead: " + exeFile.canRead() +
                       ", canExecute: " + exeFile.canExecute());
            chmod(exePath);
            cleanUpExeDir(exeDir, exePath);
            ProcessBuilder pb = new ProcessBuilder(exePath);
            if (engineWorkDir.canRead() && engineWorkDir.isDirectory())
                pb.directory(engineWorkDir);
            configureProcessBuilder(pb);
            Log.d(TAG, "Starting engine process...");
            synchronized (EngineUtil.nativeLock) {
                engineProc = pb.start();
            }
            Log.d(TAG, "Engine process started successfully");
            reNice();

            startupThread = new Thread(() -> {
                try {
                    Thread.sleep(10000);
                } catch (InterruptedException e) {
                    return;
                }
                if (!startedOk) {
                    Log.e(TAG, "Engine produced no output after 10s");
                    report.reportError("Engine not responding - no output after 10s. Path: " + exePath);
                } else if (isRunning && !isUCI) {
                    report.reportError(context.getString(R.string.uci_protocol_error));
                }
            });
            startupThread.start();

            exitThread = new Thread(() -> {
                try {
                    Process ep = engineProc;
                    if (ep != null)
                        ep.waitFor();
                    isRunning = false;
                    if (!startedOk) {
                        Log.e(TAG, "Engine process exited before producing output. Path: " + exePath);
                        report.reportError(context.getString(R.string.failed_to_start_engine));
                    } else {
                        Log.w(TAG, "Engine process terminated");
                        report.reportError(context.getString(R.string.engine_terminated));
                    }
                } catch (InterruptedException ignore) {
                }
            });
            exitThread.start();

            // Start a thread to read stdin
            stdInThread = new Thread(() -> {
                Process ep = engineProc;
                if (ep == null)
                    return;
                InputStream is = ep.getInputStream();
                InputStreamReader isr = new InputStreamReader(is);
                BufferedReader br = new BufferedReader(isr, 8192);
                String line;
                try {
                    boolean first = true;
                    while ((line = br.readLine()) != null) {
                        if (Thread.currentThread().isInterrupted())
                            return;
                        if (first)
                            Log.d(TAG, "Engine first output: " + line);
                        synchronized (inLines) {
                            inLines.addLine(line);
                            if (first) {
                                startedOk = true;
                                isRunning = true;
                                first = false;
                            }
                        }
                    }
                    Log.d(TAG, "Engine stdout stream ended");
                } catch (IOException e) {
                    Log.w(TAG, "Engine stdout read error: " + e.getMessage());
                }
                inLines.close();
            });
            stdInThread.start();

            // Start a thread to read and log stderr (to logcat + log file)
            stdErrThread = new Thread(() -> {
                Process ep = engineProc;
                if (ep == null)
                    return;
                BufferedWriter logWriter = null;
                try {
                    File logFile = getEngineLogFile();
                    if (logFile != null) {
                        logWriter = new BufferedWriter(new FileWriter(logFile, true));
                        SimpleDateFormat sdf = new SimpleDateFormat(
                                "yyyy-MM-dd HH:mm:ss", Locale.US);
                        logWriter.write("--- Engine started " + sdf.format(new Date()) + " ---\n");
                        logWriter.flush();
                    }
                } catch (IOException e) {
                    Log.w(TAG, "Could not open engine log file: " + e.getMessage());
                }
                try (BufferedReader br = new BufferedReader(
                        new InputStreamReader(ep.getErrorStream()), 4096)) {
                    String line;
                    while ((line = br.readLine()) != null) {
                        if (Thread.currentThread().isInterrupted())
                            break;
                        Log.w(TAG, "Engine stderr: " + line);
                        if (logWriter != null) {
                            try {
                                logWriter.write(line);
                                logWriter.newLine();
                                logWriter.flush();
                            } catch (IOException ignore) {
                            }
                        }
                    }
                } catch (IOException e) {
                    // stream closed
                } finally {
                    if (logWriter != null) {
                        try { logWriter.close(); } catch (IOException ignore) {}
                    }
                }
            });
            stdErrThread.start();

            // Start a thread to write data to engine
            stdOutThread = new Thread(() -> {
                try {
                    String line;
                    while ((line = outLines.readLine()) != null) {
                        if (Thread.currentThread().isInterrupted())
                            return;
                        Process ep = engineProc;
                        if (ep == null)
                            return;
                        line += "\n";
                        ep.getOutputStream().write(line.getBytes());
                        ep.getOutputStream().flush();
                    }
                } catch (IOException e) {
                    Log.w(TAG, "Engine write error: " + e.getMessage());
                }
            });
            stdOutThread.start();
        } catch (IOException | SecurityException ex) {
            Log.e(TAG, "Engine startup failed: " + ex.getMessage(), ex);
            report.reportError("Engine startup failed: " + ex.getMessage());
        }
    }

    /** Try to lower the engine process priority.
     *  Uses reflection to access the private "pid" field of the Process object
     *  because the standard Java Process API does not expose the native PID
     *  (prior to Java 9's Process.pid()). The priority is lowered via a JNI
     *  call to setpriority(2) so the engine doesn't starve the UI thread. */
    private void reNice() {
        try {
            java.lang.reflect.Field f = engineProc.getClass().getDeclaredField("pid");
            f.setAccessible(true);
            int pid = f.getInt(engineProc);
            EngineUtil.reNice(pid, 10);
        } catch (Throwable ignore) {
        }
    }

    /** Remove all files except exePath from exeDir. */
    private void cleanUpExeDir(File exeDir, String exePath) {
        try {
            exePath = new File(exePath).getCanonicalPath();
            File[] files = exeDir.listFiles();
            if (files == null)
                return;
            for (File f : files) {
                if (!f.getCanonicalPath().equals(exePath) && !keepExeDirFile(f))
                    f.delete();
            }
        } catch (IOException ignore) {
        }
    }

    private boolean keepExeDirFile(File f) {
        return InternalStockFish.keepExeDirFile(f);
    }

    private int hashMB = -1;
    private String gaviotaTbPath = "";
    private String syzygyPath = "";
    private boolean optionsInitialized = false;

    @Override
    public void initOptions(EngineOptions engineOptions) {
        super.initOptions(engineOptions);
        hashMB = getHashMB(engineOptions);
        setOption("Hash", hashMB);
        syzygyPath = engineOptions.getEngineRtbPath(false);
        setOption("SyzygyPath", syzygyPath);
        gaviotaTbPath = engineOptions.getEngineGtbPath(false);
        setOption("GaviotaTbPath", gaviotaTbPath);
        optionsInitialized = true;
    }

    @Override
    protected File getOptionsFile() {
        return new File(engineFileName.getAbsolutePath() + ".ini");
    }

    /** Reduce too large hash sizes. */
    private static int getHashMB(EngineOptions engineOptions) {
        int hashMB = engineOptions.hashMB;
        if (hashMB > 16 && !engineOptions.unSafeHash) {
            int maxMem = (int)(Runtime.getRuntime().maxMemory() / (1024*1024));
            if (maxMem < 16)
                maxMem = 16;
            if (hashMB > maxMem)
                hashMB = maxMem;
        }
        return hashMB;
    }

    @Override
    public boolean optionsOk(EngineOptions engineOptions) {
        if (!optionsInitialized)
            return true;
        if (hashMB != getHashMB(engineOptions))
            return false;
        if (hasOption("gaviotatbpath") && !gaviotaTbPath.equals(engineOptions.getEngineGtbPath(false)))
            return false;
        if (hasOption("syzygypath") && !syzygyPath.equals(engineOptions.getEngineRtbPath(false)))
            return false;
        return true;
    }

    @Override
    public String readLineFromEngine(int timeoutMillis) {
        String ret = inLines.readLine(timeoutMillis);
        if (ret == null)
            return null;
        if (ret.length() > 0) {
//            System.out.printf("Engine -> GUI: %s\n", ret);
        }
        return ret;
    }

    @Override
    public void writeLineToEngine(String data) {
        outLines.addLine(data);
    }

    @Override
    public void shutDown() {
        if (startupThread != null)
            startupThread.interrupt();
        if (exitThread != null)
            exitThread.interrupt();
        super.shutDown();
        if (engineProc != null) {
            for (int i = 0; i < 25; i++) {
                try {
                    engineProc.exitValue();
                    break;
                } catch (IllegalThreadStateException e) {
                    try { Thread.sleep(10); } catch (InterruptedException ignore) { }
                }
            }
            engineProc.destroy();
        }
        engineProc = null;
        outLines.close();
        if (stdInThread != null)
            stdInThread.interrupt();
        if (stdErrThread != null)
            stdErrThread.interrupt();
        if (stdOutThread != null)
            stdOutThread.interrupt();
    }

    protected String copyFile(File from, File exeDir) throws IOException {
        File to = new File(exeDir, "engine.exe");
        new File(internalSFPath()).delete();
        if (to.exists() && (from.length() == to.length()) && (from.lastModified() == to.lastModified()))
            return to.getAbsolutePath();
        try (FileInputStream fis = new FileInputStream(from);
             FileChannel inFC = fis.getChannel();
             FileOutputStream fos = new FileOutputStream(to);
             FileChannel outFC = fos.getChannel()) {
            long cnt = outFC.transferFrom(inFC, 0, inFC.size());
            if (cnt < inFC.size())
                throw new IOException("File copy failed");
        } finally {
            to.setLastModified(from.lastModified());
        }
        return to.getAbsolutePath();
    }

    protected void chmod(String exePath) throws IOException {
        if (!EngineUtil.chmod(exePath))
            throw new IOException("chmod failed");
    }
}

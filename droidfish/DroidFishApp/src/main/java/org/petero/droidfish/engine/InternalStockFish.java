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

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Arrays;
import java.util.Locale;

import android.os.Environment;
import android.util.Log;

import org.petero.droidfish.EngineOptions;

/** Stockfish engine running as process, started from assets resource. */
public class InternalStockFish extends ExternalEngine {
    private static final String TAG = "InternalStockFish";
    private static final String[] defaultNets = {"nn-c288c895ea92.nnue", "nn-37f18f62d772.nnue"};
    private static final String[] netOptions = {"evalfile", "evalfilesmall"};
    private final File[] defaultNetFiles = {null, null}; // Full path of the copied default network files
    private File nnueDir; // Directory containing NNUE net files

    public InternalStockFish(Report report, String workDir) {
        super("", workDir, report);
    }

    @Override
    protected File getOptionsFile() {
        File extDir = Environment.getExternalStorageDirectory();
        return new File(extDir, "/DroidFish/uci/stockfish.ini");
    }

    @Override
    protected boolean editableOption(String name) {
        name = name.toLowerCase(Locale.US);
        if (!super.editableOption(name))
            return false;
        if (name.equals("skill level") || name.equals("write debug log") ||
            name.equals("write search log"))
            return false;
        return true;
    }

    @Override
    protected String copyFile(File from, File exeDir) throws IOException {
        // On Android 10+, app data directories are noexec. The Stockfish
        // executable is packaged as lib*.so in jniLibs, so Android extracts
        // it to nativeLibraryDir which has execute permission.
        String exePath = EngineUtil.internalStockFishPath(context);
        Log.d(TAG, "Internal Stockfish path: " + exePath);
        File exeFile = new File(exePath);
        Log.d(TAG, "Stockfish exists: " + exeFile.exists() + ", size: " + exeFile.length());
        Log.d(TAG, "Copying NNUE net files to: " + exeDir.getAbsolutePath());
        copyNetFiles(exeDir);
        nnueDir = exeDir;
        Log.d(TAG, "NNUE files copied successfully");
        return exePath;
    }

    @Override
    protected void chmod(String exePath) {
        // No-op: files in nativeLibraryDir are already executable
        // and owned by the system (chmod would fail with EPERM).
    }

    @Override
    protected void configureProcessBuilder(ProcessBuilder pb) {
        // Set working directory to the NNUE file directory so Stockfish
        // can find the neural network files during initial load_networks()
        // before UCI setoption commands are received.
        if (nnueDir != null && nnueDir.isDirectory()) {
            Log.d(TAG, "Setting engine working directory to: " + nnueDir.getAbsolutePath());
            pb.directory(nnueDir);
        }
    }

    /** Copy the Stockfish default network files to "exeDir" if they are not already there. */
    private void copyNetFiles(File exeDir) throws IOException {
        for (int i = 0; i < 2; i++) {
            defaultNetFiles[i] = new File(exeDir, defaultNets[i]);
            if (!defaultNetFiles[i].exists()) {
                File tmpFile = new File(exeDir, defaultNets[i] + ".tmp");
                copyAssetFile(defaultNets[i], tmpFile);
                if (!tmpFile.renameTo(defaultNetFiles[i]))
                    throw new IOException("Rename failed");
            }
        }
    }

    /** Copy a file resource from the AssetManager to the file system,
     *  so it can be used by native code like the Stockfish engine. */
    private void copyAssetFile(String assetName, File targetFile) throws IOException {
        try (InputStream is = context.getAssets().open(assetName);
             OutputStream os = new FileOutputStream(targetFile)) {
            byte[] buf = new byte[8192];
            while (true) {
                int len = is.read(buf);
                if (len <= 0)
                    break;
                os.write(buf, 0, len);
            }
        }
    }

    /** Return true if file "f" should be kept in the exeDir directory.
     *  It would be inefficient to remove the network file every time
     *  an engine different from Stockfish is used, so this is a static
     *  check performed for all engines. */
    public static boolean keepExeDirFile(File f) {
        return Arrays.asList(defaultNets).contains(f.getName());
    }

    @Override
    public void initOptions(EngineOptions engineOptions) {
        super.initOptions(engineOptions);
        for (int i = 0; i < 2; i++) {
            UCIOptions.OptionBase opt = getUCIOptions().getOption(netOptions[i]);
            if (opt != null)
                setOption(netOptions[i], opt.getStringValue());
        }
    }

    /** Handles setting the EvalFile UCI option to a full path if needed,
     *  pointing to the network file embedded in DroidFish. */
    @Override
    public boolean setOption(String name, String value) {
        for (int i = 0; i < 2; i++) {
            if (name.toLowerCase(Locale.US).equals(netOptions[i]) &&
                (defaultNets[i].equals(value) || value.isEmpty())) {
                getUCIOptions().getOption(name).setFromString(value);
                value = defaultNetFiles[i].getAbsolutePath();
                writeLineToEngine(String.format(Locale.US, "setoption name %s value %s", name, value));
                return true;
            }
        }
        return super.setOption(name, value);
    }
}

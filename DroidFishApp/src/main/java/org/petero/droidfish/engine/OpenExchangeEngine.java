/*
    DroidFish - An Android chess program.
    Copyright (C) 2014,2016  Peter Österlund, peterosterlund2@gmail.com

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
import java.io.IOException;
import java.util.List;

import com.kalab.chess.enginesupport.ChessEngine;
import com.kalab.chess.enginesupport.ChessEngineResolver;

import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.util.Log;

/** Engine imported from a different android app, resolved using the open exchange format. */
public class OpenExchangeEngine extends ExternalEngine {
    private static final String TAG = "OpenExchangeEngine";

    /** True when the engine binary is in the source APK's nativeLibraryDir
     *  (already executable, no chmod needed). */
    private boolean usingNativePath = false;

    public OpenExchangeEngine(String engine, String workDir, Report report) {
        super(engine, workDir, report);
    }

    @Override
    protected String copyFile(File from, File exeDir) throws IOException {
        new File(internalSFPath()).delete();
        ChessEngineResolver resolver = new ChessEngineResolver(context);
        List<ChessEngine> engines = resolver.resolveEngines();
        for (ChessEngine engine : engines) {
            if (EngineUtil.openExchangeFileName(engine).equals(from.getName())) {
                // On Android 10+ (API 29+), getFilesDir() is mounted noexec so
                // copied binaries cannot be executed. Try to run the engine
                // directly from the source APK's nativeLibraryDir instead.
                String nativePath = findNativeLibPath(engine);
                if (nativePath != null) {
                    Log.d(TAG, "Using engine from nativeLibraryDir: " + nativePath);
                    usingNativePath = true;
                    return nativePath;
                }

                // Fallback: copy via ContentProvider (works on Android < 10)
                Log.d(TAG, "Falling back to ContentProvider copy for: " + engine.getName());
                File engineFile = engine.copyToFiles(context.getContentResolver(), exeDir);
                return engineFile.getAbsolutePath();
            }
        }
        throw new IOException("Engine not found");
    }

    /** Look for the engine binary in the source APK's nativeLibraryDir.
     *  Engine APKs package their binaries as lib*.so in jniLibs/, which
     *  Android extracts to nativeLibraryDir with execute permission. */
    private String findNativeLibPath(ChessEngine engine) {
        try {
            ApplicationInfo ai = context.getPackageManager()
                    .getApplicationInfo(engine.getPackageName(), 0);
            String nativeLibDir = ai.nativeLibraryDir;
            if (nativeLibDir == null) return null;

            String fileName = engine.getFileName();
            Log.d(TAG, "Looking for engine in: " + nativeLibDir
                       + ", fileName=" + fileName);

            // Try exact filename (e.g., "liblc0.so")
            File f = new File(nativeLibDir, fileName);
            if (f.exists() && f.canExecute()) {
                Log.d(TAG, "Found exact: " + f.getAbsolutePath());
                return f.getAbsolutePath();
            }

            // Try lib<name>.so convention (e.g., filename="lc0" → "liblc0.so")
            f = new File(nativeLibDir, "lib" + fileName + ".so");
            if (f.exists() && f.canExecute()) {
                Log.d(TAG, "Found with lib prefix: " + f.getAbsolutePath());
                return f.getAbsolutePath();
            }

            // Try adding .so suffix (e.g., filename="lc0" → "lc0.so")
            f = new File(nativeLibDir, fileName + ".so");
            if (f.exists() && f.canExecute()) {
                Log.d(TAG, "Found with .so suffix: " + f.getAbsolutePath());
                return f.getAbsolutePath();
            }

            // Try stripping extension and wrapping with lib...so
            // (e.g., filename="lc0.so" → "liblc0.so")
            int dotIdx = fileName.lastIndexOf('.');
            if (dotIdx > 0) {
                String base = fileName.substring(0, dotIdx);
                f = new File(nativeLibDir, "lib" + base + ".so");
                if (f.exists() && f.canExecute()) {
                    Log.d(TAG, "Found with lib wrap: " + f.getAbsolutePath());
                    return f.getAbsolutePath();
                }
            }

            // List all files in nativeLibDir for diagnostics
            File dir = new File(nativeLibDir);
            File[] files = dir.listFiles();
            if (files != null) {
                for (File file : files) {
                    Log.d(TAG, "  nativeLib file: " + file.getName()
                               + " canExec=" + file.canExecute());
                }
            }

            return null;
        } catch (PackageManager.NameNotFoundException e) {
            Log.w(TAG, "Package not found: " + engine.getPackageName());
            return null;
        }
    }

    @Override
    protected void chmod(String exePath) throws IOException {
        if (usingNativePath) {
            // Binary is in source APK's nativeLibraryDir — already executable
            return;
        }
        super.chmod(exePath);
    }
}

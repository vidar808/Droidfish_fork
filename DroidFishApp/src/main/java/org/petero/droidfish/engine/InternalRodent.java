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

import android.os.Environment;
import android.util.Log;

/** Rodent IV engine running as a process, started from bundled native library. */
public class InternalRodent extends ExternalEngine {
    private static final String TAG = "InternalRodent";

    public InternalRodent(Report report, String workDir) {
        super("", workDir, report);
    }

    @Override
    protected File getOptionsFile() {
        File extDir = Environment.getExternalStorageDirectory();
        File iniFile = new File(extDir, "/DroidFish/uci/rodent4.ini");
        File parent = iniFile.getParentFile();
        if (parent != null && !parent.exists())
            parent.mkdirs();
        return iniFile;
    }

    @Override
    protected String copyFile(File from, File exeDir) throws IOException {
        String exePath = EngineUtil.internalRodentPath(context);
        Log.d(TAG, "Internal Rodent IV path: " + exePath);
        copyDataFiles();
        return exePath;
    }

    @Override
    protected void chmod(String exePath) {
        // No-op: files in nativeLibraryDir are already executable
    }

    @Override
    protected void configureProcessBuilder(ProcessBuilder pb) {
        // Set environment variables so Rodent finds personalities and books
        // via absolute paths. Rodent checks RIIIPERSONALITIES and RIIIBOOKS
        // env vars before falling back to relative ChDir paths.
        File dataDir = new File(context.getFilesDir(), "rodent");
        dataDir.mkdirs();
        pb.directory(dataDir);
        pb.environment().put("RIIIPERSONALITIES",
                new File(dataDir, "personalities").getAbsolutePath());
        pb.environment().put("RIIIBOOKS",
                new File(dataDir, "books").getAbsolutePath());
        Log.d(TAG, "Rodent IV data dir: " + dataDir.getAbsolutePath());
    }

    /** Copy personality files, book files, and guide.bin from assets to internal storage. */
    private void copyDataFiles() throws IOException {
        File dataDir = new File(context.getFilesDir(), "rodent");
        File persDir = new File(dataDir, "personalities");
        File booksDir = new File(dataDir, "books");
        persDir.mkdirs();
        booksDir.mkdirs();

        // Copy personality files
        String[] persFiles = context.getAssets().list("rodent/personalities");
        if (persFiles != null) {
            for (String name : persFiles) {
                File dst = new File(persDir, name);
                if (!dst.exists()) {
                    copyAssetFile("rodent/personalities/" + name, dst);
                }
            }
        }

        // Copy book file
        File bookFile = new File(booksDir, "rodent.bin");
        if (!bookFile.exists()) {
            copyAssetFile("rodent/books/rodent.bin", bookFile);
        }

        // Copy guide.bin
        File guideFile = new File(dataDir, "guide.bin");
        if (!guideFile.exists()) {
            copyAssetFile("rodent/guide.bin", guideFile);
        }

        Log.d(TAG, "Rodent IV data files ready at: " + dataDir.getAbsolutePath());
    }

    private void copyAssetFile(String assetName, File targetFile) throws IOException {
        try (InputStream is = context.getAssets().open(assetName);
             OutputStream os = new FileOutputStream(targetFile)) {
            byte[] buf = new byte[8192];
            int len;
            while ((len = is.read(buf)) > 0) {
                os.write(buf, 0, len);
            }
        }
    }
}

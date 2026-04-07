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
import java.io.IOException;

import android.os.Environment;
import android.util.Log;

/** Patricia engine running as a process, started from bundled native library. */
public class InternalPatricia extends ExternalEngine {
    private static final String TAG = "InternalPatricia";

    public InternalPatricia(Report report, String workDir) {
        super("", workDir, report);
    }

    @Override
    protected File getOptionsFile() {
        File extDir = Environment.getExternalStorageDirectory();
        File iniFile = new File(extDir, "/DroidFish/uci/patricia.ini");
        File parent = iniFile.getParentFile();
        if (parent != null && !parent.exists())
            parent.mkdirs();
        return iniFile;
    }

    @Override
    protected String copyFile(File from, File exeDir) throws IOException {
        String exePath = EngineUtil.internalPatriciaPath(context);
        Log.d(TAG, "Internal Patricia path: " + exePath);
        return exePath;
    }

    @Override
    protected void chmod(String exePath) {
        // No-op: files in nativeLibraryDir are already executable
    }
}

/*
    DroidFish - An Android chess program.
    Copyright (C) 2024  Peter Österlund, peterosterlund2@gmail.com

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
import java.util.Locale;
import java.util.Map;

import org.petero.droidfish.EngineOptions;

import android.util.Log;

/** Engine configured via an engine.json manifest file. Supports forced UCI
 *  options, hidden options, and go command overrides (for engines like Maia
 *  that need "go nodes 1" instead of normal go commands). */
public class ConfiguredEngine extends ExternalEngine {
    private static final String TAG = "ConfiguredEngine";

    private final String enginePath;
    private final EngineManifest manifest;
    private final EngineManifest.Variant variant;
    private final String goOverride;

    public ConfiguredEngine(String engine, String workDir, Report report) {
        super(engine, workDir, report);
        this.enginePath = engine;
        this.manifest = EngineManifest.fromEnginePath(engine);
        String variantId = EngineManifest.getVariantId(engine);
        this.variant = (manifest != null) ? manifest.findVariant(variantId) : null;
        this.goOverride = (variant != null) ? variant.goOverride : null;
    }

    @Override
    protected String copyFile(File from, File exeDir) throws IOException {
        if (manifest == null)
            return super.copyFile(from, exeDir);
        File binaryFile = manifest.getBinaryFile();
        if (!binaryFile.exists())
            throw new IOException("Engine binary not found: " + binaryFile.getAbsolutePath());
        return super.copyFile(binaryFile, exeDir);
    }

    @Override
    protected void configureProcessBuilder(ProcessBuilder pb) {
        if (manifest != null) {
            File dir = manifest.engineDir;
            if (dir.isDirectory())
                pb.directory(dir);
        }
    }

    @Override
    public void initOptions(EngineOptions engineOptions) {
        super.initOptions(engineOptions);
        if (manifest != null) {
            Map<String,String> opts = manifest.getMergedOptions(variant);
            for (Map.Entry<String,String> entry : opts.entrySet()) {
                setOption(entry.getKey(), entry.getValue());
            }
        }
    }

    @Override
    protected boolean editableOption(String name) {
        if (!super.editableOption(name))
            return false;
        if (manifest != null) {
            for (String hidden : manifest.hiddenOptions) {
                if (hidden.equalsIgnoreCase(name))
                    return false;
            }
        }
        return true;
    }

    @Override
    protected File getOptionsFile() {
        if (manifest == null)
            return super.getOptionsFile();
        // Use the binary path with .ini extension, plus variant suffix if applicable
        File binary = manifest.getBinaryFile();
        String basePath = binary.getAbsolutePath();
        if (variant != null)
            basePath += "." + variant.id;
        return new File(basePath + ".ini");
    }

    @Override
    public void writeLineToEngine(String data) {
        if (goOverride != null && data.startsWith("go ") &&
                !data.startsWith("go ponder")) {
            super.writeLineToEngine(goOverride);
        } else {
            super.writeLineToEngine(data);
        }
    }
}

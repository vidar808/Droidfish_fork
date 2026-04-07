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
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import org.petero.droidfish.FileUtil;

import android.util.Log;

/** Parses an engine.json manifest file that describes an engine and its variants. */
public class EngineManifest {
    private static final String TAG = "EngineManifest";

    public final String id;
    public final String binary;
    public final String displayName;
    public final Map<String,String> uciOptions;
    public final Set<String> hiddenOptions;
    public final List<Variant> variants;
    public final File engineDir;

    public static class Variant {
        public final String id;
        public final String displayName;
        public final String goOverride;
        public final Map<String,String> uciOptions;

        Variant(String id, String displayName, String goOverride,
                Map<String,String> uciOptions) {
            this.id = id;
            this.displayName = displayName;
            this.goOverride = goOverride;
            this.uciOptions = uciOptions;
        }
    }

    private EngineManifest(String id, String binary, String displayName,
                           Map<String,String> uciOptions, Set<String> hiddenOptions,
                           List<Variant> variants, File engineDir) {
        this.id = id;
        this.binary = binary;
        this.displayName = displayName;
        this.uciOptions = uciOptions;
        this.hiddenOptions = hiddenOptions;
        this.variants = variants;
        this.engineDir = engineDir;
    }

    /** Return true if the engine path references a manifest-based engine.
     *  Engine IDs that contain '#' are variant references (e.g. /path/to/lc0#maia-1500). */
    public static boolean hasManifest(String enginePath) {
        String path = enginePath;
        int hashIdx = path.indexOf('#');
        if (hashIdx >= 0)
            path = path.substring(0, hashIdx);
        File binaryFile = new File(path);
        File dir = binaryFile.getParentFile();
        if (dir == null)
            return false;
        return new File(dir, "engine.json").isFile();
    }

    /** Parse a manifest from the directory containing the given engine path.
     *  The engine path may include a #variant-id suffix. */
    public static EngineManifest fromEnginePath(String enginePath) {
        String path = enginePath;
        int hashIdx = path.indexOf('#');
        if (hashIdx >= 0)
            path = path.substring(0, hashIdx);
        File binaryFile = new File(path);
        File dir = binaryFile.getParentFile();
        if (dir == null)
            return null;
        return parse(dir);
    }

    /** Extract the variant ID from an engine path, or null if none. */
    public static String getVariantId(String enginePath) {
        int hashIdx = enginePath.indexOf('#');
        if (hashIdx >= 0 && hashIdx < enginePath.length() - 1)
            return enginePath.substring(hashIdx + 1);
        return null;
    }

    /** Parse engine.json in the given directory. Returns null on error. */
    public static EngineManifest parse(File dir) {
        File manifestFile = new File(dir, "engine.json");
        if (!manifestFile.isFile())
            return null;
        try {
            String json = readFileAsString(manifestFile);
            JSONObject root = new JSONObject(json);
            String dirPath = dir.getAbsolutePath();

            String id = root.optString("id", dir.getName());
            String binary = root.getString("binary");
            String displayName = root.optString("display_name", id);

            Map<String,String> uciOptions = parseOptions(root.optJSONObject("uci_options"), dirPath);

            Set<String> hiddenOptions = new HashSet<>();
            JSONArray hiddenArr = root.optJSONArray("hidden_options");
            if (hiddenArr != null) {
                for (int i = 0; i < hiddenArr.length(); i++)
                    hiddenOptions.add(hiddenArr.getString(i));
            }

            List<Variant> variants = new ArrayList<>();
            JSONArray varArr = root.optJSONArray("variants");
            if (varArr != null) {
                for (int i = 0; i < varArr.length(); i++) {
                    JSONObject v = varArr.getJSONObject(i);
                    String vId = v.getString("id");
                    String vName = v.optString("display_name", vId);
                    String goOverride = v.optString("go_override", null);
                    Map<String,String> vOptions = parseOptions(v.optJSONObject("uci_options"), dirPath);
                    variants.add(new Variant(vId, vName, goOverride, vOptions));
                }
            }

            return new EngineManifest(id, binary, displayName, uciOptions,
                                      hiddenOptions, variants, dir);
        } catch (IOException | JSONException e) {
            Log.w(TAG, "Failed to parse engine.json in " + dir + ": " + e.getMessage());
            return null;
        }
    }

    /** Get the binary file path. */
    public File getBinaryFile() {
        return new File(engineDir, binary);
    }

    /** Find the variant matching the given ID, or null. */
    public Variant findVariant(String variantId) {
        if (variantId == null)
            return null;
        for (Variant v : variants) {
            if (v.id.equals(variantId))
                return v;
        }
        return null;
    }

    /** Get merged UCI options for a variant (base options + variant overrides). */
    public Map<String,String> getMergedOptions(Variant variant) {
        Map<String,String> merged = new HashMap<>(uciOptions);
        if (variant != null)
            merged.putAll(variant.uciOptions);
        return merged;
    }

    private static Map<String,String> parseOptions(JSONObject obj, String engineDirPath) {
        Map<String,String> opts = new HashMap<>();
        if (obj != null) {
            for (java.util.Iterator<String> it = obj.keys(); it.hasNext(); ) {
                String key = it.next();
                String val = obj.optString(key, "");
                val = val.replace("{engine_dir}", engineDirPath);
                opts.put(key, val);
            }
        }
        return opts;
    }

    private static String readFileAsString(File file) throws IOException {
        try (InputStream is = new FileInputStream(file)) {
            return FileUtil.readFromStream(is);
        }
    }
}

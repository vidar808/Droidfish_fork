/*
    DroidFish - An Android chess program.
    Copyright (C) 2016  Peter Österlund, peterosterlund2@gmail.com

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

package org.petero.droidfish;

import android.net.Uri;
import android.os.Environment;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.RandomAccessFile;
import java.io.UnsupportedEncodingException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.petero.droidfish.engine.EngineManifest;

public class FileUtil {
    /** Read a text file. Return string array with one string per line. */
    public static String[] readFile(String filename) throws IOException {
        ArrayList<String> ret = new ArrayList<>();
        try (InputStream inStream = new FileInputStream(filename);
             InputStreamReader inFile = new InputStreamReader(inStream, "UTF-8");
             BufferedReader inBuf = new BufferedReader(inFile)) {
            String line;
            while ((line = inBuf.readLine()) != null)
                ret.add(line);
            return ret.toArray(new String[0]);
        }
    }

    /** Read all data from an input stream. Return null if IO error. */
    public static String readFromStream(InputStream is) {
        try (InputStreamReader isr = new InputStreamReader(is, "UTF-8");
             BufferedReader br = new BufferedReader(isr)) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) {
                sb.append(line);
                sb.append('\n');
            }
            return sb.toString();
        } catch (UnsupportedEncodingException e) {
            return null;
        } catch (IOException e) {
            return null;
        }
    }

    /** Read data from input stream and write to file. */
    public static void writeFile(InputStream is, String outFile) throws IOException {
        try (OutputStream os = new FileOutputStream(outFile)) {
            byte[] buffer = new byte[16384];
            while (true) {
                int len = is.read(buffer);
                if (len <= 0)
                    break;
                os.write(buffer, 0, len);
            }
        }
    }

    /** Return the length of a file, or -1 if length can not be determined. */
    public static long getFileLength(String filename) {
        try (RandomAccessFile raf = new RandomAccessFile(filename, "r")) {
            return raf.length();
        } catch (IOException ex) {
            return -1;
        }
    }

    public interface FileNameFilter {
        boolean accept(String filename);
    }

    public static String[] findFilesInDirectory(String dirName, final FileNameFilter filter) {
        File extDir = Environment.getExternalStorageDirectory();
        String sep = File.separator;
        File dir = new File(extDir.getAbsolutePath() + sep + dirName);
        File[] files = dir.listFiles(pathname -> {
            if (!pathname.isFile())
                return false;
            return (filter == null) || filter.accept(pathname.getAbsolutePath());
        });
        if (files == null)
            files = new File[0];
        final int numFiles = files.length;
        String[] fileNames = new String[numFiles];
        for (int i = 0; i < files.length; i++)
            fileNames[i] = files[i].getName();
        Arrays.sort(fileNames, String.CASE_INSENSITIVE_ORDER);
        return fileNames;
    }

    /** An engine entry discovered in a sub-folder. */
    public static class EngineEntry {
        public final String path;        // Full path, possibly with #variant-id
        public final String displayName; // User-visible name

        public EngineEntry(String path, String displayName) {
            this.path = path;
            this.displayName = displayName;
        }
    }

    /** Extensions for data files that should not be treated as engine executables. */
    private static final Set<String> DATA_EXTENSIONS = new HashSet<>(Arrays.asList(
        ".json", ".ini", ".pb.gz", ".bin", ".dat", ".log", ".txt", ".md",
        ".nnue", ".cfg", ".sh", ".bat", ".xml", ".yml", ".yaml"
    ));

    /** Find engine entries in subdirectories of the given directory.
     *  If a subdirectory has engine.json, the manifest is parsed and entries
     *  are created for each variant. Otherwise, executable-looking files
     *  are returned as plain engine entries. */
    public static List<EngineEntry> findEnginesInSubdirectories(String dirName) {
        List<EngineEntry> result = new ArrayList<>();
        File extDir = Environment.getExternalStorageDirectory();
        String sep = File.separator;
        File dir = new File(extDir.getAbsolutePath() + sep + dirName);
        if (!dir.isDirectory())
            return result;

        File[] subDirs = dir.listFiles(File::isDirectory);
        if (subDirs == null)
            return result;
        Arrays.sort(subDirs, (a, b) -> a.getName().compareToIgnoreCase(b.getName()));

        for (File subDir : subDirs) {
            if (subDir.getName().equals("logs") || subDir.getName().equals("oex"))
                continue;

            EngineManifest manifest = EngineManifest.parse(subDir);
            if (manifest != null) {
                String binaryPath = manifest.getBinaryFile().getAbsolutePath();
                if (manifest.variants.isEmpty()) {
                    result.add(new EngineEntry(binaryPath, manifest.displayName));
                } else {
                    for (EngineManifest.Variant v : manifest.variants) {
                        result.add(new EngineEntry(
                            binaryPath + "#" + v.id,
                            v.displayName
                        ));
                    }
                }
            } else {
                // No manifest - find executable-looking files
                File[] files = subDir.listFiles(File::isFile);
                if (files == null)
                    continue;
                Arrays.sort(files, (a, b) -> a.getName().compareToIgnoreCase(b.getName()));
                for (File f : files) {
                    if (!isDataFile(f.getName())) {
                        result.add(new EngineEntry(
                            f.getAbsolutePath(),
                            subDir.getName() + "/" + f.getName()
                        ));
                    }
                }
            }
        }
        return result;
    }

    /** Return true if the filename looks like a data file (not an executable). */
    private static boolean isDataFile(String name) {
        String lower = name.toLowerCase();
        for (String ext : DATA_EXTENSIONS) {
            if (lower.endsWith(ext))
                return true;
        }
        return false;
    }

    public static String getFilePathFromUri(Uri uri) {
        if (uri == null)
            return null;
        return uri.getPath();
    }
}

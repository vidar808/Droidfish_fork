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

import android.app.Application;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.content.res.Resources;
import android.os.Build;
import android.preference.PreferenceManager;
import android.util.Log;
import android.widget.Toast;

import android.os.Environment;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.Locale;

public class DroidFishApp extends Application {
    private static final String TAG = "DroidFishApp";
    private static Context appContext;
    private static Toast toast;

    public DroidFishApp() {
        super();
        appContext = this;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        final Thread.UncaughtExceptionHandler defaultHandler =
            Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread, throwable) -> {
            try {
                StringWriter sw = new StringWriter();
                PrintWriter pw = new PrintWriter(sw);
                pw.println("=== CRASH REPORT ===");
                pw.println("Time: " + new java.util.Date());
                pw.println("Thread: " + thread.getName());
                pw.println("Android SDK: " + Build.VERSION.SDK_INT);
                throwable.printStackTrace(pw);
                pw.println();
                String trace = sw.toString();
                Log.e(TAG, "FATAL CRASH:\n" + trace);
                boolean written = false;
                try {
                    File extDir = new File(Environment.getExternalStorageDirectory(), "DroidFish");
                    if (extDir.exists() || extDir.mkdirs()) {
                        File crashFile = new File(extDir, "crash_log.txt");
                        FileWriter fw = new FileWriter(crashFile, true);
                        fw.write(trace);
                        fw.close();
                        written = true;
                    }
                } catch (Exception ignore) {
                }
                if (!written) {
                    File crashFile = new File(getFilesDir(), "crash_log.txt");
                    FileWriter fw = new FileWriter(crashFile, true);
                    fw.write(trace);
                    fw.close();
                }
            } catch (Exception ignore) {
            }
            if (defaultHandler != null)
                defaultHandler.uncaughtException(thread, throwable);
        });
    }

    /** Get the application context. */
    public static Context getContext() {
        return appContext;
    }

    @Override
    protected void attachBaseContext(Context base) {
        super.attachBaseContext(setLanguage(base, false));
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        setLanguage(appContext, false);
    }

    public static Context setLanguage(Context context, boolean restartIfLangChange) {
        Context ret = context;
        SharedPreferences settings = PreferenceManager.getDefaultSharedPreferences(context);
        String lang = settings.getString("language", "default");
        Locale newLocale;
        if ("default".equals(lang)) {
            newLocale = Resources.getSystem().getConfiguration().locale;
        } else if (lang.contains("_")) {
            String[] parts = lang.split("_");
            newLocale = new Locale(parts[0], parts[1]);
        } else {
            newLocale = new Locale(lang);
        }
        String currLang = context.getResources().getConfiguration().locale.getLanguage();
        if (!newLocale.getLanguage().equals(currLang)) {
            Locale.setDefault(newLocale);
            Resources res = context.getResources();
            Configuration config = new Configuration(res.getConfiguration());
            if (Build.VERSION.SDK_INT >= 17) {
                config.setLocale(newLocale);
                ret = context.createConfigurationContext(config);
            } else {
                config.locale = newLocale;
                res.updateConfiguration(config, res.getDisplayMetrics());
            }
            if (restartIfLangChange) {
                Intent i = new Intent(context, DroidFish.class);
                context.startActivity(i.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK |
                                                 Intent.FLAG_ACTIVITY_NEW_TASK));
            }
        }
        return ret;
    }

    /** Show a toast after canceling current toast. */
    public static void toast(int resId, int duration) {
        if (toast != null) {
            toast.cancel();
            toast = null;
        }
        toast = Toast.makeText(appContext, resId, duration);
        toast.show();
    }

    /** Show a toast after canceling current toast. */
    public static void toast(CharSequence text, int duration) {
        if (toast != null) {
            toast.cancel();
            toast = null;
        }
        toast = Toast.makeText(appContext, text, duration);
        toast.show();
    }
}

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

package org.petero.droidfish.activities;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.ConnectException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.List;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

import org.json.JSONArray;
import org.json.JSONObject;
import org.petero.droidfish.DroidFishApp;
import org.petero.droidfish.FileUtil;
import org.petero.droidfish.R;
import org.petero.droidfish.engine.EngineUtil;
import org.petero.droidfish.engine.NetworkDiscovery;

import android.Manifest;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.ListView;
import android.widget.ProgressBar;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

/** Activity for configuring a network chess engine connection. */
public class NetworkEngineConfig extends AppCompatActivity {
    private static final String TAG = "NetworkEngineConfig";
    public static final String EXTRA_CONFIG_PATH = "configPath";
    public static final String EXTRA_ENGINE_NAME = "engineName";
    public static final String EXTRA_ACTIVATE_ENGINE = "activateEngine";
    public static final int RESULT_DELETED = 100;
    public static final int RESULT_IMPORT_FILE = 101;

    private static final int PERMISSION_REQUEST_CAMERA = 1001;
    private static final int RESULT_SCAN_QR = 2001;
    private static final int REQUEST_IMPORT_FILE = 2002;
    private static final int CONNECT_TIMEOUT_MS = 5000;

    // UI references
    private EditText hostView;
    private EditText portView;
    private CheckBox tlsView;
    private EditText authTokenView;
    private EditText pskView;
    private Spinner securitySpinner;
    private View tokenRow;
    private View pskRow;
    private View fingerprintRow;
    private TextView fingerprintValue;
    private Button testButton;
    private ProgressBar testProgress;
    private TextView testResult;
    private ListView enginesList;
    private Button discoverButton;
    private Button fetchEnginesButton;
    private TextView selectedEngineLabel;

    private String configPath;
    private String engineName;
    private String selectedEngineName = "";

    // QR-scanned relay/network info — saved to NETE file by saveConfig()
    private String qrRelayHost = "";
    private String qrRelayPort = "0";
    private String qrRelaySession = "";
    private String qrExternalHost = "";
    private String qrMdnsName = "";

    // Discovered engines from QR/mDNS (for multi-engine)
    private List<EngineInfo> discoveredEngines = new ArrayList<>();

    private static class EngineInfo {
        String name;
        int port;
        String host;
        boolean tls;
        String token;
        String psk;
        String authMethod;
        String fingerprint;
        String relayHost = "";
        int relayPort = 0;
        String relaySessionId = "";
        String externalHost = "";
        String mdnsServiceName = "";
        String selectedEngine = "";

        @Override
        public String toString() {
            return name + " (port " + port + ")";
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_network_engine_config);
        setTitle(R.string.net_config_title);

        configPath = getIntent().getStringExtra(EXTRA_CONFIG_PATH);
        engineName = getIntent().getStringExtra(EXTRA_ENGINE_NAME);

        // Bind views
        hostView = findViewById(R.id.net_config_host);
        portView = findViewById(R.id.net_config_port);
        tlsView = findViewById(R.id.net_config_tls);
        authTokenView = findViewById(R.id.net_config_auth_token);
        pskView = findViewById(R.id.net_config_psk);
        securitySpinner = findViewById(R.id.net_config_security_spinner);
        tokenRow = findViewById(R.id.net_config_token_row);
        pskRow = findViewById(R.id.net_config_psk_row);
        fingerprintRow = findViewById(R.id.net_config_fingerprint_row);
        fingerprintValue = findViewById(R.id.net_config_fingerprint_value);
        testButton = findViewById(R.id.net_config_test);
        testProgress = findViewById(R.id.net_config_test_progress);
        testResult = findViewById(R.id.net_config_test_result);
        enginesList = findViewById(R.id.net_config_engines_list);
        discoverButton = findViewById(R.id.net_config_discover);
        fetchEnginesButton = findViewById(R.id.net_config_fetch_engines);
        selectedEngineLabel = findViewById(R.id.net_config_selected_engine);

        setupSecuritySpinner();
        loadConfig();
        setupButtons();
    }

    private void setupSecuritySpinner() {
        String[] methods = {
            getString(R.string.net_config_auth_none),
            getString(R.string.net_config_auth_token),
            getString(R.string.net_config_auth_psk),
        };
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this,
                android.R.layout.simple_spinner_item, methods);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        securitySpinner.setAdapter(adapter);

        securitySpinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int pos, long id) {
                updateSecurityVisibility(pos);
            }
            @Override
            public void onNothingSelected(AdapterView<?> parent) {}
        });
    }

    private void updateSecurityVisibility(int securityIndex) {
        // 0=None, 1=TLS+Token, 2=PSK
        switch (securityIndex) {
            case 0: // None
                tlsView.setVisibility(View.GONE);
                tokenRow.setVisibility(View.GONE);
                pskRow.setVisibility(View.GONE);
                fingerprintRow.setVisibility(View.GONE);
                break;
            case 1: // TLS + Token
                tlsView.setVisibility(View.VISIBLE);
                tokenRow.setVisibility(View.VISIBLE);
                pskRow.setVisibility(View.GONE);
                fingerprintRow.setVisibility(View.VISIBLE);
                break;
            case 2: // PSK
                tlsView.setVisibility(View.VISIBLE);
                tokenRow.setVisibility(View.GONE);
                pskRow.setVisibility(View.VISIBLE);
                fingerprintRow.setVisibility(View.VISIBLE);
                break;
        }
    }

    private void loadConfig() {
        if (configPath == null || configPath.isEmpty())
            return;

        String hostName = "";
        String port = "0";
        boolean useTLS = false;
        String authToken = "";
        String fingerprint = "";
        String authMethod = "token";
        String pskKey = "";

        try {
            if (EngineUtil.isNetEngine(configPath)) {
                String[] lines = FileUtil.readFile(configPath);
                if (lines.length > 1) hostName = lines[1];
                if (lines.length > 2) port = lines[2];
                if (lines.length > 3) useTLS = "tls".equalsIgnoreCase(lines[3].trim());
                if (lines.length > 4) authToken = lines[4].trim();
                if (lines.length > 5) fingerprint = lines[5].trim();
                if (lines.length > 6) authMethod = lines[6].trim();
                if (lines.length > 7) pskKey = lines[7].trim();
            }
        } catch (IOException e) {
            Log.e(TAG, "Failed to read config", e);
        }

        // Read selected engine (line 13)
        try {
            if (EngineUtil.isNetEngine(configPath)) {
                String[] lines2 = FileUtil.readFile(configPath);
                if (lines2.length > 13) {
                    selectedEngineName = lines2[13].trim();
                }
            }
        } catch (IOException ignore) {}

        hostView.setText(hostName);
        portView.setText(port);
        tlsView.setChecked(useTLS);
        authTokenView.setText(authToken);
        pskView.setText(pskKey);

        if (!fingerprint.isEmpty()) {
            fingerprintValue.setText(fingerprint);
            fingerprintRow.setVisibility(View.VISIBLE);
        }

        // Show selected engine if set
        if (!selectedEngineName.isEmpty()) {
            selectedEngineLabel.setText(String.format(getString(R.string.server_engine_selected),
                    selectedEngineName));
            selectedEngineLabel.setVisibility(View.VISIBLE);
        }

        // Set spinner based on auth method
        if ("psk".equals(authMethod)) {
            securitySpinner.setSelection(2);
        } else if ("none".equals(authMethod) || (authToken.isEmpty() && pskKey.isEmpty() && !useTLS)) {
            securitySpinner.setSelection(0);
        } else {
            securitySpinner.setSelection(1);
        }
    }

    private void setupButtons() {
        // Scan QR
        findViewById(R.id.net_config_scan_qr).setOnClickListener(v -> {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                    != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(this,
                        new String[]{Manifest.permission.CAMERA}, PERMISSION_REQUEST_CAMERA);
            } else {
                launchQrScanner();
            }
        });

        // Import File
        findViewById(R.id.net_config_import_file).setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            intent.setType("*/*");
            startActivityForResult(intent, REQUEST_IMPORT_FILE);
        });

        // Discover
        discoverButton.setOnClickListener(v -> startDiscovery());

        // Fetch engine list from server
        if (fetchEnginesButton != null) {
            fetchEnginesButton.setOnClickListener(v -> fetchEngineList());
        }

        // Test connection
        testButton.setOnClickListener(v -> testConnection());

        // Save
        findViewById(R.id.net_config_save).setOnClickListener(v -> {
            saveConfig();
            setResult(RESULT_OK);
            finish();
        });

        // Cancel
        findViewById(R.id.net_config_cancel).setOnClickListener(v -> {
            setResult(RESULT_CANCELED);
            finish();
        });

        // Delete
        Button deleteBtn = findViewById(R.id.net_config_delete);
        if (configPath != null && new File(configPath).exists()) {
            deleteBtn.setOnClickListener(v -> confirmDelete());
        } else {
            deleteBtn.setVisibility(View.GONE);
        }
    }

    private void saveConfig() {
        if (configPath == null || configPath.isEmpty())
            return;

        String host = hostView.getText().toString().trim();
        String port = portView.getText().toString().trim();
        boolean tls = tlsView.isChecked();
        String token = authTokenView.getText().toString().trim();
        String fingerprint = fingerprintValue.getText().toString().trim();
        String psk = pskView.getText().toString().trim();

        int secIdx = securitySpinner.getSelectedItemPosition();
        String authMethod;
        switch (secIdx) {
            case 2: authMethod = "psk"; break;
            case 0: authMethod = "none"; break;
            default: authMethod = "token"; break;
        }

        // Use QR-scanned relay info if available; otherwise preserve from existing file
        String relayHost = qrRelayHost;
        String relayPort2 = qrRelayPort;
        String relaySession = qrRelaySession;
        String externalHost = qrExternalHost;
        String mdnsServiceName = qrMdnsName;
        if (relayHost.isEmpty() && relayPort2.equals("0") && relaySession.isEmpty()) {
            // No QR info — try to preserve from existing file
            try {
                String[] existingLines = FileUtil.readFile(configPath);
                if (existingLines.length >= 9) relayHost = existingLines[8].trim();
                if (existingLines.length >= 10) relayPort2 = existingLines[9].trim();
                if (existingLines.length >= 11) relaySession = existingLines[10].trim();
                if (existingLines.length >= 12 && externalHost.isEmpty())
                    externalHost = existingLines[11].trim();
                if (existingLines.length >= 13 && mdnsServiceName.isEmpty())
                    mdnsServiceName = existingLines[12].trim();
            } catch (IOException ignore) {}
        }

        try (FileWriter fw = new FileWriter(new File(configPath), false)) {
            fw.write("NETE\n");
            fw.write(host + "\n");
            fw.write(port + "\n");
            fw.write((tls ? "tls" : "notls") + "\n");
            fw.write(token + "\n");
            fw.write(fingerprint + "\n");
            fw.write(authMethod + "\n");
            fw.write(psk + "\n");
            fw.write(relayHost + "\n");
            fw.write(relayPort2 + "\n");
            fw.write(relaySession + "\n");
            fw.write(externalHost + "\n");
            fw.write(mdnsServiceName + "\n");
            fw.write(selectedEngineName + "\n");
        } catch (IOException e) {
            DroidFishApp.toast(e.getMessage(), Toast.LENGTH_LONG);
        }
    }

    private void confirmDelete() {
        String msg = configPath;
        if (msg.lastIndexOf('/') >= 0)
            msg = msg.substring(msg.lastIndexOf('/') + 1);

        // Count associated engine files that share the same host:port
        File[] associated = findAssociatedEngineFiles();
        String displayMsg = getString(R.string.network_engine) + ": " + msg;
        if (associated.length > 0) {
            displayMsg += "\n\n" + (associated.length) + " associated engine(s) will also be removed.";
        }

        new AlertDialog.Builder(this)
            .setTitle(R.string.delete_network_engine)
            .setMessage(displayMsg)
            .setPositiveButton(R.string.yes, (dialog, which) -> {
                // Delete associated engine NETE files that share same host:port
                for (File f : associated) {
                    f.delete();
                }
                new File(configPath).delete();
                setResult(RESULT_DELETED);
                finish();
            })
            .setNegativeButton(R.string.no, null)
            .show();
    }

    /** Find all NETE files in the same directory that share the same host:port
     *  as this config file (excluding this file itself). */
    private File[] findAssociatedEngineFiles() {
        File configFile = new File(configPath);
        File dir = configFile.getParentFile();
        if (dir == null || !dir.isDirectory())
            return new File[0];

        // Read host:port from the file being deleted
        String serverKey;
        try {
            String[] lines = FileUtil.readFile(configPath);
            if (lines.length < 3) return new File[0];
            serverKey = lines[1].trim() + ":" + lines[2].trim();
        } catch (IOException e) {
            return new File[0];
        }

        List<File> matches = new ArrayList<>();
        File[] files = dir.listFiles();
        if (files == null) return new File[0];

        for (File f : files) {
            if (!f.isFile() || f.equals(configFile))
                continue;
            if (!EngineUtil.isNetEngine(f.getAbsolutePath()))
                continue;
            try {
                String[] lines = FileUtil.readFile(f.getAbsolutePath());
                if (lines.length >= 3) {
                    String key = lines[1].trim() + ":" + lines[2].trim();
                    if (key.equals(serverKey)) {
                        matches.add(f);
                    }
                }
            } catch (IOException ignore) {}
        }
        return matches.toArray(new File[0]);
    }

    // ---------------------------------------------------------------
    // QR Scanner
    // ---------------------------------------------------------------

    private void launchQrScanner() {
        try {
            Intent intent = new Intent("com.google.zxing.client.android.SCAN");
            intent.putExtra("SCAN_MODE", "QR_CODE_MODE");
            startActivityForResult(intent, RESULT_SCAN_QR);
        } catch (ActivityNotFoundException e) {
            try {
                Intent intent = new Intent(this,
                        Class.forName("com.journeyapps.barcodescanner.CaptureActivity"));
                startActivityForResult(intent, RESULT_SCAN_QR);
            } catch (ClassNotFoundException | ActivityNotFoundException ex) {
                DroidFishApp.toast("QR scanner not available. Install Barcode Scanner app.",
                        Toast.LENGTH_LONG);
            }
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == PERMISSION_REQUEST_CAMERA) {
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
                launchQrScanner();
            } else {
                DroidFishApp.toast(getString(R.string.qr_camera_permission), Toast.LENGTH_SHORT);
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == RESULT_SCAN_QR && resultCode == RESULT_OK && data != null) {
            String content = data.getStringExtra("SCAN_RESULT");
            handleQrScanResult(content);
        } else if (requestCode == REQUEST_IMPORT_FILE && resultCode == RESULT_OK && data != null) {
            Uri uri = data.getData();
            if (uri != null && isChessUciFile(uri)) {
                Intent result = new Intent();
                result.setData(uri);
                setResult(RESULT_IMPORT_FILE, result);
                finish();
            } else {
                DroidFishApp.toast(getString(R.string.net_config_not_chessuci), Toast.LENGTH_SHORT);
            }
        }
    }

    private boolean isChessUciFile(Uri uri) {
        String displayName = null;
        try (Cursor cursor = getContentResolver().query(uri, null, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (idx >= 0) {
                    displayName = cursor.getString(idx);
                }
            }
        }
        if (displayName == null) {
            displayName = uri.getLastPathSegment();
        }
        return displayName != null && displayName.endsWith(".chessuci");
    }

    private void handleQrScanResult(String qrContent) {
        if (qrContent == null || qrContent.isEmpty()) {
            DroidFishApp.toast(getString(R.string.qr_scan_failed), Toast.LENGTH_SHORT);
            return;
        }
        try {
            JSONObject payload = new JSONObject(qrContent);
            if (!"chess-uci-server".equals(payload.optString("type", ""))) {
                DroidFishApp.toast(getString(R.string.qr_invalid_payload), Toast.LENGTH_SHORT);
                return;
            }

            String host = payload.getString("host");
            boolean tls = payload.optBoolean("tls", false);
            String token = payload.optString("token", "");
            String psk = payload.optString("psk", "");
            String authMethod = payload.optString("auth_method", "token");
            String fingerprint = payload.optString("fingerprint", "");
            String externalHost = payload.optString("external_host", "");
            JSONArray engines = payload.getJSONArray("engines");

            // Prefer external_host (WAN IP) as primary host when available;
            // mDNS discovery handles the local-network case regardless.
            String primaryHost = !externalHost.isEmpty() ? externalHost : host;

            // Extract relay info
            String relayHost = "";
            int relayPort = 0;
            JSONObject relayObj = payload.optJSONObject("relay");
            if (relayObj != null) {
                relayHost = relayObj.optString("host", "");
                relayPort = relayObj.optInt("port", 0);
            }

            // Store QR relay/network info so saveConfig() can persist it
            qrRelayHost = relayHost;
            qrRelayPort = String.valueOf(relayPort);
            qrExternalHost = externalHost;
            if (engines.length() > 0) {
                JSONObject firstEngine = engines.getJSONObject(0);
                qrRelaySession = firstEngine.optString("relay_session", "");
                qrMdnsName = firstEngine.optString("mdns_name", firstEngine.getString("name"));
            }

            // Populate form from first engine
            if (engines.length() > 0) {
                int port = engines.getJSONObject(0).getInt("port");
                hostView.setText(primaryHost);
                portView.setText(String.valueOf(port));
            }
            tlsView.setChecked(tls);
            authTokenView.setText(token);
            pskView.setText(psk);

            if (!fingerprint.isEmpty()) {
                fingerprintValue.setText(fingerprint);
                fingerprintRow.setVisibility(View.VISIBLE);
            }

            // Smart detection: if method is "token" but no token and no TLS, treat as "none"
            Log.i(TAG, "QR parsed: host=" + host + " tls=" + tls
                    + " authMethod=" + authMethod + " hasToken=" + !token.isEmpty()
                    + " hasPsk=" + !psk.isEmpty() + " singlePort=" + payload.optBoolean("single_port", false)
                    + " relay=" + relayHost + ":" + relayPort
                    + " engines=" + engines.length());
            if ("token".equals(authMethod) && token.isEmpty() && !tls) {
                Log.i(TAG, "QR: overriding authMethod to 'none' (no token, no TLS)");
                authMethod = "none";
            }

            // Set security method
            if ("psk".equals(authMethod)) {
                securitySpinner.setSelection(2);
            } else if ("none".equals(authMethod)) {
                securitySpinner.setSelection(0);
            } else {
                securitySpinner.setSelection(1);
            }

            // Check for single_port mode
            boolean singlePort = payload.optBoolean("single_port", false);

            // Engine import: build EngineInfo list from QR data
            if (engines.length() >= 1) {
                discoveredEngines.clear();
                for (int i = 0; i < engines.length(); i++) {
                    JSONObject e = engines.getJSONObject(i);
                    EngineInfo info = new EngineInfo();
                    info.name = e.getString("name");
                    info.port = e.getInt("port");
                    info.host = primaryHost;
                    info.tls = tls;
                    info.token = token;
                    info.psk = psk;
                    info.authMethod = authMethod;
                    info.fingerprint = fingerprint;
                    info.externalHost = externalHost;
                    info.relayHost = relayHost;
                    info.relayPort = relayPort;
                    info.relaySessionId = e.optString("relay_session", "");
                    info.mdnsServiceName = e.optString("mdns_name", e.getString("name"));
                    // In single_port mode, all engines share the same port
                    if (singlePort) {
                        int sharedPort = payload.optInt("port", e.getInt("port"));
                        info.port = sharedPort;
                        info.selectedEngine = info.name;
                    }
                    discoveredEngines.add(info);
                }
                if (engines.length() > 1) {
                    showMultiEngineDialog();
                } else {
                    // Single engine: install directly and auto-activate
                    configureAllEngines();
                }
            }

            // Hide fetch engines button when QR already provided engine info
            if (engines.length() > 0 && fetchEnginesButton != null) {
                fetchEnginesButton.setVisibility(View.GONE);
            }

            String msg = String.format(getString(R.string.qr_engines_found),
                    engines.length(), host);
            DroidFishApp.toast(msg, Toast.LENGTH_SHORT);

        } catch (Exception e) {
            DroidFishApp.toast(getString(R.string.qr_invalid_payload), Toast.LENGTH_SHORT);
        }
    }

    // ---------------------------------------------------------------
    // mDNS Discovery
    // ---------------------------------------------------------------

    private void startDiscovery() {
        discoverButton.setEnabled(false);
        discoverButton.setText(R.string.discovering_servers);

        NetworkDiscovery discovery = new NetworkDiscovery(this);
        discovery.startDiscovery(new NetworkDiscovery.DiscoveryListener() {
            @Override
            public void onEngineFound(NetworkDiscovery.DiscoveredEngine engine) {}
            @Override
            public void onEngineRemoved(String serviceName) {}
            @Override
            public void onDiscoveryError(String message) {
                discoverButton.setEnabled(true);
                discoverButton.setText(R.string.discover_servers);
                DroidFishApp.toast(message, Toast.LENGTH_SHORT);
            }
        });

        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            discovery.stopDiscovery();
            discoverButton.setEnabled(true);
            discoverButton.setText(R.string.discover_servers);

            List<NetworkDiscovery.DiscoveredEngine> found = discovery.getDiscoveredEngines();
            if (found.isEmpty()) {
                DroidFishApp.toast(getString(R.string.no_servers_found), Toast.LENGTH_SHORT);
            } else if (found.size() == 1) {
                NetworkDiscovery.DiscoveredEngine engine = found.get(0);
                hostView.setText(engine.host);
                portView.setText(String.valueOf(engine.port));
                tlsView.setChecked(engine.tls);
            } else {
                showDiscoveredEngineDialog(found);
            }
        }, 3000);
    }

    private void showDiscoveredEngineDialog(List<NetworkDiscovery.DiscoveredEngine> engines) {
        String[] items = new String[engines.size()];
        for (int i = 0; i < engines.size(); i++) {
            items[i] = engines.get(i).toString();
        }
        new AlertDialog.Builder(this)
            .setTitle(R.string.select_discovered_engine)
            .setItems(items, (dialog, which) -> {
                NetworkDiscovery.DiscoveredEngine engine = engines.get(which);
                hostView.setText(engine.host);
                portView.setText(String.valueOf(engine.port));
                tlsView.setChecked(engine.tls);
            })
            .setNegativeButton(R.string.cancel, null)
            .show();
    }

    // ---------------------------------------------------------------
    // Multi-engine (C2)
    // ---------------------------------------------------------------

    private void showMultiEngineDialog() {
        String[] items = new String[discoveredEngines.size()];
        for (int i = 0; i < discoveredEngines.size(); i++) {
            items[i] = discoveredEngines.get(i).toString();
        }

        new AlertDialog.Builder(this)
            .setTitle(R.string.net_config_select_engines)
            .setItems(items, (dialog, which) -> {
                EngineInfo info = discoveredEngines.get(which);
                portView.setText(String.valueOf(info.port));
            })
            .setNeutralButton(R.string.net_config_configure_all, (dialog, which) -> {
                configureAllEngines();
            })
            .setNegativeButton(R.string.cancel, null)
            .show();
    }

    private void configureAllEngines() {
        if (configPath == null) return;

        String baseDir = new File(configPath).getParent();
        if (baseDir == null) baseDir = Environment.getExternalStorageDirectory()
                + File.separator + "DroidFish" + File.separator + "uci";

        int count = 0;
        for (EngineInfo info : discoveredEngines) {
            String path = baseDir + File.separator + info.name;
            Log.i(TAG, "configureAllEngines: writing " + info.name
                    + " auth=" + info.authMethod + " hasToken=" + (info.token != null && !info.token.isEmpty())
                    + " engine=" + info.selectedEngine
                    + " relay=" + info.relayHost + ":" + info.relayPort
                    + " session=" + (info.relaySessionId != null ? info.relaySessionId.length() + "c" : "null"));
            try (FileWriter fw = new FileWriter(new File(path), false)) {
                fw.write("NETE\n");
                fw.write(info.host + "\n");
                fw.write(info.port + "\n");
                fw.write((info.tls ? "tls" : "notls") + "\n");
                fw.write(info.token + "\n");
                fw.write(info.fingerprint + "\n");
                fw.write(info.authMethod + "\n");
                fw.write(info.psk + "\n");
                fw.write(info.relayHost + "\n");
                fw.write(info.relayPort + "\n");
                fw.write(info.relaySessionId + "\n");
                fw.write(info.externalHost + "\n");
                fw.write(info.mdnsServiceName + "\n");
                fw.write(info.selectedEngine + "\n");
                count++;
            } catch (IOException e) {
                Log.e(TAG, "Failed to write config for " + info.name, e);
            }
        }

        DroidFishApp.toast(String.format(getString(R.string.net_config_engines_added), count),
                Toast.LENGTH_SHORT);

        // Clean up the original config file if it's not one of the new engine files
        // (e.g., a generic "Network Server" placeholder that was opened for QR scanning)
        if (configPath != null) {
            File configFile = new File(configPath);
            boolean isNewEngine = false;
            for (EngineInfo ei : discoveredEngines) {
                if (configFile.getName().equals(ei.name)) {
                    isNewEngine = true;
                    break;
                }
            }
            if (!isNewEngine && configFile.exists()) {
                configFile.delete();
                Log.i(TAG, "Cleaned up placeholder config: " + configFile.getName());
            }
        }

        // Auto-activate: set result so DroidFish switches to the first imported engine
        if (!discoveredEngines.isEmpty()) {
            String firstPath = baseDir + File.separator + discoveredEngines.get(0).name;
            Intent resultIntent = new Intent();
            resultIntent.putExtra(EXTRA_ACTIVATE_ENGINE, firstPath);
            setResult(RESULT_OK, resultIntent);
            finish();
        }
    }

    // ---------------------------------------------------------------
    // Fetch engine list from server (single-port mode)
    // ---------------------------------------------------------------

    private void fetchEngineList() {
        String host = hostView.getText().toString().trim();
        String portStr = portView.getText().toString().trim();
        boolean useTLS = tlsView.isChecked();
        String token = authTokenView.getText().toString().trim();
        String psk = pskView.getText().toString().trim();
        int secIdx = securitySpinner.getSelectedItemPosition();

        if (host.isEmpty() || portStr.isEmpty()) {
            DroidFishApp.toast(getString(R.string.network_engine_config_error), Toast.LENGTH_SHORT);
            return;
        }

        int port;
        try {
            port = Integer.parseInt(portStr);
        } catch (NumberFormatException e) {
            DroidFishApp.toast(getString(R.string.invalid_network_port), Toast.LENGTH_SHORT);
            return;
        }

        fetchEnginesButton.setEnabled(false);

        new Thread(() -> {
            try {
                Socket socket;
                if (useTLS) {
                    socket = createTestTLSSocket(host, port);
                } else {
                    socket = new Socket();
                    socket.connect(new InetSocketAddress(host, port), CONNECT_TIMEOUT_MS);
                }
                socket.setSoTimeout(CONNECT_TIMEOUT_MS);

                BufferedReader in = new BufferedReader(
                        new InputStreamReader(socket.getInputStream()));
                OutputStream out = socket.getOutputStream();

                // Auth handshake (reuse test connection logic)
                if (secIdx == 1 && !token.isEmpty()) {
                    String line = in.readLine();
                    if (line != null && line.startsWith("AUTH_REQUIRED")) {
                        out.write(("AUTH " + token + "\n").getBytes());
                        out.flush();
                        String resp = in.readLine();
                        if (resp == null || !"AUTH_OK".equals(resp.trim())) {
                            socket.close();
                            runOnUiThread(() -> {
                                fetchEnginesButton.setEnabled(true);
                                DroidFishApp.toast(getString(R.string.net_config_test_auth_failed),
                                        Toast.LENGTH_SHORT);
                            });
                            return;
                        }
                    }
                } else if (secIdx == 2 && !psk.isEmpty()) {
                    String line = in.readLine();
                    if (line != null && line.startsWith("AUTH_REQUIRED")) {
                        out.write(("PSK_AUTH " + psk + "\n").getBytes());
                        out.flush();
                        String resp = in.readLine();
                        if (resp == null || !"AUTH_OK".equals(resp.trim())) {
                            socket.close();
                            runOnUiThread(() -> {
                                fetchEnginesButton.setEnabled(true);
                                DroidFishApp.toast(getString(R.string.net_config_test_auth_failed),
                                        Toast.LENGTH_SHORT);
                            });
                            return;
                        }
                    }
                }

                // Send ENGINE_LIST
                out.write("ENGINE_LIST\n".getBytes());
                out.flush();

                List<String> engines = new ArrayList<>();
                String line;
                long startTime = System.currentTimeMillis();
                while ((line = in.readLine()) != null) {
                    String trimmed = line.trim();
                    if ("ENGINES_END".equals(trimmed)) {
                        break;
                    }
                    if (trimmed.startsWith("ENGINE ")) {
                        engines.add(trimmed.substring(7));
                    }
                    // Timeout safety
                    if (System.currentTimeMillis() - startTime > CONNECT_TIMEOUT_MS) {
                        break;
                    }
                }

                // Send quit
                out.write("quit\n".getBytes());
                out.flush();
                socket.close();

                if (engines.isEmpty()) {
                    runOnUiThread(() -> {
                        fetchEnginesButton.setEnabled(true);
                        DroidFishApp.toast(getString(R.string.no_engine_selection),
                                Toast.LENGTH_SHORT);
                    });
                    return;
                }

                final String[] engineArray = engines.toArray(new String[0]);
                runOnUiThread(() -> {
                    fetchEnginesButton.setEnabled(true);
                    new AlertDialog.Builder(NetworkEngineConfig.this)
                        .setTitle(R.string.select_server_engine)
                        .setItems(engineArray, (dialog, which) -> {
                            selectedEngineName = engineArray[which];
                            selectedEngineLabel.setText(String.format(
                                    getString(R.string.server_engine_selected),
                                    selectedEngineName));
                            selectedEngineLabel.setVisibility(View.VISIBLE);
                        })
                        .setNegativeButton(R.string.cancel, null)
                        .show();
                });

            } catch (Exception e) {
                Log.w(TAG, "Failed to fetch engine list", e);
                runOnUiThread(() -> {
                    fetchEnginesButton.setEnabled(true);
                    DroidFishApp.toast(getString(R.string.no_engine_selection),
                            Toast.LENGTH_SHORT);
                });
            }
        }).start();
    }

    // ---------------------------------------------------------------
    // Connection test (C3)
    // ---------------------------------------------------------------

    private void testConnection() {
        String host = hostView.getText().toString().trim();
        String portStr = portView.getText().toString().trim();
        boolean useTLS = tlsView.isChecked();
        String token = authTokenView.getText().toString().trim();
        String psk = pskView.getText().toString().trim();
        int secIdx = securitySpinner.getSelectedItemPosition();

        if (host.isEmpty() || portStr.isEmpty()) {
            showTestResult(getString(R.string.network_engine_config_error), false);
            return;
        }

        int port;
        try {
            port = Integer.parseInt(portStr);
        } catch (NumberFormatException e) {
            showTestResult(getString(R.string.invalid_network_port), false);
            return;
        }

        testButton.setEnabled(false);
        testProgress.setVisibility(View.VISIBLE);
        testResult.setVisibility(View.GONE);

        new Thread(() -> {
            long startTime = System.currentTimeMillis();
            String resultMsg;
            boolean success = false;

            try {
                Socket socket;
                if (useTLS) {
                    socket = createTestTLSSocket(host, port);
                } else {
                    socket = new Socket();
                    socket.connect(new InetSocketAddress(host, port), CONNECT_TIMEOUT_MS);
                }
                socket.setSoTimeout(CONNECT_TIMEOUT_MS);

                BufferedReader in = new BufferedReader(
                        new InputStreamReader(socket.getInputStream()));
                OutputStream out = socket.getOutputStream();

                // Auth handshake
                if (secIdx == 1 && !token.isEmpty()) {
                    // Token auth
                    String line = in.readLine();
                    if (line != null && line.startsWith("AUTH_REQUIRED")) {
                        out.write(("AUTH " + token + "\n").getBytes());
                        out.flush();
                        String resp = in.readLine();
                        if (resp == null || !"AUTH_OK".equals(resp.trim())) {
                            socket.close();
                            resultMsg = getString(R.string.net_config_test_auth_failed);
                            showTestResultOnUi(resultMsg, false);
                            return;
                        }
                    }
                } else if (secIdx == 2 && !psk.isEmpty()) {
                    // PSK auth
                    String line = in.readLine();
                    if (line != null && line.startsWith("AUTH_REQUIRED")) {
                        out.write(("PSK_AUTH " + psk + "\n").getBytes());
                        out.flush();
                        String resp = in.readLine();
                        if (resp == null || !"AUTH_OK".equals(resp.trim())) {
                            socket.close();
                            resultMsg = getString(R.string.net_config_test_auth_failed);
                            showTestResultOnUi(resultMsg, false);
                            return;
                        }
                    }
                }

                // Send UCI and wait for response
                out.write("uci\n".getBytes());
                out.flush();

                String engineName = null;
                String line;
                while ((line = in.readLine()) != null) {
                    if (line.startsWith("id name ")) {
                        engineName = line.substring(8).trim();
                    }
                    if ("uciok".equals(line.trim())) {
                        break;
                    }
                }

                // Send quit
                out.write("quit\n".getBytes());
                out.flush();
                socket.close();

                long elapsed = System.currentTimeMillis() - startTime;

                if (engineName != null) {
                    resultMsg = String.format(getString(R.string.net_config_test_success),
                            engineName, elapsed);
                    success = true;

                    // Extract TLS fingerprint if applicable
                    if (useTLS) {
                        // fingerprint was extracted during createTestTLSSocket
                    }
                } else {
                    resultMsg = getString(R.string.net_config_test_no_uci);
                }

            } catch (UnknownHostException e) {
                resultMsg = String.format(getString(R.string.net_config_test_unknown_host), host);
            } catch (ConnectException e) {
                resultMsg = getString(R.string.net_config_test_refused);
            } catch (SocketTimeoutException e) {
                resultMsg = getString(R.string.net_config_test_timeout) + "\n"
                    + String.format(getString(R.string.net_config_test_timeout_hint), portStr);
            } catch (SSLHandshakeException e) {
                resultMsg = getString(R.string.net_config_test_tls_failed);
            } catch (Exception e) {
                resultMsg = String.format(getString(R.string.net_config_test_error),
                        e.getMessage());
            }

            final String msg = resultMsg;
            final boolean ok = success;
            showTestResultOnUi(msg, ok);
        }).start();
    }

    private Socket createTestTLSSocket(String host, int port) throws Exception {
        SSLContext sslCtx = SSLContext.getInstance("TLS");
        final X509Certificate[] serverCerts = new X509Certificate[1];
        TrustManager[] tm = new TrustManager[]{
            new X509TrustManager() {
                public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
                public void checkClientTrusted(X509Certificate[] c, String t) {}
                public void checkServerTrusted(X509Certificate[] c, String t) {
                    if (c != null && c.length > 0) serverCerts[0] = c[0];
                }
            }
        };
        sslCtx.init(null, tm, new java.security.SecureRandom());
        SSLSocketFactory factory = sslCtx.getSocketFactory();

        Socket plain = new Socket();
        plain.connect(new InetSocketAddress(host, port), CONNECT_TIMEOUT_MS);
        SSLSocket ssl = (SSLSocket) factory.createSocket(plain, host, port, true);
        ssl.setEnabledProtocols(new String[]{"TLSv1.2", "TLSv1.3"});
        ssl.startHandshake();

        // Extract fingerprint
        if (serverCerts[0] != null) {
            try {
                byte[] der = serverCerts[0].getEncoded();
                MessageDigest md = MessageDigest.getInstance("SHA-256");
                byte[] digest = md.digest(der);
                StringBuilder fp = new StringBuilder();
                for (int i = 0; i < digest.length; i++) {
                    if (i > 0) fp.append(":");
                    fp.append(String.format("%02x", digest[i]));
                }
                final String fingerprint = fp.toString();
                runOnUiThread(() -> {
                    fingerprintValue.setText(fingerprint);
                    fingerprintRow.setVisibility(View.VISIBLE);
                });
            } catch (Exception e) {
                Log.w(TAG, "Could not extract cert fingerprint", e);
            }
        }

        return ssl;
    }

    private void showTestResultOnUi(String msg, boolean success) {
        runOnUiThread(() -> showTestResult(msg, success));
    }

    private void showTestResult(String msg, boolean success) {
        testButton.setEnabled(true);
        testProgress.setVisibility(View.GONE);
        testResult.setVisibility(View.VISIBLE);
        testResult.setText(msg);
        testResult.setTextColor(success ? Color.parseColor("#2E7D32") : Color.parseColor("#D32F2F"));
    }
}

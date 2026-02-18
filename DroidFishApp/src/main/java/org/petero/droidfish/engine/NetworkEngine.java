/*
    DroidFish - An Android chess program.
    Copyright (C) 2012-2014  Peter Österlund, peterosterlund2@gmail.com

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
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.ConnectException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.security.KeyManagementException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

import org.petero.droidfish.DroidFishApp;
import org.petero.droidfish.EngineOptions;
import org.petero.droidfish.FileUtil;
import org.petero.droidfish.R;

import android.content.Context;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.util.Log;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Engine running on a different computer. */
public class NetworkEngine extends UCIEngineBase {
    private static final String TAG = "NetworkEngine";

    protected final Context context;
    private final Report report;

    private String fileName;
    private String networkID;
    private Socket socket;
    private Thread startupThread;
    private Thread stdInThread;
    private Thread stdOutThread;
    private final LocalPipe guiToEngine;
    private final LocalPipe engineToGui;
    private volatile boolean startedOk;
    private volatile boolean isRunning;
    private volatile boolean isError;
    private volatile boolean authNegotiationDone;  // true after auth + engine negotiation complete

    // Config read from file
    private String host;
    private int portNr;
    private boolean useTLS;
    private String authToken;
    private String certFingerprint;
    private String authMethod;  // "none", "token", "psk"
    private String pskKey;

    /** Result of mDNS resolution: host IP and port. */
    private static class MdnsResult {
        final String host;
        final int port;
        MdnsResult(String host, int port) {
            this.host = host;
            this.port = port;
        }
    }

    // Extended connection endpoints (lines 8-13 of NETE file)
    private String relayHost = "";
    private int relayPort = 0;
    private String relaySessionId = "";
    private String externalHost = "";
    private String mdnsServiceName = "";
    private String selectedEngine = "";

    // File logger for connection debugging (writes to DroidFish/logs/network.log)
    private final NetworkFileLogger fileLog = NetworkFileLogger.getInstance();

    // Reconnection support
    private static final int MAX_RECONNECT_ATTEMPTS = 5;
    private static final long INITIAL_BACKOFF_MS = 1000;
    private static final long MAX_BACKOFF_MS = 30000;
    private static final int CONNECT_TIMEOUT_MS = 15000;
    private static final int STARTUP_TIMEOUT_MS = 10000;
    private static final int LAN_TIMEOUT_MS = 2000;
    private static final int UPNP_TIMEOUT_MS = 5000;
    private static final int RELAY_TIMEOUT_MS = 10000;
    private static final long MDNS_TIMEOUT_MS = 1500;
    private String lastPosition;
    private String lastGo;
    private volatile boolean shutdownRequested;

    public NetworkEngine(String engine, EngineOptions engineOptions, Report report) {
        context = DroidFishApp.getContext();
        this.report = report;
        fileName = engine;
        networkID = engineOptions.networkID;
        startupThread = null;
        stdInThread = null;
        guiToEngine = new LocalPipe();
        engineToGui = new LocalPipe();
        startedOk = false;
        isRunning = false;
        isError = false;
        shutdownRequested = false;
        authNegotiationDone = false;
        lastPosition = null;
        lastGo = null;

        // Parse config file
        parseConfig();
    }

    /** Parse the network engine config file (NETE format).
     *  Line 0: "NETE"
     *  Line 1: hostname (LAN IP)
     *  Line 2: port
     *  Line 3: "tls" or "notls" (optional, default notls)
     *  Line 4: auth token (optional, default empty = no auth)
     *  Line 5: cert fingerprint (optional, default empty = no pinning)
     *  Line 6: auth method (optional: none/token/psk, default token)
     *  Line 7: PSK key (optional, default empty)
     *  Line 8: relay host (optional, default empty)
     *  Line 9: relay port (optional, default 0)
     *  Line 10: relay session ID (optional, default empty)
     *  Line 11: external host / UPnP IP (optional, default empty)
     *  Line 12: mDNS service name (optional, default empty)
     *  Line 13: selected remote engine (optional, default empty = use default)
     */
    private void parseConfig() {
        host = null;
        portNr = 0;
        useTLS = false;
        authToken = "";
        certFingerprint = "";
        authMethod = "token";
        pskKey = "";
        relayHost = "";
        relayPort = 0;
        relaySessionId = "";
        externalHost = "";
        selectedEngine = "";

        if (!EngineUtil.isNetEngine(fileName))
            return;

        try {
            String[] lines = FileUtil.readFile(fileName);
            if (lines.length >= 3) {
                host = lines[1];
                portNr = Integer.parseInt(lines[2]);
            }
            if (lines.length >= 4) {
                useTLS = "tls".equalsIgnoreCase(lines[3].trim());
            }
            if (lines.length >= 5) {
                authToken = lines[4].trim();
            }
            if (lines.length >= 6) {
                certFingerprint = lines[5].trim();
            }
            if (lines.length >= 7) {
                authMethod = lines[6].trim();
                if (authMethod.isEmpty()) authMethod = "token";
            }
            if (lines.length >= 8) {
                pskKey = lines[7].trim();
            }
            if (lines.length >= 9) {
                relayHost = lines[8].trim();
            }
            if (lines.length >= 10) {
                try {
                    relayPort = Integer.parseInt(lines[9].trim());
                } catch (NumberFormatException ignore) {}
            }
            if (lines.length >= 11) {
                relaySessionId = lines[10].trim();
            }
            if (lines.length >= 12) {
                externalHost = lines[11].trim();
            }
            if (lines.length >= 13) {
                mdnsServiceName = lines[12].trim();
            }
            if (lines.length >= 14) {
                selectedEngine = lines[13].trim();
            }
        } catch (IOException | NumberFormatException e) {
            Log.e(TAG, "Failed to parse network engine config", e);
            fileLog.e(TAG, "Failed to parse network engine config", e);
        }

        // Diagnostic: log parsed auth and connection fields
        fileLog.i(TAG, "parseConfig: file=" + (fileName != null ? new File(fileName).getName() : "null")
                + " authMethod=" + authMethod
                + " hasToken=" + !authToken.isEmpty()
                + " hasPsk=" + (pskKey != null && !pskKey.isEmpty())
                + " selectedEngine=" + selectedEngine
                + " relay=" + relayHost + ":" + relayPort
                + " session=" + (relaySessionId != null ? relaySessionId.length() + "chars" : "null"));
    }

    /** Create socket connection to remote server (primary endpoint). */
    private synchronized Socket createSocket() throws IOException {
        return createSocketTo(host, portNr, CONNECT_TIMEOUT_MS);
    }

    /** Create socket connection to a specific host:port with timeout. */
    private Socket createSocketTo(String targetHost, int targetPort, int timeout) throws IOException {
        if (targetHost == null || targetHost.isEmpty() || targetPort <= 0) {
            throw new IOException(context.getString(R.string.network_engine_config_error));
        }

        Socket sock;
        if (useTLS) {
            sock = createTLSSocketTo(targetHost, targetPort, timeout);
        } else {
            sock = new Socket();
            sock.connect(new InetSocketAddress(targetHost, targetPort), timeout);
        }
        sock.setTcpNoDelay(true);
        return sock;
    }

    /** Create a TLS-wrapped socket with optional certificate pinning.
     *  When certFingerprint is non-empty, validates the server cert's SHA-256
     *  fingerprint matches the configured value.
     */
    private Socket createTLSSocket() throws IOException {
        return createTLSSocketTo(host, portNr, CONNECT_TIMEOUT_MS);
    }

    /** Create a TLS-wrapped socket to a specific host:port. */
    private Socket createTLSSocketTo(String targetHost, int targetPort, int timeout) throws IOException {
        try {
            SSLContext sslCtx = SSLContext.getInstance("TLS");
            final String expectedFp = certFingerprint;
            TrustManager[] trustManagers = new TrustManager[]{
                new X509TrustManager() {
                    public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
                    public void checkClientTrusted(X509Certificate[] certs, String authType) {}
                    public void checkServerTrusted(X509Certificate[] certs, String authType)
                            throws CertificateException {
                        if (expectedFp != null && !expectedFp.isEmpty() && certs != null && certs.length > 0) {
                            String actualFp = getCertFingerprint(certs[0]);
                            if (!expectedFp.equalsIgnoreCase(actualFp)) {
                                throw new CertificateException("Certificate fingerprint mismatch");
                            }
                            Log.i(TAG, "Certificate fingerprint verified");
                        }
                    }
                }
            };
            sslCtx.init(null, trustManagers, new java.security.SecureRandom());
            SSLSocketFactory factory = sslCtx.getSocketFactory();

            Socket plainSocket = new Socket();
            plainSocket.connect(new InetSocketAddress(targetHost, targetPort), timeout);

            SSLSocket sslSocket = (SSLSocket) factory.createSocket(
                plainSocket, targetHost, targetPort, true
            );
            sslSocket.setEnabledProtocols(new String[]{"TLSv1.2", "TLSv1.3"});
            sslSocket.startHandshake();
            Log.i(TAG, "TLS handshake completed with " + targetHost + ":" + targetPort);
            fileLog.i(TAG, "TLS handshake completed with " + targetHost + ":" + targetPort);
            return sslSocket;
        } catch (NoSuchAlgorithmException | KeyManagementException e) {
            throw new IOException("TLS initialization failed: " + e.getMessage(), e);
        }
    }

    /** Compute SHA-256 fingerprint of an X509 certificate. */
    private static String getCertFingerprint(X509Certificate cert) {
        try {
            byte[] der = cert.getEncoded();
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] digest = md.digest(der);
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < digest.length; i++) {
                if (i > 0) sb.append(":");
                sb.append(String.format("%02x", digest[i]));
            }
            return sb.toString();
        } catch (Exception e) {
            return "";
        }
    }

    /** Perform authentication handshake supporting token and PSK methods.
     *  Protocol: server sends AUTH_REQUIRED [methods], client responds
     *  AUTH token or PSK_AUTH key, server sends AUTH_OK or AUTH_FAIL.
     */
    private boolean authenticate(BufferedReader in, OutputStream out) throws IOException {
        // Determine if we have credentials
        boolean hasToken = !authToken.isEmpty();
        boolean hasPsk = pskKey != null && !pskKey.isEmpty();

        if ("none".equals(authMethod) || (!hasToken && !hasPsk)) {
            fileLog.i(TAG, "Auth: skipping (method=" + authMethod
                    + " hasToken=" + hasToken + " hasPsk=" + hasPsk + ")");
            return true;
        }

        fileLog.i(TAG, "Auth: attempting (method=" + authMethod
                + " hasToken=" + hasToken + " hasPsk=" + hasPsk + ")");

        // Read server greeting (AUTH_REQUIRED or first UCI response)
        String line = in.readLine();
        if (line == null)
            return false;

        String trimmed = line.trim();
        if (trimmed.startsWith("AUTH_REQUIRED")) {
            // Send appropriate auth command based on configured method
            String authCmd;
            if ("psk".equals(authMethod) && hasPsk) {
                authCmd = "PSK_AUTH " + pskKey + "\n";
            } else if (hasToken) {
                authCmd = "AUTH " + authToken + "\n";
            } else {
                Log.w(TAG, "Server requires auth but no credentials configured");
                fileLog.w(TAG, "Server requires auth but no credentials configured");
                return false;
            }
            out.write(authCmd.getBytes());
            out.flush();

            String response = in.readLine();
            if (response == null)
                return false;

            if ("AUTH_OK".equals(response.trim())) {
                Log.i(TAG, "Authentication succeeded");
                fileLog.i(TAG, "Authentication succeeded (method: " + authMethod + ")");
                return true;
            } else {
                Log.w(TAG, "Authentication failed: " + response);
                fileLog.w(TAG, "Authentication failed: " + response);
                return false;
            }
        } else {
            // Server didn't require auth - push the line back through engineToGui
            engineToGui.addLine(line);
            return true;
        }
    }

    /** Negotiate engine selection on a single-port multiplexed server.
     *  If selectedEngine is set, sends ENGINE_LIST, reads available engines,
     *  then sends SELECT_ENGINE. Skips negotiation if selectedEngine is empty.
     *  Returns true on success (or skip), false on error.
     */
    private boolean negotiateEngine(BufferedReader in, OutputStream out) throws IOException {
        if (selectedEngine == null || selectedEngine.isEmpty()) {
            fileLog.i(TAG, "Engine negotiation: skipping (no selectedEngine)");
            return true;  // No engine selection needed (legacy per-port mode)
        }
        fileLog.i(TAG, "Engine negotiation: requesting '" + selectedEngine + "'");

        // Request engine list
        out.write("ENGINE_LIST\n".getBytes());
        out.flush();

        // Read available engines
        List<String> available = new ArrayList<>();
        String line;
        while ((line = in.readLine()) != null) {
            String trimmed = line.trim();
            if ("ENGINES_END".equals(trimmed)) {
                break;
            }
            if (trimmed.startsWith("ENGINE ")) {
                available.add(trimmed.substring(7));
            }
        }

        if (available.isEmpty()) {
            // Server may not support engine listing (old server)
            Log.w(TAG, "Server did not return any engines - may not support ENGINE_LIST");
            fileLog.w(TAG, "Engine negotiation: server returned no engines");
            report.reportError(context.getString(R.string.engine_not_available, selectedEngine));
            return false;
        }

        // Check if our desired engine is available
        if (!available.contains(selectedEngine)) {
            Log.w(TAG, "Engine '" + selectedEngine + "' not in server list: " + available);
            fileLog.w(TAG, "Engine '" + selectedEngine + "' not in server list: " + available);
            report.reportError(context.getString(R.string.engine_not_available, selectedEngine));
            return false;
        }

        // Select the engine
        out.write(("SELECT_ENGINE " + selectedEngine + "\n").getBytes());
        out.flush();

        String response = in.readLine();
        if (response == null) {
            return false;
        }
        String trimmedResp = response.trim();
        if ("ENGINE_SELECTED".equals(trimmedResp)) {
            Log.i(TAG, "Engine selected: " + selectedEngine);
            fileLog.i(TAG, "Engine selected: " + selectedEngine);
            return true;
        } else {
            Log.w(TAG, "Engine selection failed: " + trimmedResp);
            fileLog.w(TAG, "Engine selection failed: " + trimmedResp);
            report.reportError(context.getString(R.string.engine_not_available, selectedEngine));
            return false;
        }
    }

    /** Attempt to connect with exponential backoff. */
    private Socket connectWithRetry() throws IOException {
        long backoff = INITIAL_BACKOFF_MS;
        IOException lastException = null;

        for (int attempt = 1; attempt <= MAX_RECONNECT_ATTEMPTS; attempt++) {
            if (shutdownRequested)
                throw new IOException("Shutdown requested");

            try {
                Log.i(TAG, "Connection attempt " + attempt + "/" + MAX_RECONNECT_ATTEMPTS
                        + " to " + host + ":" + portNr
                        + (useTLS ? " (TLS)" : ""));
                fileLog.i(TAG, "Connection attempt " + attempt + "/" + MAX_RECONNECT_ATTEMPTS
                        + " to " + host + ":" + portNr + (useTLS ? " (TLS)" : ""));
                return createSocket();
            } catch (IOException e) {
                lastException = e;
                Log.w(TAG, "Connection attempt " + attempt + " failed: " + e.getMessage());
                fileLog.w(TAG, "Connection attempt " + attempt + " failed: " + e.getMessage());
                if (attempt < MAX_RECONNECT_ATTEMPTS) {
                    try {
                        Thread.sleep(backoff);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        throw new IOException("Connection interrupted", ie);
                    }
                    backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
                }
            }
        }
        throw lastException != null ? lastException
                : new IOException("Failed to connect after " + MAX_RECONNECT_ATTEMPTS + " attempts");
    }

    /** Try endpoints in order: LAN -> UPnP external -> relay -> fallback retry.
     *  Returns the first successful socket connection.
     */
    private Socket connectWithStrategy() throws IOException {
        boolean hasExternal = externalHost != null && !externalHost.isEmpty();
        boolean hasRelay = relayHost != null && !relayHost.isEmpty()
                && relaySessionId != null && !relaySessionId.isEmpty()
                && relayPort > 0;
        boolean hasMdns = mdnsServiceName != null && !mdnsServiceName.isEmpty();

        fileLog.i(TAG, "Strategy config: host=" + host + ":" + portNr
                + " external=" + externalHost
                + " relay=" + relayHost + ":" + relayPort + " session=" + relaySessionId
                + " mdns=" + mdnsServiceName + " engine=" + selectedEngine);
        fileLog.i(TAG, "Strategy flags: hasExternal=" + hasExternal
                + " hasRelay=" + hasRelay + " hasMdns=" + hasMdns);

        // If no alternate endpoints, use standard retry logic
        if (!hasExternal && !hasRelay && !hasMdns) {
            fileLog.w(TAG, "No alternate endpoints — falling back to connectWithRetry()");
            return connectWithRetry();
        }

        // Accumulate per-strategy failure reasons for the error message
        List<String> failures = new ArrayList<>();

        // 0. Try mDNS resolution first (discovers current server IP and port)
        if (hasMdns) {
            try {
                MdnsResult mdns = resolveMdns(MDNS_TIMEOUT_MS);
                if (mdns != null) {
                    Log.i(TAG, "Strategy: mDNS resolved " + mdnsServiceName
                            + " to " + mdns.host + ":" + mdns.port);
                    fileLog.i(TAG, "Strategy: mDNS resolved " + mdnsServiceName
                            + " to " + mdns.host + ":" + mdns.port);
                    try {
                        return createSocketTo(mdns.host, mdns.port, LAN_TIMEOUT_MS);
                    } catch (IOException e) {
                        Log.i(TAG, "Strategy: mDNS-resolved host failed: " + e.getMessage());
                        fileLog.w(TAG, "Strategy: mDNS-resolved host failed: " + e.getMessage());
                        failures.add("mDNS(" + mdns.host + "): " + e.getMessage());
                    }
                } else {
                    Log.i(TAG, "Strategy: mDNS resolution timed out");
                    fileLog.i(TAG, "Strategy: mDNS resolution timed out");
                    failures.add("mDNS: timeout");
                }
            } catch (Exception e) {
                Log.i(TAG, "Strategy: mDNS failed: " + e.getMessage());
                fileLog.w(TAG, "Strategy: mDNS failed: " + e.getMessage());
                failures.add("mDNS: " + e.getMessage());
            }
        }

        // 1. Try LAN direct (fast timeout, hardcoded IP)
        try {
            Log.i(TAG, "Strategy: trying LAN " + host + ":" + portNr);
            fileLog.i(TAG, "Strategy: trying LAN " + host + ":" + portNr);
            return createSocketTo(host, portNr, LAN_TIMEOUT_MS);
        } catch (IOException e) {
            Log.i(TAG, "Strategy: LAN failed: " + e.getMessage());
            fileLog.w(TAG, "Strategy: LAN failed: " + e.getMessage());
            failures.add("LAN(" + host + ":" + portNr + "): " + e.getMessage());
        }

        // 2. Try UPnP external IP (skip if same as host — already tried)
        if (hasExternal && !externalHost.equals(host)) {
            try {
                Log.i(TAG, "Strategy: trying UPnP " + externalHost + ":" + portNr);
                fileLog.i(TAG, "Strategy: trying UPnP " + externalHost + ":" + portNr);
                return createSocketTo(externalHost, portNr, UPNP_TIMEOUT_MS);
            } catch (IOException e) {
                Log.i(TAG, "Strategy: UPnP failed: " + e.getMessage());
                fileLog.w(TAG, "Strategy: UPnP failed: " + e.getMessage());
                failures.add("UPnP(" + externalHost + "): " + e.getMessage());
            }
        }

        // 3. Try relay
        if (hasRelay) {
            try {
                Log.i(TAG, "Strategy: trying relay " + relayHost + ":" + relayPort);
                fileLog.i(TAG, "Strategy: trying relay " + relayHost + ":" + relayPort);
                return connectViaRelay();
            } catch (IOException e) {
                Log.i(TAG, "Strategy: relay failed: " + e.getMessage());
                fileLog.w(TAG, "Strategy: relay failed: " + e.getMessage());
                failures.add("Relay(" + relayHost + ":" + relayPort + "): " + e.getMessage());
            }
        }

        // 4. Fall back to standard retry on primary host
        //    Skip if relay was available — retrying an unreachable host wastes time.
        if (hasRelay) {
            StringBuilder sb = new StringBuilder("All connection strategies failed:\n");
            for (String f : failures) {
                sb.append("  - ").append(f).append("\n");
            }
            throw new IOException(sb.toString().trim());
        }
        Log.i(TAG, "Strategy: all fast paths failed, falling back to retry");
        fileLog.i(TAG, "Strategy: all fast paths failed, falling back to retry");
        return connectWithRetry();
    }

    /** Connect via the relay server.
     *  Opens a plain TCP socket to the relay, sends SESSION command,
     *  and waits for CONNECTED response. Auth happens on top of this socket.
     *  Relay connections are always plain TCP (no TLS to relay itself).
     *
     *  IMPORTANT: reads the relay response using raw byte reads (not BufferedReader)
     *  to avoid buffering ahead and consuming the server's AUTH_REQUIRED line.
     */
    private Socket connectViaRelay() throws IOException {
        Socket relaySock = new Socket();
        relaySock.connect(new InetSocketAddress(relayHost, relayPort), RELAY_TIMEOUT_MS);
        relaySock.setTcpNoDelay(true);

        try {
            OutputStream out = relaySock.getOutputStream();
            String cmd = "SESSION " + relaySessionId + " client\n";
            out.write(cmd.getBytes());
            out.flush();

            // Read relay response byte-by-byte to avoid buffering past the
            // newline. A BufferedReader would consume AUTH_REQUIRED from the
            // server into its internal buffer, which is then lost when
            // startProcess() creates a new reader on the same socket.
            InputStream rawIn = relaySock.getInputStream();
            StringBuilder sb = new StringBuilder(64);
            int b;
            while ((b = rawIn.read()) != -1) {
                if (b == '\n') break;
                if (b != '\r') sb.append((char) b);
            }
            if (b == -1 && sb.length() == 0) {
                throw new IOException("Relay closed connection");
            }
            String response = sb.toString().trim();
            if ("CONNECTED".equals(response)) {
                Log.i(TAG, "Relay: connected via " + relayHost + ":" + relayPort);
                fileLog.i(TAG, "Relay: connected via " + relayHost + ":" + relayPort);
                return relaySock;
            } else if (response.startsWith("ERROR")) {
                throw new IOException("Relay error: " + response);
            } else {
                throw new IOException("Unexpected relay response: " + response);
            }
        } catch (IOException e) {
            try { relaySock.close(); } catch (IOException ignore) {}
            throw e;
        }
    }

    /** Resolve the server's current IP and port via mDNS/NSD discovery.
     *  Discovers _chess-uci._tcp services on the local network and matches
     *  by service name. Returns the resolved host and port, or null on timeout.
     *
     *  @param timeoutMs maximum time to wait for resolution
     *  @return MdnsResult with host and port, or null if not found within timeout
     */
    private MdnsResult resolveMdns(long timeoutMs) {
        final NsdManager nsdManager = (NsdManager) context.getSystemService(Context.NSD_SERVICE);
        if (nsdManager == null) {
            Log.w(TAG, "NsdManager not available");
            return null;
        }

        final String[] resolvedHost = {null};
        final int[] resolvedPort = {0};
        final CountDownLatch latch = new CountDownLatch(1);
        final String serviceType = "_chess-uci._tcp.";
        final String targetName = mdnsServiceName;

        final NsdManager.ResolveListener resolveListener = new NsdManager.ResolveListener() {
            @Override
            public void onResolveFailed(NsdServiceInfo serviceInfo, int errorCode) {
                Log.w(TAG, "mDNS resolve failed: " + errorCode);
                latch.countDown();
            }

            @Override
            public void onServiceResolved(NsdServiceInfo serviceInfo) {
                if (serviceInfo.getHost() != null) {
                    resolvedHost[0] = serviceInfo.getHost().getHostAddress();
                    resolvedPort[0] = serviceInfo.getPort();
                    Log.d(TAG, "mDNS resolved: " + serviceInfo.getServiceName()
                            + " -> " + resolvedHost[0] + ":" + resolvedPort[0]);
                }
                latch.countDown();
            }
        };

        final NsdManager.DiscoveryListener[] listenerHolder = {null};
        NsdManager.DiscoveryListener discoveryListener = new NsdManager.DiscoveryListener() {
            @Override
            public void onDiscoveryStarted(String regType) {
                Log.d(TAG, "mDNS discovery started");
            }

            @Override
            public void onServiceFound(NsdServiceInfo service) {
                Log.d(TAG, "mDNS found: " + service.getServiceName());
                if (service.getServiceName().equals(targetName)) {
                    nsdManager.resolveService(service, resolveListener);
                }
            }

            @Override
            public void onServiceLost(NsdServiceInfo service) {}

            @Override
            public void onDiscoveryStopped(String serviceType) {
                Log.d(TAG, "mDNS discovery stopped");
            }

            @Override
            public void onStartDiscoveryFailed(String serviceType, int errorCode) {
                Log.w(TAG, "mDNS start discovery failed: " + errorCode);
                latch.countDown();
            }

            @Override
            public void onStopDiscoveryFailed(String serviceType, int errorCode) {
                Log.w(TAG, "mDNS stop discovery failed: " + errorCode);
            }
        };
        listenerHolder[0] = discoveryListener;

        try {
            nsdManager.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, discoveryListener);
            latch.await(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (IllegalArgumentException e) {
            Log.w(TAG, "mDNS discovery error: " + e.getMessage());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } finally {
            try {
                nsdManager.stopServiceDiscovery(discoveryListener);
            } catch (IllegalArgumentException ignore) {
                // Listener not registered or already stopped
            }
        }

        if (resolvedHost[0] != null && resolvedPort[0] > 0) {
            return new MdnsResult(resolvedHost[0], resolvedPort[0]);
        }
        return null;
    }

    @Override
    protected void startProcess() {
        // Start thread to check for startup error
        startupThread = new Thread(() -> {
            try {
                Thread.sleep(STARTUP_TIMEOUT_MS);
            } catch (InterruptedException e) {
                return;
            }
            if (startedOk && isRunning && !isUCI) {
                isError = true;
                report.reportError(context.getString(R.string.uci_protocol_error));
            }
        });
        startupThread.start();

        // Start a thread to read data from engine
        stdInThread = new Thread(() -> {
            fileLog.i(TAG, "=== Connection starting === host=" + host
                    + " port=" + portNr + " tls=" + useTLS
                    + " relay=" + relayHost + ":" + relayPort
                    + " mdns=" + mdnsServiceName
                    + " engine=" + selectedEngine);
            try {
                socket = connectWithStrategy();
                InputStream is = socket.getInputStream();
                OutputStream os = socket.getOutputStream();
                InputStreamReader isr = new InputStreamReader(is);
                BufferedReader br = new BufferedReader(isr, 8192);

                // Authenticate if token is configured
                if (!authenticate(br, os)) {
                    isError = true;
                    report.reportError(context.getString(R.string.auth_failed));
                    return;
                }

                // Engine negotiation (single-port multiplexing)
                if (!negotiateEngine(br, os)) {
                    isError = true;
                    return;
                }

                // Signal write thread that auth/negotiation is complete
                authNegotiationDone = true;
                fileLog.i(TAG, "Auth + negotiation complete, write thread unblocked");

                String line;
                boolean first = true;
                while ((line = br.readLine()) != null) {
                    if (Thread.currentThread().isInterrupted())
                        return;
                    // Detect auth mismatch: server requires auth but client skipped it
                    if (first && line.trim().startsWith("AUTH_REQUIRED")) {
                        fileLog.e(TAG, "Server requires auth but client has authMethod="
                                + authMethod + " — re-scan QR code or check NETE file");
                        isError = true;
                        report.reportError(context.getString(R.string.auth_required_mismatch));
                        return;
                    }
                    synchronized (engineToGui) {
                        engineToGui.addLine(line);
                        if (first) {
                            startedOk = true;
                            isRunning = true;
                            first = false;
                        }
                    }
                }
            } catch (UnknownHostException e) {
                isError = true;
                fileLog.e(TAG, "Unknown host: " + host, e);
                report.reportError(String.format(
                    context.getString(R.string.net_config_test_unknown_host), host));
            } catch (ConnectException e) {
                isError = true;
                fileLog.e(TAG, "Connection refused: " + host + ":" + portNr, e);
                report.reportError(context.getString(R.string.net_config_test_refused));
            } catch (SocketTimeoutException e) {
                isError = true;
                fileLog.e(TAG, "Connection timed out: " + host + ":" + portNr, e);
                String diagInfo = " [relay=" + relayHost + ":" + relayPort
                        + " session=" + (relaySessionId != null ? relaySessionId.length() + "chars" : "null")
                        + " ext=" + externalHost
                        + " mdns=" + mdnsServiceName
                        + " file=" + (fileName != null ? new File(fileName).getName() : "null") + "]";
                report.reportError(context.getString(R.string.net_config_test_timeout) + diagInfo);
            } catch (SSLHandshakeException e) {
                isError = true;
                fileLog.e(TAG, "TLS handshake failed", e);
                String msg = e.getMessage();
                if (msg != null && msg.contains("fingerprint")) {
                    report.reportError(context.getString(R.string.net_config_fingerprint_mismatch));
                } else {
                    report.reportError(context.getString(R.string.net_config_test_tls_failed));
                }
            } catch (IllegalArgumentException e) {
                isError = true;
                fileLog.e(TAG, "Invalid network configuration", e);
                report.reportError(context.getString(R.string.invalid_network_port));
            } catch (IOException e) {
                if (!shutdownRequested) {
                    isError = true;
                    fileLog.e(TAG, "IO error" + (startedOk ? " (engine was running)" : " (during connect)"), e);
                    if (!startedOk) {
                        String detail = e.getMessage();
                        if (detail != null && detail.contains("strategies")) {
                            report.reportError(detail);
                        } else {
                            report.reportError(context.getString(R.string.failed_to_start_engine));
                        }
                    } else {
                        report.reportError(context.getString(R.string.engine_terminated));
                    }
                }
            } catch (SecurityException e) {
                isError = true;
                fileLog.e(TAG, "Security exception", e);
                report.reportError(e.getMessage());
            } finally {
                if (isRunning && !shutdownRequested) {
                    isError = true;
                    isRunning = false;
                    if (!startedOk)
                        report.reportError(context.getString(R.string.failed_to_start_engine));
                    else
                        report.reportError(context.getString(R.string.engine_terminated));
                }
            }
            engineToGui.close();
        });
        stdInThread.start();

        // Start a thread to write data to engine
        stdOutThread = new Thread(() -> {
            try {
                // Wait for auth + engine negotiation to complete before sending
                // any UCI commands.  Without this gate the write thread can race
                // ahead and send "uci" before the read thread has finished the
                // AUTH/SELECT_ENGINE handshake, causing auth failures.
                while (!authNegotiationDone && !shutdownRequested && !isError) {
                    Thread.sleep(50);
                }
                if (socket == null || shutdownRequested || isError)
                    return;

                String line;
                while ((line = guiToEngine.readLine()) != null) {
                    if (Thread.currentThread().isInterrupted())
                        return;

                    // Track position and go commands for potential reconnection
                    if (line.startsWith("position "))
                        lastPosition = line;
                    else if (line.startsWith("go "))
                        lastGo = line;

                    line += "\n";
                    socket.getOutputStream().write(line.getBytes());
                    socket.getOutputStream().flush();
                }
            } catch (IOException e) {
                if (isRunning && !shutdownRequested) {
                    isError = true;
                    report.reportError(e.getMessage());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                if (isRunning && !isError && !shutdownRequested) {
                    isError = true;
                    report.reportError(context.getString(R.string.engine_terminated));
                }
                isRunning = false;
                closeSocket();
            }
        });
        stdOutThread.start();
    }

    /** Close socket safely. */
    private void closeSocket() {
        if (socket != null) {
            try { socket.getOutputStream().write("quit\n".getBytes()); } catch (IOException ignore) {}
            try { socket.close(); } catch (IOException ignore) {}
        }
    }

    private int hashMB = -1;
    private String gaviotaTbPath = "";
    private String syzygyPath = "";
    private boolean optionsInitialized = false;

    @Override
    public void initOptions(EngineOptions engineOptions) {
        super.initOptions(engineOptions);
        hashMB = engineOptions.hashMB;
        setOption("Hash", engineOptions.hashMB);
        syzygyPath = engineOptions.getEngineRtbPath(true);
        setOption("SyzygyPath", syzygyPath);
        gaviotaTbPath = engineOptions.getEngineGtbPath(true);
        setOption("GaviotaTbPath", gaviotaTbPath);
        optionsInitialized = true;
    }

    @Override
    protected File getOptionsFile() {
        return new File(fileName + ".ini");
    }

    @Override
    public boolean optionsOk(EngineOptions engineOptions) {
        if (isError)
            return false;
        if (!optionsInitialized)
            return true;
        if (!networkID.equals(engineOptions.networkID))
            return false;
        if (hashMB != engineOptions.hashMB)
            return false;
        if (hasOption("gaviotatbpath") && !gaviotaTbPath.equals(engineOptions.getEngineGtbPath(true)))
            return false;
        if (hasOption("syzygypath") && !syzygyPath.equals(engineOptions.getEngineRtbPath(true)))
            return false;
        return true;
    }

    @Override
    public String readLineFromEngine(int timeoutMillis) {
        String ret = engineToGui.readLine(timeoutMillis);
        if (ret == null)
            return null;
        if (ret.length() > 0) {
            Log.d(TAG, "Engine -> GUI: " + ret);
        }
        return ret;
    }

    @Override
    public void writeLineToEngine(String data) {
        Log.d(TAG, "GUI -> Engine: " + data);
        guiToEngine.addLine(data);
    }

    @Override
    public void shutDown() {
        fileLog.i(TAG, "=== Connection shutting down ===");
        shutdownRequested = true;
        isRunning = false;
        if (startupThread != null)
            startupThread.interrupt();
        super.shutDown();
        if (stdOutThread != null)
            stdOutThread.interrupt();
        if (stdInThread != null)
            stdInThread.interrupt();
    }
}

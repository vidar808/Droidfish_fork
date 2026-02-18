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

import android.content.Context;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Discovers chess-uci-server instances on the local network via mDNS/DNS-SD.
 *
 * Uses Android's NsdManager to find services of type "_chess-uci._tcp".
 * Each discovered service represents a UCI engine available on the network.
 */
public class NetworkDiscovery {
    private static final String TAG = "NetworkDiscovery";
    private static final String SERVICE_TYPE = "_chess-uci._tcp.";

    private final NsdManager nsdManager;
    private final CopyOnWriteArrayList<DiscoveredEngine> engines = new CopyOnWriteArrayList<>();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private DiscoveryListener listener;
    private NsdManager.DiscoveryListener nsdListener;
    private boolean discovering = false;

    /** Represents a discovered engine on the network. */
    public static class DiscoveredEngine {
        public final String name;
        public final String host;
        public final int port;
        public final boolean tls;
        public final boolean auth;

        public DiscoveredEngine(String name, String host, int port, boolean tls, boolean auth) {
            this.name = name;
            this.host = host;
            this.port = port;
            this.tls = tls;
            this.auth = auth;
        }

        @Override
        public String toString() {
            StringBuilder sb = new StringBuilder();
            sb.append(name).append(" (").append(host).append(":").append(port).append(")");
            if (tls) sb.append(" [TLS]");
            if (auth) sb.append(" [AUTH]");
            return sb.toString();
        }
    }

    /** Callback interface for discovery events. */
    public interface DiscoveryListener {
        void onEngineFound(DiscoveredEngine engine);
        void onEngineRemoved(String serviceName);
        void onDiscoveryError(String message);
    }

    public NetworkDiscovery(Context context) {
        nsdManager = (NsdManager) context.getSystemService(Context.NSD_SERVICE);
    }

    /** Start discovering chess-uci-server services on the local network. */
    public void startDiscovery(DiscoveryListener listener) {
        if (discovering) {
            stopDiscovery();
        }
        this.listener = listener;
        engines.clear();

        nsdListener = new NsdManager.DiscoveryListener() {
            @Override
            public void onDiscoveryStarted(String serviceType) {
                Log.d(TAG, "Discovery started for " + serviceType);
            }

            @Override
            public void onServiceFound(NsdServiceInfo serviceInfo) {
                Log.d(TAG, "Service found: " + serviceInfo.getServiceName());
                // Resolve to get host/port
                nsdManager.resolveService(serviceInfo, new NsdManager.ResolveListener() {
                    @Override
                    public void onResolveFailed(NsdServiceInfo serviceInfo, int errorCode) {
                        Log.w(TAG, "Resolve failed for " + serviceInfo.getServiceName()
                                + " error=" + errorCode);
                    }

                    @Override
                    public void onServiceResolved(NsdServiceInfo info) {
                        String name = info.getServiceName();
                        String host = info.getHost().getHostAddress();
                        int port = info.getPort();

                        // Read TXT record attributes
                        Map<String, byte[]> attrs = info.getAttributes();
                        boolean tls = "true".equals(getAttr(attrs, "tls"));
                        boolean auth = "true".equals(getAttr(attrs, "auth"));

                        DiscoveredEngine engine = new DiscoveredEngine(
                                name, host, port, tls, auth);
                        engines.add(engine);

                        mainHandler.post(() -> {
                            if (NetworkDiscovery.this.listener != null)
                                NetworkDiscovery.this.listener.onEngineFound(engine);
                        });
                    }
                });
            }

            @Override
            public void onServiceLost(NsdServiceInfo serviceInfo) {
                String name = serviceInfo.getServiceName();
                Log.d(TAG, "Service lost: " + name);
                engines.removeIf(e -> e.name.equals(name));
                mainHandler.post(() -> {
                    if (NetworkDiscovery.this.listener != null)
                        NetworkDiscovery.this.listener.onEngineRemoved(name);
                });
            }

            @Override
            public void onDiscoveryStopped(String serviceType) {
                Log.d(TAG, "Discovery stopped for " + serviceType);
            }

            @Override
            public void onStartDiscoveryFailed(String serviceType, int errorCode) {
                Log.e(TAG, "Start discovery failed: error=" + errorCode);
                discovering = false;
                mainHandler.post(() -> {
                    if (NetworkDiscovery.this.listener != null)
                        NetworkDiscovery.this.listener.onDiscoveryError(
                                "Discovery failed (error " + errorCode + ")");
                });
            }

            @Override
            public void onStopDiscoveryFailed(String serviceType, int errorCode) {
                Log.e(TAG, "Stop discovery failed: error=" + errorCode);
            }
        };

        nsdManager.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, nsdListener);
        discovering = true;
    }

    /** Stop discovering services. */
    public void stopDiscovery() {
        if (discovering && nsdListener != null) {
            try {
                nsdManager.stopServiceDiscovery(nsdListener);
            } catch (IllegalArgumentException e) {
                Log.w(TAG, "stopDiscovery: " + e.getMessage());
            }
            discovering = false;
        }
    }

    /** Get all currently discovered engines. */
    public List<DiscoveredEngine> getDiscoveredEngines() {
        return new ArrayList<>(engines);
    }

    /** Check if discovery is currently active. */
    public boolean isDiscovering() {
        return discovering;
    }

    private static String getAttr(Map<String, byte[]> attrs, String key) {
        if (attrs == null) return "";
        byte[] val = attrs.get(key);
        if (val == null) return "";
        return new String(val);
    }
}

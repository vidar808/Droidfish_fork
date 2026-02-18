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

package org.petero.droidfish.book;

import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;
import org.petero.droidfish.book.DroidBook.BookEntry;
import org.petero.droidfish.gamelogic.Move;
import org.petero.droidfish.gamelogic.Position;
import org.petero.droidfish.gamelogic.TextIO;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Opening book backed by the Lichess Opening Explorer API. */
public class LichessExplorerBook implements IOpeningBook {
    private static final String TAG = "LichessExplorerBook";
    private static final String BASE_URL = "https://explorer.lichess.ovh";
    private static final int CACHE_CAPACITY = 128;
    private static final long CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
    private static final long MIN_REQUEST_INTERVAL_MS = 1500;
    private static final long RATE_LIMIT_BACKOFF_MS = 60 * 1000;
    private static final int CONNECT_TIMEOUT_MS = 5000;
    private static final int READ_TIMEOUT_MS = 5000;
    private static final int MAX_MOVES = 12;

    // Options
    private boolean explorerEnabled = false;
    private String database = "masters";
    private String playerName = "";

    // Cache: FEN (without move counters) -> ExplorerResult
    private final Map<String, ExplorerResult> cache;

    // Async fetch
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Set<String> pendingFetches = Collections.synchronizedSet(new HashSet<String>());
    private volatile long lastRequestTimeMs = 0;
    private volatile long rateLimitUntilMs = 0;
    private volatile Runnable onDataReady;

    /** A single move from the explorer response. */
    public static class ExplorerMove {
        public final String uci;
        public final String san;
        public final long white;
        public final long draws;
        public final long black;
        public final int avgRating;

        ExplorerMove(String uci, String san, long white, long draws, long black, int avgRating) {
            this.uci = uci;
            this.san = san;
            this.white = white;
            this.draws = draws;
            this.black = black;
            this.avgRating = avgRating;
        }

        public long totalGames() {
            return white + draws + black;
        }
    }

    /** Cached result for a position. */
    public static class ExplorerResult {
        public final String opening;
        public final long totalWhite;
        public final long totalDraws;
        public final long totalBlack;
        public final ArrayList<ExplorerMove> moves;
        final long fetchTimestamp;

        ExplorerResult(String opening, long totalWhite, long totalDraws, long totalBlack,
                       ArrayList<ExplorerMove> moves) {
            this.opening = opening;
            this.totalWhite = totalWhite;
            this.totalDraws = totalDraws;
            this.totalBlack = totalBlack;
            this.moves = moves;
            this.fetchTimestamp = System.currentTimeMillis();
        }

        public long totalGames() {
            return totalWhite + totalDraws + totalBlack;
        }

        boolean isExpired() {
            return System.currentTimeMillis() - fetchTimestamp > CACHE_TTL_MS;
        }
    }

    @SuppressWarnings("serial")
    public LichessExplorerBook() {
        cache = Collections.synchronizedMap(
            new LinkedHashMap<String, ExplorerResult>(CACHE_CAPACITY + 1, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<String, ExplorerResult> eldest) {
                    return size() > CACHE_CAPACITY;
                }
            }
        );
    }

    /** Set callback invoked (on background thread) when async fetch completes. */
    public void setOnDataReady(Runnable callback) {
        this.onDataReady = callback;
    }

    @Override
    public boolean enabled() {
        return explorerEnabled;
    }

    @Override
    public void setOptions(BookOptions options) {
        this.explorerEnabled = options.lichessExplorerEnabled;
        this.database = options.lichessExplorerDb;
        this.playerName = options.lichessPlayerName;
    }

    /**
     * Return book entries from cache only (non-blocking).
     * If not cached, fires an async fetch and returns null.
     */
    @Override
    public ArrayList<BookEntry> getBookEntries(BookPosInput posInput) {
        if (!explorerEnabled)
            return null;

        Position pos = posInput.getCurrPos();
        String fen = TextIO.toFEN(pos);
        String cacheKey = makeCacheKey(fen);

        ExplorerResult result = cache.get(cacheKey);
        if (result != null && !result.isExpired()) {
            return resultToBookEntries(result, pos);
        }

        // Fire async fetch
        fetchAsync(fen, cacheKey);
        return null;
    }

    /**
     * Return book entries with blocking fetch (for computer search thread).
     * Checks cache first, then does synchronous HTTP with timeout.
     */
    public ArrayList<BookEntry> getBookEntriesBlocking(BookPosInput posInput, int timeoutMs) {
        if (!explorerEnabled)
            return null;

        Position pos = posInput.getCurrPos();
        String fen = TextIO.toFEN(pos);
        String cacheKey = makeCacheKey(fen);

        ExplorerResult result = cache.get(cacheKey);
        if (result != null && !result.isExpired()) {
            return resultToBookEntries(result, pos);
        }

        // Synchronous fetch
        result = doFetch(fen, timeoutMs);
        if (result != null) {
            cache.put(cacheKey, result);
            return resultToBookEntries(result, pos);
        }
        return null;
    }

    /**
     * Get rich HTML-formatted explorer info for display.
     * Returns empty string if no cached data available.
     */
    public String getExplorerInfoHtml(Position pos) {
        if (!explorerEnabled)
            return "";

        String fen = TextIO.toFEN(pos);
        String cacheKey = makeCacheKey(fen);

        ExplorerResult result = cache.get(cacheKey);
        if (result == null || result.isExpired()) {
            fetchAsync(fen, cacheKey);
            return "";
        }

        return formatExplorerHtml(result);
    }

    /** Format an ExplorerResult as HTML for the thinking panel. */
    static String formatExplorerHtml(ExplorerResult result) {
        StringBuilder sb = new StringBuilder();

        // Header: database name + opening + total games
        sb.append("<b>Explorer");
        if (result.opening != null && !result.opening.isEmpty()) {
            sb.append(" &#8226; ").append(escapeHtml(result.opening));
        }
        sb.append("</b>");
        long total = result.totalGames();
        if (total > 0) {
            sb.append(" &#8226; ").append(formatNumber(total)).append(" games");
        }

        // Per-move lines
        for (ExplorerMove move : result.moves) {
            sb.append("<br>");
            sb.append("<b>").append(escapeHtml(move.san)).append("</b>");

            long moveTotal = move.totalGames();
            if (moveTotal > 0) {
                int wPct = Math.round(move.white * 100f / moveTotal);
                int dPct = Math.round(move.draws * 100f / moveTotal);
                int bPct = 100 - wPct - dPct;

                sb.append("  ");
                sb.append("<font color=\"#4CAF50\">").append(wPct).append("%</font>");
                sb.append(" / ");
                sb.append("<font color=\"#9E9E9E\">").append(dPct).append("%</font>");
                sb.append(" / ");
                sb.append("<font color=\"#F44336\">").append(bPct).append("%</font>");
                sb.append("  ").append(formatNumber(moveTotal));
            }

            if (move.avgRating > 0) {
                sb.append("  ~").append(move.avgRating);
            }
        }

        return sb.toString();
    }

    /**
     * Return the cached ExplorerResult for the given position (non-blocking).
     * If not cached, fires an async fetch and returns null.
     */
    public ExplorerResult getExplorerResult(Position pos) {
        if (!explorerEnabled)
            return null;
        String fen = TextIO.toFEN(pos);
        String cacheKey = makeCacheKey(fen);
        ExplorerResult result = cache.get(cacheKey);
        if (result != null && !result.isExpired())
            return result;
        fetchAsync(fen, cacheKey);
        return null;
    }

    /** Shut down the background executor. */
    public void shutdown() {
        executor.shutdownNow();
    }

    // --- Internal methods ---

    private void fetchAsync(String fen, String cacheKey) {
        if (pendingFetches.contains(cacheKey))
            return;
        pendingFetches.add(cacheKey);

        executor.submit(() -> {
            try {
                ExplorerResult result = doFetch(fen, CONNECT_TIMEOUT_MS + READ_TIMEOUT_MS);
                if (result == null) {
                    // Cache empty result so UI stops showing "Loading..."
                    result = new ExplorerResult("", 0, 0, 0, new ArrayList<>());
                }
                cache.put(cacheKey, result);
                Runnable cb = onDataReady;
                if (cb != null) cb.run();
            } catch (Exception e) {
                Log.w(TAG, "Async fetch failed: " + e.getMessage());
                Runnable cb = onDataReady;
                if (cb != null) cb.run();
            } finally {
                pendingFetches.remove(cacheKey);
            }
        });
    }

    private ExplorerResult doFetch(String fen, int timeoutMs) {
        // Rate limiting
        long now = System.currentTimeMillis();
        if (now < rateLimitUntilMs)
            return null;

        long elapsed = now - lastRequestTimeMs;
        if (elapsed < MIN_REQUEST_INTERVAL_MS) {
            try {
                Thread.sleep(MIN_REQUEST_INTERVAL_MS - elapsed);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return null;
            }
        }

        HttpURLConnection conn = null;
        try {
            String urlStr = buildUrl(fen);
            URL url = new URL(urlStr);
            conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(Math.min(timeoutMs, CONNECT_TIMEOUT_MS));
            conn.setReadTimeout(Math.min(timeoutMs, READ_TIMEOUT_MS));
            conn.setRequestProperty("Accept", "application/json");

            lastRequestTimeMs = System.currentTimeMillis();

            int responseCode = conn.getResponseCode();
            if (responseCode == 429) {
                rateLimitUntilMs = System.currentTimeMillis() + RATE_LIMIT_BACKOFF_MS;
                Log.w(TAG, "Rate limited, backing off for 60s");
                return null;
            }
            if (responseCode != 200) {
                Log.w(TAG, "HTTP " + responseCode + " from explorer API");
                return null;
            }

            BufferedReader reader = new BufferedReader(
                new InputStreamReader(conn.getInputStream(), "UTF-8"));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null)
                sb.append(line);
            reader.close();

            return parseResponse(sb.toString());
        } catch (Exception e) {
            Log.w(TAG, "Explorer fetch error: " + e.getMessage());
            return null;
        } finally {
            if (conn != null)
                conn.disconnect();
        }
    }

    /** Build the API URL for the configured database. */
    String buildUrl(String fen) {
        try {
            String encodedFen = URLEncoder.encode(fen, "UTF-8");
            switch (database) {
                case "lichess":
                    return BASE_URL + "/lichess?fen=" + encodedFen
                            + "&speeds=blitz,rapid,classical"
                            + "&ratings=1600,1800,2000,2200,2500"
                            + "&moves=" + MAX_MOVES;
                case "player":
                    String encodedPlayer = URLEncoder.encode(playerName, "UTF-8");
                    return BASE_URL + "/player?player=" + encodedPlayer
                            + "&fen=" + encodedFen
                            + "&moves=" + MAX_MOVES;
                case "masters":
                default:
                    return BASE_URL + "/masters?fen=" + encodedFen
                            + "&moves=" + MAX_MOVES;
            }
        } catch (Exception e) {
            return BASE_URL + "/masters?fen=" + fen + "&moves=" + MAX_MOVES;
        }
    }

    /** Parse the JSON response from the Lichess explorer API. */
    static ExplorerResult parseResponse(String json) {
        try {
            JSONObject obj = new JSONObject(json);

            long totalWhite = obj.optLong("white", 0);
            long totalDraws = obj.optLong("draws", 0);
            long totalBlack = obj.optLong("black", 0);

            // Opening name
            String opening = "";
            JSONObject openingObj = obj.optJSONObject("opening");
            if (openingObj != null) {
                String eco = openingObj.optString("eco", "");
                String name = openingObj.optString("name", "");
                if (!eco.isEmpty() && !name.isEmpty())
                    opening = eco + ": " + name;
                else if (!name.isEmpty())
                    opening = name;
                else if (!eco.isEmpty())
                    opening = eco;
            }

            // Moves
            ArrayList<ExplorerMove> moves = new ArrayList<>();
            JSONArray movesArr = obj.optJSONArray("moves");
            if (movesArr != null) {
                for (int i = 0; i < movesArr.length(); i++) {
                    JSONObject m = movesArr.getJSONObject(i);
                    String uci = m.optString("uci", "");
                    String san = m.optString("san", "");
                    long w = m.optLong("white", 0);
                    long d = m.optLong("draws", 0);
                    long b = m.optLong("black", 0);
                    int avg = m.optInt("averageRating", 0);
                    if (!uci.isEmpty() && !san.isEmpty()) {
                        moves.add(new ExplorerMove(uci, san, w, d, b, avg));
                    }
                }
            }

            return new ExplorerResult(opening, totalWhite, totalDraws, totalBlack, moves);
        } catch (Exception e) {
            Log.w(TAG, "JSON parse error: " + e.getMessage());
            return null;
        }
    }

    /** Convert ExplorerResult moves to BookEntry list. Weight = total games. */
    private ArrayList<BookEntry> resultToBookEntries(ExplorerResult result, Position pos) {
        if (result.moves.isEmpty())
            return null;
        ArrayList<BookEntry> entries = new ArrayList<>();
        for (ExplorerMove em : result.moves) {
            Move move = TextIO.UCIstringToMove(em.uci);
            if (move != null) {
                BookEntry be = new BookEntry(move);
                be.weight = em.totalGames();
                entries.add(be);
            }
        }
        return entries.isEmpty() ? null : entries;
    }

    /** Build cache key including database name and FEN (without move counters). */
    private String makeCacheKey(String fen) {
        return database + ":" + stripMoveCounters(fen);
    }

    /** Strip halfmove clock and fullmove counter from FEN for cache key. */
    static String stripMoveCounters(String fen) {
        // FEN: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        // We want: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"
        int spaceCount = 0;
        for (int i = 0; i < fen.length(); i++) {
            if (fen.charAt(i) == ' ') {
                spaceCount++;
                if (spaceCount == 4)
                    return fen.substring(0, i);
            }
        }
        return fen;
    }

    private static String escapeHtml(String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }

    /** Format a number with K/M suffixes for compactness. */
    public static String formatNumber(long n) {
        if (n >= 1000000000L)
            return String.format("%.1fB", n / 1000000000.0);
        if (n >= 1000000L)
            return String.format("%.1fM", n / 1000000.0);
        if (n >= 10000L)
            return String.format("%.0fK", n / 1000.0);
        if (n >= 1000L)
            return String.format("%.1fK", n / 1000.0);
        return String.valueOf(n);
    }
}

package org.petero.droidfish.book;

import org.junit.Test;
import static org.junit.Assert.*;

import java.util.ArrayList;

public class LichessExplorerBookTest {

    // --- JSON Parsing ---

    @Test
    public void testParseNormalResponse() {
        String json = "{"
                + "\"white\":5000,\"draws\":3000,\"black\":2000,"
                + "\"opening\":{\"eco\":\"C50\",\"name\":\"Italian Game\"},"
                + "\"moves\":["
                + "  {\"uci\":\"e2e4\",\"san\":\"e4\",\"white\":2000,\"draws\":1500,\"black\":500,\"averageRating\":2650},"
                + "  {\"uci\":\"d2d4\",\"san\":\"d4\",\"white\":1800,\"draws\":1000,\"black\":800,\"averageRating\":2620}"
                + "]}";

        LichessExplorerBook.ExplorerResult result = LichessExplorerBook.parseResponse(json);

        assertNotNull(result);
        assertEquals("C50: Italian Game", result.opening);
        assertEquals(5000, result.totalWhite);
        assertEquals(3000, result.totalDraws);
        assertEquals(2000, result.totalBlack);
        assertEquals(10000, result.totalGames());
        assertEquals(2, result.moves.size());

        LichessExplorerBook.ExplorerMove e4 = result.moves.get(0);
        assertEquals("e2e4", e4.uci);
        assertEquals("e4", e4.san);
        assertEquals(2000, e4.white);
        assertEquals(1500, e4.draws);
        assertEquals(500, e4.black);
        assertEquals(4000, e4.totalGames());
        assertEquals(2650, e4.avgRating);

        LichessExplorerBook.ExplorerMove d4 = result.moves.get(1);
        assertEquals("d2d4", d4.uci);
        assertEquals("d4", d4.san);
        assertEquals(3600, d4.totalGames());
    }

    @Test
    public void testParseEmptyPosition() {
        String json = "{\"white\":0,\"draws\":0,\"black\":0,\"moves\":[]}";

        LichessExplorerBook.ExplorerResult result = LichessExplorerBook.parseResponse(json);

        assertNotNull(result);
        assertEquals(0, result.totalGames());
        assertTrue(result.moves.isEmpty());
        assertEquals("", result.opening);
    }

    @Test
    public void testParseMalformedJson() {
        LichessExplorerBook.ExplorerResult result = LichessExplorerBook.parseResponse("not json");
        assertNull(result);
    }

    @Test
    public void testParseNoOpening() {
        String json = "{\"white\":100,\"draws\":50,\"black\":30,\"moves\":["
                + "{\"uci\":\"e2e4\",\"san\":\"e4\",\"white\":100,\"draws\":50,\"black\":30}"
                + "]}";

        LichessExplorerBook.ExplorerResult result = LichessExplorerBook.parseResponse(json);
        assertNotNull(result);
        assertEquals("", result.opening);
        assertEquals(1, result.moves.size());
        assertEquals(0, result.moves.get(0).avgRating);
    }

    @Test
    public void testParseEcoOnly() {
        String json = "{\"white\":10,\"draws\":5,\"black\":3,"
                + "\"opening\":{\"eco\":\"A00\",\"name\":\"\"},"
                + "\"moves\":[]}";

        LichessExplorerBook.ExplorerResult result = LichessExplorerBook.parseResponse(json);
        assertNotNull(result);
        assertEquals("A00", result.opening);
    }

    // --- FEN Cache Key ---

    @Test
    public void testStripMoveCounters() {
        String fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
        assertEquals("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -",
                LichessExplorerBook.stripMoveCounters(fen));
    }

    @Test
    public void testStripMoveCountersAfterMoves() {
        String fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1";
        assertEquals("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3",
                LichessExplorerBook.stripMoveCounters(fen));
    }

    @Test
    public void testStripMoveCountersHighNumbers() {
        String fen = "8/8/8/8/8/8/8/4K3 w - - 45 120";
        assertEquals("8/8/8/8/8/8/8/4K3 w - -",
                LichessExplorerBook.stripMoveCounters(fen));
    }

    // --- HTML Formatting ---

    @Test
    public void testFormatExplorerHtml() {
        ArrayList<LichessExplorerBook.ExplorerMove> moves = new ArrayList<>();
        moves.add(new LichessExplorerBook.ExplorerMove("e2e4", "e4", 50, 30, 20, 2650));
        moves.add(new LichessExplorerBook.ExplorerMove("d2d4", "d4", 40, 35, 25, 2620));

        LichessExplorerBook.ExplorerResult result =
                new LichessExplorerBook.ExplorerResult("C50: Italian Game", 100, 60, 40, moves);

        String html = LichessExplorerBook.formatExplorerHtml(result);

        assertTrue(html.contains("<b>Explorer"));
        assertTrue(html.contains("C50: Italian Game"));
        assertTrue(html.contains("200 games"));
        assertTrue(html.contains("<b>e4</b>"));
        assertTrue(html.contains("<b>d4</b>"));
        assertTrue(html.contains("4CAF50")); // green for white
        assertTrue(html.contains("F44336")); // red for black
        assertTrue(html.contains("~2650"));
    }

    @Test
    public void testFormatExplorerHtmlEmptyOpening() {
        ArrayList<LichessExplorerBook.ExplorerMove> moves = new ArrayList<>();
        LichessExplorerBook.ExplorerResult result =
                new LichessExplorerBook.ExplorerResult("", 0, 0, 0, moves);

        String html = LichessExplorerBook.formatExplorerHtml(result);
        assertTrue(html.contains("<b>Explorer</b>"));
        assertFalse(html.contains("&#8226;")); // no bullet for empty opening/games
    }

    // --- Number Formatting ---

    @Test
    public void testFormatNumber() {
        assertEquals("0", LichessExplorerBook.formatNumber(0));
        assertEquals("999", LichessExplorerBook.formatNumber(999));
        assertEquals("1.0K", LichessExplorerBook.formatNumber(1000));
        assertEquals("5.4K", LichessExplorerBook.formatNumber(5432));
        assertEquals("10K", LichessExplorerBook.formatNumber(10000));
        assertEquals("100K", LichessExplorerBook.formatNumber(100000));
        assertEquals("1.0M", LichessExplorerBook.formatNumber(1000000));
        assertEquals("7.2M", LichessExplorerBook.formatNumber(7200000));
    }

    // --- URL Construction ---

    @Test
    public void testBuildUrlMasters() {
        LichessExplorerBook book = new LichessExplorerBook();
        BookOptions opts = new BookOptions();
        opts.lichessExplorerEnabled = true;
        opts.lichessExplorerDb = "masters";
        book.setOptions(opts);

        String url = book.buildUrl("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");
        assertTrue(url.startsWith("https://explorer.lichess.ovh/masters?fen="));
        assertTrue(url.contains("moves=12"));
        assertFalse(url.contains("speeds="));
        assertFalse(url.contains("player="));
    }

    @Test
    public void testBuildUrlLichess() {
        LichessExplorerBook book = new LichessExplorerBook();
        BookOptions opts = new BookOptions();
        opts.lichessExplorerEnabled = true;
        opts.lichessExplorerDb = "lichess";
        book.setOptions(opts);

        String url = book.buildUrl("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");
        assertTrue(url.startsWith("https://explorer.lichess.ovh/lichess?fen="));
        assertTrue(url.contains("speeds="));
        assertTrue(url.contains("ratings="));
    }

    @Test
    public void testBuildUrlPlayer() {
        LichessExplorerBook book = new LichessExplorerBook();
        BookOptions opts = new BookOptions();
        opts.lichessExplorerEnabled = true;
        opts.lichessExplorerDb = "player";
        opts.lichessPlayerName = "DrNykterstein";
        book.setOptions(opts);

        String url = book.buildUrl("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");
        assertTrue(url.startsWith("https://explorer.lichess.ovh/player?player=DrNykterstein"));
        assertTrue(url.contains("fen="));
    }

    // --- Options / Enabled ---

    @Test
    public void testDisabledByDefault() {
        LichessExplorerBook book = new LichessExplorerBook();
        assertFalse(book.enabled());
    }

    @Test
    public void testEnabledFromOptions() {
        LichessExplorerBook book = new LichessExplorerBook();
        BookOptions opts = new BookOptions();
        opts.lichessExplorerEnabled = true;
        opts.lichessExplorerDb = "lichess";
        opts.lichessPlayerName = "testuser";
        book.setOptions(opts);

        assertTrue(book.enabled());
    }

    @Test
    public void testDisabledReturnsNull() {
        LichessExplorerBook book = new LichessExplorerBook();
        assertNull(book.getBookEntries(null)); // null posInput ok since enabled() is false
    }

    @Test
    public void testDisabledExplorerInfoReturnsEmpty() {
        LichessExplorerBook book = new LichessExplorerBook();
        assertEquals("", book.getExplorerInfoHtml(null)); // null pos ok since enabled() is false
    }

    // --- BookOptions equality ---

    @Test
    public void testBookOptionsEquality() {
        BookOptions a = new BookOptions();
        a.lichessExplorerEnabled = true;
        a.lichessExplorerDb = "masters";
        a.lichessPlayerName = "user1";

        BookOptions b = new BookOptions(a);
        assertEquals(a, b);

        b.lichessExplorerDb = "lichess";
        assertNotEquals(a, b);
    }

    @Test
    public void testBookOptionsCopy() {
        BookOptions orig = new BookOptions();
        orig.lichessExplorerEnabled = true;
        orig.lichessExplorerDb = "player";
        orig.lichessPlayerName = "magnus";

        BookOptions copy = new BookOptions(orig);
        assertTrue(copy.lichessExplorerEnabled);
        assertEquals("player", copy.lichessExplorerDb);
        assertEquals("magnus", copy.lichessPlayerName);
    }
}

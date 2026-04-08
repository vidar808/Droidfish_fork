/*
    DroidFish - An Android chess program.
    Copyright (C) 2011  Peter Österlund, peterosterlund2@gmail.com

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

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;

import org.petero.droidfish.DroidFishApp;
import org.petero.droidfish.book.DroidBook.BookEntry;
import org.petero.droidfish.gamelogic.ChessParseError;
import org.petero.droidfish.gamelogic.Move;
import org.petero.droidfish.gamelogic.Piece;
import org.petero.droidfish.gamelogic.Position;
import org.petero.droidfish.gamelogic.TextIO;
import org.petero.droidfish.gamelogic.UndoInfo;

import android.annotation.SuppressLint;
import android.util.Log;

@SuppressLint("UseSparseArrays")
final class InternalBook implements IOpeningBook {
    private static final String TAG = "InternalBook";
    private static HashMap<Long, ArrayList<BookEntry>> bookMap;
    private static int numBookMoves = -1;
    private boolean enabled = false;

    InternalBook() {
        Thread t = new Thread(this::initInternalBook);
        t.setPriority(Thread.MIN_PRIORITY);
        t.start();
    }

    @Override
    public boolean enabled() {
        return enabled;
    }

    @Override
    public ArrayList<BookEntry> getBookEntries(BookPosInput posInput) {
        Position pos = posInput.getCurrPos();
        initInternalBook();
        ArrayList<BookEntry> ents = bookMap.get(pos.zobristHash());
        if (ents == null)
            return null;
        ArrayList<BookEntry> ret = new ArrayList<>();
        for (BookEntry be : ents) {
            BookEntry be2 = new BookEntry(be.move);
            be2.weight = (float)(Math.sqrt(be.weight) * 100 + 1);
            be2.lineType = be.lineType;
            be2.quality = be.quality;
            ret.add(be2);
        }
        return ret;
    }

    @Override
    public void setOptions(BookOptions options) {
        enabled = options.filename.equals("internal:");
    }

    /** Magic bytes identifying the enhanced v2 book format. */
    private static final byte[] MAGIC_V2 = { 'D', 'F', 'B', '2' };

    private synchronized void initInternalBook() {
        if (numBookMoves >= 0)
            return;
        bookMap = new HashMap<>();
        gambitVotes = new HashMap<>();
        numBookMoves = 0;
        try {
            InputStream inStream = DroidFishApp.getContext().getAssets().open("book.bin");
            List<Byte> buf = new ArrayList<>(8192);
            byte[] tmpBuf = new byte[1024];
            while (true) {
                int len = inStream.read(tmpBuf);
                if (len <= 0) break;
                for (int i = 0; i < len; i++)
                    buf.add(tmpBuf[i]);
            }
            inStream.close();

            // Detect format: v2 starts with magic "DFB2"
            boolean v2 = buf.size() >= 4 &&
                         buf.get(0) == MAGIC_V2[0] && buf.get(1) == MAGIC_V2[1] &&
                         buf.get(2) == MAGIC_V2[2] && buf.get(3) == MAGIC_V2[3];
            int offset = v2 ? 4 : 0;
            int step = v2 ? 4 : 2;

            Position startPos = TextIO.readFEN(TextIO.startPosFEN);
            Position pos = new Position(startPos);
            UndoInfo ui = new UndoInfo();
            int len = buf.size();
            for (int i = offset; i + step - 1 < len; i += step) {
                int b0 = buf.get(i) & 0xFF;
                int b1 = buf.get(i + 1) & 0xFF;
                int move = (b0 << 8) + b1;

                int meta = 0;
                if (v2) {
                    int m0 = buf.get(i + 2) & 0xFF;
                    int m1 = buf.get(i + 3) & 0xFF;
                    meta = (m0 << 8) + m1;
                }

                if (move == 0) {
                    pos = new Position(startPos);
                } else {
                    boolean bad = ((move >> 15) & 1) != 0;
                    int prom = (move >> 12) & 7;
                    Move m = new Move(move & 63, (move >> 6) & 63,
                                      promToPiece(prom, pos.whiteMove));
                    if (!bad) {
                        int lineType = meta & 0x3;
                        int quality = (meta >> 2) & 0x3;
                        addToBook(pos, m, lineType, quality);
                    }
                    pos.makeMove(m, ui);
                }
            }
            applyGambitVotes();
        } catch (ChessParseError ex) {
            Log.w(TAG, "Failed to parse internal opening book");
        } catch (IOException ex) {
            Log.w(TAG, "Internal opening book not found (book.bin missing). " +
                       "Using engine's own opening play instead.");
        }
    }


    /** Per-entry gambit vote counters, used during loading then discarded. */
    private static HashMap<Long, HashMap<Integer, int[]>> gambitVotes;
    // Outer key = position zobrist, inner key = move compact (from*64+to),
    // value = [normalCount, gambitCount, lastGambitType]

    /** Add a move to a position in the opening book. */
    private void addToBook(Position pos, Move moveToAdd, int lineType, int quality) {
        long posHash = pos.zobristHash();
        ArrayList<BookEntry> ent = bookMap.get(posHash);
        if (ent == null) {
            ent = new ArrayList<>();
            bookMap.put(posHash, ent);
        }

        // Track gambit votes per move per position
        int moveKey = moveToAdd.from * 64 + moveToAdd.to;
        HashMap<Integer, int[]> posVotes = gambitVotes.get(posHash);
        if (posVotes == null) {
            posVotes = new HashMap<>();
            gambitVotes.put(posHash, posVotes);
        }
        int[] votes = posVotes.get(moveKey);
        if (votes == null) {
            votes = new int[3];
            posVotes.put(moveKey, votes);
        }
        if (lineType == DroidBook.LINE_NORMAL)
            votes[0]++;
        else {
            votes[1]++;
            votes[2] = lineType;
        }

        for (int i = 0; i < ent.size(); i++) {
            BookEntry be = ent.get(i);
            if (be.move.equals(moveToAdd)) {
                be.weight++;
                if (quality > be.quality)
                    be.quality = quality;
                return;
            }
        }
        BookEntry be = new BookEntry(moveToAdd);
        be.quality = quality;
        ent.add(be);
        numBookMoves++;
    }

    /** Apply gambit tags using majority voting — only tag a move as gambit
     *  if more than half its occurrences come from gambit lines. */
    private static void applyGambitVotes() {
        for (HashMap.Entry<Long, ArrayList<BookEntry>> mapEntry : bookMap.entrySet()) {
            long posHash = mapEntry.getKey();
            HashMap<Integer, int[]> posVotes = gambitVotes.get(posHash);
            if (posVotes == null) continue;
            for (BookEntry be : mapEntry.getValue()) {
                int moveKey = be.move.from * 64 + be.move.to;
                int[] votes = posVotes.get(moveKey);
                if (votes != null && votes[1] > votes[0]) {
                    be.lineType = votes[2];
                }
            }
        }
        gambitVotes = null; // Free memory
    }

    private static int promToPiece(int prom, boolean whiteMove) {
        switch (prom) {
        case 1: return whiteMove ? Piece.WQUEEN : Piece.BQUEEN;
        case 2: return whiteMove ? Piece.WROOK  : Piece.BROOK;
        case 3: return whiteMove ? Piece.WBISHOP : Piece.BBISHOP;
        case 4: return whiteMove ? Piece.WKNIGHT : Piece.BKNIGHT;
        default: return Piece.EMPTY;
        }
    }
}

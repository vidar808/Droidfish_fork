/*
    CuckooChess - A java chess program.
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

package chess;

import java.io.BufferedReader;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.LineNumberReader;
import java.util.ArrayList;
import java.util.List;

/** Implements an opening book. */
public class Book {
    /** Line type constants for gambit classification. */
    public static final int LINE_NORMAL       = 0;
    public static final int LINE_GAMBIT_WHITE  = 1;
    public static final int LINE_GAMBIT_BLACK  = 2;
    public static final int LINE_GAMBIT_MUTUAL = 3;

    /** Quality constants for line classification. */
    public static final int QUALITY_UNRATED  = 0;
    public static final int QUALITY_MAINLINE = 1;
    public static final int QUALITY_SIDELINE = 2;
    public static final int QUALITY_DUBIOUS  = 3;

    /** Magic bytes written at the start of the enhanced book format (v2). */
    private static final byte[] MAGIC = { 'D', 'F', 'B', '2' };

    /** Creates the book.bin file. */
    public static void main(String[] args) throws IOException {
        String inFile = args[0];
        String outFile = args[1];
        main2(inFile, outFile);
    }
    public static void main2(String inFile, String outFile) throws IOException {
        List<Byte> binBook = createBinBook(inFile);
        try (FileOutputStream out = new FileOutputStream(outFile)) {
            int bookLen = binBook.size();
            byte[] binBookA = new byte[bookLen];
            for (int i = 0; i < bookLen; i++)
                binBookA[i] = binBook.get(i);
            out.write(binBookA);
        }
    }

    public static List<Byte> createBinBook(String inFileName) {
        List<Byte> binBook = new ArrayList<>(0);
        // Write magic header for v2 format detection
        for (byte b : MAGIC)
            binBook.add(b);
        try (InputStream inStream = new FileInputStream(inFileName);
            InputStreamReader inFile = new InputStreamReader(inStream);
            BufferedReader inBuf = new BufferedReader(inFile);
            LineNumberReader lnr = new LineNumberReader(inBuf)) {
            String line;
            int lineType = LINE_NORMAL;
            int quality = QUALITY_SIDELINE;
            while ((line = lnr.readLine()) != null) {
                if (line.length() == 0) {
                    continue;
                }
                if (line.startsWith("# META ")) {
                    // Parse metadata line: "# META <lineType> <quality>"
                    String[] parts = line.substring(7).trim().split("\\s+");
                    lineType = parseLineType(parts.length > 0 ? parts[0] : "");
                    quality = parseQuality(parts.length > 1 ? parts[1] : "");
                    continue;
                }
                if (line.startsWith("#")) {
                    continue;
                }
                int meta = (lineType & 0x3) | ((quality & 0x3) << 2);
                if (!addBookLine(line, binBook, meta)) {
                    System.out.printf("Book parse error, line:%d\n", lnr.getLineNumber());
                    throw new RuntimeException();
                }
                // Reset metadata for next entry
                lineType = LINE_NORMAL;
                quality = QUALITY_SIDELINE;
            }
        } catch (ChessParseError ex) {
            throw new RuntimeException();
        } catch (IOException ex) {
            System.out.println("Can't read opening book resource");
            throw new RuntimeException();
        }
        return binBook;
    }

    private static int parseLineType(String s) {
        switch (s) {
            case "gambit-white":  return LINE_GAMBIT_WHITE;
            case "gambit-black":  return LINE_GAMBIT_BLACK;
            case "gambit-mutual": return LINE_GAMBIT_MUTUAL;
            default:              return LINE_NORMAL;
        }
    }

    private static int parseQuality(String s) {
        switch (s) {
            case "mainline": return QUALITY_MAINLINE;
            case "sideline": return QUALITY_SIDELINE;
            case "dubious":  return QUALITY_DUBIOUS;
            default:         return QUALITY_UNRATED;
        }
    }

    /** Add a sequence of moves, starting from the initial position, to the binary opening book.
     *  Each move is encoded as 4 bytes: 2-byte move + 2-byte metadata. */
    private static boolean addBookLine(String line, List<Byte> binBook, int meta) throws ChessParseError {
        Position pos = TextIO.readFEN(TextIO.startPosFEN);
        UndoInfo ui = new UndoInfo();
        String[] strMoves = line.split(" ");
        for (String strMove : strMoves) {
            if (strMove.isEmpty()) {
                continue;
            }
            if ("*".equals(strMove) || "1-0".equals(strMove) ||
                    "0-1".equals(strMove) || "1/2-1/2".equals(strMove)) {
                break;
            }
            int bad = 0;
            if (strMove.endsWith("?")) {
                strMove = strMove.substring(0, strMove.length() - 1);
                bad = 1;
            }
            Move m = TextIO.stringToMove(pos, strMove);
            if (m == null) {
                return false;
            }
            int prom = pieceToProm(m.promoteTo);
            int val = m.from + (m.to << 6) + (prom << 12) + (bad << 15);
            // Write 2-byte move
            binBook.add((byte)(val >> 8));
            binBook.add((byte)(val & 255));
            // Write 2-byte metadata
            binBook.add((byte)((meta >> 8) & 0xFF));
            binBook.add((byte)(meta & 0xFF));
            pos.makeMove(m, ui);
        }
        // 4-byte terminator (two zero words)
        binBook.add((byte)0);
        binBook.add((byte)0);
        binBook.add((byte)0);
        binBook.add((byte)0);
        return true;
    }

    private static int pieceToProm(int p) {
        switch (p) {
        case Piece.WQUEEN: case Piece.BQUEEN:
            return 1;
        case Piece.WROOK: case Piece.BROOK:
            return 2;
        case Piece.WBISHOP: case Piece.BBISHOP:
            return 3;
        case Piece.WKNIGHT: case Piece.BKNIGHT:
            return 4;
        default:
            return 0;
        }
    }
}

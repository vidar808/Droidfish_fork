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

package org.petero.droidfish.activities.util;

import org.petero.droidfish.gamelogic.Move;
import org.petero.droidfish.gamelogic.Piece;
import org.petero.droidfish.gamelogic.Position;
import org.petero.droidfish.view.ChessBoard;

import android.content.Context;
import android.graphics.Canvas;
import android.util.AttributeSet;

/** Interactive chess board for the Opening Explorer. Supports tap-to-move. */
public class ChessBoardExplorer extends ChessBoard {

    public ChessBoardExplorer(Context context, AttributeSet attrs) {
        super(context, attrs);
    }

    @Override
    public Move mousePressed(int sq) {
        if (sq < 0)
            return null;
        if ((selectedSquare != -1) && !userSelectedSquare)
            setSelection(-1);

        int p = pos.getPiece(sq);
        if (selectedSquare != -1) {
            if (sq == selectedSquare) {
                setSelection(-1);
                return null;
            }
            if (!myColor(p)) {
                Move m = new Move(selectedSquare, sq, Piece.EMPTY);
                setSelection(highlightLastMove ? sq : -1);
                userSelectedSquare = false;
                return m;
            } else {
                setSelection(sq);
            }
        } else {
            if (myColor(p))
                setSelection(sq);
        }
        return null;
    }

    @Override protected int getSquare(int x, int y) { return Position.getSquare(x, y); }

    @Override
    protected XYCoord sqToPix(int x, int y) {
        int xPix = x0 + sqSize * (flipped ? 7 - x : x);
        int yPix = y0 + sqSize * (flipped ? y : 7 - y);
        return new XYCoord(xPix, yPix);
    }

    @Override
    protected XYCoord pixToSq(int xCrd, int yCrd) {
        int x = (int)Math.floor((xCrd - x0) / (double)sqSize); if (flipped) x = 7 - x;
        int y = (int)Math.floor((yCrd - y0) / (double)sqSize); if (!flipped) y = 7 - y;
        return new XYCoord(x, y);
    }

    @Override protected int getWidth(int sqSize) { return sqSize * 8; }
    @Override protected int getHeight(int sqSize) { return sqSize * 8; }
    @Override protected int getSqSizeW(int width) { return width / 8; }
    @Override protected int getSqSizeH(int height) { return height / 8; }
    @Override protected int getMaxHeightPercentage() { return 100; }
    @Override protected int getMaxWidthPercentage() { return 100; }

    @Override
    protected void computeOrigin(int width, int height) {
        x0 = (width - sqSize * 8) / 2;
        y0 = (height - sqSize * 8) / 2;
    }

    @Override protected int getXFromSq(int sq) { return Position.getX(sq); }
    @Override protected int getYFromSq(int sq) { return Position.getY(sq); }

    @Override protected void drawExtraSquares(Canvas canvas) { }
}

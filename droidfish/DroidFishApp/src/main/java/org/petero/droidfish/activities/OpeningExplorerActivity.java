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

import android.app.Activity;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.MotionEvent;
import android.view.View;
import android.widget.Button;
import android.widget.ListView;
import android.widget.TextView;

import org.petero.droidfish.R;
import org.petero.droidfish.activities.util.ChessBoardExplorer;
import org.petero.droidfish.activities.util.ExplorerMoveAdapter;
import org.petero.droidfish.book.BookOptions;
import org.petero.droidfish.book.LichessExplorerBook;
import org.petero.droidfish.book.LichessExplorerBook.ExplorerMove;
import org.petero.droidfish.book.LichessExplorerBook.ExplorerResult;
import org.petero.droidfish.gamelogic.ChessParseError;
import org.petero.droidfish.gamelogic.Move;
import org.petero.droidfish.gamelogic.MoveGen;
import org.petero.droidfish.gamelogic.Piece;
import org.petero.droidfish.gamelogic.Position;
import org.petero.droidfish.gamelogic.TextIO;
import org.petero.droidfish.gamelogic.UndoInfo;

import java.util.ArrayList;
import java.util.List;

/** Dedicated Lichess-style Opening Explorer activity. */
public class OpeningExplorerActivity extends Activity {
    private ChessBoardExplorer board;
    private TextView tabMasters, tabLichess, tabPlayer;
    private TextView openingNameView;
    private TextView movePathView;
    private ListView moveListView;
    private TextView statusText;
    private Button btnBack, btnForward;

    private LichessExplorerBook explorerBook;
    private ExplorerMoveAdapter adapter;

    private ArrayList<Position> posHistory;
    private ArrayList<Move> moveHistory;
    private int currentIndex;

    private String playerName = "";
    private boolean boardFlipped = false;
    private int selectedDbIndex = 0;

    // Touch handling for board
    private int touchDownSq = -1;
    private float touchDownX, touchDownY;
    private boolean isDrag;
    private static final float SWIPE_THRESHOLD_DP = 40;

    private static final String[] DB_VALUES = {"masters", "lichess", "player"};
    private static final int COLOR_TAB_ACTIVE   = 0xFFE8E6E3;
    private static final int COLOR_TAB_INACTIVE = 0xFF7B7769;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_opening_explorer);

        board = findViewById(R.id.explorerBoard);
        tabMasters = findViewById(R.id.tabMasters);
        tabLichess = findViewById(R.id.tabLichess);
        tabPlayer = findViewById(R.id.tabPlayer);
        openingNameView = findViewById(R.id.openingName);
        movePathView = findViewById(R.id.movePath);
        moveListView = findViewById(R.id.moveList);
        statusText = findViewById(R.id.statusText);
        btnBack = findViewById(R.id.btnBack);
        btnForward = findViewById(R.id.btnForward);

        board.highlightLastMove = true;

        // Parse intent extras
        String lichessDb = getIntent().getStringExtra("lichessDb");
        if (lichessDb == null)
            lichessDb = "masters";
        playerName = getIntent().getStringExtra("playerName");
        if (playerName == null)
            playerName = "";
        boardFlipped = getIntent().getBooleanExtra("flipped", false);
        board.setFlipped(boardFlipped);

        // Determine initial db index
        for (int i = 0; i < DB_VALUES.length; i++) {
            if (DB_VALUES[i].equals(lichessDb)) { selectedDbIndex = i; break; }
        }

        // Always start from standard starting position
        posHistory = new ArrayList<>();
        moveHistory = new ArrayList<>();
        Position startPos;
        try {
            startPos = TextIO.readFEN(TextIO.startPosFEN);
        } catch (ChessParseError e) {
            startPos = new Position();
        }
        posHistory.add(startPos);
        currentIndex = 0;

        // Database tab buttons
        tabMasters.setOnClickListener(v -> selectDb(0));
        tabLichess.setOnClickListener(v -> selectDb(1));
        tabPlayer.setOnClickListener(v -> selectDb(2));
        updateTabAppearance();

        // Explorer book
        explorerBook = new LichessExplorerBook();
        setupExplorerOptions(DB_VALUES[selectedDbIndex]);

        // Move list adapter
        ArrayList<ExplorerMove> moveData = new ArrayList<>();
        adapter = new ExplorerMoveAdapter(this, moveData);
        moveListView.setAdapter(adapter);
        moveListView.setOnItemClickListener((parent, view, position, id) ->
            onMoveRowClick(position));

        // Navigation buttons
        btnBack.setOnClickListener(v -> goBack());
        btnForward.setOnClickListener(v -> goForward());

        // Board touch: tap-to-move + drag + horizontal swipe for back/forward
        final float swipeThresholdPx = SWIPE_THRESHOLD_DP * getResources().getDisplayMetrics().density;
        board.setOnTouchListener((v, event) -> {
            switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                touchDownSq = board.eventToSquare(event);
                touchDownX = event.getX();
                touchDownY = event.getY();
                isDrag = false;
                if (board.isValidDragSquare(touchDownSq))
                    board.setDragState(touchDownSq, (int)event.getX(), (int)event.getY());
                return true;
            case MotionEvent.ACTION_MOVE:
                float dx = event.getX() - touchDownX;
                float dy = event.getY() - touchDownY;
                if (!isDrag && Math.abs(dx) > swipeThresholdPx && Math.abs(dx) > Math.abs(dy) * 1.5f) {
                    isDrag = true;
                    board.setDragState(-1, 0, 0);
                }
                if (!isDrag && board.isValidDragSquare(touchDownSq)) {
                    int sq = board.eventToSquare(event);
                    if (sq != touchDownSq)
                        board.setDragState(touchDownSq, (int)event.getX(), (int)event.getY());
                }
                return true;
            case MotionEvent.ACTION_UP:
                board.setDragState(-1, 0, 0);
                if (isDrag) {
                    float swipeDx = event.getX() - touchDownX;
                    if (swipeDx > swipeThresholdPx)
                        goForward();
                    else if (swipeDx < -swipeThresholdPx)
                        goBack();
                } else {
                    int sq = board.eventToSquare(event);
                    if (touchDownSq >= 0 && sq >= 0 && sq != touchDownSq &&
                            board.isValidDragSquare(touchDownSq)) {
                        Move m = new Move(touchDownSq, sq, Piece.EMPTY);
                        applyBoardMove(m);
                    } else {
                        Move m = board.mousePressed(sq);
                        if (m != null)
                            applyBoardMove(m);
                    }
                }
                return true;
            case MotionEvent.ACTION_CANCEL:
                board.setDragState(-1, 0, 0);
                return true;
            }
            return false;
        });

        // Initial state
        updateBoard();
        refreshExplorer();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (explorerBook != null)
            explorerBook.shutdown();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        outState.putInt("currentIndex", currentIndex);
        outState.putBoolean("flipped", boardFlipped);
        outState.putInt("dbIndex", selectedDbIndex);
        outState.putString("playerName", playerName);
        ArrayList<String> fens = new ArrayList<>();
        for (Position p : posHistory)
            fens.add(TextIO.toFEN(p));
        outState.putStringArrayList("posHistory", fens);
        ArrayList<String> uciMoves = new ArrayList<>();
        for (Move m : moveHistory)
            uciMoves.add(TextIO.moveToUCIString(m));
        outState.putStringArrayList("moveHistory", uciMoves);
    }

    @Override
    protected void onRestoreInstanceState(Bundle savedInstanceState) {
        super.onRestoreInstanceState(savedInstanceState);
        if (savedInstanceState == null)
            return;

        boardFlipped = savedInstanceState.getBoolean("flipped", false);
        board.setFlipped(boardFlipped);
        playerName = savedInstanceState.getString("playerName", "");
        selectedDbIndex = savedInstanceState.getInt("dbIndex", 0);
        updateTabAppearance();

        ArrayList<String> fens = savedInstanceState.getStringArrayList("posHistory");
        ArrayList<String> uciMoves = savedInstanceState.getStringArrayList("moveHistory");
        if (fens != null && fens.size() > 0) {
            posHistory.clear();
            for (String f : fens) {
                try { posHistory.add(TextIO.readFEN(f)); }
                catch (ChessParseError ignored) { }
            }
        }
        if (uciMoves != null) {
            moveHistory.clear();
            for (String u : uciMoves) {
                Move m = TextIO.UCIstringToMove(u);
                if (m != null) moveHistory.add(m);
            }
        }
        currentIndex = savedInstanceState.getInt("currentIndex", 0);
        if (currentIndex >= posHistory.size())
            currentIndex = posHistory.size() - 1;

        setupExplorerOptions(DB_VALUES[selectedDbIndex]);
        updateBoard();
        refreshExplorer();
    }

    private void selectDb(int index) {
        if (index == selectedDbIndex)
            return;
        selectedDbIndex = index;
        updateTabAppearance();
        setupExplorerOptions(DB_VALUES[index]);
        refreshExplorer();
    }

    private void updateTabAppearance() {
        TextView[] tabs = {tabMasters, tabLichess, tabPlayer};
        for (int i = 0; i < tabs.length; i++) {
            if (i == selectedDbIndex) {
                tabs[i].setTextColor(COLOR_TAB_ACTIVE);
                tabs[i].setTypeface(null, Typeface.BOLD);
            } else {
                tabs[i].setTextColor(COLOR_TAB_INACTIVE);
                tabs[i].setTypeface(null, Typeface.NORMAL);
            }
        }
    }

    private void setupExplorerOptions(String db) {
        BookOptions opts = new BookOptions();
        opts.lichessExplorerEnabled = true;
        opts.lichessExplorerDb = db;
        opts.lichessPlayerName = playerName;
        explorerBook.setOptions(opts);
    }

    private Position currentPos() {
        return posHistory.get(currentIndex);
    }

    private void applyBoardMove(Move move) {
        Position pos = currentPos();
        ArrayList<Move> legalMoves = new MoveGen().legalMoves(pos);
        Move legalMatch = null;
        for (Move lm : legalMoves) {
            if (lm.from == move.from && lm.to == move.to) {
                if (move.promoteTo != Piece.EMPTY) {
                    if (lm.promoteTo == move.promoteTo) { legalMatch = lm; break; }
                } else {
                    if (legalMatch == null) legalMatch = lm;
                }
            }
        }
        if (legalMatch == null) return;
        applyMove(legalMatch);
    }

    private void applyMove(Move legalMatch) {
        // Truncate forward history
        while (posHistory.size() > currentIndex + 1)
            posHistory.remove(posHistory.size() - 1);
        while (moveHistory.size() > currentIndex)
            moveHistory.remove(moveHistory.size() - 1);

        Position newPos = new Position(currentPos());
        UndoInfo ui = new UndoInfo();
        newPos.makeMove(legalMatch, ui);

        moveHistory.add(legalMatch);
        posHistory.add(newPos);
        currentIndex++;

        updateBoard();
        updateMovePath();
        refreshExplorer();
    }

    private void refreshExplorer() {
        if (DB_VALUES[selectedDbIndex].equals("player") && playerName.isEmpty()) {
            showPlayerNameRequired();
            updateNavButtons();
            return;
        }
        Position pos = currentPos();
        ExplorerResult result = explorerBook.getExplorerResult(pos);

        if (result != null) {
            showResult(result);
        } else {
            showLoading();
            explorerBook.setOnDataReady(() -> runOnUiThread(this::refreshExplorer));
        }
        updateNavButtons();
    }

    private void showPlayerNameRequired() {
        statusText.setText(R.string.explorer_player_name_required);
        statusText.setVisibility(View.VISIBLE);
        moveListView.setVisibility(View.GONE);
        board.setMoveHints(null);
        adapter.updateMoves(null);
    }

    private void showResult(ExplorerResult result) {
        statusText.setVisibility(View.GONE);
        moveListView.setVisibility(View.VISIBLE);
        adapter.updateMoves(result);

        if (result.opening != null && !result.opening.isEmpty()) {
            openingNameView.setText(result.opening);
        } else {
            openingNameView.setText(R.string.opening_explorer_title);
        }

        if (result.moves.isEmpty()) {
            statusText.setText(R.string.explorer_no_data);
            statusText.setVisibility(View.VISIBLE);
            moveListView.setVisibility(View.GONE);
            board.setMoveHints(null);
        } else {
            updateMoveArrows(result);
        }
    }

    private void updateMoveArrows(ExplorerResult result) {
        Position pos = currentPos();
        ArrayList<Move> legalMoves = new MoveGen().legalMoves(pos);
        List<Move> hints = new ArrayList<>();
        int maxArrows = Math.min(result.moves.size(), 8);
        for (int i = 0; i < maxArrows; i++) {
            Move uciMove = TextIO.UCIstringToMove(result.moves.get(i).uci);
            if (uciMove == null) continue;
            for (Move lm : legalMoves) {
                if (lm.from == uciMove.from && lm.to == uciMove.to &&
                    lm.promoteTo == uciMove.promoteTo) {
                    hints.add(lm);
                    break;
                }
            }
        }
        board.setMoveHints(hints.isEmpty() ? null : hints);
    }

    private void showLoading() {
        statusText.setText(R.string.explorer_loading);
        statusText.setVisibility(View.VISIBLE);
        moveListView.setVisibility(View.GONE);
        board.setMoveHints(null);
    }

    private void onMoveRowClick(int position) {
        if (position < 0 || position >= adapter.getCount())
            return;
        ExplorerMove explorerMove = adapter.getItem(position);
        if (explorerMove == null)
            return;

        Move move = TextIO.UCIstringToMove(explorerMove.uci);
        if (move == null) return;

        Position pos = currentPos();
        ArrayList<Move> legalMoves = new MoveGen().legalMoves(pos);
        Move legalMatch = null;
        for (Move lm : legalMoves) {
            if (lm.from == move.from && lm.to == move.to &&
                lm.promoteTo == move.promoteTo) {
                legalMatch = lm;
                break;
            }
        }
        if (legalMatch != null)
            applyMove(legalMatch);
    }

    private void goBack() {
        if (currentIndex > 0) {
            currentIndex--;
            updateBoard();
            updateMovePath();
            refreshExplorer();
        }
    }

    private void goForward() {
        if (currentIndex < posHistory.size() - 1) {
            currentIndex++;
            updateBoard();
            updateMovePath();
            refreshExplorer();
        }
    }

    private void updateBoard() {
        board.setPosition(currentPos());
        if (currentIndex > 0 && currentIndex - 1 < moveHistory.size()) {
            board.setSelection(moveHistory.get(currentIndex - 1).to);
            board.userSelectedSquare = false;
        } else {
            board.setSelection(-1);
        }
    }

    private void updateMovePath() {
        if (moveHistory.isEmpty() || currentIndex == 0) {
            movePathView.setVisibility(View.GONE);
            return;
        }
        StringBuilder sb = new StringBuilder();
        int limit = Math.min(currentIndex, moveHistory.size());
        for (int i = 0; i < limit; i++) {
            Position pos = posHistory.get(i);
            if (pos.whiteMove) {
                if (sb.length() > 0) sb.append(" ");
                sb.append(pos.fullMoveCounter).append(". ");
            } else if (i == 0) {
                sb.append(pos.fullMoveCounter).append("... ");
            } else {
                sb.append(" ");
            }
            sb.append(TextIO.moveToString(pos, moveHistory.get(i), false, false));
        }
        movePathView.setText(sb.toString());
        movePathView.setVisibility(View.VISIBLE);
    }

    private void updateNavButtons() {
        btnBack.setEnabled(currentIndex > 0);
        btnForward.setEnabled(currentIndex < posHistory.size() - 1);
    }
}

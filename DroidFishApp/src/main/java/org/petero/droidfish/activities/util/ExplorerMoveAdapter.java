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

import android.content.Context;
import android.graphics.Typeface;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.TextView;

import org.petero.droidfish.R;
import org.petero.droidfish.book.LichessExplorerBook;
import org.petero.droidfish.book.LichessExplorerBook.ExplorerMove;
import org.petero.droidfish.book.LichessExplorerBook.ExplorerResult;

import java.util.ArrayList;

/**
 * ListView adapter for opening explorer move rows.
 * Matches the Lichess table layout: Move | %games | count | W/D/L bar.
 * Appends a summary row (sigma) when multiple moves exist.
 */
public class ExplorerMoveAdapter extends ArrayAdapter<ExplorerMove> {
    private final LayoutInflater inflater;
    private final ArrayList<ExplorerMove> moves;
    private long totalAllGames = 0;    // sum of all move totals for percentage calculation
    private long sumWhite = 0, sumDraws = 0, sumBlack = 0; // for summary row
    private boolean hasSummary = false;

    public ExplorerMoveAdapter(Context context, ArrayList<ExplorerMove> moves) {
        super(context, R.layout.explorer_move_row, moves);
        this.inflater = LayoutInflater.from(context);
        this.moves = moves;
    }

    /** Replace all data and refresh the list. */
    public void updateMoves(ExplorerResult result) {
        moves.clear();
        totalAllGames = 0;
        sumWhite = 0;
        sumDraws = 0;
        sumBlack = 0;
        hasSummary = false;
        if (result != null && result.moves != null) {
            moves.addAll(result.moves);
            sumWhite = result.totalWhite;
            sumDraws = result.totalDraws;
            sumBlack = result.totalBlack;
            totalAllGames = sumWhite + sumDraws + sumBlack;
            hasSummary = moves.size() > 1;
        }
        notifyDataSetChanged();
    }

    @Override
    public int getCount() {
        return moves.size() + (hasSummary ? 1 : 0);
    }

    @Override
    public ExplorerMove getItem(int position) {
        if (position < moves.size())
            return moves.get(position);
        return null; // summary row
    }

    @Override
    public boolean isEnabled(int position) {
        return position < moves.size(); // summary row not clickable
    }

    @Override
    public View getView(int position, View convertView, ViewGroup parent) {
        ViewHolder holder;
        if (convertView == null) {
            convertView = inflater.inflate(R.layout.explorer_move_row, parent, false);
            holder = new ViewHolder();
            holder.san = convertView.findViewById(R.id.moveSan);
            holder.gamePct = convertView.findViewById(R.id.gamePct);
            holder.gameCount = convertView.findViewById(R.id.gameCount);
            holder.wdlBar = convertView.findViewById(R.id.wdlBar);
            convertView.setTag(holder);
        } else {
            holder = (ViewHolder) convertView.getTag();
        }

        boolean isSummary = hasSummary && position == moves.size();

        if (isSummary) {
            // Summary row
            holder.san.setText("\u03A3"); // sigma
            holder.san.setTypeface(null, Typeface.NORMAL);
            long total = sumWhite + sumDraws + sumBlack;
            holder.gamePct.setText("");
            holder.gameCount.setText(LichessExplorerBook.formatNumber(total));
            if (total > 0) {
                int wPct = Math.round(sumWhite * 100f / total);
                int dPct = Math.round(sumDraws * 100f / total);
                int bPct = 100 - wPct - dPct;
                holder.wdlBar.setPercentages(wPct, dPct, bPct);
            } else {
                holder.wdlBar.setPercentages(0, 0, 0);
            }
            convertView.setBackgroundColor(0x1ABAB6AD);
        } else {
            // Regular move row
            ExplorerMove move = moves.get(position);
            holder.san.setText(move.san);
            holder.san.setTypeface(null, Typeface.BOLD);

            long moveTotal = move.totalGames();
            if (moveTotal > 0 && totalAllGames > 0) {
                int pct = Math.round(moveTotal * 100f / totalAllGames);
                holder.gamePct.setText(pct + "%");
                holder.gameCount.setText(LichessExplorerBook.formatNumber(moveTotal));
                int wPct = Math.round(move.white * 100f / moveTotal);
                int dPct = Math.round(move.draws * 100f / moveTotal);
                int bPct = 100 - wPct - dPct;
                holder.wdlBar.setPercentages(wPct, dPct, bPct);
            } else {
                holder.gamePct.setText("");
                holder.gameCount.setText("");
                holder.wdlBar.setPercentages(0, 0, 0);
            }
            convertView.setBackgroundColor(0x00000000);
        }

        return convertView;
    }

    private static class ViewHolder {
        TextView san;
        TextView gamePct;
        TextView gameCount;
        WDLBarView wdlBar;
    }
}

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

import android.app.AlertDialog;
import android.app.Dialog;
import android.content.Context;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.RadioGroup;
import android.widget.SeekBar;
import android.widget.Spinner;
import android.widget.TextView;

import org.petero.droidfish.GameMode;
import org.petero.droidfish.R;

/**
 * Quick Play dialog - lets user start a new game with minimal taps.
 *
 * Shows:
 * - Color selection (White/Black radio buttons)
 * - ELO strength slider (1320-3190 for Stockfish UCI_Elo range)
 * - Time control dropdown (Bullet/Blitz/Rapid/Classical presets)
 *
 * On "Start Game", calls the listener with the selected parameters.
 */
public class QuickPlayDialog {

    /** ELO range matching Stockfish UCI_Elo option. */
    private static final int MIN_ELO = 1320;
    private static final int MAX_ELO = 3190;

    /** Time control presets: name, time(ms), increment(ms). */
    private static final String[] TIME_LABELS = {
        "1 min (Bullet)",
        "3 min (Blitz)",
        "5 min (Blitz)",
        "10 min (Rapid)",
        "15+10 (Rapid)",
        "30 min (Classical)",
        "No time limit",
    };
    private static final int[][] TIME_VALUES = {
        {60000, 0},
        {180000, 0},
        {300000, 0},
        {600000, 0},
        {900000, 10000},
        {1800000, 0},
        {0, 0},  // 0 = no limit
    };

    /** Callback when user starts a game. */
    public interface QuickPlayListener {
        void onQuickPlay(int gameMode, int elo, int timeMs, int incrementMs);
    }

    /** Show the Quick Play dialog. */
    public static Dialog create(Context context, QuickPlayListener listener) {
        View content = View.inflate(context, R.layout.quick_play_dialog, null);

        RadioGroup colorGroup = content.findViewById(R.id.quick_play_color);
        SeekBar eloSeekBar = content.findViewById(R.id.quick_play_elo);
        TextView eloLabel = content.findViewById(R.id.quick_play_elo_label);
        Spinner timeSpinner = content.findViewById(R.id.quick_play_time);

        // ELO slider (0-100 maps to MIN_ELO-MAX_ELO)
        eloSeekBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                int elo = progressToElo(progress);
                eloLabel.setText("ELO: " + elo);
            }
            @Override
            public void onStartTrackingTouch(SeekBar seekBar) { }
            @Override
            public void onStopTrackingTouch(SeekBar seekBar) { }
        });
        eloSeekBar.setProgress(50);

        // Time control dropdown
        ArrayAdapter<String> adapter = new ArrayAdapter<>(
            context, android.R.layout.simple_spinner_item, TIME_LABELS);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        timeSpinner.setAdapter(adapter);
        timeSpinner.setSelection(2); // Default: 5 min

        AlertDialog.Builder builder = new AlertDialog.Builder(context);
        builder.setView(content);
        builder.setPositiveButton(R.string.start_game, (dialog, which) -> {
            // Determine game mode based on color selection
            int gameMode;
            if (colorGroup.getCheckedRadioButtonId() == R.id.quick_play_white) {
                gameMode = GameMode.PLAYER_WHITE;
            } else {
                gameMode = GameMode.PLAYER_BLACK;
            }

            int elo = progressToElo(eloSeekBar.getProgress());
            int timeIdx = timeSpinner.getSelectedItemPosition();
            int timeMs = TIME_VALUES[timeIdx][0];
            int incrementMs = TIME_VALUES[timeIdx][1];

            listener.onQuickPlay(gameMode, elo, timeMs, incrementMs);
        });
        builder.setNegativeButton(R.string.cancel, null);

        return builder.create();
    }

    /** Convert seekbar progress (0-100) to ELO rating. */
    static int progressToElo(int progress) {
        return MIN_ELO + (progress * (MAX_ELO - MIN_ELO)) / 100;
    }

    /** Convert ELO rating to seekbar progress (0-100). */
    static int eloToProgress(int elo) {
        return ((elo - MIN_ELO) * 100) / (MAX_ELO - MIN_ELO);
    }
}

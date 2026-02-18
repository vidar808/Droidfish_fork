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
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.AttributeSet;
import android.util.TypedValue;
import android.view.View;

/**
 * Horizontal stacked bar showing Win / Draw / Loss percentages.
 * Styled to match the Lichess opening explorer (dark theme).
 */
public class WDLBarView extends View {
    // Lichess dark-mode colors
    private static final int COLOR_WHITE_WINS = 0xFFCCCCCC;
    private static final int COLOR_DRAWS      = 0xFF666666;
    private static final int COLOR_BLACK_WINS  = 0xFF333333;
    private static final int COLOR_BORDER     = 0xFF555555;
    private static final int COLOR_TEXT_DARK  = 0xFF222222; // text on light segments
    private static final int COLOR_TEXT_LIGHT = 0xFFDDDDDD; // text on dark segments

    private int wPct = 0, dPct = 0, bPct = 0;
    private final Paint barPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint textPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint borderPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();

    public WDLBarView(Context context) {
        super(context);
        init();
    }

    public WDLBarView(Context context, AttributeSet attrs) {
        super(context, attrs);
        init();
    }

    public WDLBarView(Context context, AttributeSet attrs, int defStyleAttr) {
        super(context, attrs, defStyleAttr);
        init();
    }

    private void init() {
        textPaint.setTextSize(dpToPx(9));
        textPaint.setTextAlign(Paint.Align.CENTER);
        textPaint.setFakeBoldText(true);
        borderPaint.setColor(COLOR_BORDER);
        borderPaint.setStyle(Paint.Style.STROKE);
        borderPaint.setStrokeWidth(dpToPx(1));
    }

    public void setPercentages(int wPct, int dPct, int bPct) {
        this.wPct = wPct;
        this.dPct = dPct;
        this.bPct = bPct;
        invalidate();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        int w = getWidth();
        int h = getHeight();
        if (w <= 0 || h <= 0)
            return;

        int total = wPct + dPct + bPct;
        if (total <= 0)
            return;

        float wWidth = w * wPct / (float) total;
        float dWidth = w * dPct / (float) total;
        float bWidth = w - wWidth - dWidth;

        float textY = h / 2f - (textPaint.descent() + textPaint.ascent()) / 2f;
        float x = 0;

        // White wins
        if (wWidth > 0.5f) {
            barPaint.setColor(COLOR_WHITE_WINS);
            canvas.drawRect(x, 0, x + wWidth, h, barPaint);
            if (wPct >= 12) {
                textPaint.setColor(COLOR_TEXT_DARK);
                String label = wPct > 20 ? wPct + "%" : String.valueOf(wPct);
                canvas.drawText(label, x + wWidth / 2f, textY, textPaint);
            }
            x += wWidth;
        }

        // Draws
        if (dWidth > 0.5f) {
            barPaint.setColor(COLOR_DRAWS);
            canvas.drawRect(x, 0, x + dWidth, h, barPaint);
            if (dPct >= 12) {
                textPaint.setColor(COLOR_TEXT_LIGHT);
                String label = dPct > 20 ? dPct + "%" : String.valueOf(dPct);
                canvas.drawText(label, x + dWidth / 2f, textY, textPaint);
            }
            x += dWidth;
        }

        // Black wins
        if (bWidth > 0.5f) {
            barPaint.setColor(COLOR_BLACK_WINS);
            canvas.drawRect(x, 0, x + bWidth, h, barPaint);
            if (bPct >= 12) {
                textPaint.setColor(COLOR_TEXT_LIGHT);
                String label = bPct > 20 ? bPct + "%" : String.valueOf(bPct);
                canvas.drawText(label, x + bWidth / 2f, textY, textPaint);
            }
        }

        // Border
        rect.set(0, 0, w, h);
        canvas.drawRect(rect, borderPaint);
    }

    private float dpToPx(float dp) {
        return TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, dp,
                getResources().getDisplayMetrics());
    }
}

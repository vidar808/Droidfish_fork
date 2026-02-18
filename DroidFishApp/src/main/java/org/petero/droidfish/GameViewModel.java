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

package org.petero.droidfish;

import androidx.lifecycle.ViewModel;

import org.petero.droidfish.gamelogic.DroidChessController;

/**
 * ViewModel that holds game state across configuration changes (rotation).
 *
 * Since DroidFish declares android:configChanges for orientation, this
 * ViewModel primarily helps with:
 * - Surviving process death (when combined with SavedStateHandle)
 * - Decoupling game state from Activity lifecycle
 * - Providing a clean holder for the chess controller
 *
 * The DroidChessController manages all game logic, engine communication,
 * and game tree state. By hosting it in a ViewModel, we ensure it survives
 * any Activity recreation Android may trigger.
 */
public class GameViewModel extends ViewModel {

    /** The chess controller - persists across config changes. */
    private DroidChessController ctrl;

    /** Serialized game state from last save. */
    private byte[] savedGameState;

    /** Serialization version for state format compatibility. */
    private int savedGameStateVersion = 1;

    /** Whether the controller has been initialized for this session. */
    private boolean initialized = false;

    public DroidChessController getCtrl() {
        return ctrl;
    }

    public void setCtrl(DroidChessController ctrl) {
        this.ctrl = ctrl;
        this.initialized = true;
    }

    public boolean isInitialized() {
        return initialized;
    }

    /** Save game state for process death recovery. */
    public void saveGameState() {
        if (ctrl != null) {
            savedGameState = ctrl.toByteArray();
        }
    }

    /** Get saved game state bytes. */
    public byte[] getSavedGameState() {
        return savedGameState;
    }

    /** Set saved game state from Bundle restoration. */
    public void setSavedGameState(byte[] data, int version) {
        this.savedGameState = data;
        this.savedGameStateVersion = version;
    }

    public int getSavedGameStateVersion() {
        return savedGameStateVersion;
    }

    /** Restore controller state from saved data. */
    public boolean restoreGameState() {
        if (ctrl != null && savedGameState != null) {
            ctrl.fromByteArray(savedGameState, savedGameStateVersion);
            return true;
        }
        return false;
    }

    @Override
    protected void onCleared() {
        super.onCleared();
        if (ctrl != null) {
            ctrl.shutdownEngine();
        }
    }
}

package org.petero.droidfish.engine;

import org.junit.Test;
import static org.junit.Assert.*;

public class UCIOptionsTest {

    @Test
    public void testCheckOption() {
        UCIOptions.CheckOption opt = new UCIOptions.CheckOption("Ponder", true);
        assertEquals("Ponder", opt.name);
        assertEquals(UCIOptions.Type.CHECK, opt.type);
        assertTrue(opt.value);
        assertTrue(opt.defaultValue);
        assertFalse(opt.modified());
        assertEquals("true", opt.getStringValue());

        assertTrue(opt.set(false));
        assertFalse(opt.value);
        assertTrue(opt.modified());
        assertEquals("false", opt.getStringValue());

        assertFalse(opt.set(false)); // no change
    }

    @Test
    public void testSpinOption() {
        UCIOptions.SpinOption opt = new UCIOptions.SpinOption("Hash", 1, 1024, 16);
        assertEquals("Hash", opt.name);
        assertEquals(UCIOptions.Type.SPIN, opt.type);
        assertEquals(16, opt.value);
        assertEquals(1, opt.minValue);
        assertEquals(1024, opt.maxValue);
        assertFalse(opt.modified());
        assertEquals("16", opt.getStringValue());

        assertTrue(opt.set(256));
        assertEquals(256, opt.value);
        assertTrue(opt.modified());
        assertEquals("256", opt.getStringValue());

        assertFalse(opt.set(256)); // no change
    }

    @Test
    public void testSpinOptionBounds() {
        UCIOptions.SpinOption opt = new UCIOptions.SpinOption("Threads", 1, 128, 1);

        assertFalse(opt.set(0));   // below min
        assertEquals(1, opt.value);

        assertFalse(opt.set(129)); // above max
        assertEquals(1, opt.value);

        assertTrue(opt.set(1));    // at min (but same as default)
        assertFalse(opt.modified());

        assertTrue(opt.set(128)); // at max
        assertEquals(128, opt.value);
    }

    @Test
    public void testComboOption() {
        String[] allowed = {"var1", "var2", "var3"};
        UCIOptions.ComboOption opt = new UCIOptions.ComboOption("Style", allowed, "var1");
        assertEquals("var1", opt.value);
        assertFalse(opt.modified());

        assertTrue(opt.set("var2"));
        assertEquals("var2", opt.value);
        assertTrue(opt.modified());

        assertFalse(opt.set("var2")); // no change
        assertFalse(opt.set("invalid")); // not in allowed
    }

    @Test
    public void testComboOptionCaseInsensitive() {
        String[] allowed = {"Normal", "Aggressive"};
        UCIOptions.ComboOption opt = new UCIOptions.ComboOption("Style", allowed, "Normal");

        assertTrue(opt.set("aggressive"));
        assertEquals("Aggressive", opt.value); // preserves original case
    }

    @Test
    public void testButtonOption() {
        UCIOptions.ButtonOption opt = new UCIOptions.ButtonOption("Clear Hash");
        assertEquals("Clear Hash", opt.name);
        assertEquals(UCIOptions.Type.BUTTON, opt.type);
        assertFalse(opt.modified());
        assertEquals("", opt.getStringValue());
    }

    @Test
    public void testStringOption() {
        UCIOptions.StringOption opt = new UCIOptions.StringOption("SyzygyPath", "/path");
        assertEquals("/path", opt.value);
        assertFalse(opt.modified());

        assertTrue(opt.set("/new/path"));
        assertEquals("/new/path", opt.value);
        assertTrue(opt.modified());

        assertFalse(opt.set("/new/path")); // no change
    }

    @Test
    public void testSetFromStringCheck() {
        UCIOptions.CheckOption opt = new UCIOptions.CheckOption("Ponder", false);
        assertTrue(opt.setFromString("true"));
        assertTrue(opt.value);
        assertTrue(opt.setFromString("false"));
        assertFalse(opt.value);
        assertFalse(opt.setFromString("invalid"));
    }

    @Test
    public void testSetFromStringSpin() {
        UCIOptions.SpinOption opt = new UCIOptions.SpinOption("Hash", 1, 1024, 16);
        assertTrue(opt.setFromString("256"));
        assertEquals(256, opt.value);
        assertFalse(opt.setFromString("not_a_number"));
    }

    @Test
    public void testSetFromStringCombo() {
        String[] allowed = {"a", "b"};
        UCIOptions.ComboOption opt = new UCIOptions.ComboOption("X", allowed, "a");
        assertTrue(opt.setFromString("b"));
        assertEquals("b", opt.value);
        assertFalse(opt.setFromString("c"));
    }

    @Test
    public void testSetFromStringButton() {
        UCIOptions.ButtonOption opt = new UCIOptions.ButtonOption("Clear");
        assertFalse(opt.setFromString("anything"));
    }

    @Test
    public void testSetFromStringString() {
        UCIOptions.StringOption opt = new UCIOptions.StringOption("Path", "old");
        assertTrue(opt.setFromString("new"));
        assertEquals("new", opt.value);
    }

    @Test
    public void testUCIOptionsAddAndGet() {
        UCIOptions options = new UCIOptions();
        UCIOptions.SpinOption spin = new UCIOptions.SpinOption("Hash", 1, 1024, 16);
        UCIOptions.CheckOption check = new UCIOptions.CheckOption("Ponder", true);

        options.addOption(spin);
        options.addOption(check);

        assertTrue(options.contains("Hash"));
        assertTrue(options.contains("hash")); // case insensitive
        assertTrue(options.contains("Ponder"));
        assertFalse(options.contains("Nonexistent"));

        assertNotNull(options.getOption("hash"));
        assertEquals("Hash", options.getOption("hash").name);
    }

    @Test
    public void testUCIOptionsGetNames() {
        UCIOptions options = new UCIOptions();
        options.addOption(new UCIOptions.SpinOption("Hash", 1, 1024, 16));
        options.addOption(new UCIOptions.CheckOption("Ponder", true));

        String[] names = options.getOptionNames();
        assertEquals(2, names.length);
        assertEquals("hash", names[0]);
        assertEquals("ponder", names[1]);
    }

    @Test
    public void testUCIOptionsClear() {
        UCIOptions options = new UCIOptions();
        options.addOption(new UCIOptions.SpinOption("Hash", 1, 1024, 16));
        assertTrue(options.contains("Hash"));

        options.clear();
        assertFalse(options.contains("Hash"));
        assertEquals(0, options.getOptionNames().length);
    }

    @Test
    public void testUCIOptionsClone() throws Exception {
        UCIOptions options = new UCIOptions();
        UCIOptions.SpinOption spin = new UCIOptions.SpinOption("Hash", 1, 1024, 16);
        options.addOption(spin);

        UCIOptions cloned = options.clone();
        assertNotNull(cloned.getOption("hash"));

        // Modifying clone should not affect original
        UCIOptions.SpinOption clonedSpin = (UCIOptions.SpinOption) cloned.getOption("hash");
        clonedSpin.set(512);
        assertEquals(16, ((UCIOptions.SpinOption) options.getOption("hash")).value);
        assertEquals(512, clonedSpin.value);
    }
}

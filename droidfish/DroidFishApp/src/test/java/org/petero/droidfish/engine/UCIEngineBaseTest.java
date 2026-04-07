package org.petero.droidfish.engine;

import org.junit.Before;
import org.junit.Test;
import static org.junit.Assert.*;

import java.io.File;

/** Tests for UCIEngineBase option registration parsing. */
public class UCIEngineBaseTest {

    /** Minimal concrete implementation for testing registerOption. */
    private static class TestEngine extends UCIEngineBase {
        @Override protected void startProcess() {}
        @Override protected File getOptionsFile() { return new File("/dev/null"); }
        @Override public String readLineFromEngine(int timeoutMillis) { return null; }
        @Override public void writeLineToEngine(String data) {}
        @Override public boolean optionsOk(org.petero.droidfish.EngineOptions eo) { return true; }
    }

    private TestEngine engine;

    @Before
    public void setUp() {
        engine = new TestEngine();
    }

    @Test
    public void testRegisterCheckOption() {
        String[] tokens = "option name Ponder type check default true".split(" ");
        UCIOptions.OptionBase opt = engine.registerOption(tokens);

        assertNotNull(opt);
        assertTrue(opt instanceof UCIOptions.CheckOption);
        assertEquals("Ponder", opt.name);
        UCIOptions.CheckOption check = (UCIOptions.CheckOption) opt;
        assertTrue(check.defaultValue);
        assertTrue(check.value);
    }

    @Test
    public void testRegisterCheckOptionFalse() {
        String[] tokens = "option name UCI_AnalyseMode type check default false".split(" ");
        UCIOptions.OptionBase opt = engine.registerOption(tokens);

        assertNotNull(opt);
        UCIOptions.CheckOption check = (UCIOptions.CheckOption) opt;
        assertFalse(check.defaultValue);
    }

    @Test
    public void testRegisterSpinOption() {
        String[] tokens = "option name Hash type spin default 16 min 1 max 1024".split(" ");
        UCIOptions.OptionBase opt = engine.registerOption(tokens);

        assertNotNull(opt);
        assertTrue(opt instanceof UCIOptions.SpinOption);
        UCIOptions.SpinOption spin = (UCIOptions.SpinOption) opt;
        assertEquals("Hash", spin.name);
        assertEquals(16, spin.defaultValue);
        assertEquals(1, spin.minValue);
        assertEquals(1024, spin.maxValue);
    }

    @Test
    public void testRegisterSpinOptionLargeValues() {
        String[] tokens = "option name Threads type spin default 1 min 1 max 512".split(" ");
        UCIOptions.OptionBase opt = engine.registerOption(tokens);

        assertNotNull(opt);
        UCIOptions.SpinOption spin = (UCIOptions.SpinOption) opt;
        assertEquals(1, spin.defaultValue);
        assertEquals(512, spin.maxValue);
    }

    @Test
    public void testRegisterComboOption() {
        String[] tokens = "option name Style type combo default Normal var Solid var Normal var Risky".split(" ");
        UCIOptions.OptionBase opt = engine.registerOption(tokens);

        assertNotNull(opt);
        assertTrue(opt instanceof UCIOptions.ComboOption);
        UCIOptions.ComboOption combo = (UCIOptions.ComboOption) opt;
        assertEquals("Normal", combo.defaultValue);
        assertEquals(3, combo.allowedValues.length);
        assertEquals("Solid", combo.allowedValues[0]);
        assertEquals("Normal", combo.allowedValues[1]);
        assertEquals("Risky", combo.allowedValues[2]);
    }

    @Test
    public void testRegisterButtonOption() {
        String[] tokens = "option name Clear Hash type button".split(" ");
        UCIOptions.OptionBase opt = engine.registerOption(tokens);

        assertNotNull(opt);
        assertTrue(opt instanceof UCIOptions.ButtonOption);
        assertEquals("Clear Hash", opt.name);
    }

    @Test
    public void testRegisterStringOption() {
        String[] tokens = "option name SyzygyPath type string default <empty>".split(" ");
        UCIOptions.OptionBase opt = engine.registerOption(tokens);

        assertNotNull(opt);
        assertTrue(opt instanceof UCIOptions.StringOption);
        UCIOptions.StringOption str = (UCIOptions.StringOption) opt;
        assertEquals("<empty>", str.defaultValue);
    }

    @Test
    public void testRegisterMultiWordName() {
        String[] tokens = "option name Skill Level type spin default 20 min 0 max 20".split(" ");
        UCIOptions.OptionBase opt = engine.registerOption(tokens);

        assertNotNull(opt);
        assertEquals("Skill Level", opt.name);
    }

    @Test
    public void testRegisterInvalidInput() {
        // Too few tokens
        String[] tokens = "option name".split(" ");
        UCIOptions.OptionBase opt = engine.registerOption(tokens);
        assertNull(opt);
    }

    @Test
    public void testRegisterMissingName() {
        String[] tokens = "option type spin default 1 min 0 max 10".split(" ");
        UCIOptions.OptionBase opt = engine.registerOption(tokens);
        assertNull(opt); // missing "name" keyword
    }

    @Test
    public void testRegisteredOptionsAccessible() {
        String[] tokens1 = "option name Hash type spin default 16 min 1 max 1024".split(" ");
        String[] tokens2 = "option name Ponder type check default true".split(" ");
        engine.registerOption(tokens1);
        engine.registerOption(tokens2);

        UCIOptions options = engine.getUCIOptions();
        assertTrue(options.contains("Hash"));
        assertTrue(options.contains("Ponder"));
        assertEquals(2, options.getOptionNames().length);
    }

    @Test
    public void testClearOptions() {
        String[] tokens = "option name Hash type spin default 16 min 1 max 1024".split(" ");
        engine.registerOption(tokens);
        assertTrue(engine.getUCIOptions().contains("Hash"));

        engine.clearOptions();
        assertFalse(engine.getUCIOptions().contains("Hash"));
    }

    @Test
    public void testEditableOptionFilters() {
        // UCI_ options should not be visible
        String[] tokens = "option name UCI_LimitStrength type check default false".split(" ");
        UCIOptions.OptionBase opt = engine.registerOption(tokens);
        assertNotNull(opt);
        assertFalse(opt.visible);

        // Hash should not be visible (in ignored list)
        tokens = "option name Hash type spin default 16 min 1 max 1024".split(" ");
        opt = engine.registerOption(tokens);
        assertNotNull(opt);
        assertFalse(opt.visible);

        // Regular option should be visible
        tokens = "option name Contempt type spin default 0 min -100 max 100".split(" ");
        opt = engine.registerOption(tokens);
        assertNotNull(opt);
        assertTrue(opt.visible);
    }
}

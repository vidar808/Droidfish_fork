package org.petero.droidfish.engine;

import org.junit.Test;
import static org.junit.Assert.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class LocalPipeTest {

    @Test
    public void testBasicReadWrite() {
        LocalPipe pipe = new LocalPipe();
        pipe.addLine("hello");
        pipe.addLine("world");
        assertEquals("hello", pipe.readLine(100));
        assertEquals("world", pipe.readLine(100));
    }

    @Test
    public void testReadLineTimeout() {
        LocalPipe pipe = new LocalPipe();
        long start = System.currentTimeMillis();
        String result = pipe.readLine(50);
        long elapsed = System.currentTimeMillis() - start;
        assertEquals("", result);
        assertTrue("Timeout should take at least 40ms, took " + elapsed, elapsed >= 40);
    }

    @Test
    public void testReadLineNoTimeout() {
        LocalPipe pipe = new LocalPipe();
        pipe.addLine("data");
        String result = pipe.readLine(1000);
        assertEquals("data", result);
    }

    @Test
    public void testCloseReturnsNull() {
        LocalPipe pipe = new LocalPipe();
        pipe.close();
        assertNull(pipe.readLine(100));
        assertNull(pipe.readLine());
    }

    @Test
    public void testIsClosed() {
        LocalPipe pipe = new LocalPipe();
        assertFalse(pipe.isClosed());
        pipe.close();
        assertTrue(pipe.isClosed());
    }

    @Test
    public void testPrintLine() {
        LocalPipe pipe = new LocalPipe();
        pipe.printLine("test %d %s", 42, "abc");
        assertEquals("test 42 abc", pipe.readLine(100));
    }

    @Test
    public void testPrintLineNoArgs() {
        LocalPipe pipe = new LocalPipe();
        pipe.printLine("simple line");
        assertEquals("simple line", pipe.readLine(100));
    }

    @Test
    public void testConcurrentReadWrite() throws Exception {
        LocalPipe pipe = new LocalPipe();
        int numLines = 1000;
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<String> error = new AtomicReference<>(null);

        Thread writer = new Thread(() -> {
            for (int i = 0; i < numLines; i++) {
                pipe.addLine("line-" + i);
            }
        });

        Thread reader = new Thread(() -> {
            try {
                for (int i = 0; i < numLines; i++) {
                    String line = pipe.readLine(5000);
                    if (line == null) {
                        error.set("Unexpected null at index " + i);
                        return;
                    }
                    if (!line.equals("line-" + i)) {
                        error.set("Expected line-" + i + " but got " + line);
                        return;
                    }
                }
                done.countDown();
            } catch (Exception e) {
                error.set("Exception: " + e.getMessage());
            }
        });

        reader.start();
        writer.start();
        writer.join(5000);
        reader.join(5000);

        assertNull(error.get(), error.get());
        assertEquals(0, done.getCount());
    }

    @Test
    public void testEmptyLineHandling() {
        LocalPipe pipe = new LocalPipe();
        pipe.addLine("");
        String result = pipe.readLine(100);
        assertEquals("", result);
    }

    @Test
    public void testCloseWakesReader() throws Exception {
        LocalPipe pipe = new LocalPipe();
        AtomicReference<String> result = new AtomicReference<>("not-set");

        Thread reader = new Thread(() -> {
            result.set(pipe.readLine());
        });
        reader.start();
        Thread.sleep(50);
        pipe.close();
        reader.join(1000);

        assertNull(result.get());
    }

    @Test
    public void testReadBeforeWrite() throws Exception {
        LocalPipe pipe = new LocalPipe();
        AtomicReference<String> result = new AtomicReference<>(null);

        Thread reader = new Thread(() -> {
            result.set(pipe.readLine(2000));
        });
        reader.start();
        Thread.sleep(50);
        pipe.addLine("delayed");
        reader.join(2000);

        assertEquals("delayed", result.get());
    }
}

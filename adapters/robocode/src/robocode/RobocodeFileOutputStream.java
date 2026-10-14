package robocode;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;

/** Writing a file in the robot's data directory (getDataFile()). */
public class RobocodeFileOutputStream extends OutputStream {
    private final FileOutputStream out;

    public RobocodeFileOutputStream(String name) throws IOException { this(new File(name), false); }

    public RobocodeFileOutputStream(String name, boolean append) throws IOException { this(new File(name), append); }

    public RobocodeFileOutputStream(File file) throws IOException { this(file, false); }

    public RobocodeFileOutputStream(File file, boolean append) throws IOException {
        if (file.getParentFile() != null) file.getParentFile().mkdirs();
        out = new FileOutputStream(file, append);
    }

    @Override public void write(int b) throws IOException { out.write(b); }
    @Override public void write(byte[] b, int off, int len) throws IOException { out.write(b, off, len); }
    @Override public void flush() throws IOException { out.flush(); }
    @Override public void close() throws IOException { out.close(); }
    public String getName() { return ""; }
}

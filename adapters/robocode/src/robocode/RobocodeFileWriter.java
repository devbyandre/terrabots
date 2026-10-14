package robocode;

import java.io.File;
import java.io.IOException;
import java.io.OutputStreamWriter;

/** Writing text into the robot's data directory. */
public class RobocodeFileWriter extends OutputStreamWriter {
    public RobocodeFileWriter(String name) throws IOException { super(new RobocodeFileOutputStream(name)); }
    public RobocodeFileWriter(String name, boolean append) throws IOException { super(new RobocodeFileOutputStream(name, append)); }
    public RobocodeFileWriter(File file) throws IOException { super(new RobocodeFileOutputStream(file)); }
}

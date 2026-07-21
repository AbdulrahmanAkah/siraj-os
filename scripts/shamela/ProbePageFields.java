import org.apache.lucene.index.*;
import org.apache.lucene.store.*;
import java.nio.file.*;

public class ProbePageFields {

    public static void main(String[] args) throws Exception {

        Directory dir =
            FSDirectory.open(Paths.get(args[0]));

        DirectoryReader reader =
            DirectoryReader.open(dir);

        FieldInfos infos =
            FieldInfos.getMergedFieldInfos(reader);

        for (FieldInfo f : infos) {

            System.out.println(
                f.name
                + " | index="
                + f.getIndexOptions()
                + " | dv="
                + f.getDocValuesType()
            );
        }

        reader.close();
        dir.close();
    }
}
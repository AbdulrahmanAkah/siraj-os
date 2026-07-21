import org.apache.lucene.index.*;
import org.apache.lucene.store.*;
import java.nio.file.*;
import java.io.*;

public class ReadShamelaBodyStoreSample {

    public static void main(String[] args) throws Exception {

        String indexPath = args[0];
        String outputPath = args[1];
        String targetId = args[2];

        Directory dir = FSDirectory.open(Paths.get(indexPath));
        DirectoryReader reader = DirectoryReader.open(dir);

        BufferedWriter out = new BufferedWriter(
            new OutputStreamWriter(
                new FileOutputStream(outputPath),
                "UTF-8"
            )
        );

        int matched = 0;

        for (int i = 0; i < reader.maxDoc(); i++) {

            Document doc = reader.document(i);

            String id = doc.get("id");

            if (id == null || !id.equals(targetId))
                continue;

            String body = doc.get("body_store");

            if (body == null)
                continue;

            out.write("{\"doc_id\":" + i +
                    ",\"book_id\":\"" + id +
                    "\",\"length\":" + body.length() +
                    ",\"text\":\"");

            out.write(
                body
                .replace("\\","\\\\")
                .replace("\"","\\\"")
                .replace("\n","\\n")
                .replace("\r","\\r")
            );

            out.write("\"}");
            out.newLine();

            matched++;

            if (matched >= 10)
                break;
        }

        out.close();
        reader.close();
        dir.close();

        System.out.println(
            "BODY_STORE_EXTRACTION_COMPLETE segments=" + matched
        );
    }
}

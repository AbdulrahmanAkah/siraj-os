import org.apache.lucene.index.*;
import org.apache.lucene.store.*;
import org.apache.lucene.document.*;
import java.nio.file.*;

public class ProbePageDocs {

    public static void main(String[] args) throws Exception {

        Directory dir =
            FSDirectory.open(Paths.get(args[0]));

        DirectoryReader reader =
            DirectoryReader.open(dir);

        StoredFields stored = reader.storedFields();

        for(int i=0;i<10;i++){

            Document doc = stored.document(i);

            System.out.println("DOC="+i);
            System.out.println("book="+doc.get("book"));
            System.out.println("book_key="+doc.get("book_key"));
            System.out.println("id="+doc.get("id"));
            System.out.println("page="+doc.get("page"));
            System.out.println("body="+
                (doc.get("body")==null ? "NULL" : doc.get("body").substring(0,100))
            );
            System.out.println("----------------");
        }

        reader.close();
        dir.close();
    }
}
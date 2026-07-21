import org.apache.lucene.index.*;
import org.apache.lucene.store.*;
import org.apache.lucene.document.*;
import java.nio.file.*;

public class ReadPageSample {

    public static void main(String[] args) throws Exception {

        Directory dir =
            FSDirectory.open(Paths.get(args[0]));

        DirectoryReader reader =
            DirectoryReader.open(dir);

        StoredFields stored = reader.storedFields();

        String targetBook=args[1];

        int found=0;

        for(int i=0;i<reader.maxDoc();i++){

            Document doc=stored.document(i);

            String book=doc.get("book");

            if(book==null)
                continue;

            if(!book.equals(targetBook))
                continue;


            System.out.println("DOC="+i);
            System.out.println("BOOK="+book);
            System.out.println("ID="+doc.get("id"));
            System.out.println("PAGE="+doc.get("page"));
            System.out.println("BODY=");
            System.out.println(doc.get("body"));

            System.out.println("---------------------");

            found++;

            if(found>=3)
                break;
        }

        System.out.println("FOUND="+found);

        reader.close();
        dir.close();
    }
}
import org.apache.lucene.index.*;
import org.apache.lucene.store.*;
import org.apache.lucene.document.*;
import org.apache.lucene.util.*;
import java.nio.file.*;
import java.io.*;

public class ExtractBookRawFixed {

    public static void main(String[] args) throws Exception {

        Directory dir =
            FSDirectory.open(Paths.get(args[0]));

        DirectoryReader reader =
            DirectoryReader.open(dir);

        StoredFields stored =
            reader.storedFields();

        String bookId=args[1];

        BufferedWriter out =
            new BufferedWriter(
                new OutputStreamWriter(
                    new FileOutputStream(args[2]),
                    "UTF-8"
                )
            );

        int count=0;

        for(int i=0;i<reader.maxDoc();i++){

            Document doc=stored.document(i);

            String id=doc.get("id");

            if(id==null || !id.startsWith(bookId+"-"))
                continue;


            String body=doc.get("body");


            out.write("===PAGE "+id+"===\n");
            out.write(body==null ? "" : body);
            out.write("\n\n");


            count++;

            if(count>=3)
                break;
        }

        out.close();

        System.out.println("EXTRACTED="+count);

        reader.close();
        dir.close();
    }
}
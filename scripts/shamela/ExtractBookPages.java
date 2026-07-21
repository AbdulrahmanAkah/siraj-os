import org.apache.lucene.index.*;
import org.apache.lucene.store.*;
import org.apache.lucene.document.*;
import java.nio.file.*;
import java.io.*;

public class ExtractBookPages {

    public static void main(String[] args) throws Exception {

        Directory dir =
            FSDirectory.open(Paths.get(args[0]));

        DirectoryReader reader =
            DirectoryReader.open(dir);

        StoredFields stored =
            reader.storedFields();

        String bookId=args[1];
        String output=args[2];

        BufferedWriter out =
            new BufferedWriter(
                new OutputStreamWriter(
                    new FileOutputStream(output),
                    "UTF-8"
                )
            );

        int count=0;

        for(int i=0;i<reader.maxDoc();i++){

            Document doc =
                stored.document(i);

            String id =
                doc.get("id");

            if(id==null)
                continue;

            if(!id.startsWith(bookId+"-"))
                continue;


            String body =
                doc.get("body");


            out.write(
                "{\"id\":\""+id+
                "\",\"text\":\""+
                body
                .replace("\\","\\\\")
                .replace("\"","\\\"")
                .replace("\n","\\n")
                +"\"}"
            );

            out.newLine();

            count++;

            if(count>=10)
                break;
        }

        out.close();

        System.out.println(
            "EXTRACTED="+count
        );

        reader.close();
        dir.close();
    }
}
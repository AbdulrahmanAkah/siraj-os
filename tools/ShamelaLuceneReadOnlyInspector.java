import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.lucene.document.Document;
import org.apache.lucene.index.DirectoryReader;
import org.apache.lucene.index.FieldInfo;
import org.apache.lucene.index.FieldInfos;
import org.apache.lucene.index.IndexableField;
import org.apache.lucene.store.Directory;
import org.apache.lucene.store.FSDirectory;
import org.apache.lucene.util.BytesRef;

/**
 * Minimal read-only inspector for a local Shamela Lucene index.
 *
 * The tool never creates an IndexWriter and limits stored-value output to a
 * small, caller-supplied character count. It exists only to support the local
 * discovery report; it is not a source adapter.
 */
public final class ShamelaLuceneReadOnlyInspector {
    private ShamelaLuceneReadOnlyInspector() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 3) {
            throw new IllegalArgumentException(
                "usage: ShamelaLuceneReadOnlyInspector <index-path> [document-limit] [text-limit]"
            );
        }

        Path indexPath = Path.of(args[0]).toAbsolutePath().normalize();
        int documentLimit = args.length >= 2 ? Integer.parseInt(args[1]) : 3;
        int textLimit = args.length >= 3 ? Integer.parseInt(args[2]) : 160;
        if (documentLimit < 0 || documentLimit > 10 || textLimit < 0 || textLimit > 500) {
            throw new IllegalArgumentException("inspection limits exceed the read-only discovery bounds");
        }

        try (Directory directory = FSDirectory.open(indexPath);
             DirectoryReader reader = DirectoryReader.open(directory)) {
            List<Map<String, Object>> fields = new ArrayList<>();
            FieldInfos infos = FieldInfos.getMergedFieldInfos(reader);
            for (FieldInfo info : infos) {
                Map<String, Object> field = new LinkedHashMap<>();
                field.put("name", info.name);
                field.put("index_options", info.getIndexOptions().name());
                field.put("doc_values_type", info.getDocValuesType().name());
                field.put("has_vectors", info.hasVectors());
                fields.add(field);
            }
            fields.sort(Comparator.comparing(value -> value.get("name").toString()));

            List<Map<String, Object>> documents = new ArrayList<>();
            int inspected = 0;
            for (int docId = 0; docId < reader.maxDoc() && inspected < documentLimit; docId++) {
                Document document = reader.storedFields().document(docId);
                Map<String, Object> values = new LinkedHashMap<>();
                for (IndexableField field : document.getFields()) {
                    String rendered;
                    if (field.stringValue() != null) {
                        rendered = field.stringValue();
                    } else if (field.numericValue() != null) {
                        rendered = field.numericValue().toString();
                    } else {
                        BytesRef binary = field.binaryValue();
                        rendered = binary == null
                            ? ""
                            : new String(binary.bytes, binary.offset, binary.length, StandardCharsets.UTF_8);
                    }
                    rendered = rendered.replace('\r', ' ').replace('\n', ' ');
                    if (rendered.length() > textLimit) {
                        rendered = rendered.substring(0, textLimit);
                    }
                    values.put(field.name(), rendered);
                }
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("lucene_doc_id", docId);
                item.put("stored_fields", values);
                documents.add(item);
                inspected++;
            }

            StringBuilder json = new StringBuilder();
            json.append("{\n");
            json.append("  \"index_path\": \"").append(escape(indexPath.toString())).append("\",\n");
            json.append("  \"document_count\": ").append(reader.numDocs()).append(",\n");
            json.append("  \"max_document_id\": ").append(reader.maxDoc()).append(",\n");
            json.append("  \"fields\": ").append(toJson(fields)).append(",\n");
            json.append("  \"sample_documents\": ").append(toJson(documents)).append("\n");
            json.append("}\n");
            System.out.print(json);
        }
    }

    private static String toJson(Object value) {
        if (value == null) return "null";
        if (value instanceof Boolean || value instanceof Number) return value.toString();
        if (value instanceof String string) return "\"" + escape(string) + "\"";
        if (value instanceof Map<?, ?> map) {
            StringBuilder result = new StringBuilder("{");
            boolean first = true;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!first) result.append(',');
                first = false;
                result.append(toJson(entry.getKey().toString())).append(':').append(toJson(entry.getValue()));
            }
            return result.append('}').toString();
        }
        if (value instanceof Iterable<?> iterable) {
            StringBuilder result = new StringBuilder("[");
            boolean first = true;
            for (Object item : iterable) {
                if (!first) result.append(',');
                first = false;
                result.append(toJson(item));
            }
            return result.append(']').toString();
        }
        return toJson(value.toString());
    }

    private static String escape(String value) {
        return value
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\b", "\\b")
            .replace("\f", "\\f")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t");
    }
}

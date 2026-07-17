"""Bounded read-only access to the Lucene indexes bundled with Shamela.

The local Shamela distribution contains a Java runtime and Lucene jars but not
the Java compiler.  The bridge emits one tiny class into a temporary directory
outside the Shamela installation, opens DirectoryReader only, and streams
stored fields for a single exact ``book_key``.  It never creates IndexWriter,
locks, indexes, repairs, or mutates the source directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import struct
import subprocess
import tempfile
from typing import Iterable


class LuceneUnavailableError(RuntimeError):
    """Raised when the installed read-only Lucene runtime cannot be used."""


@dataclass(frozen=True)
class LuceneStoredDocument:
    document_id: str
    body: str
    foot: str | None


class _ConstantPool:
    def __init__(self) -> None:
        self._entries: list[bytes] = []
        self._cache: dict[tuple[object, ...], int] = {}

    @staticmethod
    def _u1(value: int) -> bytes:
        return struct.pack(">B", value)

    @staticmethod
    def _u2(value: int) -> bytes:
        return struct.pack(">H", value)

    def _add(self, key: tuple[object, ...], value: bytes) -> int:
        if key not in self._cache:
            self._entries.append(value)
            self._cache[key] = len(self._entries)
        return self._cache[key]

    def utf8(self, value: str) -> int:
        encoded = value.encode("utf-8")
        return self._add(("utf8", value), self._u1(1) + self._u2(len(encoded)) + encoded)

    def class_(self, value: str) -> int:
        return self._add(("class", value), self._u1(7) + self._u2(self.utf8(value)))

    def string(self, value: str) -> int:
        return self._add(("string", value), self._u1(8) + self._u2(self.utf8(value)))

    def name_type(self, name: str, descriptor: str) -> int:
        return self._add(
            ("name_type", name, descriptor),
            self._u1(12) + self._u2(self.utf8(name)) + self._u2(self.utf8(descriptor)),
        )

    def method(self, owner: str, name: str, descriptor: str) -> int:
        return self._add(
            ("method", owner, name, descriptor),
            self._u1(10) + self._u2(self.class_(owner)) + self._u2(self.name_type(name, descriptor)),
        )

    def field(self, owner: str, name: str, descriptor: str) -> int:
        return self._add(
            ("field", owner, name, descriptor),
            self._u1(9) + self._u2(self.class_(owner)) + self._u2(self.name_type(name, descriptor)),
        )

    def render(self) -> bytes:
        return self._u2(len(self._entries) + 1) + b"".join(self._entries)


def _u1(value: int) -> bytes:
    return struct.pack(">B", value)


def _u2(value: int) -> bytes:
    return struct.pack(">H", value)


def _u4(value: int) -> bytes:
    return struct.pack(">I", value)


def _instruction(opcode: int, index: int | None = None) -> bytes:
    return _u1(opcode) if index is None else _u1(opcode) + _u2(index)


def _code_attribute(pool: _ConstantPool, code: bytes, stack: int, locals_: int) -> bytes:
    body = _u2(stack) + _u2(locals_) + _u4(len(code)) + code + _u2(0) + _u2(0)
    return _u2(pool.utf8("Code")) + _u4(len(body)) + body


def _method(
    pool: _ConstantPool,
    access: int,
    name: str,
    descriptor: str,
    code: bytes,
    stack: int,
    locals_: int,
) -> bytes:
    attribute = _code_attribute(pool, code, stack, locals_)
    return _u2(access) + _u2(pool.utf8(name)) + _u2(pool.utf8(descriptor)) + _u2(1) + attribute


def _build_reader_class(output: Path) -> None:
    """Emit a Java 5 class so it runs on the bundled Java 21 JRE without javac."""

    pool = _ConstantPool()
    class_name = "SirajShamelaLuceneReader"
    this_class = pool.class_(class_name)
    super_class = pool.class_("java/lang/Object")

    object_init = pool.method("java/lang/Object", "<init>", "()V")
    paths_get = pool.method("java/nio/file/Paths", "get", "(Ljava/lang/String;[Ljava/lang/String;)Ljava/nio/file/Path;")
    fs_open = pool.method("org/apache/lucene/store/FSDirectory", "open", "(Ljava/nio/file/Path;)Lorg/apache/lucene/store/FSDirectory;")
    reader_open = pool.method("org/apache/lucene/index/DirectoryReader", "open", "(Lorg/apache/lucene/store/Directory;)Lorg/apache/lucene/index/DirectoryReader;")
    searcher_init = pool.method("org/apache/lucene/search/IndexSearcher", "<init>", "(Lorg/apache/lucene/index/IndexReader;)V")
    term_init = pool.method("org/apache/lucene/index/Term", "<init>", "(Ljava/lang/String;Ljava/lang/String;)V")
    term_query_init = pool.method("org/apache/lucene/search/TermQuery", "<init>", "(Lorg/apache/lucene/index/Term;)V")
    parse_int = pool.method("java/lang/Integer", "parseInt", "(Ljava/lang/String;)I")
    search = pool.method("org/apache/lucene/search/IndexSearcher", "search", "(Lorg/apache/lucene/search/Query;I)Lorg/apache/lucene/search/TopDocs;")
    score_docs = pool.field("org/apache/lucene/search/TopDocs", "scoreDocs", "[Lorg/apache/lucene/search/ScoreDoc;")
    score_doc_id = pool.field("org/apache/lucene/search/ScoreDoc", "doc", "I")
    stored_fields = pool.method("org/apache/lucene/index/IndexReader", "storedFields", "()Lorg/apache/lucene/index/StoredFields;")
    document = pool.method("org/apache/lucene/index/StoredFields", "document", "(I)Lorg/apache/lucene/document/Document;")
    document_get = pool.method("org/apache/lucene/document/Document", "get", "(Ljava/lang/String;)Ljava/lang/String;")
    system_out = pool.field("java/lang/System", "out", "Ljava/io/PrintStream;")
    println = pool.method("java/io/PrintStream", "println", "(Ljava/lang/String;)V")
    reader_close = pool.method("org/apache/lucene/index/IndexReader", "close", "()V")
    directory_close = pool.method("org/apache/lucene/store/Directory", "close", "()V")

    init = _u1(0x2A) + _instruction(0xB7, object_init) + _u1(0xB1)
    code = bytearray()
    # args[0] -> Path -> FSDirectory -> DirectoryReader
    code += _u1(0x2A) + _u1(0x03) + _u1(0x32) + _u1(0x03) + _instruction(0xBD, pool.class_("java/lang/String"))
    code += _instruction(0xB8, paths_get) + _u1(0x4C)
    code += _u1(0x2B) + _instruction(0xB8, fs_open) + _u1(0x4D)
    code += _u1(0x2C) + _instruction(0xB8, reader_open) + _u1(0x4E)
    # IndexSearcher(reader), Term(book_key,args[1]), TermQuery(term)
    code += _instruction(0xBB, pool.class_("org/apache/lucene/search/IndexSearcher")) + _u1(0x59) + _u1(0x2D) + _instruction(0xB7, searcher_init) + bytes((0x3A, 0x04))
    code += _instruction(0xBB, pool.class_("org/apache/lucene/index/Term")) + _u1(0x59) + _instruction(0x13, pool.string("book_key")) + _u1(0x2A) + _u1(0x04) + _u1(0x32) + _instruction(0xB7, term_init) + bytes((0x3A, 0x05))
    code += _instruction(0xBB, pool.class_("org/apache/lucene/search/TermQuery")) + _u1(0x59) + bytes((0x19, 0x05)) + _instruction(0xB7, term_query_init) + bytes((0x3A, 0x06))
    # TopDocs -> ScoreDoc[] -> loop index
    code += bytes((0x19, 0x04, 0x19, 0x06, 0x2A, 0x05, 0x32)) + _instruction(0xB8, parse_int) + _instruction(0xB6, search) + bytes((0x3A, 0x07, 0x19, 0x07)) + _instruction(0xB4, score_docs) + bytes((0x3A, 0x08, 0x03, 0x36, 0x09))
    loop_start = len(code)
    code += bytes((0x15, 0x09, 0x19, 0x08, 0xBE))
    branch_position = len(code)
    code += bytes((0xA2, 0x00, 0x00))  # if_icmpge end
    # document = reader.storedFields().document(scoreDocs[index].doc)
    code += _u1(0x2D) + _instruction(0xB6, stored_fields) + bytes((0x19, 0x08, 0x15, 0x09, 0x32)) + _instruction(0xB4, score_doc_id) + _instruction(0xB6, document) + bytes((0x3A, 0x0A))
    # Emit marker, id, body, foot, end. Document.get may return null; PrintStream supports it.
    for marker, field in (("@@BEGIN@@", None), (None, "id"), ("@@BODY@@", None), (None, "body"), ("@@FOOT@@", None), (None, "foot"), ("@@END@@", None)):
        code += _instruction(0xB2, system_out)
        if marker is not None:
            code += _instruction(0x13, pool.string(marker))
        else:
            code += bytes((0x19, 0x0A)) + _instruction(0x13, pool.string(field or "")) + _instruction(0xB6, document_get)
        code += _instruction(0xB6, println)
    code += bytes((0x84, 0x09, 0x01))
    goto_position = len(code)
    code += bytes((0xA7, 0x00, 0x00))
    end_position = len(code)
    code[branch_position + 1:branch_position + 3] = struct.pack(">h", end_position - branch_position)
    code[goto_position + 1:goto_position + 3] = struct.pack(">h", loop_start - goto_position)
    code += _u1(0x2D) + _instruction(0xB6, reader_close) + _u1(0x2C) + _instruction(0xB6, directory_close) + _u1(0xB1)

    methods = [
        _method(pool, 0x0001, "<init>", "()V", init, 1, 1),
        _method(pool, 0x0009, "main", "([Ljava/lang/String;)V", bytes(code), 5, 11),
    ]
    payload = b"\xCA\xFE\xBA\xBE" + _u2(0) + _u2(49) + pool.render()
    payload += _u2(0x0031) + _u2(this_class) + _u2(super_class) + _u2(0) + _u2(0)
    payload += _u2(len(methods)) + b"".join(methods) + _u2(0)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)


def _snapshot(paths: Iterable[Path]) -> dict[str, tuple[int, int]]:
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(paths, key=lambda item: str(item).casefold())
        if path.is_file()
    }


def _parse_documents(raw: str) -> list[LuceneStoredDocument]:
    # The bundled Windows Java runtime emits CRCRLF when its UTF-8 console
    # properties and the Windows console newline policy are both active.
    # Canonicalize transport newlines before parsing; stored field content is
    # subsequently normalized conservatively by the adapter.
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    documents: list[LuceneStoredDocument] = []
    for chunk in raw.split("@@BEGIN@@\n")[1:]:
        record, marker, _ = chunk.partition("\n@@END@@")
        if not marker:
            raise LuceneUnavailableError("LUCENE_BRIDGE_MALFORMED_RECORD")
        document_id, marker, remaining = record.partition("\n@@BODY@@\n")
        if not marker:
            raise LuceneUnavailableError("LUCENE_BRIDGE_MISSING_BODY_MARKER")
        body, marker, foot = remaining.partition("\n@@FOOT@@\n")
        if not marker or not document_id.strip():
            raise LuceneUnavailableError("LUCENE_BRIDGE_INVALID_DOCUMENT")
        documents.append(
            LuceneStoredDocument(
                document_id=document_id.strip(),
                # A Lucene hit may represent a structural page whose body was
                # not stored. The adapter deterministically records it as a
                # skipped empty segment rather than failing the entire book.
                body="" if body == "null" else body,
                foot=None if foot == "null" else foot,
            )
        )
    return sorted(documents, key=lambda item: item.document_id)


class LuceneReadOnlyBridge:
    def __init__(self, installation_root: str | Path, *, timeout_seconds: int = 180) -> None:
        self.installation_root = Path(installation_root).resolve()
        self.timeout_seconds = timeout_seconds
        self.java_bin = self.installation_root / "app" / "win" / "64" / "jre" / "2" / "bin" / "java.exe"
        self.classpath = self.installation_root / "app" / "lucene" / "2"

    def read_book(self, index_path: str | Path, book_id: int, maximum_documents: int) -> list[LuceneStoredDocument]:
        index = Path(index_path).resolve()
        if not self.java_bin.is_file() or not self.classpath.is_dir():
            raise LuceneUnavailableError("LUCENE_RUNTIME_UNAVAILABLE")
        if not index.is_dir() or maximum_documents < 1:
            raise LuceneUnavailableError("LUCENE_INDEX_UNAVAILABLE")

        before = _snapshot(index.iterdir())
        with tempfile.TemporaryDirectory(prefix="siraj-shamela-lucene-") as temporary:
            class_file = Path(temporary) / "SirajShamelaLuceneReader.class"
            _build_reader_class(class_file)
            command = [
                str(self.java_bin),
                "-Dfile.encoding=UTF-8",
                "-Dsun.stdout.encoding=UTF-8",
                "-Dsun.stderr.encoding=UTF-8",
                "-cp",
                str(Path(temporary)) + os.pathsep + str(self.classpath / "*"),
                "SirajShamelaLuceneReader",
                str(index),
                str(book_id),
                str(maximum_documents),
            ]
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                timeout=self.timeout_seconds,
            )

        after = _snapshot(index.iterdir())
        if before != after:
            raise LuceneUnavailableError("LUCENE_SOURCE_MUTATION_DETECTED")
        if completed.returncode != 0:
            raise LuceneUnavailableError("LUCENE_READ_FAILED")
        try:
            output = completed.stdout.decode("utf-8")
        except UnicodeDecodeError as error:
            raise LuceneUnavailableError("LUCENE_OUTPUT_NOT_UTF8") from error
        return _parse_documents(output)

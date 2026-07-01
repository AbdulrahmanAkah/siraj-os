from domain.sources.source import Source

source = Source(
    title="Sahih al-Bukhari",
    source_type="Hadith Collection",
    author="Imam al-Bukhari",
)

print(source.to_dict())
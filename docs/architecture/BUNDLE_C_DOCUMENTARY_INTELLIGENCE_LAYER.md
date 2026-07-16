# Bundle C — Documentary Intelligence Layer

## Canonical chain

ValidatedReasoningResult flows through Documentary Planning v2, Narrative
Architecture v2, Documentary Script Runtime, Scene Generation Runtime,
Storyboard Runtime, Documentary Assembly, Visual Evidence, Source Attribution,
Documentary Verification, Publication Packaging, Export Architecture, and
Production Runtime.

Every layer is deterministic and compositional. It copies existing event,
claim, evidence, source, and reasoning references; it does not create
historical facts, narration, image prompts, media, or semantic conclusions.

## Layer contracts

| Layer | Deterministic output | Gate |
| --- | --- | --- |
| Documentary Planning v2 | DocumentaryPlan | Validated reasoning, event graph, timeline, interpretation trace |
| Narrative Architecture v2 | NarrativeArchitecture | Valid documentary plan |
| Documentary Script Runtime | DocumentaryScript | Evidence-referenced narrative beats |
| Scene Generation Runtime | ScenePlanRuntime | One traceable scene per script section |
| Storyboard Runtime | Storyboard | One evidence-linked frame per scene |
| Documentary Assembly | DocumentaryPackage | Referential integrity across plan through storyboard |
| Visual Evidence | VisualEvidenceMap | Event, claim, and source-to-visual links |
| Source Attribution | AttributionResult | Evidence-linked visual artifact records |
| Documentary Verification | VerificationReport | Coverage, evidence, references, attribution, timeline, reasoning |
| Publication Packaging | PublicationPackage | Verified package metadata, credits, sources, appendix |
| Export Architecture | ExportBundle | Manifest and architecture-only export job |
| Production Runtime | ProductionReadyDocumentary | Verified publication plus export bundle |

## Audit requirements

All Bundle C models hold deterministic SHA-256-derived IDs, canonical created
timestamp `1970-01-01T00:00:00Z`, stable position metadata, and trace metadata.
The fixed timestamp is deliberate: no execution-time clock value can change
content identity or reproducibility.

No layer performs LLM calls, NLP, embeddings, semantic search, machine
learning, external APIs, file export, media creation, or network access.

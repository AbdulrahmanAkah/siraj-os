# SIRAJ Gold-20 Fast Track Specification v1

## Status

- Dataset ID: `gold-20-fast-track-v1`
- Gold schema: `siraj-gold-semantic-v1`
- Evaluation schema: `siraj-semantic-evaluation-v1`
- Target size: 20 real historical segments
- Provider outputs are never accepted directly as Gold labels.

## Objective

Create the smallest real, versioned and human-reviewed dataset that can
measure whether SIRAJ semantic extraction is usable for the documentary
production pipeline.

The dataset is a calibration and evaluation asset. It is not a training set.

## Sampling matrix

Five segments are selected for each currently supported critical route:

| Route | Count |
|---|---:|
| PERSON_AND_STATUS | 5 |
| APPOINTMENT_AND_OFFICE | 5 |
| ISNAD | 5 |
| SIRA_POETRY | 5 |

Difficulty distribution:

| Difficulty | Count |
|---|---:|
| DIRECT | 6 |
| COREFERENCE | 5 |
| AMBIGUOUS | 4 |
| MULTI_ITEM | 3 |
| ABSTENTION | 2 |

Each segment receives one primary route and may contain secondary semantic
collections. The primary route controls stratification only.

## Source requirements

Every segment must preserve:

- source ID
- book ID and title
- immutable locator
- segment ID
- exact original text
- deterministic source-text hash

Segments must come from real books and must not be copied from Critical-20
synthetic benchmark cases.

## Annotation workflow

1. Produce machine pre-annotation.
2. Review every segment manually.
3. Review every ambiguous case a second time.
4. Review at least ten percent of clear cases a second time.
5. Adjudicate every disagreement.
6. Accept a segment only after literal evidence validation.
7. Record explicit versus inferred information.
8. Use abstention when the text does not support a stable extraction.

Machine output remains separate from Gold annotation at all times.

## Gold collections

The initial contract supports:

- entities
- statuses
- relations
- appointments
- isnads
- events

Every accepted semantic item must contain literal evidence or a documented
abstention decision.

## Evaluation contract

Required quality metrics:

- route accuracy
- entity precision, recall and F1
- semantic-item precision, recall and F1
- evidence exact match
- evidence overlap F1
- abstention accuracy
- hallucination rate
- malformed-output rate

Required operational metrics:

- latency
- input tokens
- output tokens
- estimated cost

## Fast-track quality gates

Gold-20 may close only when:

- exactly 20 valid segments exist
- all provenance fields are complete
- every segment has human review
- all failures have taxonomy labels
- malformed-output rate is zero
- critical hallucination count is zero
- literal evidence is enforced
- provider outputs and Gold labels remain separated

Provider accuracy is measured and reported, but a perfect provider score is
not required to close the dataset itself.

## Failure taxonomy

- route error
- entity boundary or type error
- relation or status error
- appointment, isnad or event error
- evidence error
- coreference error
- abstention error
- hallucination
- malformed output
- source ambiguity
- annotation error
- schema error
- provider error

## Deferred work

This package does not include:

- Gold-50 or Gold-120
- a new annotation web application
- knowledge-graph writes
- corpus-scale scheduling
- production indexing
- provider execution
- final provider quality gates

Those steps begin only after the Gold-20 source manifest and annotation shells
are generated.
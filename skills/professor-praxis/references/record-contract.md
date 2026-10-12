# Evidence record contract

The CLI stores one JSON assessment per stable source in the explicitly selected workspace. Filenames are canonical SHA-256-derived names; use `save` rather than writing manually named JSON files into the store. It does not acquire a transcript or ask a model to grade content. Hermes supplies the grounded record and a saved Markdown note. Legacy `log.jsonl` imports are unsupported, including empty legacy logs. `save` does not automatically render the dashboard; call `refresh` after persistence.

## Source fields

| Field | Meaning |
|---|---|
| `id` | Stable identifier, letters/digits/colon/underscore/hyphen, at most120 characters |
| `realm` | Explicit `personal` or `work`, matching the workspace |
| `kind` | `video`, `podcast` or `article` |
| `title`, `author` | Actually supplied/retrieved metadata; nonblank strings |
| `url` | Public HTTPS source URL, without credentials or secret/session query parameters |
| `captured_at` | Actual original capture time, timezone-aware ISO datetime |
| `duration_minutes` | Positive finite number or null; keep precise value |
| `coverage` | `full_text`, `full_transcript`, `metadata_only` or `prior_note` |
| `summary`, `ideas` | Lists of source-supported strings; empty for metadata-only |
| `tools` | List of tool mentions/leads with provenance |
| `source_text` | Complete retained retrieved/supplied text for full text/transcript coverage; private |
| `note_path` | Nonblank absolute `.md` path without traversal/control characters, within the approved notes root and actually saved, or null; malformed false/empty values are rejected |
| `assessment` | Object below or null |
| `action`, `action_state` | Optional proposed action and null/open/applied/dropped; never invent application |

Full-source grades require retained text. Metadata-only and prior-note coverage cannot support a firm content-based grade. Missing content stays Unknown; a title is not evidence of source ideas, tools or novelty.

## Assessment

Required:

* `recommendation`: Watch/Listen/Read/Skim/Skip/Unknown.
* `value`: high/moderate/low/unknown.
* `confidence`: high/medium/low.
* Nonblank `rationale`, `time_guidance` and aware `reviewed_at`.
* `novelty`: list of `{idea, bucket, evidence, compared_with, prior_evidence}`.
* `credibility`: `{topic, established, comparison_established, compared_sources, judgment, comparison, evidence, unknowns}`.

Novelty `bucket` is new/reinforcement/repetition/unknown. Literal `evidence` must occur in the retained source. Every comparison ID must reference an actual usable source; literal `prior_evidence` must be supported by each referenced prior source's evidence available by the review time. Reinforcement/repetition require a prior source. New means absent from the recorded library, not new to the person.

Credibility evidence is a list of `{claim, url, checked_at}` with nonblank claim, safe HTTPS URL and aware timestamp. An established judgment requires citations; an established comparison requires `established=true` as well as usable prior sources and appropriate chronology. The contradictory `established=false, comparison_established=true` pair is rejected, including when citations/prior IDs are supplied. Both false remains valid Unknown; true/false remains a cited standalone judgment. Product documentation corroborates documented behavior, not security, creator savings or personal suitability. Missing establishment stays Not established.

Chronology is capture <= review <= dashboard generation; citation checks <= review. Current saved-note modification time is evidence availability, not a retroactive capture date. Do not move timestamps backwards merely to pass a validator.

## Tool entries

Required `name`, `kind`, `origin`, `purpose`, `source_evidence`, `decision`.

* `kind`: platform/MCP/CLI/library/other/unclear. A model/native feature may be other, not falsely sold as an installable product.
* `origin`: video/source/assistant_suggestion/unclear. Do not label assistant suggestions as source mentions.
* `decision`: investigate/already use/skip/unclear. Mention does not mean installation recommended or already used.
* Literal `source_evidence` for source mentions must occur in retained source text.

Optional string/null fields: `source_anchor`, `chapter_anchor`, `verification_status`, `verification_date`, `official_docs_url`, `pricing`, `security`, `relevance`. Verify docs URLs or mark them unavailable; do not guess identities, prices or interface types. Real chapters are approximate navigation, not precise timing for untimed quotations. Legacy unclear provenance remains explicitly unclear.

## Projection and failure safety

The dashboard allowlists source metadata, assessment, summaries, ideas, tool provenance and selected saved-note text. Raw `source_text` and `note_path` are not projected wholesale. Notes are rendered as text, not executable HTML. Local path/credential-pattern scrubbing is not a complete privacy audit; selected note text remains personal data.

`prior_evidence_available_at` is projection-only metadata: the earliest availability of nonblank retained prior evidence, or null. The validator derives it from source text/ideas available at capture or reassessment, and saved-note content available no earlier than capture and its current modification time. It is not an accepted persisted record field, a trust judgment, or a claim that a current note existed at capture. The dashboard requires this marker and valid chronology for credibility comparisons; it never needs private source text to establish evidence availability.

The CLI rejects out-of-scope notes, duplicate stable IDs, malformed evidence and incompatible setup. Refresh uses scoped locks, atomic replacement and a freshness watermark to preserve last-good output. Do not remove locks or corrupt metadata automatically. A failed save/refresh must not be described as a complete result.

`metadata-record.json` is a synthetic schema illustration only. It is not a real assessment and is never loaded automatically.

"""Measure CER on representative system-audio and microphone transcripts."""

import argparse
import json
from pathlib import Path
import unicodedata

from asr_metrics import edit_distance


SOURCE_NAMES = ("system", "mic")
BASELINE_NAME = "whisper-small"
MINIMUM_RELATIVE_IMPROVEMENT = 0.10


def _normalized_characters(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return [
        character
        for character in normalized
        if not character.isspace() and not unicodedata.category(character).startswith("P")
    ]


def character_error_rate(reference: str, transcript: str) -> float:
    """Return edit distance per reference character after agreed normalization."""
    reference_characters = _normalized_characters(reference)
    if not reference_characters:
        raise ValueError("reference has no transcription characters")
    transcript_characters = _normalized_characters(transcript)
    return edit_distance(reference_characters, transcript_characters) / len(reference_characters)


def evaluate_transcripts(references: dict[str, str], transcripts: dict[str, dict[str, str]]) -> dict:
    """Score both sources equally and flag the CER gate only."""
    for source in SOURCE_NAMES:
        if source not in references or not _normalized_characters(references[source]):
            raise ValueError(f"{source} reference has no transcription characters")
    if BASELINE_NAME not in transcripts:
        raise ValueError(f"missing {BASELINE_NAME} baseline")

    engines = {}
    for engine_name, by_source in transcripts.items():
        source_scores = {}
        for source in SOURCE_NAMES:
            if source not in by_source:
                raise ValueError(f"{engine_name} is missing {source} transcript")
            source_scores[f"{source}_cer"] = character_error_rate(references[source], by_source[source])
        source_scores["mean_cer"] = sum(source_scores.values()) / len(SOURCE_NAMES)
        engines[engine_name] = source_scores

    baseline = engines[BASELINE_NAME]
    baseline_mean_cer = baseline["mean_cer"]
    for engine_name, scores in engines.items():
        scores["cer_gate_passed"] = (
            engine_name != BASELINE_NAME
            and baseline_mean_cer > 0
            and scores["mean_cer"] <= baseline_mean_cer * (1 - MINIMUM_RELATIVE_IMPROVEMENT)
            and all(scores[f"{source}_cer"] <= baseline[f"{source}_cer"] for source in SOURCE_NAMES)
        )
    return {"baseline_mean_cer": baseline_mean_cer, "engines": engines}


def score_manifest(manifest_path: Path) -> dict:
    """Read text paths relative to a manifest without including text in output."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    directory = manifest_path.parent
    references = {
        source: (directory / manifest["references"][source]).read_text(encoding="utf-8-sig")
        for source in SOURCE_NAMES
    }
    transcripts = {
        engine_name: {
            source: (directory / by_source[source]).read_text(encoding="utf-8-sig")
            for source in SOURCE_NAMES
        }
        for engine_name, by_source in manifest["transcripts"].items()
    }
    return evaluate_transcripts(references, transcripts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON file listing two references and each engine's text files")
    arguments = parser.parse_args()
    print(json.dumps(score_manifest(arguments.manifest), indent=2, sort_keys=True))

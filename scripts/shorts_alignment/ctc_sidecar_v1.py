#!/usr/bin/env python
"""Local CTC emissions + SIRAJ-owned forced-alignment DP.

No ASR-decoded transcript is used. The target sequence is always the trusted
SIRAJ transcript supplied in the request.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import unicodedata

ALGORITHM_ID = "SIRAJ_CTC_TRELLIS_BACKTRACK_V1"
ALGORITHM_VERSION = "1.1.0"
ARABIC_DIACRITICS = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
)
PUNCT = re.compile(r"""[!"#$%&'()*+,\-./:;<=>?@\[\]^_`{|}~،؛؟«»…ـ]""")


MODEL_ORTHOGRAPHIC_TRANSLATION = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ة": "ه",
        "ى": "ي",
    }
)


def normalize_word(word: str) -> str:
    value = unicodedata.normalize("NFKC", word)
    value = ARABIC_DIACRITICS.sub("", value).replace("ـ", "")
    return PUNCT.sub("", value).strip()


def normalize_model_word(word: str) -> str:
    """Normalize only the CTC model input; trusted source text is retained."""

    return (
        normalize_word(word)
        .replace("﴿", "")
        .replace("﴾", "")
        .translate(MODEL_ORTHOGRAPHIC_TRANSLATION)
    )


def tokenize_words(text, tokenizer, blank_id, unk_id):
    original_words = re.findall(r"\S+", text, flags=re.UNICODE)
    target, token_word, lexical = [], [], []
    for original in original_words:
        source_normalized = normalize_word(original)
        model_input = normalize_model_word(source_normalized)
        if not model_input:
            continue
        ids = [int(x) for x in tokenizer(model_input, add_special_tokens=False).input_ids]
        ids = [x for x in ids if x != int(blank_id)]
        if not ids or (
            unk_id is not None and any(x == int(unk_id) for x in ids)
        ):
            lexical.append(
                {
                    "original": original,
                    "normalized": model_input,
                    "source_normalized": source_normalized,
                    "status": "UNALIGNED_OOV",
                }
            )
            continue
        word_index = len(lexical)
        lexical.append(
            {
                "original": original,
                "normalized": model_input,
                "source_normalized": source_normalized,
                "status": "TARGET",
            }
        )
        for token_id in ids:
            target.append(token_id)
            token_word.append(word_index)
    return lexical, target, token_word


def ctc_forced_align(log_probs, target, blank_id):
    import numpy as np

    if not target:
        raise RuntimeError("EMPTY_CTC_TARGET")
    frames, _vocab = log_probs.shape
    states = 2 * len(target) + 1
    if frames < len(target):
        raise RuntimeError(
            f"CTC_TARGET_LONGER_THAN_FRAMES:{len(target)}>{frames}"
        )

    expanded = np.full(states, int(blank_id), dtype=np.int64)
    expanded[1::2] = np.asarray(target, dtype=np.int64)
    negative = -1e30
    previous = np.full(states, negative, dtype=np.float64)
    previous[0] = 0.0
    back = np.zeros((frames, states), dtype=np.int8)

    jump_allowed = np.zeros(states, dtype=bool)
    for state in range(2, states):
        if (
            expanded[state] != blank_id
            and expanded[state] != expanded[state - 2]
        ):
            jump_allowed[state] = True

    columns = np.arange(states)
    for frame in range(frames):
        stay = previous
        move_one = np.full(states, negative, dtype=np.float64)
        move_one[1:] = previous[:-1]
        move_two = np.full(states, negative, dtype=np.float64)
        move_two[2:] = previous[:-2]
        move_two[~jump_allowed] = negative
        alternatives = np.stack([stay, move_one, move_two], axis=0)
        choice = np.argmax(alternatives, axis=0).astype(np.int8)
        previous = (
            alternatives[choice, columns]
            + log_probs[frame, expanded]
        )
        back[frame] = choice

    ending_states = [states - 1, states - 2] if states >= 2 else [0]
    state = max(ending_states, key=lambda item: previous[item])
    if (
        not math.isfinite(float(previous[state]))
        or float(previous[state]) < negative / 2
    ):
        raise RuntimeError("CTC_NO_FINITE_ALIGNMENT_PATH")

    path_states = [0] * frames
    for frame in range(frames - 1, -1, -1):
        path_states[frame] = state
        state -= int(back[frame, state])
        if state < 0:
            raise RuntimeError("CTC_BACKTRACK_UNDERFLOW")

    token_frames = [[] for _ in target]
    for frame, state in enumerate(path_states):
        if state % 2 == 1:
            token_frames[(state - 1) // 2].append(frame)
    if any(not item for item in token_frames):
        raise RuntimeError("CTC_TOKEN_WITHOUT_FRAME")
    score = float(max(previous[item] for item in ending_states))
    return token_frames, score


def extract_pcm(ffmpeg, video_path, start, end):
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.6f}",
        "-to",
        f"{end:.6f}",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
        "pipe:1",
    ]
    process = subprocess.run(command, capture_output=True, check=False)
    if process.returncode != 0 or not process.stdout:
        raise RuntimeError(
            "FFMPEG_AUDIO_EXTRACTION_FAILED:"
            + process.stderr.decode("utf-8", "replace")[-600:]
        )
    import numpy as np

    return (
        np.frombuffer(process.stdout, dtype=np.int16)
        .astype(np.float32)
        / 32768.0
    )


def self_test():
    import numpy as np

    ids = [0, 1, 1, 0, 2, 2, 0, 2, 2, 0, 3, 3, 0]
    log_probs = np.full((len(ids), 4), -8.0, dtype=np.float64)
    for frame, token in enumerate(ids):
        log_probs[frame, token] = -0.01
    token_frames, score = ctc_forced_align(
        log_probs, [1, 2, 2, 3], 0
    )
    assert len(token_frames) == 4 and all(token_frames)
    assert max(token_frames[0]) < min(token_frames[1])
    assert max(token_frames[1]) < min(token_frames[2])
    assert max(token_frames[2]) < min(token_frames[3])
    print(
        json.dumps(
            {
                "status": "PASS",
                "algorithm": ALGORITHM_ID,
                "score": score,
            }
        )
    )
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request")
    parser.add_argument("--response")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()

    request = json.loads(
        Path(args.request).read_text(encoding="utf-8")
    )
    runtime_root = Path(os.environ["SIRAJ_SHORTS_CTC_RUNTIME_ROOT"])
    runtime = json.loads(
        (runtime_root / "runtime-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    model_path = Path(runtime["model_path"])
    ffmpeg = runtime["ffmpeg_path"]
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )

    import numpy as np
    import torch
    from transformers import AutoModelForCTC, AutoProcessor

    processor = AutoProcessor.from_pretrained(
        str(model_path), local_files_only=True
    )
    model = AutoModelForCTC.from_pretrained(
        str(model_path),
        local_files_only=True,
        use_safetensors=True,
    ).eval()
    tokenizer = processor.tokenizer
    blank_id = int(
        getattr(model.config, "pad_token_id", tokenizer.pad_token_id)
    )
    unk_id = getattr(tokenizer, "unk_token_id", None)

    output = []
    trusted_words = 0
    uncertain_regions = 0

    for segment in request["segments"]:
        segment_id = str(segment["segment_id"])
        start = float(segment["start_time"])
        end = float(segment["end_time"])
        text = str(segment["text"])
        lexical, target, token_word = tokenize_words(
            text, tokenizer, blank_id, unk_id
        )
        if not target or any(
            item["status"] != "TARGET" for item in lexical
        ):
            output.append(
                {
                    **segment,
                    "alignment_status": "UNCERTAIN",
                    "code": "UNALIGNABLE_TRUSTED_TOKEN",
                    "word_boundaries": [],
                }
            )
            uncertain_regions += 1
            continue

        try:
            audio = extract_pcm(
                ffmpeg,
                Path(request["source_video_path"]),
                start,
                end,
            )
            inputs = processor(
                audio,
                sampling_rate=16000,
                return_tensors="pt",
                padding=False,
            )
            with torch.no_grad():
                logits = model(inputs.input_values).logits[0]
                log_probs = (
                    torch.log_softmax(logits, dim=-1)
                    .cpu()
                    .numpy()
                    .astype(np.float64)
                )

            token_frames, path_score = ctc_forced_align(
                log_probs, target, blank_id
            )
            frame_count = log_probs.shape[0]
            word_frames = {}
            word_probs = {}
            for token_index, frames in enumerate(token_frames):
                word_index = token_word[token_index]
                word_frames.setdefault(word_index, []).extend(frames)
                token_id = target[token_index]
                probabilities = np.exp(
                    log_probs[
                        np.asarray(frames, dtype=np.int64),
                        token_id,
                    ]
                )
                word_probs.setdefault(word_index, []).extend(
                    float(item) for item in probabilities
                )

            boundaries = []
            for word_index, item in enumerate(lexical):
                if word_index not in word_frames:
                    raise RuntimeError("WORD_WITHOUT_CTC_FRAMES")
                frames = word_frames[word_index]
                absolute_start = (
                    start
                    + (min(frames) / frame_count) * (end - start)
                )
                absolute_end = (
                    start
                    + ((max(frames) + 1) / frame_count) * (end - start)
                )
                mean_probability = float(
                    sum(word_probs[word_index])
                    / max(1, len(word_probs[word_index]))
                )
                structurally_valid = (
                    absolute_end > absolute_start
                    and absolute_start >= start - 1e-4
                    and absolute_end <= end + 1e-4
                )
                status = (
                    "TRUSTED"
                    if structurally_valid and mean_probability > 1e-6
                    else "UNCERTAIN"
                )
                trusted_words += int(status == "TRUSTED")
                uncertain_regions += int(status != "TRUSTED")
                boundaries.append(
                    {
                        "word_id": (
                            f"{segment_id}-WORD-{word_index + 1:04d}"
                        ),
                        "text": item["original"],
                        "normalized_alignment_text": item["normalized"],
                        "start_seconds": round(
                            absolute_start, 6
                        ),
                        "end_seconds": round(absolute_end, 6),
                        "confidence": round(mean_probability, 8),
                        "status": status,
                        "source": (
                            "LOCAL_CTC_ACOUSTIC_FORCED_ALIGNMENT"
                        ),
                    }
                )
            if any(
                item["status"] != "TRUSTED"
                for item in boundaries
            ):
                raise RuntimeError(
                    "SEGMENT_HAS_UNCERTAIN_WORD_ALIGNMENT"
                )

            output.append(
                {
                    **segment,
                    "word_boundaries": boundaries,
                    "alignment_status": "PASS",
                    "alignment_path_score": path_score,
                    "alignment_frame_count": int(frame_count),
                }
            )
        except Exception as exc:
            uncertain_regions += 1
            output.append(
                {
                    **segment,
                    "alignment_status": "UNCERTAIN",
                    "code": type(exc).__name__,
                    "detail": str(exc),
                    "word_boundaries": [],
                }
            )

    canonical = json.dumps(
        request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    response = {
        "status": "PASS",
        "schema_version": "SIRAJ_FINE_GRAINED_TIMING_V1",
        "algorithm_id": ALGORITHM_ID,
        "algorithm_version": ALGORITHM_VERSION,
        "episode_key": hashlib.sha256(canonical).hexdigest(),
        "model_repo_id": runtime["model_repo_id"],
        "model_revision": runtime["model_revision"],
        "model_sha256": runtime["model_sha256"],
        "segments": output,
        "trusted_words": trusted_words,
        "uncertain_regions": uncertain_regions,
        "text_authority": "TRUSTED_SIRAJ_TRANSCRIPT_ONLY",
        "asr_decoded_text_used": False,
        "provider_calls": 0,
        "paid_calls": 0,
        "network_runtime_calls": 0,
    }
    Path(args.response).write_text(
        json.dumps(response, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

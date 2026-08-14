"""Offline YuNet screening for PR01.

This is deliberately a helper.  It can identify candidate frames for human
review, but it cannot approve an asset, waive the global face ban, or replace
all-decoded-frame human conformance review.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping, Sequence


MODEL_REL = Path("config/pr01/face_detector/face_detection_yunet_2023mar.onnx")
MODEL_METADATA_REL = Path("config/pr01/face_detector/face_detector_model_v1.json")
EXPECTED_MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
DEFAULT_SCORE_THRESHOLD = 0.8
NMS_THRESHOLD = 0.3
TOP_K = 5000
CALIBRATION_THRESHOLDS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


class FaceDetectorConfigurationError(RuntimeError):
    """The local detector cannot be trusted in its current configuration."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cv2() -> Any:
    try:
        import cv2  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise FaceDetectorConfigurationError("OPENCV_FACE_RUNTIME_MISSING") from exc
    return cv2


@dataclass(frozen=True, slots=True)
class FrameDetection:
    frame_index: int | None
    detected: bool
    scores: tuple[float, ...]
    threshold: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "detected": self.detected,
            "scores": list(self.scores),
            "threshold": self.threshold,
        }


@dataclass(frozen=True, slots=True)
class ThresholdResult:
    threshold: float
    positive_count: int
    positive_detected: int
    negative_count: int
    negative_detected: int

    @property
    def recall(self) -> float:
        return self.positive_detected / self.positive_count if self.positive_count else 0.0

    @property
    def false_positive_rate(self) -> float:
        return self.negative_detected / self.negative_count if self.negative_count else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "positive_count": self.positive_count,
            "positive_detected": self.positive_detected,
            "negative_count": self.negative_count,
            "negative_detected": self.negative_detected,
            "positive_recall": self.recall,
            "false_positive_rate": self.false_positive_rate,
        }


class OfflineYuNetDetector:
    """A deterministic local YuNet detector with explicit model binding."""

    def __init__(
        self,
        repo_root: Path,
        *,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        nms_threshold: float = NMS_THRESHOLD,
        top_k: int = TOP_K,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.model_path = self.repo_root / MODEL_REL
        if not self.model_path.is_file():
            raise FaceDetectorConfigurationError("YU_NET_MODEL_MISSING")
        actual_hash = sha256_file(self.model_path)
        if actual_hash != EXPECTED_MODEL_SHA256:
            raise FaceDetectorConfigurationError("YU_NET_MODEL_HASH_MISMATCH")
        cv2 = _cv2()
        self.cv2 = cv2
        self.score_threshold = float(score_threshold)
        self.nms_threshold = float(nms_threshold)
        self.top_k = int(top_k)
        self._detector = cv2.FaceDetectorYN.create(
            str(self.model_path),
            "",
            (320, 320),
            self.score_threshold,
            self.nms_threshold,
            self.top_k,
        )

    def detect_array(self, image: Any, *, frame_index: int | None = None) -> FrameDetection:
        if image is None or getattr(image, "size", 0) == 0:
            raise FaceDetectorConfigurationError("DECODED_IMAGE_EMPTY")
        height, width = image.shape[:2]
        self._detector.setInputSize((int(width), int(height)))
        _, detections = self._detector.detect(image)
        scores: tuple[float, ...]
        if detections is None:
            scores = ()
        else:
            scores = tuple(sorted((float(row[14]) for row in detections), reverse=True))
        return FrameDetection(frame_index, bool(scores), scores, self.score_threshold)

    def detect_image(self, path: Path) -> FrameDetection:
        image = self.cv2.imread(str(path), self.cv2.IMREAD_COLOR)
        return self.detect_array(image)

    def scan_video_all_decoded_frames(self, path: Path) -> dict[str, Any]:
        capture = self.cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise FaceDetectorConfigurationError("VIDEO_OPEN_FAILED")
        decoded = 0
        positives: list[dict[str, Any]] = []
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                result = self.detect_array(frame, frame_index=decoded)
                if result.detected:
                    positives.append(result.as_dict())
                decoded += 1
            reported = int(capture.get(self.cv2.CAP_PROP_FRAME_COUNT) or 0)
        finally:
            capture.release()
        return {
            "path": str(path),
            "decoded_frame_count": decoded,
            "reported_frame_count": reported,
            "frame_count_match": reported in (0, decoded),
            "positive_frame_count": len(positives),
            "positive_frames": positives,
            "human_review_required": True,
            "detector_is_final_approver": False,
        }


def _detected(repo_root: Path, path: Path, threshold: float) -> bool:
    return OfflineYuNetDetector(repo_root, score_threshold=threshold).detect_image(path).detected


def calibrate_thresholds(
    repo_root: Path,
    positive_paths: Sequence[Path],
    negative_paths: Sequence[Path],
    thresholds: Iterable[float] = CALIBRATION_THRESHOLDS,
) -> dict[str, Any]:
    if not positive_paths or not negative_paths:
        raise FaceDetectorConfigurationError("CALIBRATION_CLASSES_REQUIRED")
    results: list[ThresholdResult] = []
    for threshold in thresholds:
        positive_detected = sum(_detected(repo_root, path, threshold) for path in positive_paths)
        negative_detected = sum(_detected(repo_root, path, threshold) for path in negative_paths)
        results.append(
            ThresholdResult(
                float(threshold),
                len(positive_paths),
                positive_detected,
                len(negative_paths),
                negative_detected,
            )
        )
    passing = [row for row in results if row.recall == 1.0]
    if not passing:
        raise FaceDetectorConfigurationError("CALIBRATION_CRITICAL_POSITIVE_RECALL_BELOW_100")
    selected = max(passing, key=lambda row: row.threshold)
    return {
        "selected_threshold": selected.threshold,
        "critical_positive_recall": selected.recall,
        "selected_false_positive_rate": selected.false_positive_rate,
        "threshold_sweep": [row.as_dict() for row in results],
        "positive_count": len(positive_paths),
        "negative_count": len(negative_paths),
        "all_decoded_frames_human_review_required": True,
        "detector_is_final_approver": False,
        "calibration_invalidating_changes": [
            "model_sha256",
            "opencv_runtime_version",
            "score_threshold",
            "nms_threshold",
            "input_resize_policy",
            "calibration_corpus_hash",
            "frame_coverage_policy",
        ],
    }


def load_detector_metadata(repo_root: Path) -> dict[str, Any]:
    path = Path(repo_root).resolve() / MODEL_METADATA_REL
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if value.get("model_sha256") != EXPECTED_MODEL_SHA256:
        raise FaceDetectorConfigurationError("YU_NET_METADATA_HASH_MISMATCH")
    return value

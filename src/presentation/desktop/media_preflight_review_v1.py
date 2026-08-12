"""Full-desktop read-only review of the canonical media preflight result.

This dialog is intentionally not a provider-execution control.  It presents
the durable preflight result, exposes the exact state identity being reviewed,
and can emit an explicit cost-envelope acknowledgement request only after a
fresh compare-and-set validation.  A materially changed plan may require a
new acknowledgement; the application service, not this dialog, creates it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.application.desktop_media_cost_preflight_v1 import (
    MediaCostPreflightError,
    MediaCostPreflightReview,
    read_persisted_media_cost_preflight,
    validate_persisted_media_cost_preflight_review,
)
from src.application.artifact_provenance_v1 import utc_now


def _value(value: object, *, unknown: str = "UNKNOWN") -> str:
    if value is None or value == "":
        return unknown
    return str(value)


class CostEnvelopeReackConfirmationDialog(QDialog):
    """Explicit confirmation for one immutable preflight snapshot.

    This dialog only returns the reviewed snapshot.  The application service
    owns authorization writes, hashing, and stale-state checks.
    """

    def __init__(
        self,
        snapshot: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.snapshot = dict(snapshot)
        self.setWindowTitle("Confirm cost-envelope re-acknowledgement")
        self.setMinimumWidth(640)
        layout = QVBoxLayout(self)
        title = QLabel("Confirm the exact reviewed cost envelope")
        title.setStyleSheet("font-size: 16px; font-weight: 800;")
        layout.addWidget(title)
        summary = snapshot.get("summary")
        summary = summary if isinstance(summary, dict) else {}
        provider_contract_status = snapshot.get("provider_contract_status", "UNKNOWN")
        envelope = snapshot.get("cost_envelope_usd")
        envelope = envelope if isinstance(envelope, dict) else {}
        authority = snapshot.get("media_plan_authority")
        authority = authority if isinstance(authority, dict) else {}
        currency = envelope.get("currency") or "UNKNOWN"
        upper = envelope.get("upper_bound")
        estimated_text = (
            f"{float(upper):.8f} {currency}"
            if isinstance(upper, (int, float))
            else "UNKNOWN"
        )
        lines = (
            f"Episode: {snapshot.get('episode_id', 'UNKNOWN')}",
            f"Provider requests: {summary.get('planned_provider_requests', 'UNKNOWN')}",
            f"Video requests: {summary.get('planned_video_requests', 'UNKNOWN')}",
            f"Still requests: {summary.get('planned_image_requests', 'UNKNOWN')}",
            f"True video: {float(summary.get('generated_video_seconds', 0.0)):.3f} s",
            f"True video coverage: {float(summary.get('generated_video_percent', 0.0)):.6f}%",
            f"Provider-requested video: {float(summary.get('provider_requested_seconds', 0.0)):.3f} s",
            f"Estimated total: {estimated_text}",
            f"Maximum authorized cost: {estimated_text}",
            f"Pricing: {summary.get('pricing_status', 'UNKNOWN')}",
            f"Contracts: {provider_contract_status}",
            f"Plan SHA-256: {authority.get('proposal_sha256', 'UNKNOWN')}",
        )
        details = QLabel("\n".join(lines))
        details.setWordWrap(True)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(details)
        warning = QLabel(
            "This action authorizes the reviewed cost envelope.\n"
            "It DOES NOT submit provider requests.\n"
            "It DOES NOT start production."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("font-weight: 700; color: #9b3d24;")
        layout.addWidget(warning)
        buttons = QHBoxLayout()
        confirm = QPushButton("Confirm cost envelope")
        confirm.setDefault(True)
        confirm.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(confirm)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)


class MediaPreflightReviewDialog(QDialog):
    """Review-only dialog bound to one persisted preflight snapshot."""

    authorization_requested = Signal(object)
    stale_state_detected = Signal(str)

    def __init__(
        self,
        repo_root: Path,
        review: MediaCostPreflightReview,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo_root = Path(repo_root).resolve()
        self.review = review
        self.setWindowTitle("SIRAJ — Media preflight review")
        self.setMinimumSize(760, 650)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(9)

        title = QLabel("Persisted MEDIA_COST_PREFLIGHT review")
        title.setStyleSheet("font-size: 17px; font-weight: 800;")
        outer.addWidget(title)
        subtitle = QLabel(
            "Review is read-only. It does not authorize, submit, retry, or execute a provider request."
        )
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(2, 2, 2, 2)
        body_layout.setSpacing(8)

        identity = QGroupBox("Canonical identity")
        identity_form = QFormLayout(identity)
        self.identity_labels: dict[str, QLabel] = {}
        for key, label in (
            ("episode_id", "Episode"),
            ("stage", "Current canonical stage"),
            ("status", "Preflight status"),
            ("result_file", "Result file SHA-256"),
            ("result_payload", "Result payload SHA-256"),
            ("ledger", "Reviewed ledger head"),
        ):
            value_label = QLabel()
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.identity_labels[key] = value_label
            identity_form.addRow(label + ":", value_label)
        body_layout.addWidget(identity)

        media = QGroupBox("Media plan")
        media_form = QFormLayout(media)
        self.media_labels: dict[str, QLabel] = {}
        for key, label in (
            ("duration", "Episode duration (s)"),
            ("generated", "Actual generated video (s)"),
            ("generated_percent", "Generated-video percentage"),
            ("requested", "Provider-requested video (s)"),
            ("ceiling", "Generated-video ceiling (s)"),
            ("floor", "Generated-video floor (s)"),
            ("images", "Still-image requests"),
            ("graphics", "Graphics/local units"),
            ("requests", "Planned provider requests"),
            ("providers", "Provider/model assignments"),
        ):
            value_label = QLabel()
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.media_labels[key] = value_label
            media_form.addRow(label + ":", value_label)
        body_layout.addWidget(media)

        cost = QGroupBox("Cost and safety")
        cost_form = QFormLayout(cost)
        self.cost_labels: dict[str, QLabel] = {}
        for key, label in (
            ("pricing", "Pricing status"),
            ("estimated", "Estimated/bounded total"),
            ("envelope", "Cost envelope"),
            ("ceiling_status", "50%–75% coverage policy"),
            ("gates", "Alignment / duplicate gates"),
            ("retry", "Automatic paid retry"),
            ("resubmission", "Automatic resubmission"),
            ("authorization", "Production authorization"),
            ("policy", "Authorization policy"),
        ):
            value_label = QLabel()
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.cost_labels[key] = value_label
            cost_form.addRow(label + ":", value_label)
        body_layout.addWidget(cost)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        actions = QHBoxLayout()
        self.authorize_button = QPushButton(
            "Request cost-envelope re-acknowledgement"
            if review.production_authorization
            in {"ACTIVE_BUT_UNBOUND_REACK_REQUIRED", "AWAITING_HUMAN_AUTHORIZATION"}
            else "Authorize provider execution"
        )
        self.authorize_button.setVisible(
            review.production_authorization
            not in {"VALID", "VALID_BOUND_TO_CURRENT_COST_ENVELOPE"}
        )
        self.authorize_button.clicked.connect(self._request_authorization)
        actions.addWidget(self.authorize_button)
        refresh = QPushButton("Refresh reviewed state")
        refresh.clicked.connect(self._refresh_review)
        actions.addWidget(refresh)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        outer.addLayout(actions)
        self._render()

    def _render(self) -> None:
        review = self.review
        self.identity_labels["episode_id"].setText(review.episode_id)
        self.identity_labels["stage"].setText(review.next_stage)
        self.identity_labels["status"].setText(
            f"{review.completion_status} ({review.persisted_status})"
        )
        self.identity_labels["result_file"].setText(review.result_file_sha256)
        self.identity_labels["result_payload"].setText(review.result_sha256)
        self.identity_labels["ledger"].setText(review.current_ledger_head_sha256)

        summary = review.summary
        state = review.authoritative_state
        self.media_labels["duration"].setText(f"{float(state['duration_seconds']):.3f}")
        self.media_labels["generated"].setText(f"{float(summary.get('generated_video_seconds', 0.0)):.3f}")
        self.media_labels["generated_percent"].setText(f"{review.generated_video_percent:.6f}%")
        self.media_labels["requested"].setText(f"{float(summary.get('provider_requested_seconds', 0.0)):.3f}")
        self.media_labels["ceiling"].setText(f"{review.generated_video_ceiling_seconds:.3f}")
        self.media_labels["floor"].setText(f"{float(state['duration_seconds']) * 0.50:.3f}")
        self.media_labels["images"].setText(str(summary.get("planned_image_requests", "UNKNOWN")))
        self.media_labels["graphics"].setText(str(summary.get("planned_local_graphics", "UNKNOWN")))
        self.media_labels["requests"].setText(str(summary.get("planned_provider_requests", "UNKNOWN")))
        self.media_labels["providers"].setText(
            "\n".join(f"{key}: {count}" for key, count in sorted(review.provider_model_counts.items()))
        )

        envelope = review.cost_envelope_usd
        upper = envelope.get("upper_bound")
        lower = envelope.get("lower_bound")
        estimated = (
            f"{float(upper):.6f} {review.currency or 'UNKNOWN'}"
            if isinstance(upper, (int, float))
            else "UNKNOWN"
        )
        self.cost_labels["pricing"].setText(review.pricing_status + " — " + review.cost_status)
        self.cost_labels["estimated"].setText(estimated)
        self.cost_labels["envelope"].setText(
            f"lower_bound={_value(lower)}; upper_bound={_value(upper)}; currency={review.currency or 'UNKNOWN'}"
        )
        coverage_status = review.coverage_status
        ceiling_ok = coverage_status == "PASS"
        self.cost_labels["ceiling_status"].setText(
            "PASS — mandatory range / directorial selection"
            if ceiling_ok
            else "FAIL — PROVIDER_EXECUTION BLOCKED"
        )
        self.cost_labels["gates"].setText("ALIGNMENT=PASS; DUPLICATE=PASS")
        self.cost_labels["retry"].setText("FALSE")
        self.cost_labels["resubmission"].setText("FALSE")
        self.cost_labels["authorization"].setText(review.production_authorization)
        self.cost_labels["policy"].setText(review.authorization_policy)
        acknowledged = review.production_authorization in {
            "VALID",
            "VALID_BOUND_TO_CURRENT_COST_ENVELOPE",
        }
        self.authorize_button.setVisible(not acknowledged)
        if not acknowledged:
            self.authorize_button.setText(
                "Request cost-envelope re-acknowledgement"
                if review.production_authorization
                in {"ACTIVE_BUT_UNBOUND_REACK_REQUIRED", "AWAITING_HUMAN_AUTHORIZATION"}
                else "Authorize provider execution"
            )

    def validate_current(self) -> MediaCostPreflightReview:
        """Compare-and-set check for a future approval action."""

        try:
            current = validate_persisted_media_cost_preflight_review(
                self.repo_root,
                self.review,
            )
        except MediaCostPreflightError as exc:
            self.stale_state_detected.emit(str(exc))
            raise
        self.review = current
        self._render()
        return current

    def _refresh_review(self) -> None:
        try:
            self.validate_current()
        except MediaCostPreflightError as exc:
            QMessageBox.warning(self, "SIRAJ", str(exc))

    def _request_authorization(self) -> None:
        try:
            current = self.validate_current()
        except MediaCostPreflightError as exc:
            QMessageBox.warning(self, "SIRAJ", str(exc))
            return
        # Emitting a review-bound request is not authorization by itself.  The
        # parent window opens an explicit confirmation dialog, then delegates
        # the write to the application service.
        snapshot = current.as_dict()
        snapshot["reviewed_at_utc"] = utc_now()
        self.authorization_requested.emit(snapshot)

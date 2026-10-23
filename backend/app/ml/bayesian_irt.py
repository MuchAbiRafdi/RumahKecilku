"""Guarded interface for future CDI estimates.

Do not enable a clinical estimate until an authorized item bank, calibrated item
parameters, validated priors, review thresholds, and clinical approval exist.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelStatus:
    available: bool
    model_name: str
    reason: str


MODEL_STATUS = ModelStatus(
    available=False,
    model_name="Bayesian IRT · not calibrated",
    reason=(
        "The supplied proposal/PDF does not include a validated KPSP item bank, "
        "calibrated IRT parameters, or clinical validation dataset."
    ),
)


def estimate_domain_scores(*_args, **_kwargs):
    """Fail closed instead of returning unsupported or fabricated scores."""
    raise RuntimeError(
        "Bayesian IRT is disabled until authorized calibration data and validation are supplied."
    )

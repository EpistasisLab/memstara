## Robustness and validation

Interpret the recorded model and hypothesis through separate ML reproducibility and robustness evidence.
Reproducibility means the saved input, split, preprocessing and model settings produce
identical predictions on independent refitting in the recorded environment. Use only the
measured evaluation.reproducibility status; missing evidence means not recorded, not weak.
Different splits/seeds test robustness, not the ability to repeat the original computation.
Identify the actual training/hold-out strategy, seed, cross-validation and replicates.
Use measured metrics only. Highlight rare outcomes, possible leakage, missing predictors,
and instability only when supported by the recorded artifacts; otherwise label them as
checks still needed. A single hold-out AUC is not a confidence interval. Explain whether
the evidence justifies prioritizing this hypothesis for external validation. Provide a
plain-language limitation and concrete next validation step, not clinical advice.

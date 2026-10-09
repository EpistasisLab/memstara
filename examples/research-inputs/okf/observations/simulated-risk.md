---
id: simulated-risk
title: Simulated measurements and a toy binary outcome
tags: [synthetic, tutorial, prediction]
---

# Simulated measurements and a toy binary outcome

This is invented educational knowledge, not a publication or a patient study.
The accompanying CSV contains entirely generated numbers. All four predictors
are available at a simulated baseline. The target is a simulated event at a
later time, with no clinical definition or validated medical interpretation.

Predictor meanings:

- `systolic_pressure`: an invented baseline pressure-like measurement.
- `resting_pulse`: an invented baseline pulse-like measurement.
- `activity_score`: an invented activity index from 0 to 9.
- `synthetic_marker`: an invented numerical marker from 0 to 6.

For a software demonstration, investigate whether these four baseline quantities
can predict the generated event. Their labels do not establish real measurement
units, causal relationships or applicability to patients. Use all four when the
runtime requests at least four predictors. Do not infer a real clinical target.

The intended hypothesis is limited to this simulation: measured differences in
these four baseline quantities may help discriminate the generated event labels.
Any measured performance is a software demonstration, not clinical validation.

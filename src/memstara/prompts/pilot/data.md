---
goal: Choose an explicit data partition following the selected allocation skill.
---
Return exactly one JSON object with test_size (fraction), seed (nonnegative integer), and stratify (true).
Follow the attached skill's train/test allocation constraints.
Do not change the feature list, target, values or rows. No preprocessing or imputation is allowed at this stage.
The code will create the split once and share its row identities between both ML estimators.

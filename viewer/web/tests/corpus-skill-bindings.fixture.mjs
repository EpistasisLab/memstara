// Explicit current corpus profiles for isolated UI tests; no patient data.
export const corpusSkillBindings={
  "profiles": {
    "hiv": {
      "label": "HIV / Addiction knowledge corpus",
      "hypothesis": [
        "hiv-psychiatric-or-substance-use",
        "addiction-sdoh",
        "hiv-okf-whole-graph",
        "hiv-no-knowledge"
      ],
      "report": [
        "shared-hiv",
        "shared-addiction"
      ]
    },
    "heart_failure": {
      "label": "HeartFailure knowledge corpus",
      "hypothesis": [
        "heart-failure-cardiovascular",
        "heart-failure-metabolic-renal",
        "heart-failure-lifestyle-social"
      ],
      "report": [
        "shared-heart-failure-cardiovascular",
        "shared-heart-failure-comorbidity"
      ]
    },
    "general": {
      "label": "General research corpus / model knowledge",
      "hypothesis": [
        "hypothesis_general"
      ],
      "report": [
        "shared-hiv",
        "shared-addiction"
      ]
    }
  },
  "default": "hiv",
  "research": {
    "hiv": "hiv",
    "heart": "heart_failure"
  }
};

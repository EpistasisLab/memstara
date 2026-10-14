// Explicit corpus profiles for isolated UI tests; no patient data.
export const corpusSkillBindings={
  "profiles": {
    "hiv": {
      "label": "HIV / Addiction knowledge corpus",
      "hypothesis": [
        "addiction-substance-use",
        "addiction-sdoh",
        "addiction-psychiatric",
        "random_features"
      ],
      "report": [
        "shared-anil-addiction",
        "shared-anil-hiv"
      ]
    },
    "heart_failure": {
      "label": "HeartFailure knowledge corpus",
      "hypothesis": [
        "heart-failure-cardiovascular",
        "heart-failure-metabolic-renal",
        "heart-failure-lifestyle-social",
        "random_features"
      ],
      "report": [
        "report_general"
      ]
    },
    "general": {
      "label": "General research corpus / model knowledge",
      "hypothesis": [
        "hypothesis_general",
        "random_features"
      ],
      "report": [
        "report_general"
      ]
    }
  },
  "default": "hiv",
  "research": {
    "hiv": "hiv",
    "heart": "heart_failure"
  }
};

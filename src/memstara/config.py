"""The settings class every sandbox script shares."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from motoro import CoreSettings


class Settings(CoreSettings):
    """Settings for the sandbox experiments.

    Apart from the four fields below, every value is core's default, untouched.
    """

    model_config = SettingsConfigDict(env_prefix="MOTORO_", env_file=None, extra="ignore")

    mcp_allowed_env_vars: str = (
        "MEMSTARA_DATASET_PATH,MEMSTARA_OUTPUT_DIR,MEMSTARA_ML_ENGINE,MEMSTARA_DATABASE_URL,"
        "MEMSTARA_OUTCOME_COLUMN,MEMSTARA_OKF_FIELDS,MEMSTARA_RUN_CONFIG,MEMSTARA_LEAKAGE_RULES_PATH,"
        "MEMSTARA_USER_SKILLS_DIR,MEMSTARA_SKILL_ALIASES_PATH,"
        # Keep explicitly selected caches and numerical limits consistent in
        # tool subprocesses. Provider credentials remain outside this allowlist.
        "HF_HOME,HF_HUB_CACHE,HF_HUB_OFFLINE,XDG_CACHE_HOME,"
        "OMP_NUM_THREADS,OPENBLAS_NUM_THREADS,MKL_NUM_THREADS,TOKENIZERS_PARALLELISM,"
        "MEMSTARA_DEBUGPY,MEMSTARA_DEBUGPY_WAIT,"
        # debugpy runs its check and prints its warning **the moment** the child
        # Python starts. Switching it off from inside the code is already too late
        # (tried that in quiet_child, and confirmed it). The parent has to set it
        # beforehand, and it has to be on this list to reach the child. Not a secret.
        "PYDEVD_DISABLE_FILE_VALIDATION"
    )

    # ------------------------------------------------------------------ #
    # Timeouts — core's shipped defaults are inverted
    # ------------------------------------------------------------------ #
    #
    # Core ships hook_timeout_seconds=30 while llm_call_timeout_seconds=120
    # (config.py:77,102). The outer bound is 4x tighter than the inner one, so a
    # slow completion always trips the hook first — and the abort message names
    # hook_timeout_seconds regardless of which timeout actually fired, which
    # points at the wrong knob.
    #
    # README.md:153-160 says to keep hook_timeout_seconds "comfortably above"
    # llm_call_timeout_seconds. The defaults contradict that. Observed here: at
    # concurrency 5 against Foundry, reason_act's pre_act hook exceeded 30s on
    # 5 of 8 trials.
    #
    # So the outer bound is widened to 300 seconds here.
    llm_call_timeout_seconds: int = 120
    hook_timeout_seconds: int = 300

    # ------------------------------------------------------------------ #
    # Tool-result truncation — the shipped default cuts real OKF bodies in half
    # ------------------------------------------------------------------ #
    #
    # Core truncates a prior tool result at 4,000 characters (config.py:88). That is
    # fine for the synthetic sample bundle, whose concepts are a few hundred
    # characters, and wrong for anything written from real papers.
    #
    # Measured on the shared hiv-suppression bundle (142 paper concepts): median body
    # 8,145 characters, maximum 40,223, and **124 of 142 (87%) exceed 4,000**. The
    # predictor tables those concepts carry sit near the end of the body, so at the
    # default the agent opens a concept and receives everything except the part it
    # came for.
    #
    # 12,000 covers the median comfortably without carrying the longest outliers whole.
    act_prior_result_max_chars: int = 12000

    # Sandbox-only fields go here. Core never sees them.
    #
    # For example:
    #   data_dir: str = "./sandbox/outputs"
    #   my_feature_flag: bool = False
    #
    # Overriding one from the environment takes the prefix — MOTORO_DATA_DIR.

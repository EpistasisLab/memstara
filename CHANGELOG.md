# Changelog

## v0.1.0

First MVP release, bringing the research workflow into one application.

- **Data setup:** Upload and check CSV files, choose a prediction target, and optionally fill missing predictor values using training data only.
- **Research workflow:** Choose agent skills for hypothesis generation, data preparation, machine learning, SHAP/LIME interpretation and expert explanation. Use research documents or LLM knowledge only.
- **Model settings:** Start without LLM credentials and configure Azure Foundry in the GUI, or use `.env` defaults. Field examples distinguish the base model from its Azure deployment name. GUI settings apply to all agents in that experiment; a complete model configuration is required before execution.
- **Reproducible runs:** Configure train/test splitting, pipeline order and replicates. Save execution seeds and apply each run's seed to both the split and model random state.
- **Execution controls:** Follow live agent activity and logs, pause/resume supported executions, and retry interrupted work while preserving saved progress and results.
- **Results and usage:** Browse completed outputs by pipeline and replicate. Results show saved Interpretation output, Conclusions show saved Explanation output, and Usage shows Motoro-reported usage and cost estimates. Subtle New badges highlight unread updates in all three views.
- **Usability and reliability:** Simplify experiment setup and responsive layouts; improve input validation, saved-state recovery and automated regression checks.
- **Installation:** Start the application with Docker, Motoro 0.13.0 and the included Heart Failure example. Align package and Docker release versions and exclude local design photos from source packages.

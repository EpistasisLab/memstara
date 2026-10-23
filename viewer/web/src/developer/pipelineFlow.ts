/** Source-reviewed board execution guide; edges are semantic handoffs, not imports. */
export const pipelineSteps = [
  {
    "id": "launch",
    "title": "Launch & validate",
    "owner": "Frontend \u2192 control",
    "input": "Selected skills, model, knowledge scope, loop limits",
    "output": "Validated workspace configuration and child process",
    "detail": "Validate requested settings; freeze the combination schedule; create a run directory; launch the board entry point.",
    "sources": [
      "viewer/web/src/store/pipelines.ts",
      "src/memstara/control/service.py",
      "src/memstara/control/workspace.py"
    ]
  },
  {
    "id": "freeze",
    "title": "Freeze & resume",
    "owner": "Pipeline controller",
    "input": "CLI arguments, optional checkpoint",
    "output": "config.json, resume_arguments.json, checkpoint",
    "detail": "Acquire execution ownership; freeze evaluation policy; restore checkpoint and recorded calls for resume.",
    "sources": [
      "src/memstara/pipeline/board.py",
      "src/memstara/pipeline/checkpoint.py",
      "src/memstara/pipeline/run_ownership.py",
      "src/memstara/evaluation.py"
    ]
  },
  {
    "id": "provision",
    "title": "Provision agents & tools",
    "owner": "Runtime boundary",
    "input": "Selected stage playbooks, provider/model",
    "output": "Agent IDs, prompt hashes, allowed tool sets",
    "detail": "Provision named agents; launch MCP child processes; filter tools by stage and validate required tools.",
    "sources": [
      "src/memstara/pipeline/core.py",
      "src/memstara/pipeline/board.py",
      "src/memstara/pipeline/failures.py"
    ]
  },
  {
    "id": "schedule",
    "title": "Choose loop configuration",
    "owner": "All combinations / standard",
    "input": "Frozen skill combinations and repetition limit",
    "output": "Loop-specific agent roster and skill hashes",
    "detail": "All combinations uses a frozen Cartesian schedule. Random Start rotates its starting point; it does not mean random feature selection. Standard execution uses the configured roster.",
    "sources": [
      "src/memstara/combinations.py",
      "src/memstara/pipeline/board.py"
    ]
  },
  {
    "id": "question",
    "title": "Generate & validate question",
    "owner": "Hypothesis agent: question phase",
    "input": "Knowledge scope, prior question bank, fixed target",
    "output": "Grounded question contract and question ID",
    "detail": "Read the catalog and knowledge; propose questions; reject invalid or duplicate proposals; apply the configured question repair and exploration policy. Question generation is a phase of the hypothesis role.",
    "sources": [
      "src/memstara/pipeline/board.py",
      "src/memstara/pipeline/question_contract.py",
      "src/memstara/pipeline/question_repair.py",
      "src/memstara/pipeline/exploration.py"
    ]
  },
  {
    "id": "hypothesis",
    "title": "Ground hypothesis & map features",
    "owner": "Hypothesis agent",
    "input": "Claimed question, knowledge documents, dataset schema",
    "output": "Hypothesis, selected columns, concept IDs, task ID",
    "detail": "Search and read OKF evidence; match clinical concepts to candidate columns; create the analysis task; preserve matcher provenance. The target must not be a feature.",
    "sources": [
      "src/memstara/prompts/board/hypothesis.md",
      "src/memstara/mcp_servers/okf.py",
      "src/memstara/mcp_servers/matcher.py",
      "src/memstara/pipeline/board.py"
    ]
  },
  {
    "id": "claim",
    "title": "Claim ready work",
    "owner": "Blackboard / scheduler",
    "input": "Ready tasks and worker capacity",
    "output": "Atomic task ownership and stage invocation",
    "detail": "StageWorkers launches only eligible available workers. claim_task uses an atomic row claim; different tasks may occupy different stages concurrently.",
    "sources": [
      "src/memstara/pipeline/scheduler.py",
      "src/memstara/mcp_servers/blackboard.py"
    ]
  },
  {
    "id": "data",
    "title": "Extract data",
    "owner": "Data agent \u2192 data tool",
    "input": "Claimed task, selected columns and target",
    "output": "Subset artifact, used/missing columns",
    "detail": "The current board branch grants the data agent describe_dataset, slice_columns, claim_task and submit_result. The extraction itself runs in code.",
    "sources": [
      "src/memstara/pipeline/core.py",
      "src/memstara/mcp_servers/data.py"
    ]
  },
  {
    "id": "ml",
    "title": "Train & evaluate",
    "owner": "ML agent \u2192 ML tool",
    "input": "Subset, fixed evaluation configuration",
    "output": "Metrics, confusion matrices, feature explanations",
    "detail": "The current board branch grants the ML agent train_and_score, claim_task and submit_result. The ML tool performs fitting, scoring and explanation calculations; inspect the stored result for the actual split and settings.",
    "sources": [
      "src/memstara/pipeline/core.py",
      "src/memstara/mcp_servers/ml.py",
      "src/memstara/evaluation.py"
    ]
  },
  {
    "id": "interpret",
    "title": "Interpret measurements",
    "owner": "Interpretation worker(s)",
    "input": "Saved ML evidence and interpretation skill",
    "output": "Structured interpretation, optional branch results",
    "detail": "Claim the interpretation task; analyze saved evidence; submit the interpretation. Configured interpretation fan-out uses eligible worker slots and records branches separately.",
    "sources": [
      "src/memstara/interpretation_fanout.py",
      "src/memstara/prompts/board/interpreter.md",
      "src/memstara/mcp_servers/blackboard.py"
    ]
  },
  {
    "id": "outcome",
    "title": "Persist question outcomes",
    "owner": "Controller / blackboard",
    "input": "Completed and failed tasks",
    "output": "Question scores, retirement state, round status",
    "detail": "Write outcomes back to the question bank before the next loop. Verify analysis completion from persisted task state, not an agent completion claim.",
    "sources": [
      "src/memstara/pipeline/board.py",
      "src/memstara/mcp_servers/blackboard.py"
    ]
  },
  {
    "id": "report",
    "title": "Explain & report",
    "owner": "Explanation / report agent",
    "input": "Saved results, supporting knowledge, report skill",
    "output": "report.md and report_status.json",
    "detail": "Read saved results and knowledge; explain implications and limitations. Repeated/combination runs generate loop reports; final synthesis follows the configured path. A report failure does not erase analysis evidence.",
    "sources": [
      "src/memstara/prompts/board/report.md",
      "src/memstara/pipeline/board.py"
    ]
  },
  {
    "id": "archive",
    "title": "Archive & finalize",
    "owner": "Controller cleanup",
    "input": "Task board, calls and final report status",
    "output": "board.json, runs.json, trace/, execution factors",
    "detail": "Persist status and trace artifacts. Finally cleanup closes workers and tool processes; trace recording also runs on interrupted execution.",
    "sources": [
      "src/memstara/pipeline/board.py",
      "src/memstara/trace/run.py"
    ]
  },
  {
    "id": "read",
    "title": "Read & render evidence",
    "owner": "Read API \u2192 frontend",
    "input": "Database records and archived execution artifacts",
    "output": "Experiments, results, question universe, live log",
    "detail": "The viewer assembles read-only snapshots. A polling/display error is not evidence of pipeline failure. Selected execution IDs scope detailed inspection.",
    "sources": [
      "viewer/api/scene.py",
      "viewer/api/main.py",
      "viewer/web/src/store/viewer.ts",
      "viewer/web/src/panels/PipelineWorkspace.tsx"
    ]
  },
  {
    "id": "repair",
    "title": "Repair / retry / block",
    "owner": "Recovery policy",
    "input": "Invalid question, missing artifact, worker failure",
    "output": "Verified artifact, another attempt, or explicit failure",
    "detail": "Recovery is bounded by the applicable policy. Check persisted artifacts before replay; completed work must not be duplicated. Inspect attempt records rather than assuming every retry succeeds.",
    "sources": [
      "src/memstara/pipeline/recovery.py",
      "src/memstara/pipeline/question_repair.py",
      "src/memstara/pipeline/failures.py"
    ]
  },
  {
    "id": "control",
    "title": "Pause / resume / end",
    "owner": "Execution gate & ownership",
    "input": "Explicit control command and process state",
    "output": "Checkpoint, cancellation or resumed execution",
    "detail": "Control applies across phases. Pausing does not mean a tool response has instantly returned; inspect recorded state and controller status. Resume restores checkpointed phases.",
    "sources": [
      "src/memstara/control/service.py",
      "src/memstara/pipeline/checkpoint.py",
      "src/memstara/pipeline/board.py"
    ]
  }
];
export const pipelineLinks = [["launch", "freeze", "handoff"], ["freeze", "provision", "handoff"], ["provision", "schedule", "handoff"], ["schedule", "question", "handoff"], ["question", "hypothesis", "handoff"], ["hypothesis", "claim", "handoff"], ["claim", "data", "handoff"], ["data", "ml", "handoff"], ["ml", "interpret", "handoff"], ["interpret", "outcome", "handoff"], ["outcome", "report", "handoff"], ["report", "archive", "handoff"], ["archive", "read", "handoff"], ["question", "repair", "invalid / no artifact"], ["hypothesis", "repair", "missing task"], ["data", "repair", "failure"], ["ml", "repair", "failure"], ["interpret", "repair", "incomplete"], ["repair", "question", "question repair"], ["repair", "claim", "eligible retry"], ["report", "schedule", "next loop, if configured"], ["control", "freeze", "resume checkpoint"], ["provision", "report", "report-only mode"], ["schedule", "hypothesis", "question phase disabled"], ["question", "schedule", "empty wave / exploration policy"]];

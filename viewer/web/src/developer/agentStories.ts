/** Source-reviewed educational scenarios. Never a recorded execution or measured timing. */
export type ComponentKind = 'source'|'tool'|'runtime'|'agent'|'database'|'ui';
export type Profile = {inputs:string[]; outputs:string[]; tools:string[]; boundary:string; failure:string; sources:string[]};
export type Actor = {id:string; name:string; kind:ComponentKind; subtitle:string; description:string; source:string; x:number; y:number; profile:Profile|null};
export type StoryStep = {id:string; fromId:string; toId:string; title:string; body:string; input:string; output:string; operation:string; owner:string; source:string};
export type Scenario = {id:string; name:string; caption:string; steps:StoryStep[]};
export const actors:Actor[] = [
  {
    "id": "knowledge",
    "name": "Knowledge corpus",
    "kind": "source",
    "subtitle": "Documents, metadata and evidence",
    "description": "The selected knowledge bundle is a file-backed source, not the cohort database. Search identifies candidates; reading retrieves their supporting text.",
    "source": "src/memstara/mcp_servers/okf.py",
    "x": 0,
    "y": 0,
    "profile": null
  },
  {
    "id": "okf",
    "name": "Knowledge tools",
    "kind": "tool",
    "subtitle": "okf_search \u00b7 okf_read",
    "description": "The MCP server searches the configured bundle and returns documents within its scope. Citations are evidence provenance, not measured model results.",
    "source": "src/memstara/mcp_servers/okf.py",
    "x": 238,
    "y": 0,
    "profile": null
  },
  {
    "id": "catalog",
    "name": "Column catalog",
    "kind": "source",
    "subtitle": "Concept-to-column candidates",
    "description": "The matcher uses catalog metadata and its configured ranking machinery. A candidate match is not a clinical conclusion.",
    "source": "src/memstara/matcher/matcher.py",
    "x": 476,
    "y": 0,
    "profile": null
  },
  {
    "id": "matcher",
    "name": "Semantic matcher",
    "kind": "tool",
    "subtitle": "match_concept(s)",
    "description": "Maps proposed concepts to available column candidates. The hypothesis stage verifies selections and preserves match provenance.",
    "source": "src/memstara/mcp_servers/matcher.py",
    "x": 714,
    "y": 0,
    "profile": null
  },
  {
    "id": "llm",
    "name": "Model provider",
    "kind": "runtime",
    "subtitle": "LLM requests and responses",
    "description": "Role instructions, task context and permitted tool schemas are passed to the configured model. The runtime executes tool requests and returns observations; the model does not directly connect to the databases.",
    "source": "src/memstara/pipeline/core.py",
    "x": 952,
    "y": 0,
    "profile": null
  },
  {
    "id": "hypothesis",
    "name": "Hypothesis",
    "kind": "agent",
    "subtitle": "Question design + feature grounding",
    "description": "First generates grounded questions with a restricted tool set, then investigates a selected question and creates a feature-bound analysis task. These are two phases of the same role.",
    "source": "src/memstara/prompts/board/hypothesis.md",
    "x": 0,
    "y": 150,
    "profile": {
      "inputs": [
        "Selected knowledge scope and question policy",
        "Question catalog and driver-supplied feedback",
        "Fixed target and permitted dataset feature context"
      ],
      "outputs": [
        "Grounded question and stable question ID",
        "Hypothesis, selected predictors and concept links",
        "Analysis task and matcher provenance"
      ],
      "tools": [
        "Question phase: okf_list_domains, okf_search, okf_read, read_question_catalog, propose_questions",
        "Investigation: okf_list_domains, okf_search, okf_read, describe_dataset, match_concepts, match_concept, claim_question, create_task"
      ],
      "boundary": "A generated question must satisfy the question contract. Mapping candidates and plausible mechanisms are not measured predictive evidence.",
      "failure": "Invalid or duplicate questions follow exploration/repair policy. Missing task artifacts are checked before replay.",
      "sources": [
        "src/memstara/pipeline/scientific_policy.py",
        "src/memstara/pipeline/question_contract.py",
        "src/memstara/pipeline/question_repair.py"
      ]
    }
  },
  {
    "id": "data",
    "name": "Data",
    "kind": "agent",
    "subtitle": "Claim \u2192 extract \u2192 hand off",
    "description": "In this checkout the Data agent orchestrates deterministic extraction through tools. It does not rewrite the dataset or invent missing columns.",
    "source": "src/memstara/prompts/board/data.md",
    "x": 238,
    "y": 150,
    "profile": {
      "inputs": [
        "Claimed task and selected predictor columns",
        "Fixed target and configured dataset path"
      ],
      "outputs": [
        "Subset path",
        "Used and missing columns",
        "Task handed to the ML stage"
      ],
      "tools": [
        "describe_dataset",
        "slice_columns",
        "claim_task",
        "submit_result"
      ],
      "boundary": "The agent coordinates tool use. Data extraction is code, and a missing column must be reported rather than invented.",
      "failure": "Tool failure or invalid output must not be silently promoted to a successful ML task.",
      "sources": [
        "src/memstara/mcp_servers/data.py",
        "src/memstara/mcp_servers/blackboard.py"
      ]
    }
  },
  {
    "id": "ml",
    "name": "Machine learning",
    "kind": "agent",
    "subtitle": "Claim \u2192 evaluate \u2192 persist",
    "description": "In this checkout the ML agent calls the evaluation tool. Code performs model fitting and scoring under the recorded settings; LLM prose is not a measured metric.",
    "source": "src/memstara/prompts/board/ml.md",
    "x": 476,
    "y": 150,
    "profile": {
      "inputs": [
        "Claimed task and subset artifact",
        "Frozen evaluation configuration"
      ],
      "outputs": [
        "Measured evaluation and confusion-matrix evidence where recorded",
        "Model-specific feature explanations",
        "Saved result passed to interpretation"
      ],
      "tools": [
        "train_and_score",
        "get_ml_configuration",
        "claim_task",
        "submit_result"
      ],
      "boundary": "LLM text does not create metrics. A held-out estimate, reproducibility and robustness across splits are different claims.",
      "failure": "A failed evaluation is preserved as a failure. No invented metric or automatic claim of clinical validation is permitted.",
      "sources": [
        "src/memstara/evaluation.py",
        "src/memstara/mcp_servers/ml.py"
      ]
    }
  },
  {
    "id": "interpreter",
    "name": "Interpretation",
    "kind": "agent",
    "subtitle": "Describe measured evidence",
    "description": "Describes observed findings, model performance, feature evidence and uncertainty. Its mandatory prompt excludes speculation, causal claims, recommendations and follow-up proposals.",
    "source": "src/memstara/prompts/board/interpreter.md",
    "x": 714,
    "y": 150,
    "profile": {
      "inputs": [
        "Saved hypothesis and measured model evidence",
        "Actual/missing features and interpretation skill"
      ],
      "outputs": [
        "Observed findings",
        "Model performance and feature observations",
        "Uncertainty, limitations and what is not established"
      ],
      "tools": [
        "claim_task",
        "submit_result"
      ],
      "boundary": "Describe facts and uncertainty. Do not recommend interventions, assert causality or propose follow-up experiments.",
      "failure": "Incomplete outputs may enter the guarded interpretation recovery path using saved ML evidence. A retry is not an ML rerun.",
      "sources": [
        "src/memstara/interpretation_fanout.py",
        "src/memstara/pipeline/recovery.py"
      ]
    }
  },
  {
    "id": "report",
    "name": "Explanation",
    "kind": "agent",
    "subtitle": "Explain meaning and limitations",
    "description": "The report role reads saved results and supporting knowledge to explain implications, research priorities and limits. Evidence strength, research priority and clinical readiness remain separate.",
    "source": "src/memstara/prompts/board/report.md",
    "x": 952,
    "y": 150,
    "profile": {
      "inputs": [
        "Saved analysis results and interpretations",
        "Supporting knowledge and explanation skill"
      ],
      "outputs": [
        "Explanation/report text",
        "Evidence limits and research priorities",
        "Report completion/error status"
      ],
      "tools": [
        "read_results",
        "okf_search",
        "okf_read"
      ],
      "boundary": "Knowledge supplies context, not missing experiment results. Distinguish evidence strength, research priority and clinical readiness.",
      "failure": "A read-only report retry can reuse saved results. Report failure does not erase completed analyses.",
      "sources": [
        "src/memstara/pipeline/board.py",
        "src/memstara/prompts/board/report.md"
      ]
    }
  },
  {
    "id": "control",
    "name": "Orchestrator",
    "kind": "runtime",
    "subtitle": "Schedule \u00b7 gate \u00b7 recover",
    "description": "Validates configuration, provisions agents, grants tools, claims execution ownership and checkpoints progress. Independent tasks can occupy different stages simultaneously.",
    "source": "src/memstara/pipeline/board.py",
    "x": 0,
    "y": 300,
    "profile": null
  },
  {
    "id": "board",
    "name": "Blackboard tools",
    "kind": "tool",
    "subtitle": "Claim \u00b7 validate \u00b7 submit",
    "description": "MCP operations implement atomic task claims, question contracts and result handoffs. The database stores state; the tool layer controls its valid transitions.",
    "source": "src/memstara/mcp_servers/blackboard.py",
    "x": 238,
    "y": 300,
    "profile": null
  },
  {
    "id": "datatool",
    "name": "Data tools",
    "kind": "tool",
    "subtitle": "describe_dataset \u00b7 slice_columns",
    "description": "Code inspects the configured local dataset and writes selected-column subsets. The fixed target is excluded from selectable predictors.",
    "source": "src/memstara/mcp_servers/data.py",
    "x": 476,
    "y": 300,
    "profile": null
  },
  {
    "id": "mltool",
    "name": "Evaluation tool",
    "kind": "tool",
    "subtitle": "train_and_score",
    "description": "Runs the configured numerical evaluation and returns recorded metrics and explanation artifacts. Inspect the actual evaluation payload for split, threshold and model settings.",
    "source": "src/memstara/mcp_servers/ml.py",
    "x": 714,
    "y": 300,
    "profile": null
  },
  {
    "id": "api",
    "name": "Read API",
    "kind": "runtime",
    "subtitle": "SELECT-only evidence assembly",
    "description": "Reads both databases and archived artifacts through scoped endpoints. Display errors or an old snapshot must not be treated as proof that execution failed.",
    "source": "viewer/api/main.py",
    "x": 952,
    "y": 300,
    "profile": null
  },
  {
    "id": "workspace",
    "name": "Web workspace",
    "kind": "ui",
    "subtitle": "Launch requests + evidence views",
    "description": "Sends explicit control commands and renders read-only evidence: floor plan, live log, results and question universe. This educational tour sends none of those commands.",
    "source": "viewer/web/src/panels/PipelineWorkspace.tsx",
    "x": 0,
    "y": 450,
    "profile": null
  },
  {
    "id": "memdb",
    "name": "Memstara DB",
    "kind": "database",
    "subtitle": "Questions \u00b7 tasks \u00b7 results",
    "description": "Separate PostgreSQL store: memstara_questions, memstara_blackboard and memstara_results. Question IDs, task IDs and execution tags link research evidence.",
    "source": "src/memstara/blackboard.py",
    "x": 238,
    "y": 450,
    "profile": null
  },
  {
    "id": "dataset",
    "name": "Local data files",
    "kind": "source",
    "subtitle": "Cohort + extracted subsets",
    "description": "The cohort stays local. Tools read configured paths and produce run-specific subsets. This diagram contains no patient records and uses no real example values.",
    "source": "src/memstara/mcp_servers/data.py",
    "x": 476,
    "y": 450,
    "profile": null
  },
  {
    "id": "coredb",
    "name": "Motoro DB",
    "kind": "database",
    "subtitle": "Agents \u00b7 runs \u00b7 run_steps",
    "description": "Separate runtime history store. Invocation IDs connect agent calls to recorded sequence, iteration, phase, model calls and tool calls. Source inspection here does not modify Motoro.",
    "source": "viewer/api/queries.py",
    "x": 714,
    "y": 450,
    "profile": null
  },
  {
    "id": "archive",
    "name": "Run artifacts",
    "kind": "source",
    "subtitle": "Config \u00b7 prompts \u00b7 traces \u00b7 report",
    "description": "Local files preserve frozen configuration, prompt hashes, checkpoints, manifests, reports and traces. Archived started/running status does not prove a process is still alive.",
    "source": "src/memstara/pipeline/board.py",
    "x": 952,
    "y": 450,
    "profile": null
  }
];
export const scenarios:Scenario[] = [
  {
    "id": "normal",
    "name": "One complete investigation",
    "caption": "Follow knowledge into a measured result and an explanation.",
    "steps": [
      {
        "id": "normal-1",
        "fromId": "workspace",
        "toId": "control",
        "title": "Freeze the requested experiment",
        "body": "The launch command validates the selected configuration. The controller starts a scoped board execution; this tour only illustrates that boundary.",
        "input": "Skills, model, knowledge scope and loop limits",
        "output": "Validated execution configuration",
        "operation": "Control command",
        "owner": "control",
        "source": "src/memstara/control/service.py"
      },
      {
        "id": "normal-2",
        "fromId": "control",
        "toId": "archive",
        "title": "Checkpoint the configuration",
        "body": "Freeze settings and prompt provenance so a later run can be understood and resumed.",
        "input": "Validated arguments and selected playbooks",
        "output": "Configuration, checkpoint and prompt hashes",
        "operation": "File write",
        "owner": "control",
        "source": "src/memstara/pipeline/board.py"
      },
      {
        "id": "normal-3",
        "fromId": "control",
        "toId": "hypothesis",
        "title": "Start the question phase",
        "body": "The controller gives the hypothesis role its question-only tool set. Question generation is not a separate sixth agent.",
        "input": "Knowledge scope, target and catalog policy",
        "output": "Scoped question-generation invocation",
        "operation": "Dispatch",
        "owner": "hypothesis",
        "source": "src/memstara/pipeline/core.py"
      },
      {
        "id": "normal-4",
        "fromId": "hypothesis",
        "toId": "llm",
        "title": "Ask the configured model",
        "body": "The runtime sends role instructions, user context and permitted tool schemas. Other roles use the same request/tool-observation mechanism.",
        "input": "Prompt + context + allowed tool schemas",
        "output": "Model response or tool request",
        "operation": "LLM request",
        "owner": "hypothesis",
        "source": "src/memstara/pipeline/core.py"
      },
      {
        "id": "normal-5",
        "fromId": "llm",
        "toId": "hypothesis",
        "title": "Receive the model decision",
        "body": "The runtime receives model text or a structured tool request. It dispatches permitted tools and feeds their observations back for the next turn.",
        "input": "Model response",
        "output": "Permitted tool request or answer",
        "operation": "LLM response",
        "owner": "hypothesis",
        "source": "src/memstara/pipeline/core.py"
      },
      {
        "id": "normal-6",
        "fromId": "hypothesis",
        "toId": "okf",
        "title": "Search supporting knowledge",
        "body": "The model requests a permitted knowledge tool through the runtime. Agents access evidence through tools, not direct database connections.",
        "input": "Search terms and scope",
        "output": "Scoped document candidates",
        "operation": "Tool request",
        "owner": "hypothesis",
        "source": "src/memstara/prompts/board/hypothesis.md"
      },
      {
        "id": "normal-7",
        "fromId": "okf",
        "toId": "knowledge",
        "title": "Read the selected documents",
        "body": "The knowledge server reads the configured corpus. Search results and full document text serve different purposes.",
        "input": "Document identifiers",
        "output": "Supporting document content",
        "operation": "File read",
        "owner": "okf",
        "source": "src/memstara/mcp_servers/okf.py"
      },
      {
        "id": "normal-8",
        "fromId": "knowledge",
        "toId": "hypothesis",
        "title": "Ground a candidate question",
        "body": "Document content returns through the knowledge server/runtime. This arrow summarizes that return path; it is not a direct file connection from the model.",
        "input": "Knowledge evidence and source IDs",
        "output": "Candidate question with evidence links",
        "operation": "Logical return via tools",
        "owner": "hypothesis",
        "source": "src/memstara/prompts/board/hypothesis.md"
      },
      {
        "id": "normal-9",
        "fromId": "hypothesis",
        "toId": "board",
        "title": "Propose a valid question",
        "body": "The restricted question tool surface reads the catalog and submits proposals for validation and duplicate checks.",
        "input": "Question text, target and grounding metadata",
        "output": "Accepted question or explicit rejection/duplicate",
        "operation": "propose_questions",
        "owner": "hypothesis",
        "source": "src/memstara/pipeline/question_contract.py"
      },
      {
        "id": "normal-10",
        "fromId": "board",
        "toId": "memdb",
        "title": "Persist the question",
        "body": "Accepted questions receive identities in the question bank. Invalid candidates do not become successful tasks just because the model says they are ready.",
        "input": "Validated question",
        "output": "memstara_questions row",
        "operation": "Database write",
        "owner": "board",
        "source": "src/memstara/mcp_servers/blackboard.py"
      },
      {
        "id": "normal-11",
        "fromId": "memdb",
        "toId": "hypothesis",
        "title": "Claim a question to investigate",
        "body": "Through claim_question, the answering phase receives a scoped question. A question ID keeps subsequent results attached to their origin.",
        "input": "Eligible question record",
        "output": "Claimed question and evidence context",
        "operation": "Logical return via claim_question",
        "owner": "hypothesis",
        "source": "src/memstara/prompts/board/hypothesis.md"
      },
      {
        "id": "normal-12",
        "fromId": "hypothesis",
        "toId": "datatool",
        "title": "Inspect available predictors",
        "body": "describe_dataset exposes permitted feature context. The target is excluded from the selectable predictor list.",
        "input": "Configured dataset",
        "output": "Available predictor schema",
        "operation": "describe_dataset",
        "owner": "hypothesis",
        "source": "src/memstara/prompts/board/hypothesis.md"
      },
      {
        "id": "normal-13",
        "fromId": "hypothesis",
        "toId": "matcher",
        "title": "Translate concepts into features",
        "body": "The hypothesis agent requests candidate dataset columns for its clinical concepts. Candidate ranking is not proof that a feature is causal.",
        "input": "Clinical concepts",
        "output": "Ranked column candidates",
        "operation": "match_concept(s)",
        "owner": "hypothesis",
        "source": "src/memstara/prompts/board/hypothesis.md"
      },
      {
        "id": "normal-14",
        "fromId": "matcher",
        "toId": "catalog",
        "title": "Look up column candidates",
        "body": "The matcher consults its catalog and configured ranking machinery; the agent must still select suitable columns.",
        "input": "Concept query",
        "output": "Candidate metadata and scores",
        "operation": "Catalog lookup",
        "owner": "matcher",
        "source": "src/memstara/mcp_servers/matcher.py"
      },
      {
        "id": "normal-15",
        "fromId": "matcher",
        "toId": "hypothesis",
        "title": "Return mapping evidence",
        "body": "The response retains alternatives and match evidence so reviewers can understand why a column was selected.",
        "input": "Ranked candidates",
        "output": "Selected predictors and mapping provenance",
        "operation": "Tool response",
        "owner": "hypothesis",
        "source": "src/memstara/prompts/board/hypothesis.md"
      },
      {
        "id": "normal-16",
        "fromId": "hypothesis",
        "toId": "board",
        "title": "Create the analysis task",
        "body": "The hypothesis and concrete column selection become persisted work. Recovery checks for this artifact before replaying task creation.",
        "input": "Hypothesis, columns, target and question ID",
        "output": "Analysis task ID",
        "operation": "create_task",
        "owner": "hypothesis",
        "source": "src/memstara/prompts/board/hypothesis.md"
      },
      {
        "id": "normal-17",
        "fromId": "board",
        "toId": "memdb",
        "title": "Queue the data stage",
        "body": "The blackboard stores task state. An atomic claim prevents two workers from taking the same eligible row.",
        "input": "Validated task",
        "output": "Ready task in memstara_blackboard",
        "operation": "Database write",
        "owner": "board",
        "source": "src/memstara/mcp_servers/blackboard.py"
      },
      {
        "id": "normal-18",
        "fromId": "board",
        "toId": "data",
        "title": "Claim the data task",
        "body": "The Data agent calls claim_task and receives its owned row. The scheduler only launches available workers for ready work.",
        "input": "Ready data task",
        "output": "Owned task and chosen columns",
        "operation": "claim_task response",
        "owner": "data",
        "source": "src/memstara/prompts/board/data.md"
      },
      {
        "id": "normal-19",
        "fromId": "data",
        "toId": "llm",
        "title": "Data: send the role context",
        "body": "The runtime sends the role prompt, selected skill, task context and allowed tool schemas to the configured model. This is the same model/tool loop used by other roles.",
        "input": "Role prompt + task evidence + tool schemas",
        "output": "Model request",
        "operation": "LLM request",
        "owner": "data",
        "source": "src/memstara/pipeline/core.py"
      },
      {
        "id": "normal-20",
        "fromId": "llm",
        "toId": "data",
        "title": "Data: receive the next action",
        "body": "The runtime receives a tool request or response. Tool results are observations for subsequent turns; the number of turns is execution-dependent, not fixed by this illustration.",
        "input": "Model response",
        "output": "Permitted tool request or role response",
        "operation": "LLM response",
        "owner": "data",
        "source": "src/memstara/pipeline/core.py"
      },
      {
        "id": "normal-21",
        "fromId": "data",
        "toId": "datatool",
        "title": "Request the selected-column subset",
        "body": "The Data agent coordinates the request; deterministic code performs the extraction.",
        "input": "Selected predictors and task context",
        "output": "Extraction request",
        "operation": "slice_columns",
        "owner": "data",
        "source": "src/memstara/prompts/board/data.md"
      },
      {
        "id": "normal-22",
        "fromId": "datatool",
        "toId": "dataset",
        "title": "Extract local data",
        "body": "The tool reads configured data and saves a subset artifact. Missing columns are reported explicitly.",
        "input": "Local cohort + selected columns",
        "output": "Subset file + used/missing columns",
        "operation": "File read/write",
        "owner": "datatool",
        "source": "src/memstara/mcp_servers/data.py"
      },
      {
        "id": "normal-23",
        "fromId": "datatool",
        "toId": "data",
        "title": "Return the extraction result",
        "body": "The agent receives the tool result rather than an invented description of a dataset.",
        "input": "Extraction outcome",
        "output": "Subset location and column audit",
        "operation": "Tool response",
        "owner": "data",
        "source": "src/memstara/prompts/board/data.md"
      },
      {
        "id": "normal-24",
        "fromId": "data",
        "toId": "board",
        "title": "Hand the task to ML",
        "body": "submit_result validates and persists the stage result. The logical next stage becomes eligible only through the recorded state transition.",
        "input": "Subset and column evidence",
        "output": "Task ready for ML",
        "operation": "submit_result",
        "owner": "data",
        "source": "src/memstara/prompts/board/data.md"
      },
      {
        "id": "normal-25",
        "fromId": "board",
        "toId": "ml",
        "title": "Claim the evaluation task",
        "body": "The ML role receives the saved data-stage output via claim_task.",
        "input": "Ready ML task",
        "output": "Owned task + subset + evaluation context",
        "operation": "claim_task response",
        "owner": "ml",
        "source": "src/memstara/prompts/board/ml.md"
      },
      {
        "id": "normal-26",
        "fromId": "ml",
        "toId": "llm",
        "title": "Machine learning: send the role context",
        "body": "The runtime sends the role prompt, selected skill, task context and allowed tool schemas to the configured model. This is the same model/tool loop used by other roles.",
        "input": "Role prompt + task evidence + tool schemas",
        "output": "Model request",
        "operation": "LLM request",
        "owner": "ml",
        "source": "src/memstara/pipeline/core.py"
      },
      {
        "id": "normal-27",
        "fromId": "llm",
        "toId": "ml",
        "title": "Machine learning: receive the next action",
        "body": "The runtime receives a tool request or response. Tool results are observations for subsequent turns; the number of turns is execution-dependent, not fixed by this illustration.",
        "input": "Model response",
        "output": "Permitted tool request or role response",
        "operation": "LLM response",
        "owner": "ml",
        "source": "src/memstara/pipeline/core.py"
      },
      {
        "id": "normal-28",
        "fromId": "ml",
        "toId": "mltool",
        "title": "Request numerical evaluation",
        "body": "train_and_score executes evaluation code. The LLM does not choose metric values or establish validation by writing a confident answer.",
        "input": "Subset and frozen settings",
        "output": "Evaluation job",
        "operation": "train_and_score",
        "owner": "ml",
        "source": "src/memstara/prompts/board/ml.md"
      },
      {
        "id": "normal-29",
        "fromId": "mltool",
        "toId": "dataset",
        "title": "Read the subset and evaluate",
        "body": "Code performs the configured fitting and scoring. Inspect the actual payload for split, seed, threshold, model settings and supported explanations.",
        "input": "Subset data + recorded evaluation policy",
        "output": "Measured metrics and explanation artifacts",
        "operation": "Numerical code",
        "owner": "mltool",
        "source": "src/memstara/mcp_servers/ml.py"
      },
      {
        "id": "normal-30",
        "fromId": "mltool",
        "toId": "ml",
        "title": "Return measured evidence",
        "body": "Return the measured result, including confusion-matrix and feature evidence where recorded. Missing evidence remains missing.",
        "input": "Evaluation result",
        "output": "Structured ML evidence",
        "operation": "Tool response",
        "owner": "ml",
        "source": "src/memstara/prompts/board/ml.md"
      },
      {
        "id": "normal-31",
        "fromId": "ml",
        "toId": "board",
        "title": "Save ML evidence",
        "body": "The ML result is submitted through the blackboard tools and becomes available for interpretation.",
        "input": "Measured evaluation payload",
        "output": "Persisted evidence and interpretation task",
        "operation": "submit_result",
        "owner": "ml",
        "source": "src/memstara/prompts/board/ml.md"
      },
      {
        "id": "normal-32",
        "fromId": "board",
        "toId": "interpreter",
        "title": "Claim interpretation work",
        "body": "The worker receives the saved result. When interpretation fan-out is configured, eligible branches use the same saved ML evidence.",
        "input": "Measured result + assigned interpretation skill",
        "output": "Owned interpretation task",
        "operation": "claim_task response",
        "owner": "interpreter",
        "source": "src/memstara/prompts/board/interpreter.md"
      },
      {
        "id": "normal-33",
        "fromId": "interpreter",
        "toId": "llm",
        "title": "Interpretation: send the role context",
        "body": "The runtime sends the role prompt, selected skill, task context and allowed tool schemas to the configured model. This is the same model/tool loop used by other roles.",
        "input": "Role prompt + task evidence + tool schemas",
        "output": "Model request",
        "operation": "LLM request",
        "owner": "interpreter",
        "source": "src/memstara/pipeline/core.py"
      },
      {
        "id": "normal-34",
        "fromId": "llm",
        "toId": "interpreter",
        "title": "Interpretation: receive the next action",
        "body": "The runtime receives a tool request or response. Tool results are observations for subsequent turns; the number of turns is execution-dependent, not fixed by this illustration.",
        "input": "Model response",
        "output": "Permitted tool request or role response",
        "operation": "LLM response",
        "owner": "interpreter",
        "source": "src/memstara/pipeline/core.py"
      },
      {
        "id": "normal-35",
        "fromId": "interpreter",
        "toId": "board",
        "title": "Record factual interpretation",
        "body": "Report observed findings, performance, feature observations and uncertainty. Recommendations and causal claims belong outside this role.",
        "input": "Saved evidence",
        "output": "Structured factual interpretation",
        "operation": "submit_result",
        "owner": "interpreter",
        "source": "src/memstara/prompts/board/interpreter.md"
      },
      {
        "id": "normal-36",
        "fromId": "board",
        "toId": "memdb",
        "title": "Persist completed analysis",
        "body": "The blackboard/results store retains the analysis and interpretation. Outcome bookkeeping updates question history before the next loop.",
        "input": "Completed stage outputs",
        "output": "Saved analysis + question outcome",
        "operation": "Database write",
        "owner": "board",
        "source": "src/memstara/mcp_servers/blackboard.py"
      },
      {
        "id": "normal-37",
        "fromId": "board",
        "toId": "report",
        "title": "Read completed evidence",
        "body": "The Explanation agent uses read_results for the scoped run. It must not fill missing results with literature or plausible text.",
        "input": "Saved results and interpretations",
        "output": "Scoped analysis evidence",
        "operation": "read_results response",
        "owner": "report",
        "source": "src/memstara/prompts/board/report.md"
      },
      {
        "id": "normal-38",
        "fromId": "report",
        "toId": "llm",
        "title": "Explanation: send the role context",
        "body": "The runtime sends the role prompt, selected skill, task context and allowed tool schemas to the configured model. This is the same model/tool loop used by other roles.",
        "input": "Role prompt + task evidence + tool schemas",
        "output": "Model request",
        "operation": "LLM request",
        "owner": "report",
        "source": "src/memstara/pipeline/core.py"
      },
      {
        "id": "normal-39",
        "fromId": "llm",
        "toId": "report",
        "title": "Explanation: receive the next action",
        "body": "The runtime receives a tool request or response. Tool results are observations for subsequent turns; the number of turns is execution-dependent, not fixed by this illustration.",
        "input": "Model response",
        "output": "Permitted tool request or role response",
        "operation": "LLM response",
        "owner": "report",
        "source": "src/memstara/pipeline/core.py"
      },
      {
        "id": "normal-40",
        "fromId": "report",
        "toId": "okf",
        "title": "Retrieve explanatory context",
        "body": "The report role may search and read supporting knowledge. Knowledge evidence and observed experiment results remain distinguishable.",
        "input": "Analysis context and knowledge query",
        "output": "Supporting documents",
        "operation": "okf_search / okf_read",
        "owner": "report",
        "source": "src/memstara/prompts/board/report.md"
      },
      {
        "id": "normal-41",
        "fromId": "report",
        "toId": "archive",
        "title": "Save the explanation",
        "body": "The controller saves returned report text and completion status. A report failure does not erase completed analysis results.",
        "input": "Explanation text and outcome",
        "output": "report.md + report_status.json",
        "operation": "Logical save via controller",
        "owner": "report",
        "source": "src/memstara/prompts/board/report.md"
      },
      {
        "id": "normal-42",
        "fromId": "control",
        "toId": "coredb",
        "title": "Retain the runtime trace",
        "body": "The runtime, not the remote model itself, writes invocation steps as calls progress. This cross-cutting activity occurs throughout the run, not only after reporting.",
        "input": "Recorded model/tool interactions",
        "output": "agent_runs and run_steps",
        "operation": "Cross-cutting runtime persistence",
        "owner": "control",
        "source": "src/memstara/pipeline/board.py"
      },
      {
        "id": "normal-43",
        "fromId": "control",
        "toId": "archive",
        "title": "Finalize manifests and traces",
        "body": "The controller preserves final board state, invocation IDs and trace exports; cleanup also handles interruptions.",
        "input": "Persisted calls, board and status",
        "output": "Manifests, board snapshot and trace files",
        "operation": "File write",
        "owner": "control",
        "source": "src/memstara/pipeline/board.py"
      },
      {
        "id": "normal-44",
        "fromId": "memdb",
        "toId": "api",
        "title": "Read research evidence",
        "body": "The read-only API fetches scoped questions, task states and results. It does not advance the pipeline.",
        "input": "Selected execution scope",
        "output": "Research records",
        "operation": "SELECT",
        "owner": "api",
        "source": "viewer/api/main.py"
      },
      {
        "id": "normal-45",
        "fromId": "coredb",
        "toId": "api",
        "title": "Read runtime evidence",
        "body": "Separate read-only queries obtain invocation history and individual stored steps. Missing or unavailable history is not a successful empty result.",
        "input": "Scoped invocation IDs",
        "output": "Stored steps and tool/model fields",
        "operation": "SELECT",
        "owner": "api",
        "source": "viewer/api/main.py"
      },
      {
        "id": "normal-46",
        "fromId": "archive",
        "toId": "api",
        "title": "Read saved run artifacts",
        "body": "Archived configuration, manifests and report status supplement database records. Status alone does not prove live process activity.",
        "input": "Selected execution archive",
        "output": "Configuration and report evidence",
        "operation": "File read",
        "owner": "api",
        "source": "viewer/api/main.py"
      },
      {
        "id": "normal-47",
        "fromId": "api",
        "toId": "workspace",
        "title": "Render the evidence",
        "body": "The UI presents linked results and progress. A display error remains separate from the execution state; this tour creates no new run.",
        "input": "Scoped API response",
        "output": "Floor plan, results, logs and question universe",
        "operation": "HTTP response",
        "owner": "workspace",
        "source": "viewer/web/src/panels/PipelineWorkspace.tsx"
      }
    ]
  },
  {
    "id": "repair",
    "name": "Question repair & failure",
    "caption": "Understand validation gates and artifact-aware recovery.",
    "steps": [
      {
        "id": "repair-1",
        "fromId": "hypothesis",
        "toId": "board",
        "title": "A proposed question is rejected",
        "body": "Validation or duplicate checks reject a candidate. This is a conditional example, not a prediction that every run fails.",
        "input": "Invalid/duplicate proposal",
        "output": "Rejection details",
        "operation": "Validation",
        "owner": "hypothesis",
        "source": "src/memstara/pipeline/question_contract.py"
      },
      {
        "id": "repair-2",
        "fromId": "board",
        "toId": "control",
        "title": "Check durable state before retry",
        "body": "Recovery inspects persisted artifacts and policy before replay. A failed read is not permission to duplicate a mutation.",
        "input": "Rejection or missing artifact",
        "output": "Known recovery condition",
        "operation": "Artifact check",
        "owner": "control",
        "source": "src/memstara/pipeline/recovery.py"
      },
      {
        "id": "repair-3",
        "fromId": "control",
        "toId": "hypothesis",
        "title": "Repair within the applicable policy",
        "body": "Provide repair context for another allowed attempt. Policies differ by phase; this tour does not promise unlimited retries.",
        "input": "Failure context + attempt budget",
        "output": "Revised request or blocked outcome",
        "operation": "Conditional retry",
        "owner": "hypothesis",
        "source": "src/memstara/pipeline/question_repair.py"
      },
      {
        "id": "repair-4",
        "fromId": "hypothesis",
        "toId": "board",
        "title": "Validate the repaired artifact",
        "body": "If a valid question/task is persisted, normal work can continue. Otherwise the configured policy stops or defers exploration explicitly.",
        "input": "Repaired candidate",
        "output": "Verified artifact or recorded failure",
        "operation": "Validation gate",
        "owner": "board",
        "source": "src/memstara/mcp_servers/blackboard.py"
      }
    ]
  },
  {
    "id": "pause",
    "name": "Pause & resume",
    "caption": "Separate controller commands from saved progress.",
    "steps": [
      {
        "id": "pause-1",
        "fromId": "workspace",
        "toId": "control",
        "title": "Request pause",
        "body": "An explicit control command asks the execution gate to pause. The educational Play/Pause buttons do not issue this command.",
        "input": "User pause request",
        "output": "Controller state transition",
        "operation": "Control command",
        "owner": "control",
        "source": "src/memstara/control/service.py"
      },
      {
        "id": "pause-2",
        "fromId": "control",
        "toId": "archive",
        "title": "Preserve resumable progress",
        "body": "Checkpointed progress and ownership protect completed work. A tool already in flight may still need to settle; an animation is not cancellation evidence.",
        "input": "Known phase progress",
        "output": "Durable checkpoint",
        "operation": "Checkpoint",
        "owner": "control",
        "source": "src/memstara/pipeline/checkpoint.py"
      },
      {
        "id": "pause-3",
        "fromId": "archive",
        "toId": "control",
        "title": "Restore on resume",
        "body": "Resume restores recorded phases and verifies ownership rather than blindly starting the whole pipeline again.",
        "input": "Explicit resume + saved checkpoint",
        "output": "Recovered phase state",
        "operation": "Resume",
        "owner": "control",
        "source": "src/memstara/pipeline/checkpoint.py"
      },
      {
        "id": "pause-4",
        "fromId": "control",
        "toId": "board",
        "title": "Continue eligible work",
        "body": "The scheduler examines durable task state and available workers. End/terminate is a separate operation from pause.",
        "input": "Restored state",
        "output": "Eligible work or blocked recovery",
        "operation": "Scheduling",
        "owner": "control",
        "source": "src/memstara/pipeline/scheduler.py"
      }
    ]
  },
  {
    "id": "combinations",
    "name": "All combinations",
    "caption": "Follow a frozen skill schedule across repeated loops.",
    "steps": [
      {
        "id": "combinations-1",
        "fromId": "workspace",
        "toId": "control",
        "title": "Freeze all combinations",
        "body": "Selected skills form a Cartesian schedule with a repetition/loop budget. Random Start rotates the schedule start; it is not random feature selection.",
        "input": "Stage skill choices and limits",
        "output": "Frozen ordered schedule",
        "operation": "Configuration",
        "owner": "control",
        "source": "src/memstara/combinations.py"
      },
      {
        "id": "combinations-2",
        "fromId": "control",
        "toId": "archive",
        "title": "Record the loop roster",
        "body": "Each loop records its selected skills, identities and hashes so results can be attributed to a configuration.",
        "input": "Loop index + schedule",
        "output": "Loop-specific provenance",
        "operation": "File write",
        "owner": "control",
        "source": "src/memstara/combinations.py"
      },
      {
        "id": "combinations-3",
        "fromId": "control",
        "toId": "hypothesis",
        "title": "Run the selected configuration",
        "body": "The normal question-to-explanation path runs for this loop. Different hypotheses are not a controlled measurement of topology alone.",
        "input": "Selected roster",
        "output": "Scoped invocation sequence",
        "operation": "Dispatch",
        "owner": "hypothesis",
        "source": "src/memstara/prompts/board/hypothesis.md"
      },
      {
        "id": "combinations-4",
        "fromId": "board",
        "toId": "memdb",
        "title": "Write outcomes before the next loop",
        "body": "Persist measured results and question outcomes before exploring again. Do not attribute unmatched questions solely to an agent combination.",
        "input": "Completed/failed loop evidence",
        "output": "Question outcomes and comparison evidence",
        "operation": "Database write",
        "owner": "board",
        "source": "src/memstara/mcp_servers/blackboard.py"
      },
      {
        "id": "combinations-5",
        "fromId": "archive",
        "toId": "control",
        "title": "Advance within the frozen limit",
        "body": "Continue with the next eligible configuration until the limit or another explicit stop condition is reached.",
        "input": "Recorded loop progress",
        "output": "Next loop or completion",
        "operation": "Loop boundary",
        "owner": "control",
        "source": "src/memstara/combinations.py"
      }
    ]
  }
];

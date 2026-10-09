import { HELP } from './help';
import { VIEWS } from './views';

/** Shared explanations contain labels and purposes, never input values or credentials. */
export const INTERFACE_HELP:Record<string,string>={
  ...HELP,
  ...Object.fromEntries(Object.values(VIEWS).map(v=>[v.label,v.description])),
  'Readable':'Adjust the Floor plan camera so agent labels and controls are easier to read. This changes only the view.',
  'Fit all':'Fit all configured pipelines into the visible Floor plan area. Individual agents may appear smaller.',
  'Expand':'Expand this visualization to use more screen space. Its current selection is preserved.',
  'Question observatory':'Open the question field to explore generated questions and their linked evidence.',
  'Live pipelines':'Show updates from the latest executions of the configured pipelines.',
  'Saved analysis':'Review a previously recorded execution rather than the current live output stream.',
  'Received outputs':'Expand the recent outputs received from your pipelines. These include intermediate agent outputs as well as completed results.',
  'All pipelines':'Show received outputs across the configured pipelines instead of filtering to one pipeline.',
  'Close':'Close this view or dialog. This does not stop an analysis.',
  'Tool activity':'Show or hide lines representing recently observed agent tool calls for the selected execution. These are observations, not continuous data transfers. Hiding the lines does not stop any work.',
  'Exploration overview':'Open the pipeline navigator: names, numbers, current loop, and Active/Idle status. Selecting a row switches the execution you are reviewing.',
  'Control':'Show or hide the view navigation panel. Hiding it does not stop your pipelines.',
  'Reset window layout':'Restore the standard window sizes and positions, with Control and Floor plan visible and secondary windows closed. Analysis settings and results are preserved.',
  'Run history':'Browse saved executions and choose which analysis to review. Selecting an old execution does not restart it.',
  'System status':'Check connections to the viewer API, analysis database, agent runtime and pipeline control service.',
  'Model connection':'Inspect the configured language model, deployment and connection information used by agents. This is separate from the predictive ML model.',
  'Add Pipeline':'Open the setup wizard to choose knowledge sources, a name and each agent’s skill. The pipeline is created after you confirm the final review. Creating a pipeline does not start execution.',
  'Pause flow animation':'Pause the moving visual effects in Floor plan. Agents and analyses continue running.',
  'Resume flow animation':'Resume moving visual effects in Floor plan. This does not start or resume an analysis.',
  'Play':'Start a new execution of this pipeline. It continues exploring until stopped or blocked. This can incur language-model usage charges.',
  'Stop':'Request that this pipeline stop. Saved results remain available; unfinished work may not produce a completed result.',
  'View / change skill':'Read the instructions assigned to this agent, choose a different skill or upload your own Markdown file. Confirm the settings to apply your choice to future executions.',
  'Knowledge sources':'Choose the knowledge collection used to generate hypotheses. This controls the evidence available to the agent, not the clinical dataset or its prediction target.',
  'Create pipeline':'Save this pipeline with the reviewed sources, name and agent settings. Use its Play button when you want to start an execution.',
  'Next':'Continue to the next setup step while keeping your current draft choices. This does not start an analysis.',
  'Back':'Return to the previous setup step. Your draft choices are retained.',
  'Cancel':'Close this editor without applying its pending changes. Previously uploaded skill files remain in the catalog.',
  'Save':'Apply the changes shown in this editor. Running executions keep their frozen configuration.',
  'Pipeline name':'A name you choose to recognize this research path in Floor plan, results and reports.',
  'Fixed clinical baseline columns':'Optional exact dataset column names, one per line. They are included in every loop’s comparison models. Do not include the target. Empty means a prevalence-only reference, not a clinical baseline.',
  'ML model':'Choose the predictive model trained on selected dataset columns. This is different from the language model that runs the agents.',
  'Hold-out fraction':'Fraction of exploration rows used for testing. New iterative runs separately reserve 20% of the original dataset for future independent validation. This setting applies inside the remaining exploration data.',
  'Selected run':'The saved execution currently being inspected. Tasks, calls, logs and results refer to this execution, not necessarily every execution of the pipeline.',
  'This execution':'Show analysis results for the currently selected execution only.',
  'Latest executions across pipelines':'Show received results from each configured pipeline’s latest execution. This is not the complete historical archive.',
  'AUC':'Measures how well the model ranks the two target classes. Chance-level ranking is 0.5. A higher AUC alone does not establish clinical usefulness, causality or independent validation.',
  'SHAP':'Explains the fitted model’s predictions using feature contributions. Check the recorded method and units; these contributions are not causal effects.',
  'Model importance':'Show the recorded feature-importance values for this fitted model. The meaning depends on the method shown beside the chart.',
  'SHAP magnitude':'Show mean absolute SHAP contribution when it was recorded. Magnitude shows strength of influence, not whether a feature raises or lowers a prediction.',
  'Sensitivity':'Among actual positive outcomes in the evaluated data, the fraction detected at the recorded prediction cutoff.',
  'Specificity':'Among actual negative outcomes in the evaluated data, the fraction correctly classified as negative at the recorded cutoff.',
  'Precision':'Among positive predictions, the fraction that were actually positive. It may be undefined when the model makes no positive predictions.',
  'Active pipelines':'Pipelines reported as running now, out of the configured pipelines. This is not the number of agents or completed loops.',
  'New findings':'Completed result updates received since this page opened and not yet acknowledged here. They are not automatically recommended or validated discoveries.',
  'Recent results':'Results retained for current workspace executions. The question count refers to received records, not lifetime totals.',
  'Attention':'Pipelines with recorded failed tasks or nonzero exits. Review the affected pipeline; a historical failure may have been retried.',
  'Elapsed time':'Time since the earliest currently running pipeline started. The accompanying cost covers recorded agent calls for the latest workspace executions and refreshes every 10 seconds.',
  'Loop to inspect':'Choose a recorded loop within this pipeline execution. All Telemetry tabs follow this selection. All loops includes execution-wide records; switching does not start or stop the pipeline.',
  'Previous loop':'Inspect the preceding recorded loop in this execution. All Telemetry tabs switch together.',
  'Next loop':'Inspect the next recorded loop in this execution. New loops are added automatically while the pipeline runs.',
  'Loop':'One pipeline loop, from question generation through reporting. A blocked loop is counted separately from a completed loop. Task retries and hyperparameter candidates are separate counts; a dash means the loop number was not recorded or cannot be verified.',
  'Stage-based progress':'Progress through analysis stages in the current loop. It is not a time estimate, a model-quality score or completion of the entire continuous exploration.',
  'Question field':'Explore recorded questions in an interactive spatial view. Position, size, dust and orbit paths do not rank hypotheses or imply scientific relationships.',
  'Question list':'Switch to a readable list of the loaded questions. Selecting a question opens its linked evidence.',
  'Search loaded questions':'Filter currently loaded questions by question text, rationale or knowledge tags. This does not search the entire historical database.',
  'Rotate cloud left':'Rotate the question field to reveal questions on the other side. The underlying questions and results do not change.',
  'Rotate cloud right':'Rotate the question field to reveal questions on the other side. The underlying questions and results do not change.',
  'Zoom in':'Move closer to the visualization. This changes the view only, not the analysis.',
  'Zoom out':'Move farther from the visualization to see more of the field.',
  'Toggle gentle rotation':'Turn slow automatic rotation of the question field on or off. Reduced-motion preferences suppress automatic movement.',
  'Reset question field':'Clear the selected question and restore the initial camera view. Recorded questions and results remain unchanged.',
  'Enter immersive view':'Expand the question field to full screen. Press Escape or use the exit button to return.',
  'Exit immersive view':'Return the question field from full screen to its normal workspace window.',
  'Back to question field':'Leave the selected question’s evidence view and return to the question field.',
  'Read full question':'Expand the complete wording of the selected research question.',
  'Collapse question':'Return the question text to its compact preview.',
  'Full interpretation document':'Read the complete interpreter output, including evidence, limitations and suggested next validation.',
  'Agents':'Inspect calls to agents, reasoning steps and recorded usage for the selected execution. Calls and steps are different counts.',
  'Activity':'Inspect recent observed tool actions for the selected execution. Each row is an event, not necessarily a completed analysis.',
  'Access':'Review which tools and data services agents actually called. This is an activity record, not a permissions editor.',
  'Tasks':'Inspect work items and their stage, status and handoff details for the selected execution.',
  'Logs':'Read detailed process messages and reported failures for the selected execution.',
  'Agent calls':'Invocations of agents in this execution. An invocation may contain several reasoning steps and tool calls.',
  'Reasoning steps':'Internal steps recorded within agent invocations. This count is not the number of independent agents.',
  'Execution cost':'Recorded language-model usage cost for this execution. It may be partial when calls are running or pricing is unavailable.',
};

const lookup=new Map(Object.entries(INTERFACE_HELP).map(([k,v])=>[k.toLowerCase(),v]));
export function explainElement(element:HTMLElement):{label:string;text:string}|null {
  const label=(element.dataset.help || element.getAttribute('aria-label') ||
    (element instanceof HTMLInputElement||element instanceof HTMLSelectElement||element instanceof HTMLTextAreaElement
      ? [...(element.labels??[])].map(l=>[...l.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join(' ')).join(' ')
      : element.textContent) || element.getAttribute('title') || '').replace(/\s+/g,' ').trim();
  if(!label)return null;
  const normalized=label.replace(/\s+\d+\/\d+$/,'').replace(/\s*·.*$/,'').trim();
  let text=element.dataset.helpDescription || element.getAttribute('title') || lookup.get(normalized.toLowerCase());
  if(!text||text===label) {
    text=lookup.get(normalized.toLowerCase());
    const patterns:[RegExp,string][]=[
      [/^Pan pipeline /i,'Move the Floor plan camera in this direction. Agents and pipeline execution are unchanged.'],
      [/^Knowledge sources:/i,INTERFACE_HELP['Knowledge sources']],
      [/^Inspect Hypothesis/i,'Inspect the hypothesis agent and its assigned instructions. Configure the skill used to generate and map research hypotheses here.'],
      [/^Inspect Data/i,'Inspect the extraction agent and dataset settings. The data stage selects columns; it does not generate hypotheses or interpret findings.'],
      [/^Inspect Machine learning/i,INTERFACE_HELP['ML model']+' You can also review its skill and evaluation settings.'],
      [/^Inspect Interpreter/i,INTERFACE_HELP.interpreter],
      [/^Inspect (Explanation|Report)/i,INTERFACE_HELP.report],
      [/^P\d+.*Loop/i,'Select this named pipeline to review the execution, loop and outputs associated with it. This does not start work.'],
      [/Not running.*Loop|Running.*Loop/i,'Filter the received outputs to this pipeline. The status and loop refer to its latest execution.'],
      [/^Add Pipeline/i,INTERFACE_HELP['Add Pipeline']],
      [/^Center .+ in Floor Plan/i,'Select this pipeline and center its agents in Floor plan. This changes which execution you are inspecting; it does not start a run.'],
      [/^(Start|Play) .*(pipeline|explor)/i,INTERFACE_HELP.Play],
      [/^Stop .*/i,INTERFACE_HELP.Stop],
      [/^(Remove|Delete) .*(pipeline)/i,'Remove this pipeline definition after it has stopped. Review the confirmation carefully; this is not the Stop action.'],
      [/^Rename/i,'Change the display name used to identify this pipeline. Its saved analysis results are preserved.'],
      [/^Maximize /i,'Expand this window to fill the available workspace. Other windows and pipeline execution are preserved.'],
      [/^Restore /i,'Return this window to its previous workspace size and position.'],
      [/^Reset .+ window/i,'Restore this window’s default size and position without changing analysis settings or results.'],
      [/^Collapse /i,'Hide or compact this section. This does not stop an analysis or delete its records.'],
      [/^Resize /i,'Drag this edge or corner to resize the window. With keyboard focus, use arrow keys to adjust its size.'],
      [/^Explore question/i,'Select this recorded question and inspect its linked hypothesis, model evaluation, interpretation and report. Visual prominence is not a scientific recommendation.'],
      [/skill$/i,INTERFACE_HELP['Agent skills']],
      [/^Save /i,INTERFACE_HELP.Save],
      [/^Cancel /i,INTERFACE_HELP.Cancel],
      [/^Close /i,'Close this panel or dialog and return to the workspace. Closing a view does not stop its analysis.'],
      [/^Download|^Export/i,'Save the displayed report or evidence in the format shown on this control. This does not rerun the analysis.'],
      [/^Show |^View |^Read |^Review /i,'Open the named details for the current selection. This is a view change; it does not start an analysis.'],
      [/^Search /i,'Filter the records shown in this view using the text you enter. Check this view’s scope before treating the results as complete history.'],
      [/^Loop\b/i,INTERFACE_HELP.Loop],
    ];
    text ||= patterns.find(([pattern])=>pattern.test(label))?.[1];
  }
  if(!text&&element.closest('.pipeline-selector'))text='Inspect or configure this pipeline. Its name identifies the research path; its loop and stage describe the latest execution.';
  if(!text&&element instanceof HTMLSelectElement)text='Choose an option for this labeled setting. Review the current pipeline or execution scope before applying changes.';
  if(!text&&element instanceof HTMLInputElement&&element.type==='file')text=INTERFACE_HELP['Use your own skill (.md)'];
  if(!text&&element.tagName==='SUMMARY')text='Expand or collapse the complete details under this heading. No analysis is started by opening it.';
  if(!text)return null;
  if(element.matches(':disabled,[aria-disabled="true"]'))text+=' This control is currently unavailable in the current state.';
  return {label:normalized.slice(0,100),text};
}

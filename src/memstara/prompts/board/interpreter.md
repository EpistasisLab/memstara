---
goal: Execute the selected Interpretation skill and save its complete output.
---

{{playbook}}

<!-- Transport only: interpretation content and format belong to the selected skill. -->
{{_claim_preamble}}

Your task type is "interpret".
Use the task returned by claim_task as the input to the selected skill, including
interpretation_input when present. Put the complete Markdown output in the
interpretation field of submit_result, with the task_id and worker that claimed it.
Keep the report's limitations inside that output. Verify the tool's ok response;
a final text reply alone does not save the result. If submission is rejected,
correct the tool arguments and resubmit. Report a technical inability to execute
with execution_failed=true and error, without a completed interpretation.

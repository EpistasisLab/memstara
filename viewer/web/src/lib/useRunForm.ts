import { usePipelines } from "../store/pipelines";
import { useMemo } from "react";
import { applyRunConfiguration, useControl } from "../store/control";
import { useViewer } from "../store/viewer";

export function useRunForm() {
  const pipeline = usePipelines(s => s.items.find(p => p.id === s.selected));
  const form = useControl(s => s.form);
  const preview = useViewer(s => s.newRunMode);
  const config = useViewer(s => s.snapshot?.run_configuration);
  return useMemo(() => pipeline ? pipeline.configuration : config && !preview ? applyRunConfiguration(form, config) : form, [form, config, preview, pipeline]);
}

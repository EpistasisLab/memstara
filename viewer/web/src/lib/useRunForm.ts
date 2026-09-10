import { useMemo } from "react";
import { applyRunConfiguration, useControl } from "../store/control";
import { useViewer } from "../store/viewer";

export function useRunForm() {
  const form = useControl(s => s.form);
  const preview = useViewer(s => s.newRunMode);
  const config = useViewer(s => s.snapshot?.run_configuration);
  return useMemo(() => config && !preview ? applyRunConfiguration(form, config) : form, [form, config, preview]);
}

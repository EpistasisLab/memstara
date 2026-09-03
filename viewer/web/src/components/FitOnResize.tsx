import { useEffect } from "react";
import { useReactFlow } from "@xyflow/react";

/**
 * Refit a React Flow canvas whenever the window changes size.
 *
 * `fitView` fits once, at mount. Both canvases here sit inside a responsive grid that
 * restacks at `lg`, so without this a canvas keeps the width it had when it first drew:
 * widen the window and the drawing stays in the corner it started in.
 *
 * Only useful for a canvas whose layout is **fixed** — a picture that is meant to be
 * whole at every size, rather than a map the reader pans around. That is both of ours,
 * and it is why neither of them offers zoom.
 *
 * Renders nothing. It has to be a component rather than a hook called from the panel
 * because `useReactFlow` only works inside the provider `<ReactFlow>` sets up.
 */
export default function FitOnResize({ padding = 0.08 }: { padding?: number }) {
  const { fitView } = useReactFlow();

  useEffect(() => {
    const refit = () => void fitView({ padding, duration: 0 });
    window.addEventListener("resize", refit);
    return () => window.removeEventListener("resize", refit);
  }, [fitView, padding]);

  return null;
}

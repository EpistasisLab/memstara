import { BaseEdge, type EdgeProps } from "@xyflow/react";
import { resourceRoute } from "../lib/resourceRoute";

/** Ordinary smoothstep edges do not avoid other nodes. Use the outside rail. */
export default function ResourceEdge(props: EdgeProps) {
  const {sourceX,sourceY,targetX,targetY,data,label,...rest}=props;
  const points=resourceRoute(sourceX,sourceY,targetX,targetY,Number(data?.lane??0));
  const path=points.map(([x,y],i)=>`${i?"L":"M"} ${x} ${y}`).join(" ");
  return <BaseEdge {...rest} path={path} label={label}
    labelX={sourceX} labelY={points[1][1]-7}
    labelStyle={{fill:"rgb(var(--ink-soft))",fontSize:10}}
    labelBgStyle={{fill:"rgb(var(--panel))",stroke:"rgb(var(--line))"}} labelBgPadding={[5,3]}/>;
}

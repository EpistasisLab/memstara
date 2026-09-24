/** Route a resource call outside every agent row, through reserved gutters. */
export function resourceRoute(sourceX: number, sourceY: number, targetX: number, targetY: number, lane: number) {
  const rowGutter = sourceY - 16 - lane * 3;
  const resourceGutter = targetY + 12 + lane * 3;
  const rail = -24 - lane * 12;
  return [
    [sourceX, sourceY], [sourceX, rowGutter], [rail, rowGutter],
    [rail, resourceGutter], [targetX, resourceGutter], [targetX, targetY],
  ];
}

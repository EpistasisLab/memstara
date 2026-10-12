export type WorkspaceBox = {x:number;y:number;w:number;h:number};
/** Allocate readable dock slots before clamping user-adjusted windows. */
export function workspaceGeometry(width:number, height:number, panels:string[], offset=0) {
  const mobile=width<760, gap=12, x=mobile?0:232, w=Math.max(0,width-x);
  const minima:Record<string,number>={feed:340,results:440,report:520};
  const tabbed=panels.length>1 && panels.reduce((n,id)=>n+(minima[id]??340),0)+gap*(panels.length-1)>w;
  const start=mobile?174:0;
  // Narrow toolbars wrap above the 260px diagram. Reserve this in the
  // shared geometry so the analysis tabs move with the taller floor panel.
  const minimum=w<420?940:w<900?740:640;
  const available=Math.max(minimum,height-start-(panels.length?360:0));
  const floor=panels.length?Math.max(minimum,Math.min(1100,available+offset)):Math.max(minimum,height-start);
  const panelY=start+floor+48;
  const panelH=Math.max(320,height-panelY);
  const contentHeight=panels.length?panelY+panelH:start+floor;
  const boxes:Record<string,WorkspaceBox>={control:{x:0,y:0,w:mobile?width:220,h:mobile?162:height},pipeline:{x,y:start,w,h:floor}};
  let left=x;
  const usable=w-gap*Math.max(0,panels.length-1),total=panels.reduce((n,id)=>n+(minima[id]??340),0);
  for(const id of panels) {
    const part=tabbed?w:usable*(minima[id]??340)/total;
    boxes[id]={x:tabbed?x:left,y:panelY,w:part,h:panelH};left+=part+gap;
  }
  return {boxes,tabbed,contentHeight,x,w,panelY};
}

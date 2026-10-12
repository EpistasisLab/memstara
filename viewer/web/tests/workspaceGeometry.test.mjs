import test from 'node:test';
import assert from 'node:assert/strict';
import {workspaceGeometry} from '../src/lib/workspaceGeometry.ts';
test('all panel subsets keep readable nonoverlapping dock slots',()=>{
 for(const width of [320,375,390,414,420,760,1024,1440,1920,2560])for(const height of [400,768,1000])for(let mask=0;mask<8;mask++){
  const panels=['feed','results','report'].filter((_,i)=>mask&(1<<i));
  const layout=workspaceGeometry(width,height,panels);
  const floor=layout.boxes.pipeline;assert(floor.h>=520);
  for(const id of panels){const b=layout.boxes[id];assert(b.y>=floor.y+floor.h+12);assert(b.h>=320);assert(b.x+b.w<=width+.01);assert(b.y+b.h<=layout.contentHeight+.01);}
  if(!layout.tabbed)for(let i=1;i<panels.length;i++){const a=layout.boxes[panels[i-1]],b=layout.boxes[panels[i]];assert(a.x+a.w<=b.x);}
 }
});
test('narrow multi-panel layouts use tabs; wide layouts favor report width',()=>{
 assert(workspaceGeometry(1440,900,['feed','results','report']).tabbed);
 const wide=workspaceGeometry(2000,1000,['feed','results','report']);assert(!wide.tabbed);
 assert(wide.boxes.report.w>wide.boxes.results.w&&wide.boxes.results.w>wide.boxes.feed.w);
});

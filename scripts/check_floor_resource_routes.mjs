// Run with Node's TypeScript stripping support; no browser or live execution needed.
import assert from 'node:assert/strict';
import { resourceRoute } from '../viewer/web/src/lib/resourceRoute.ts';
function intersects([ax,ay],[bx,by],r) {
  if(ax===bx) return ax>r.x && ax<r.x+r.w && Math.max(Math.min(ay,by),r.y)<Math.min(Math.max(ay,by),r.y+r.h);
  return ay>r.y && ay<r.y+r.h && Math.max(Math.min(ax,bx),r.x)<Math.min(Math.max(ax,bx),r.x+r.w);
}
const cards=[];
for(let row=0;row<3;row++)for(let col=0;col<6;col++)cards.push({x:24+col*224,y:224+row*252,w:184,h:108});
for(let col=0;col<6;col++)cards.push({x:24+col*224,y:48,w:152,h:76});
let checked=0;
for(let row=0;row<3;row++)for(let stage=1;stage<6;stage++)for(let resource=0;resource<6;resource++){
  const points=resourceRoute(24+stage*224+92,224+row*252,24+resource*224+76,124,stage-1);
  for(let i=1;i<points.length;i++)for(const card of cards){
    assert(!intersects(points[i-1],points[i],card),`Route crossed card: row ${row}, stage ${stage}, resource ${resource}`);
  }
  checked++;
}
console.log(`PASS: ${checked} resource routes avoid all agent and resource card interiors`);

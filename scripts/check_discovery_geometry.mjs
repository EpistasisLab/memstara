import assert from 'node:assert/strict';
import { pointForId, cameraForPoint, project, angleDelta, overlaps } from '../viewer/web/src/components/discovery/geometry.ts';
// Every question, not just a favorable hemisphere, must center after selection.
for(let id=1;id<=1000;id++){
  const p=pointForId(id), camera=cameraForPoint(p);
  for(const [w,h] of [[360,450],[900,600],[1400,760]]){
    const screen=project(p,camera,w,h);
    assert.ok(Math.abs(screen.x-w/2)<1e-7);
    assert.ok(Math.abs(screen.y-h*.49)<1e-7);
    assert.ok(screen.z>.999);
  }
  assert.deepEqual(pointForId(id),p);
}
assert.ok(Math.abs(angleDelta(Math.PI-.01,-Math.PI+.01)-.02)<1e-9);
assert.equal(overlaps({x:0,y:0,w:180,h:62},{x:100,y:30,w:180,h:62}),true);
assert.equal(overlaps({x:0,y:0,w:180,h:62},{x:200,y:100,w:180,h:62}),false);
console.log('Passed: 3,000 focus projections, stable positions, shortest-path rotation, label collisions.');

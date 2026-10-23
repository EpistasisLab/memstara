export const retainedWorkspaceUrl=(process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/retained-views.fixture.html';
export async function openRetainedView(page,view='discovery') {
  await page.waitForFunction(()=>typeof window.openRetainedView==='function');
  await page.evaluate(view=>window.openRetainedView(view),view);
}

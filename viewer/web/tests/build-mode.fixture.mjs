// Legacy creation is test-only; production Add experiment opens combinations directly.
export async function openBuildModeFixture(page,mode='Selected Pipelines') {
 if(mode!=='Selected Pipelines')return;
 await page.goto((process.env.MEMSTARA_FIXTURE_URL||'http://127.0.0.1:4177')+'/tests/legacy-creation.fixture.html');
}

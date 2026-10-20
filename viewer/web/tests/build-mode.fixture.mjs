import assert from 'node:assert/strict';

// Selected Pipelines is temporarily hidden from users. Exercise its retained
// wizard explicitly in fixtures without exposing a production feature flag.
export async function openBuildModeFixture(page,mode='Selected Pipelines') {
 if(mode!=='Selected Pipelines'){await page.getByText('Advanced setup',{exact:true}).click();return page.getByRole('button',{name:new RegExp('^'+mode)}).click();}
 const button=page.getByRole('dialog',{name:'Build pipelines',exact:true}).locator('button[hidden]').filter({hasText:'Selected Pipelines'});
 assert.equal(await button.isVisible(),false);
 await button.evaluate(el=>el.click());
}

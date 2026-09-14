// 前端 UI 冒烟测试（需先启动服务：python -m uvicorn app.main:app --port 8011）
// 运行：npm install playwright --no-save && node tests/ui_smoke.js
// 覆盖：上传、识别、防数据丢失确认、撤销/重做、批量命名、缩略图放大
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

function findBrowser() {
  const dir = path.join(process.env.LOCALAPPDATA || '', 'ms-playwright');
  if (!fs.existsSync(dir)) return null;
  for (const name of fs.readdirSync(dir)) {
    const exe = path.join(dir, name, 'chrome-headless-shell-win64', 'chrome-headless-shell.exe');
    if (fs.existsSync(exe)) return exe;
  }
  return null;
}

(async () => {
  const executablePath = findBrowser();
  const browser = await chromium.launch(executablePath ? { executablePath } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const dialogs = [];
  let acceptNext = false;
  page.on('dialog', async (dialog) => {
    dialogs.push({ type: dialog.type(), message: dialog.message() });
    if (acceptNext) { acceptNext = false; await dialog.accept(); }
    else await dialog.dismiss();
  });
  const errors = [];
  page.on('pageerror', (err) => errors.push(err.message));
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push(msg.text()); });

  const results = [];
  const check = (name, ok, extra = '') => {
    results.push((ok ? 'PASS' : 'FAIL') + ' ' + name + (extra ? ' | ' + extra : ''));
  };

  // 1) 打开页面并上传
  await page.goto('http://127.0.0.1:8011/');
  await page.setInputFiles('#fileInput', '_ui_sheet.png');
  await page.waitForSelector('#workspace:not([hidden])', { timeout: 15000 });
  check('upload -> workspace visible', true);
  const cropCount = await page.textContent('#cropCount');
  check('crops detected', cropCount === '2', 'count=' + cropCount);

  // 2) 修改名称 -> 点重新识别 -> 应弹确认框且取消后保留
  await page.fill('.name-input >> nth=0', '哈哈');
  await page.click('#reanalyzeButton');
  await page.waitForTimeout(300);
  check('reanalyze shows confirm dialog', dialogs.length === 1, 'dialogs=' + JSON.stringify(dialogs[0]?.message || 'none'));
  const nameAfterCancel = await page.inputValue('.name-input >> nth=0');
  check('name kept after cancel', nameAfterCancel === '哈哈', 'name=' + nameAfterCancel);
  await page.waitForTimeout(500);

  // 3) 接受确认 -> 重新识别完成 -> 名称重置
  let accepted = false;
  acceptNext = true;
  page.on('dialog', async () => { accepted = true; });
  await page.click('#reanalyzeButton');
  await page.waitForTimeout(1200);
  check('accept -> reanalyzed', accepted);
  const nameAfterReanalyze = await page.inputValue('.name-input >> nth=0');
  check('name reset after accept', nameAfterReanalyze === '表情', 'name=' + nameAfterReanalyze);

  // 4) 手动修正：新增框 -> 撤销 -> 框数恢复
  await page.click('#editModeButton');
  await page.waitForTimeout(200);
  const before = await page.locator('.crop-item').count();
  await page.click('#addBoxButton');
  const afterAdd = await page.locator('.crop-item').count();
  check('add box', afterAdd === before + 1, before + '->' + afterAdd);
  await page.click('#undoButton');
  const afterUndo = await page.locator('.crop-item').count();
  check('undo restores count', afterUndo === before, before + '->' + afterUndo);
  await page.click('#redoButton');
  const afterRedo = await page.locator('.crop-item').count();
  check('redo re-adds box', afterRedo === before + 1, before + '->' + afterRedo);
  await page.click('#undoButton'); // 撤销回去，保持干净
  await page.click('#editModeButton'); // 退出编辑模式

  // 5) 批量命名
  await page.fill('#bulkName', '快乐');
  await page.click('#bulkApplyButton');
  await page.waitForTimeout(300);
  const name1 = await page.inputValue('.name-input >> nth=0');
  const name2 = await page.inputValue('.name-input >> nth=1');
  check('bulk naming applied', name1 === '快乐' && name2 === '快乐', name1 + ',' + name2);

  // 6) 缩略图点击放大 -> Esc 关闭
  await page.click('.crop-thumb >> nth=0');
  await page.waitForTimeout(300);
  const lightboxVisible = await page.isVisible('#lightboxImg');
  const imgSrc = await page.getAttribute('#lightboxImg', 'src');
  check('lightbox opens', lightboxVisible && imgSrc && imgSrc.startsWith('data:image/png'), 'src-len=' + (imgSrc?.length || 0));
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  check('lightbox closes on Esc', !(await page.isVisible('#lightboxImg')));

  // 7) 无 JS 错误
  check('no page errors', errors.length === 0, errors.slice(0, 3).join('; '));

  console.log(results.join('\n'));
  await browser.close();
  process.exit(results.some((r) => r.startsWith('FAIL')) ? 1 : 0);
})();
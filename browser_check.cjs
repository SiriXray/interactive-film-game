const fs = require("fs");
const http = require("http");

function getJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (response) => {
      let body = "";
      response.on("data", (chunk) => { body += chunk; });
      response.on("end", () => { try { resolve(JSON.parse(body)); } catch (error) { reject(error); } });
    }).on("error", reject);
  });
}

async function main() {
  const mobile = process.argv.includes("--mobile");
  const targets = await getJson("http://127.0.0.1:9333/json/list");
  const target = targets.find((item) => item.type === "page") || targets[0];
  if (!target) throw new Error("No browser debugging target is available on port 9333.");
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  let requestId = 0;
  const pending = new Map();
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) { pending.get(message.id)(message); pending.delete(message.id); }
  };
  await new Promise((resolve) => { socket.onopen = resolve; });
  const send = (method, params = {}) => new Promise((resolve) => { const id = ++requestId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); });
  const evaluate = async (expression) => {
    const result = await send("Runtime.evaluate", { expression, returnByValue: true });
    return result.result.result.value;
  };
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", mobile
    ? { width: 390, height: 844, deviceScaleFactor: 2, mobile: true }
    : { width: 1440, height: 960, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url: "http://127.0.0.1:5100/" });
  await new Promise((resolve) => setTimeout(resolve, 3000));
  const library = JSON.parse(await evaluate("JSON.stringify({active:document.querySelector('#library-screen').classList.contains('active'),cards:document.querySelectorAll('.story-card').length,sidebar:document.querySelector('.story-sidebar'),drawer:document.querySelector('#production-drawer').open,bodyWidth:document.body.scrollWidth,viewport:window.innerWidth})"));
  if (!library.active || library.cards !== 7 || library.sidebar || library.bodyWidth > library.viewport + 2) {
    const diagnostic = await evaluate("JSON.stringify({gridText:document.querySelector('#story-grid').innerText,body:document.body.innerText.slice(0,500)})");
    throw new Error(`Unexpected library state: ${JSON.stringify(library)} ${diagnostic}`);
  }
  if (process.argv.includes("--screenshot")) {
    let screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
    fs.writeFileSync(mobile ? "ui-library-mobile.png" : "ui-library.png", Buffer.from(screenshot.result.data, "base64"));
  }
  await evaluate("document.querySelector('.story-card').click()");
  await new Promise((resolve) => setTimeout(resolve, 1000));
  const player = JSON.parse(await evaluate("JSON.stringify({story:document.querySelector('#story-screen').classList.contains('active'),frame:document.querySelector('.film-frame') !== null,videoReady:document.querySelector('#cutscene-video').classList.contains('ready'),sidebars:document.querySelectorAll('.story-sidebar').length,companions:document.querySelectorAll('.companion').length,caption:document.querySelector('#video-narration').textContent.trim(),drawer:document.querySelector('#production-drawer').open})"));
  if (!player.story || !player.frame || player.sidebars || player.companions !== 2 || !player.caption || player.drawer) throw new Error(`Unexpected player state: ${JSON.stringify(player)}`);
  if (process.argv.includes("--screenshot")) {
    let screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
    fs.writeFileSync(mobile ? "ui-player-mobile.png" : "ui-player.png", Buffer.from(screenshot.result.data, "base64"));
  }
  await evaluate("document.querySelector('#cutscene-continue').click()");
  await new Promise((resolve) => setTimeout(resolve, 200));
  const live = JSON.parse(await evaluate("JSON.stringify({live:document.querySelector('#live-view').classList.contains('active'),prompt:document.querySelector('#live-prompt').textContent.trim(),button:document.querySelector('#live-start').textContent.trim(),reason:document.querySelector('#live-reason').textContent.trim()})"));
  if (!live.live || !live.prompt || !live.button || !live.reason) throw new Error(`Unexpected live state: ${JSON.stringify(live)}`);
  if (process.argv.includes("--screenshot")) {
    let screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
    fs.writeFileSync(mobile ? "ui-live-mobile.png" : "ui-live.png", Buffer.from(screenshot.result.data, "base64"));
  }
  // Production keeps this button locked until S1 connects. The browser check
  // simulates that completed conversation so it can verify the next scene.
  await evaluate("document.querySelector('#live-next').disabled = false; document.querySelector('#live-next').click()");
  await new Promise((resolve) => setTimeout(resolve, 200));
  const choice = JSON.parse(await evaluate("JSON.stringify({choice:document.querySelector('#choice-view').classList.contains('active'),options:document.querySelectorAll('.choice-option').length,prompt:document.querySelector('#choice-prompt').textContent.trim()})"));
  if (!choice.choice || choice.options !== 2 || !choice.prompt) throw new Error(`Unexpected choice state: ${JSON.stringify(choice)}`);
  if (process.argv.includes("--screenshot")) {
    let screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
    fs.writeFileSync(mobile ? "ui-choice-mobile.png" : "ui-choice.png", Buffer.from(screenshot.result.data, "base64"));
  }
  await evaluate("document.querySelector('#production-open').click()");
  await new Promise((resolve) => setTimeout(resolve, 100));
  const drawer = JSON.parse(await evaluate("JSON.stringify({open:document.querySelector('#production-drawer').open,actions:document.querySelectorAll('.drawer-button').length,progress:document.querySelector('#overview-movies').textContent.trim(),s1Portraits:document.querySelector('#overview-s1').textContent.trim()})"));
  if (!drawer.open || drawer.actions !== 3 || !drawer.progress || !drawer.s1Portraits) throw new Error(`Unexpected drawer state: ${JSON.stringify(drawer)}`);
  if (process.argv.includes("--screenshot")) {
    let screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
    fs.writeFileSync(mobile ? "ui-production-mobile.png" : "ui-production.png", Buffer.from(screenshot.result.data, "base64"));
  }
  await evaluate("document.querySelector('#production-close').click(); document.querySelector('#story-back').click()");
  await new Promise((resolve) => setTimeout(resolve, 250));
  await evaluate("document.querySelectorAll('.story-card')[6].click()");
  await new Promise((resolve) => setTimeout(resolve, 250));
  const zeroHourPlayer = JSON.parse(await evaluate("JSON.stringify({title:document.querySelector('#player-story-title').textContent.trim(),skin:document.querySelector('#story-screen').dataset.skin,story:document.querySelector('#story-screen').classList.contains('active')})"));
  if (!zeroHourPlayer.story || zeroHourPlayer.skin !== "sci-fi-apocalypse" || !zeroHourPlayer.title) throw new Error(`Unexpected Zero Hour player state: ${JSON.stringify(zeroHourPlayer)}`);
  await evaluate("document.querySelector('#cutscene-continue').click()");
  await new Promise((resolve) => setTimeout(resolve, 200));
  const zeroHourLive = JSON.parse(await evaluate("JSON.stringify({live:document.querySelector('#live-view').classList.contains('active'),mode:document.querySelector('#live-mode').textContent.trim(),directives:document.querySelectorAll('#live-directives li').length,start:document.querySelector('#live-start').textContent.trim(),disabled:document.querySelector('#live-start').disabled,bodyWidth:document.body.scrollWidth,viewport:window.innerWidth})"));
  if (!zeroHourLive.live || !zeroHourLive.mode || zeroHourLive.directives !== 3 || !zeroHourLive.start.includes("接通监控") || !zeroHourLive.disabled || zeroHourLive.bodyWidth > zeroHourLive.viewport + 2) throw new Error(`Unexpected Zero Hour live state: ${JSON.stringify(zeroHourLive)}`);
  if (process.argv.includes("--zero-hour-screenshot")) {
    let screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
    fs.writeFileSync(mobile ? "ui-zero-hour-live-mobile.png" : "ui-zero-hour-live.png", Buffer.from(screenshot.result.data, "base64"));
  }
  console.log(JSON.stringify({ viewport: mobile ? "390x844" : "1440x960", library, player, live, choice, drawer, zeroHourPlayer, zeroHourLive }));
  await send("Emulation.clearDeviceMetricsOverride");
  socket.close();
}

main().catch((error) => { console.error(error); process.exit(1); });

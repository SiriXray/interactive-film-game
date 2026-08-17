const state = {
  stories: [],
  production: null,
  story: null,
  nodeId: null,
  choices: [],
  values: {},
  config: {},
  muted: false,
  toastTimer: null,
  live: { ws: null, rtcClient: null, liveId: "", rtc: null, sequence: 1, retryTimer: null, pingTimer: null, initRetries: 0, stage: "", idleTimer: null, idleNudges: 0 },
  transcript: { keys: new Set(), pendingUserAt: 0, lastLatencyMs: null, subtitleTimer: null },
};

const $ = (selector) => document.querySelector(selector);
const screens = { library: $("#library-screen"), story: $("#story-screen") };
const views = { fmv: $("#fmv-view"), choice: $("#choice-view"), live: $("#live-view"), ending: $("#ending-view") };
const productionDrawer = $("#production-drawer");

function showScreen(name) {
  Object.values(screens).forEach((screen) => screen.classList.remove("active"));
  screens[name].classList.add("active");
}

function showView(name) {
  Object.entries(views).forEach(([key, view]) => view.classList.toggle("active", key === name));
  screens.story.classList.remove("mode-fmv", "mode-choice", "mode-live", "mode-ending");
  screens.story.classList.add(`mode-${name}`);
}

function withTimeout(promise, timeoutMs, message, onLateResolve) {
  let timeoutId;
  let didTimeout = false;
  const timeout = new Promise((_, reject) => {
    timeoutId = window.setTimeout(() => {
      didTimeout = true;
      reject(new Error(message));
    }, timeoutMs);
  });
  const guarded = Promise.resolve(promise).then((value) => {
    if (didTimeout && onLateResolve) onLateResolve(value);
    return value;
  });
  return Promise.race([guarded, timeout]).finally(() => window.clearTimeout(timeoutId));
}

async function api(url, options = {}, timeoutMs = 120000) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const response = await fetch(url, { ...options, signal: controller.signal }).finally(() => window.clearTimeout(timeoutId));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function currentNode() { return state.story.nodes[state.nodeId]; }

function escapeHtml(value) {
  return String(value).replace(/[&<>"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[character]));
}

function showToast(message, tone = "") {
  const toast = $("#toast");
  clearTimeout(state.toastTimer);
  toast.textContent = message;
  toast.className = `toast show ${tone}`;
  state.toastTimer = window.setTimeout(() => { toast.className = "toast"; }, 4200);
}

function mediaPermissionMessage(error) {
  const message = String(error?.message || error || "");
  if (/permission|denied|notallowed|dismiss/i.test(message)) {
    return "麦克风或摄像头权限被浏览器拒绝。请在地址栏允许 http://127.0.0.1:5100 使用麦克风后重试。";
  }
  if (/notfound|devices? not found|overconstrained/i.test(message)) {
    return "没有检测到可用的麦克风或摄像头，请接入设备后重试。";
  }
  return message;
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function liveTrace(stage, detail = {}) {
  console.info("[Vidu S1]", stage, detail);
}

function paletteStyle(palette) {
  const palettes = {
    snow: "linear-gradient(145deg, #4b7798 0%, #24374f 52%, #0a101a 100%)",
    ink: "linear-gradient(145deg, #533966 0%, #1e1930 48%, #080a10 100%)",
    market: "linear-gradient(145deg, #7b8055 0%, #344f47 48%, #131820 100%)",
    palace: "linear-gradient(145deg, #9a4d40 0%, #4b2438 50%, #110e15 100%)",
    apocalypse: "linear-gradient(145deg, #234b58 0%, #10242e 46%, #070b10 100%)",
    campus: "linear-gradient(145deg, #c58f58 0%, #415b6f 46%, #101521 100%)",
    system: "linear-gradient(148deg, #1f6f86 0%, #123a4d 50%, #060d14 100%)",
  };
  return palettes[palette] || palettes.ink;
}

function updateApiIndicator(ready) {
  const indicator = $("#api-indicator");
  indicator.textContent = ready ? "密钥已连接" : "未连接 API";
  indicator.className = `api-indicator ${ready ? "ready" : "error"}`;
}

function setProductionMessage(message, tone = "") {
  const target = $("#production-message");
  target.textContent = message;
  target.className = `production-message ${tone}`;
}

function renderProductionOverview(production) {
  const totals = production.totals;
  const s1Portraits = totals.s1_portraits || { ready: 0, total: 0 };
  $("#overview-images").textContent = `${totals.images.ready}/${totals.images.total}`;
  $("#overview-s1").textContent = `${s1Portraits.ready}/${s1Portraits.total}`;
  $("#overview-clips").textContent = `${totals.clips.ready}/${totals.clips.total}`;
  $("#overview-movies").textContent = `${totals.movies.ready}/${totals.movies.total}`;
  $("#production-summary").textContent = production.worker_running
    ? "后台正在准备下一幕"
    : totals.failed ? `${totals.failed} 项需要留意` : `${totals.movies.ready} 段影像与 ${s1Portraits.ready} 个实时形象已到位`;
  $("#production-note").textContent = totals.images.ready < totals.images.total
    ? "角色的面容正在显影；角色图完成后，镜头会自动继续。"
    : "三段连续镜头会在后台缝合成一段十五秒的剧情影像。";
}

async function refreshProduction({ quiet = false } = {}) {
  try {
    const payload = await api("/api/production/refresh", { method: "POST" });
    state.production = payload.status;
    renderProductionOverview(state.production);
    renderStoryGrid();
    if (!quiet) {
      setProductionMessage(`已更新 ${payload.refresh.refreshed} 个任务。`, "success");
      showToast("制作状态已更新");
    }
    return payload.status;
  } catch (error) {
    if (!quiet) {
      setProductionMessage(`刷新失败：${error.message}`, "error");
      showToast(`刷新失败：${error.message}`, "error");
    }
    throw error;
  }
}

async function boot() {
  try {
    const [storyData, config, production] = await Promise.all([api("/api/stories"), api("/api/config"), api("/api/production/status")]);
    state.stories = storyData.stories;
    state.config = config;
    state.production = production;
    updateApiIndicator(config.vidu_configured);
    renderProductionOverview(production);
    renderStoryGrid();
    if (!config.vidu_configured) setProductionMessage("可以浏览剧情，但无法继续生成影像或开启实时对话。", "warning");
  } catch (error) {
    $("#story-grid").textContent = `无法加载互动剧：${error.message}`;
  }
}

function storyProgress(storyId) {
  return state.production?.stories?.find((story) => story.id === storyId) || { images: { ready: 0, total: 0 }, movies: { ready: 0, total: 0 }, characters: [] };
}

function storyCover(story) {
  const progress = storyProgress(story.id);
  const hero = progress.characters?.find((character) => character.name === story.hero) || progress.characters?.[0];
  return hero?.asset_url || "";
}

function renderStoryGrid() {
  const grid = $("#story-grid");
  grid.replaceChildren();
  state.stories.forEach((story) => {
    const progress = storyProgress(story.id);
    const cover = storyCover(story);
    const card = document.createElement("button");
    card.className = "story-card";
    card.style.setProperty("--card-bg", paletteStyle(story.palette));
    if (cover) card.style.setProperty("--card-art", `url("${cover}")`);
    card.innerHTML = `<span class="genre">${escapeHtml(story.genre)}</span><h2>${escapeHtml(story.title)}</h2><p>${escapeHtml(story.tagline)}</p><div class="card-progress"><span>${progress.movies.ready}/${progress.movies.total}</span></div>`;
    card.addEventListener("click", () => selectStory(story.id));
    grid.appendChild(card);
  });
}

async function submitImages() {
  if (!state.config.vidu_configured) { showToast("未检测到 VIDU_API_KEY，无法提交角色或 S1 形象。", "error"); return; }
  if (!window.confirm("将提交尚未生成的角色图和已具备参考图的 S1 正脸形象，并消耗 Vidu 额度。是否继续？")) return;
  try {
    setProductionMessage("正在提交角色与 S1 形象...", "warning");
    const payload = await api("/api/production/images/submit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) });
    const message = payload.count ? `已提交 ${payload.count} 张角色或 S1 形象。` : "没有需要提交的角色或 S1 形象。";
    setProductionMessage(message, "success");
    showToast(message);
    await refreshProduction({ quiet: true });
  } catch (error) { setProductionMessage(`提交失败：${error.message}`, "error"); showToast(`提交失败：${error.message}`, "error"); }
}

async function submitVideos() {
  if (!state.config.vidu_configured) { showToast("未检测到 VIDU_API_KEY，无法提交分镜。", "error"); return; }
  if (!window.confirm("将提交下一批最多 12 段 Q3 连续视频过渡，并消耗 Vidu 额度。是否继续？")) return;
  try {
    setProductionMessage("正在交给影像队列...", "warning");
    const payload = await api("/api/production/videos/submit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true, max_tasks: 12 }) });
    const waiting = payload.waiting_for_assets.length ? " 有镜头仍在等待角色图。" : "";
    const message = payload.count ? `已提交 ${payload.count} 段镜头。${waiting}` : `暂时没有可提交的镜头。${waiting}`;
    setProductionMessage(message, "success");
    showToast(message);
    await refreshProduction({ quiet: true });
  } catch (error) { setProductionMessage(`提交失败：${error.message}`, "error"); showToast(`提交失败：${error.message}`, "error"); }
}

async function resumeProduction() {
  if (!state.config.vidu_configured) { showToast("未检测到 VIDU_API_KEY，无法继续生产。", "error"); return; }
  if (!window.confirm("将持续提交所有尚未生成的角色、S1 正脸形象与 Q3 连续视频过渡，并消耗 Vidu 额度。已有任务不会重复提交。是否继续？")) return;
  try {
    const payload = await api("/api/production/resume", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) });
    state.production = payload.status;
    renderProductionOverview(payload.status);
    renderStoryGrid();
    const message = payload.started ? "后台续跑已启动，影像会安静抵达。" : "后台续跑已在进行。";
    setProductionMessage(message, "success");
    showToast(message);
  } catch (error) { setProductionMessage(`无法继续生产：${error.message}`, "error"); showToast(`无法继续生产：${error.message}`, "error"); }
}

async function selectStory(id) {
  try {
    state.story = await api(`/api/stories/${id}`);
    state.choices = [];
    state.values = { ...state.story.initial_state };
    $("#player-story-title").textContent = state.story.title;
    $("#story-screen").dataset.palette = state.story.palette || "snow";
    $("#story-screen").dataset.skin = state.story.skin || "ancient-timetravel";
    renderCompanions();
    renderState();
    updateRouteCount();
    showScreen("story");
    goTo(state.story.start);
  } catch (error) { showToast(`无法进入故事：${error.message}`, "error"); }
}

function primaryArtwork(node = currentNode()) {
  if (node?.poster_url) return node.poster_url;
  if (node?.avatar_url) return node.avatar_url;
  if (node?.fallback_avatar_url) return node.fallback_avatar_url;
  const hero = state.story?.characters?.find((character) => character.name === state.story.hero) || state.story?.characters?.[0];
  return hero?.asset_url || "";
}

function setArtwork(url) {
  const backdrop = $("#visual-backdrop");
  const poster = $("#video-poster");
  [backdrop, poster].forEach((element) => {
    element.classList.toggle("has-image", Boolean(url));
    element.style.backgroundImage = url ? `url("${url}")` : "";
  });
}

function renderCompanions() {
  const list = $("#companion-list");
  list.replaceChildren();
  state.story.characters.forEach((character) => {
    const item = document.createElement("div");
    item.className = "companion";
    const portrait = character.asset_url ? `<img src="${character.asset_url}" alt="${escapeHtml(character.name)}">` : `<span aria-hidden="true"></span>`;
    item.innerHTML = `${portrait}<em>${escapeHtml(character.name)}</em>`;
    list.appendChild(item);
  });
}

function renderState() {
  const list = $("#state-list");
  list.replaceChildren();
  Object.entries(state.story.state_labels).forEach(([key, label]) => {
    const item = document.createElement("div");
    item.className = "state-item";
    const value = state.values[key] ?? 0;
    item.innerHTML = `<span>${escapeHtml(label)}</span><b class="${value < 0 ? "negative" : value > 0 ? "positive" : ""}">${value > 0 ? "+" : ""}${value}</b>`;
    list.appendChild(item);
  });
}

function updateRouteCount() { $("#route-count").textContent = state.choices.length; }

function recordChoice(label, option) {
  Object.entries(option.state_delta || {}).forEach(([key, delta]) => { state.values[key] = (state.values[key] || 0) + Number(delta || 0); });
  state.choices.push({ label, detail: option.label });
  updateRouteCount();
  renderState();
  const list = $("#path-list");
  list.replaceChildren();
  state.choices.forEach((choice) => {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${escapeHtml(choice.label)}</strong><span>${escapeHtml(choice.detail)}</span>`;
    list.appendChild(li);
  });
}

function goTo(nodeId) {
  state.nodeId = nodeId;
  const node = currentNode();
  $("#chapter-label").textContent = node.chapter || "终章";
  $("#route-title").textContent = state.story.title;
  if (node.type === "cutscene") return renderCutscene(node);
  if (node.type === "interactive") return renderLive(node);
  if (node.type === "choice") return renderChoice(node);
  return renderEnding(node);
}

function updateVideoControl() {
  const video = $("#cutscene-video");
  $("#video-toggle").querySelector("span").textContent = video.paused ? "▶" : "Ⅱ";
}

function renderCutscene(node) {
  closeLive();
  showView("fmv");
  setArtwork(primaryArtwork(node));
  $("#media-label").textContent = node.media_url ? "FILM" : "MEMORY";
  $("#cutscene-title").textContent = node.title;
  $("#cutscene-narration").textContent = node.narration;
  $("#video-narration").textContent = node.narration;
  $("#cutscene-next").onclick = () => goTo(node.next);
  $("#cutscene-continue").onclick = () => goTo(node.next);
  $("#cutscene-next-bar").classList.add("hidden");
  const video = $("#cutscene-video");
  video.muted = state.muted;
  video.onended = () => { $("#cutscene-next-bar").classList.remove("hidden"); updateVideoControl(); };
  video.onplay = updateVideoControl;
  video.onpause = updateVideoControl;
  video.onerror = () => { $("#cutscene-next-bar").classList.remove("hidden"); updateVideoControl(); };
  if (node.media_url) {
    video.src = node.media_url;
    video.classList.add("ready");
    $("#cutscene-empty").classList.add("hidden");
    $("#cutscene-next-bar").classList.remove("hidden");
    video.load();
    video.play().catch(() => { $("#cutscene-next-bar").classList.remove("hidden"); updateVideoControl(); });
  } else {
    video.pause();
    video.removeAttribute("src");
    video.classList.remove("ready");
    $("#cutscene-empty").classList.remove("hidden");
    const label = node.production_state === "failed" ? "影像暂时失焦" : node.production_state === "blocked" ? "等待剪辑" : node.production_state === "processing" || node.production_state === "created" || node.production_state === "queueing" ? "影像正在显影" : "这一幕正在准备";
    $("#cutscene-status").textContent = label;
  }
  updateVideoControl();
}

function renderChoice(node) {
  closeLive();
  showView("choice");
  setArtwork(primaryArtwork(node));
  $("#choice-chapter").textContent = node.chapter || "命运正在等待";
  $("#choice-prompt").textContent = node.prompt;
  const options = $("#choice-options");
  options.replaceChildren();
  node.options.forEach((option, index) => {
    const button = document.createElement("button");
    button.className = "choice-option";
    button.dataset.tone = option.tone || "";
    button.style.setProperty("--stagger", String(index));
    button.innerHTML = `<i class="choice-dot"></i><span>${escapeHtml(option.label)}</span>`;
    button.addEventListener("click", () => { recordChoice(node.title, option); goTo(option.next); });
    options.appendChild(button);
  });
}

function rtcEngine() { return window.AliRtcEngine || window.AliRtcEngineSDK || window.AliRtcEngineDefault; }

async function loadRtcSdk() {
  if (rtcEngine()) return rtcEngine();
  await withTimeout(new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = state.config.rtc_sdk_url;
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error("AliRTC SDK 加载失败"));
    document.head.appendChild(script);
  }), 20000, "AliRTC SDK 加载超时，请检查网络是否能访问 SDK 地址。");
  if (!rtcEngine()) throw new Error("AliRTC SDK 未暴露预期接口");
  return rtcEngine();
}

function renderLiveDirectives(directives) {
  const list = $("#live-directives");
  list.replaceChildren();
  if (!Array.isArray(directives) || directives.length === 0) {
    list.classList.add("hidden");
    return;
  }
  directives.slice(0, 4).forEach((directive) => {
    const item = document.createElement("li");
    item.textContent = directive;
    list.appendChild(item);
  });
  list.classList.remove("hidden");
}

function renderLive(node) {
  closeLive();
  showView("live");
  $("#live-view").dataset.s1Mode = node.interaction_mode || "";
  const avatarUrl = node.avatar_url || node.fallback_avatar_url || primaryArtwork(node);
  setArtwork(avatarUrl);
  const avatar = $("#live-avatar");
  avatar.classList.toggle("has-image", Boolean(avatarUrl));
  avatar.style.backgroundImage = avatarUrl ? `url("${avatarUrl}")` : "";
  $("#live-mode").textContent = node.interaction_mode || "现在，和她说句话";
  $("#live-prompt").textContent = node.prompt;
  $("#live-reason").textContent = node.live_brief || "不急着决定。先听听她此刻真正想说的话。";
  renderLiveDirectives(node.live_directives);
  const start = $("#live-start");
  const startMark = document.createElement("span");
  startMark.setAttribute("aria-hidden", "true");
  startMark.textContent = "●";
  start.replaceChildren(startMark, document.createTextNode(` ${node.start_label || "开始对话"}`));
  $("#live-status").textContent = node.avatar_url ? "她已在线，等你开口" : "她的形象仍在准备";
  if (!node.avatar_url) $("#live-status").textContent = "S1 正脸形象仍在准备";
  $("#live-invite").classList.remove("hidden");
  start.disabled = !node.avatar_url;
  $("#live-next").disabled = true;
  $("#live-view").classList.remove("live-connected");
  const nudge = $("#live-nudge");
  if (nudge) {
    nudge.hidden = true;
    nudge.disabled = true;
    nudge.onclick = () => {
      state.live.idleNudges = 0;               // manual push shouldn't count against the idle cap
      if (sendLiveText(idleNudgeLine())) armIdleNudge();
    };
  }
  start.onclick = () => startLive(node);
  $("#live-next").onclick = () => { closeLive(); goTo(node.next); };
}

async function startLive(node) {
  if (!state.config.vidu_configured) { showToast("未检测到 VIDU_API_KEY，无法开始对话。", "error"); return; }
  const start = $("#live-start");
  start.disabled = true;
  $("#live-view").classList.add("live-connecting");
  try {
    state.live.stage = "create-live";
    $("#live-status").textContent = "正在靠近你";
    liveTrace("create_live_start", { storyId: state.story.id, nodeId: state.nodeId });
    const payload = await api("/api/live/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ story_id: state.story.id, node_id: state.nodeId, state: state.values, choices: state.choices.map((item) => item.detail) }) }, 120000);
    state.live.liveId = payload.live?.id || "";
    state.live.rtc = payload.rtc || null;
    if (!state.live.liveId || !state.live.rtc) throw new Error("Vidu S1 未返回 live/rtc 配置");
    liveTrace("create_live_success", { liveId: state.live.liveId });
    state.live.stage = "rtc";
    await joinRtc();
    state.live.stage = "avatar-prepare";
    $("#live-status").textContent = "正在唤醒她";
    await wait(5000);
    state.live.stage = "signaling";
    await connectLiveWs();
    $("#live-view").classList.remove("live-connecting");
    $("#live-invite").classList.add("hidden");
    $("#live-next").disabled = false;
    const nudge = $("#live-nudge");
    if (nudge) { nudge.hidden = false; nudge.disabled = false; }
  } catch (error) {
    const stage = state.live.stage || "unknown";
    liveTrace("live_failed", { stage, message: error?.message || String(error) });
    closeLive();
    $("#live-view").classList.remove("live-connecting");
    $("#live-status").textContent = "暂时没有连上她";
    start.disabled = false;
    showToast(`实时对话未连接（${stage}）：${error.message}`, "error");
  }
}

async function joinRtc() {
  const rtc = state.live.rtc;
  if (!rtc?.token || !rtc?.user_id) throw new Error("RTC 参数缺失");
  $("#live-status").textContent = "正在加载实时音视频";
  liveTrace("rtc_sdk_loading");
  const Engine = await loadRtcSdk();
  const client = typeof Engine.getInstance === "function" ? Engine.getInstance() : new Engine("");
  state.live.rtcClient = client;
  bindRtcEvents(client);
  $("#live-status").textContent = "正在进入实时房间";
  await withTimeout(client.joinChannel(rtc.token, rtc.user_id), 30000, "RTC 入会超时，请重试。");
  liveTrace("rtc_joined", { channelId: rtc.channel_id, userId: rtc.user_id });
  if (typeof client.publishLocalAudioStream === "function") {
    try {
      await withTimeout(client.publishLocalAudioStream(true), 15000, "本地麦克风发布超时，请重试。");
    } catch (error) {
      throw new Error(mediaPermissionMessage(error) || "无法发布本地麦克风。请允许浏览器使用麦克风后重试。");
    }
  }
  if (typeof client.publishLocalVideoStream === "function") {
    try {
      await withTimeout(client.publishLocalVideoStream(true), 15000, "本地摄像头发布超时，已继续语音链路。");
    } catch (error) {
      liveTrace("rtc_camera_unavailable", { message: error?.message || String(error) });
      showToast("摄像头不可用，已继续语音互动。", "warning");
    }
  }
  if (typeof client.setLocalViewConfig === "function") client.setLocalViewConfig($("#local-video"), 1);
  $("#live-status").textContent = "她正在听";
}

function bindRtcEvents(client) {
  if (!client || typeof client.on !== "function" || client.__viduBound) return;
  client.__viduBound = true;
  client.on("remoteUserOnLineNotify", (uid) => subscribeRemote(client, uid));
  client.on("remoteTrackAvailableNotify", (uid) => subscribeRemote(client, uid));
  client.on("videoSubscribeStateChanged", (uid, oldStateOrNewState, maybeNewState) => {
    const newState = maybeNewState ?? oldStateOrNewState;
    liveTrace("rtc_video_subscribe_state", { uid, newState });
    if ((newState === 3 || newState === "subscribed") && isVideoPushUid(uid)) renderRemote(client, uid);
  });
}

function isVideoPushUid(uid) {
  return String(uid || "").includes("live-video-push");
}

function subscribeRemote(client, uid) {
  const isVideoPush = isVideoPushUid(uid);
  if (typeof client.subscribe === "function") {
    Promise.resolve(client.subscribe(uid))
      .then(() => { if (isVideoPush) renderRemote(client, uid); })
      .catch((error) => liveTrace("rtc_subscribe_failed", { uid, message: error?.message || String(error) }));
  }
  if (isVideoPush && typeof client.configRemoteCameraTrack === "function") client.configRemoteCameraTrack(uid, true, true);
}

function renderRemote(client, uid) {
  if (!isVideoPushUid(uid)) return;
  if (typeof client.setRemoteViewConfig === "function") { client.setRemoteViewConfig($("#remote-video"), uid, 2); client.setRemoteViewConfig($("#remote-video"), uid, 1); }
  liveTrace("rtc_remote_rendered", { uid });
  $("#live-view").classList.add("live-connected");
  $("#live-status").textContent = "她在看着你";
}

function nestedValue(value, keys, depth = 0) {
  if (!value || typeof value !== "object" || depth > 5) return undefined;
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(value, key) && value[key] !== undefined) return value[key];
  }
  for (const child of Object.values(value)) {
    const found = nestedValue(child, keys, depth + 1);
    if (found !== undefined) return found;
  }
  return undefined;
}

// Advantage C: turn type-9 (user speech) / type-10 (avatar speech) events into an
// on-screen subtitle and a first-response latency reading. Returns null for other types.
function parseTranscriptEvent(data) {
  const type = Number(data?.type);
  if (type !== 9 && type !== 10) return null;
  const source = data?.payload || data;
  const textValue = nestedValue(source, ["text", "content", "transcript", "sentence"]);
  const text = typeof textValue === "string" ? textValue.trim() : "";
  if (!text) return null;
  const finalValue = nestedValue(source, ["is_final", "final", "finished", "is_end"]);
  return {
    speaker: type === 9 ? "user" : "avatar",
    text,
    final: finalValue === undefined ? true : finalValue === true || finalValue === 1 || finalValue === "true",
    seqId: Number.isInteger(data?.seq_id) ? data.seq_id : undefined,
    eventAtMs: Date.now(),
  };
}

function showLiveSubtitle(entry) {
  const layer = $("#live-subtitle");
  if (!layer) return;
  layer.textContent = `${entry.speaker === "user" ? "你" : "她"}：${entry.text}`;
  layer.classList.remove("hidden");
  layer.classList.toggle("subtitle-user", entry.speaker === "user");
  layer.classList.toggle("subtitle-avatar", entry.speaker === "avatar");
  window.clearTimeout(state.transcript.subtitleTimer);
  state.transcript.subtitleTimer = window.setTimeout(() => layer.classList.add("hidden"), 5200);
}

function handleTranscript(entry) {
  showLiveSubtitle(entry);
  // Any live speech means the player is engaged — restart the idle countdown.
  // When the player themselves speaks, also reset the nudge budget.
  if (state.live.idleTimer !== null) armIdleNudge();
  if (!entry.final) return;
  const key = `${entry.speaker}:${entry.seqId ?? ""}:${entry.text}`;
  if (state.transcript.keys.has(key)) return;
  state.transcript.keys.add(key);
  if (entry.speaker === "user") {
    state.transcript.pendingUserAt = entry.eventAtMs;
    state.live.idleNudges = 0;
  } else if (entry.speaker === "avatar" && state.transcript.pendingUserAt) {
    const latencyMs = Math.max(0, entry.eventAtMs - state.transcript.pendingUserAt);
    state.transcript.pendingUserAt = 0;
    state.transcript.lastLatencyMs = latencyMs;
    liveTrace("first_response_latency", { liveId: state.live.liveId, latencyMs });
    const status = $("#live-status");
    if (status) status.textContent = `她回应用时 ${(latencyMs / 1000).toFixed(1)}s`;
  }
  if (state.live.liveId) {
    fetch("/api/console/transcripts", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ live_id: state.live.liveId, entries: [{
        speaker: entry.speaker, text: entry.text, event_at_ms: entry.eventAtMs,
        ...(entry.seqId !== undefined ? { seq_id: entry.seqId } : {}),
        ...(entry.speaker === "avatar" && state.transcript.lastLatencyMs !== null ? { latency_ms: state.transcript.lastLatencyMs } : {}),
      }] }),
    }).catch(() => {});
  }
}

function sendConnInit() {
  const ws = state.live.ws;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  liveTrace("conn_init_sent", { liveId: state.live.liveId });
  ws.send(JSON.stringify({ type: 1, live_id: state.live.liveId, seq_id: state.live.sequence++, payload: { conn_init: { version: 1 } } }));
}

function sendLivePing() {
  const ws = state.live.ws;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: 3, live_id: state.live.liveId, seq_id: state.live.sequence++, payload: { ping: {} } }));
}

// Advantage: proactive interaction. Push a line for the avatar to speak on its
// own (type 99 text_msg), e.g. a scripted nudge or an idle re-engagement.
function sendLiveText(content) {
  const text = String(content || "").trim();
  const ws = state.live.ws;
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return false;
  ws.send(JSON.stringify({ type: 99, live_id: state.live.liveId, seq_id: state.live.sequence++, payload: { text_msg: { content: text } } }));
  liveTrace("text_msg_sent", { chars: text.length });
  return true;
}

// Client-side idle nudge: if the player stays silent, prompt the avatar to
// re-engage in character. This complements the server-side vad.idle_timeout_ms
// with a scripted, author-controllable line. Capped so it never spams.
const IDLE_NUDGE_MS = 18000;
const IDLE_NUDGE_MAX = 3;
function idleNudgeLine() {
  const node = currentNode() || {};
  const name = node.avatar_name || "对方";
  return `（玩家沉默了一会儿）以${name}的身份，主动、自然地追问或关心一句，把话题继续下去，只说一句，不要旁白。`;
}
function armIdleNudge() {
  clearTimeout(state.live.idleTimer);
  if (state.live.idleNudges >= IDLE_NUDGE_MAX) return;
  state.live.idleTimer = window.setTimeout(() => {
    if (sendLiveText(idleNudgeLine())) {
      state.live.idleNudges += 1;
      liveTrace("idle_nudge", { count: state.live.idleNudges });
    }
    armIdleNudge();
  }, IDLE_NUDGE_MS);
}
function stopIdleNudge() {
  clearTimeout(state.live.idleTimer);
  state.live.idleTimer = null;
}

function connectLiveWs() {
  return new Promise((resolve, reject) => {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    state.live.sequence = 1;
    state.live.initRetries = 0;
    let settled = false;
    const finish = (method, value) => { if (!settled) { settled = true; method(value); } };
    const retryInit = (reason) => {
      state.live.initRetries += 1;
      if (state.live.initRetries > 10) {
        finish(reject, new Error(`S1 长时间未就绪（${reason}），请重新创建会话`));
        return;
      }
      const delay = Math.min(3000 * (1.5 ** (state.live.initRetries - 1)), 10000);
      $("#live-status").textContent = `她正在赶来（${state.live.initRetries}/10）`;
      liveTrace("conn_init_retry", { attempt: state.live.initRetries, delay, reason });
      clearTimeout(state.live.retryTimer);
      state.live.retryTimer = window.setTimeout(openWs, delay);
    };
    const openWs = () => {
      if (settled) return;
      let expectedClose = false;
      let retryQueued = false;
      let handshakeTimer = null;
      const ws = new WebSocket(`${scheme}://${location.host}${state.config.ws_proxy}?live_id=${encodeURIComponent(state.live.liveId)}`);
      state.live.ws = ws;
      const scheduleRetry = (reason) => {
        if (settled || retryQueued) return;
        retryQueued = true;
        expectedClose = true;
        clearTimeout(handshakeTimer);
        try { ws.close(); } catch {}
        retryInit(reason);
      };
      ws.onopen = () => {
        liveTrace("signaling_proxy_open", { liveId: state.live.liveId });
        handshakeTimer = window.setTimeout(() => scheduleRetry("信令代理未确认上游连接"), 15000);
      };
      ws.onerror = () => scheduleRetry("S1 信令 WebSocket 连接失败");
      ws.onclose = () => {
        if (!settled && !expectedClose) scheduleRetry("S1 信令在初始化前关闭");
      };
      ws.onmessage = (event) => {
        let data;
        try { data = JSON.parse(event.data); } catch { return; }
        const transcript = parseTranscriptEvent(data);
        if (transcript) { handleTranscript(transcript); return; }
        if (data?.type === "proxy_connected") {
          clearTimeout(handshakeTimer);
          $("#live-status").textContent = "正在建立对话";
          liveTrace("signaling_proxy_connected", { liveId: data.live_id || state.live.liveId });
          sendConnInit();
          handshakeTimer = window.setTimeout(() => scheduleRetry("conn_init 超时"), 15000);
          return;
        }
        if (data?.type === "proxy_error" || data?.error) {
          clearTimeout(handshakeTimer);
          liveTrace("signaling_proxy_error", { message: data.error || "unknown" });
          finish(reject, new Error(`S1 信令代理失败：${data.error}`));
          return;
        }
        const ack = data?.payload?.conn_init_ack || data?.conn_init_ack;
        if (ack?.success === true) {
          clearTimeout(handshakeTimer);
          $("#live-status").textContent = "你们终于面对面";
          clearInterval(state.live.pingTimer);
          state.live.pingTimer = window.setInterval(sendLivePing, 10000);
          state.live.idleNudges = 0;
          armIdleNudge();
          liveTrace("conn_init_success", { liveId: state.live.liveId });
          finish(resolve, data);
          return;
        }
        const ackCode = String(ack?.error_code || ack?.reason || ack?.message || "").toUpperCase();
        if (ackCode.includes("NOT_READY") || ackCode.includes("INITIALIZING")) {
          scheduleRetry(ackCode || "NOT_READY");
          return;
        }
        if (ackCode.includes("LIVE_CONN_INIT_FAILED")) {
          clearTimeout(handshakeTimer);
          finish(reject, new Error("S1 初始化失败（LIVE_CONN_INIT_FAILED），请重新创建会话"));
          return;
        }
        if (ack?.success === false) { clearTimeout(handshakeTimer); finish(reject, new Error(`S1 初始化失败：${ack?.error_code || ack?.reason || "UNKNOWN"}`)); return; }
        const hangup = data?.payload?.hangup || data?.hangup;
        if (hangup) {
          clearTimeout(handshakeTimer);
          finish(reject, new Error(`S1 会话已结束：${hangup.hangup_reason || "unknown"}`));
        }
      };
    };
    openWs();
  });
}

function closeLive() {
  clearTimeout(state.live.retryTimer);
  clearInterval(state.live.pingTimer);
  stopIdleNudge();
  if (state.live.ws?.readyState === WebSocket.OPEN && state.live.liveId) {
    try { state.live.ws.send(JSON.stringify({ type: 5, live_id: state.live.liveId, seq_id: state.live.sequence++, payload: { hangup: { hangup_reason: "user_end" } } })); } catch {}
  }
  if (state.live.ws) { try { state.live.ws.close(); } catch {} }
  if (state.live.rtcClient?.leaveChannel) { try { state.live.rtcClient.leaveChannel(); } catch {} }
  if (state.live.liveId) fetch("/api/live/close", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ live_id: state.live.liveId }) }).catch(() => {});
  $("#live-view").classList.remove("live-connected", "live-connecting");
  const nudge = $("#live-nudge");
  if (nudge) { nudge.hidden = true; nudge.disabled = true; }
  window.clearTimeout(state.transcript.subtitleTimer);
  $("#live-subtitle")?.classList.add("hidden");
  state.live = { ws: null, rtcClient: null, liveId: "", rtc: null, sequence: 1, retryTimer: null, pingTimer: null, initRetries: 0, stage: "", idleTimer: null, idleNudges: 0 };
  state.transcript = { keys: new Set(), pendingUserAt: 0, lastLatencyMs: null, subtitleTimer: null };
}

function pickEndingVariant(node) {
  const variants = node.variants || [];
  return variants.find((variant) => Object.entries(variant.when || {}).every(([key, value]) => (state.values[key] || 0) >= value)) || variants[variants.length - 1];
}

function renderEnding(node) {
  closeLive();
  showView("ending");
  setArtwork(primaryArtwork(node));
  const variant = pickEndingVariant(node);
  $("#ending-title").textContent = variant?.title || node.title;
  $("#ending-text").textContent = node.text;
  $("#ending-variant").textContent = variant?.text || "";
}

async function refreshCurrentStory() {
  if (!state.story) return refreshProduction();
  const current = state.nodeId;
  await refreshProduction({ quiet: true });
  state.story = await api(`/api/stories/${state.story.id}`);
  renderCompanions();
  goTo(current);
}

$("#production-open").addEventListener("click", () => productionDrawer.showModal());
$("#production-close").addEventListener("click", () => productionDrawer.close());
$("#refresh-production").addEventListener("click", () => refreshProduction());
$("#submit-images").addEventListener("click", submitImages);
$("#submit-videos").addEventListener("click", submitVideos);
$("#resume-production").addEventListener("click", resumeProduction);
$("#story-back").addEventListener("click", () => { closeLive(); showScreen("library"); });
$("#live-back").addEventListener("click", () => { closeLive(); showScreen("library"); });
$("#path-toggle").addEventListener("click", () => $("#path-panel").classList.add("open"));
$("#path-close").addEventListener("click", () => $("#path-panel").classList.remove("open"));
$("#restart-story").addEventListener("click", () => { state.choices = []; state.values = { ...state.story.initial_state }; updateRouteCount(); renderState(); goTo(state.story.start); });
$("#video-toggle").addEventListener("click", () => { const video = $("#cutscene-video"); if (!video.src) return; if (video.paused) video.play().catch(() => {}); else video.pause(); });
$("#player-sound").addEventListener("click", () => { state.muted = !state.muted; $("#cutscene-video").muted = state.muted; $("#sound-icon").textContent = state.muted ? "×" : "◖"; showToast(state.muted ? "已静音" : "声音已开启"); });
window.addEventListener("beforeunload", closeLive);
boot();

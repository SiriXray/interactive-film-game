"use strict";

// Vidu S1 operator console: create -> RTC join -> WS conn_init -> live control.
// Credentials remain server-side or in memory; logs and saved avatar presets exclude them.

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const SYSTEM_VOICES = [
  ["", "默认 · Tina（甜甜）"], ["Maia", "Maia · 四月（知性温柔）"],
  ["Tina", "Tina · 甜甜（温暖利落）"], ["Serena", "Serena · 苏瑶（温柔）"],
  ["Katerina", "Katerina · 卡捷琳娜（御姐）"], ["Jennifer", "Jennifer · 詹妮弗（电影感美语）"],
  ["Mia", "Mia · 舒然（治愈）"], ["Sohee", "Sohee · 素熙（韩语）"],
  ["Qiao", "Qiao · 小乔妹（台腔）"], ["Momo", "Momo · 茉兔（俏皮）"],
  ["Cindy", "Cindy · 林欣宜（台腔）"], ["Andre", "Andre · 安德雷（沉稳男声）"],
  ["Ethan", "Ethan · 晨煦（阳光男声）"], ["Harvey", "Harvey · 厚（低沉男声）"],
  ["Evan", "Evan · 江晨（青年男声）"], ["Dylan", "Dylan · 北京晓东（京腔）"],
  ["Theo Calm", "Theo Calm · 予安（疗愈男声）"], ["Ryan", "Ryan · 甜茶（戏感）"],
  ["Sunny", "Sunny · 四川晴儿（川音）"], ["Kiki", "Kiki · 粤语阿清（粤语）"],
];

const state = {
  config: { vidu_configured: false, rtc_sdk_url: "", ws_proxy: "/ws/live" },
  callMode: "video",
  imageUri: "",
  phase: "idle",
  activeCapabilities: {},
  transcripts: [],
  transcriptKeys: new Map(),
  persistQueue: [],
  persistTimer: null,
  subtitleTimers: {},
  pendingResponseAt: 0,
  live: {
    ws: null, rtcClient: null, liveId: "", rtc: null, sequence: 1, retryTimer: null,
    pingTimer: null, statusTimer: null, elapsedTimer: null, initRetries: 0, stage: "",
    requestedAt: 0, startedAt: 0, ended: false,
  },
};

const LOG_CLASS = { info: "", ok: "ok", warn: "warn", error: "err", accent: "accent" };
const ASSET_KEY = "vidu-s1-avatar-assets-v1";

function log(message, level = "info") {
  const item = document.createElement("li");
  if (LOG_CLASS[level]) item.className = LOG_CLASS[level];
  const now = new Date();
  const time = document.createElement("time");
  time.textContent = now.toLocaleTimeString("zh-CN", { hour12: false });
  const text = document.createElement("span");
  text.className = "msg";
  text.textContent = message;
  item.append(time, text);
  const list = $("#event-log");
  list.prepend(item);
  while (list.childElementCount > 80) list.lastElementChild.remove();
  $("#event-count").textContent = String(list.childElementCount);
}

function toast(message, kind = "info") {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast show ${kind}`;
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => { element.className = "toast"; }, 4200);
}

function setPhase(phase, text) {
  state.phase = phase;
  $("#stage-phase").className = `phase-chip phase-${phase}`;
  $("#phase-text").textContent = text;
}

function wait(ms) { return new Promise((resolve) => window.setTimeout(resolve, ms)); }

function withTimeout(promise, ms, message) {
  let timer;
  const timeout = new Promise((_, reject) => { timer = window.setTimeout(() => reject(new Error(message)), ms); });
  return Promise.race([Promise.resolve(promise).finally(() => window.clearTimeout(timer)), timeout]);
}

async function api(url, options = {}, timeoutMs = 120000) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const response = await fetch(url, { ...options, signal: controller.signal }).finally(() => window.clearTimeout(timeoutId));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function numericValue(selector) { return Number($(selector).value); }

function mediaPermissionMessage(error) {
  const message = String(error?.message || error || "");
  if (/permission|denied|notallowed|dismiss/i.test(message)) return "麦克风或摄像头权限被拒绝，请在地址栏允许后重试。";
  if (/notfound|devices? not found|overconstrained/i.test(message)) return "未检测到可用的麦克风或摄像头。";
  return message;
}

function showConnecting(text) {
  $("#stage").classList.add("connecting");
  $("#connecting-overlay").classList.remove("hidden");
  $("#connecting-overlay").setAttribute("aria-hidden", "false");
  $("#connecting-text").textContent = text;
}

function setConnecting(text) { $("#connecting-text").textContent = text; }

function hideConnecting() {
  $("#stage").classList.remove("connecting");
  $("#connecting-overlay").classList.add("hidden");
  $("#connecting-overlay").setAttribute("aria-hidden", "true");
}

/* RTC ------------------------------------------------------------------ */

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
  }), 20000, "AliRTC SDK 加载超时。");
  if (!rtcEngine()) throw new Error("AliRTC SDK 未暴露预期接口");
  return rtcEngine();
}

function isVideoPushUid(uid) { return String(uid || "").includes("live-video-push"); }

function renderRemote(client, uid) {
  if (!isVideoPushUid(uid)) return;
  if (typeof client.setRemoteViewConfig === "function") {
    client.setRemoteViewConfig($("#remote-video"), uid, 2);
    client.setRemoteViewConfig($("#remote-video"), uid, 1);
  }
  $("#stage").classList.add("live-connected");
  hideConnecting();
  setPhase("live", "对话中");
  log("数字人音视频已就位", "ok");
}

function subscribeRemote(client, uid) {
  const videoPush = isVideoPushUid(uid);
  if (typeof client.subscribe === "function") {
    Promise.resolve(client.subscribe(uid))
      .then(() => { if (videoPush) renderRemote(client, uid); })
      .catch((error) => log(`订阅远端失败：${error?.message || error}`, "warn"));
  }
  if (videoPush && typeof client.configRemoteCameraTrack === "function") client.configRemoteCameraTrack(uid, true, true);
}

function bindRtcEvents(client) {
  if (!client || typeof client.on !== "function" || client.__viduBound) return;
  client.__viduBound = true;
  client.on("remoteUserOnLineNotify", (uid) => subscribeRemote(client, uid));
  client.on("remoteTrackAvailableNotify", (uid) => subscribeRemote(client, uid));
  client.on("videoSubscribeStateChanged", (uid, oldOrNew, maybeNew) => {
    const newState = maybeNew ?? oldOrNew;
    if ((newState === 3 || newState === "subscribed") && isVideoPushUid(uid)) renderRemote(client, uid);
  });
}

async function joinRtc() {
  const rtc = state.live.rtc;
  if (!rtc?.token || !rtc?.user_id) throw new Error("RTC 参数缺失");
  setConnecting("正在加载实时音视频");
  const Engine = await loadRtcSdk();
  const client = typeof Engine.getInstance === "function" ? Engine.getInstance() : new Engine("");
  state.live.rtcClient = client;
  bindRtcEvents(client);
  setConnecting("正在进入实时房间");
  await withTimeout(client.joinChannel(rtc.token, rtc.user_id), 30000, "RTC 入会超时，请重试。");
  log("已加入 RTC 房间", "ok");
  if (typeof client.publishLocalAudioStream === "function") {
    try {
      await withTimeout(client.publishLocalAudioStream(true), 15000, "本地麦克风发布超时。");
      $("#mic-chip").classList.add("mic-on");
    } catch (error) { throw new Error(mediaPermissionMessage(error) || "无法发布本地麦克风。"); }
  }
  if (state.callMode === "video" && typeof client.publishLocalVideoStream === "function") {
    try {
      await withTimeout(client.publishLocalVideoStream(true), 15000, "本地摄像头发布超时。");
    } catch (error) {
      log(`摄像头不可用，继续语音链路：${error?.message || error}`, "warn");
      toast("摄像头不可用，已继续语音互动。", "warning");
    }
  }
  if (typeof client.setLocalViewConfig === "function") client.setLocalViewConfig($("#local-video"), 1);
}

/* Signaling and transcripts --------------------------------------------- */

function sendSocketMessage(type, payload) {
  const ws = state.live.ws;
  if (!ws || ws.readyState !== WebSocket.OPEN || !state.live.liveId) return false;
  ws.send(JSON.stringify({ type, live_id: state.live.liveId, seq_id: state.live.sequence++, payload }));
  return true;
}

function sendConnInit() {
  if (sendSocketMessage(1, { conn_init: { version: 1 } })) log("已发送 conn_init");
}
function sendPing() { sendSocketMessage(3, { ping: {} }); }

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

function parseTranscriptEvent(data) {
  const type = Number(data?.type);
  if (type !== 9 && type !== 10) return null;
  const source = data?.payload || data;
  let textValue = nestedValue(source, ["text", "content", "sentence", "utterance"]);
  if (typeof textValue !== "string") {
    const transcriptValue = nestedValue(source, ["transcript", "result"]);
    if (typeof transcriptValue === "string") textValue = transcriptValue;
  }
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

function showSubtitle(entry) {
  const selector = entry.speaker === "user" ? "#subtitle-user" : "#subtitle-avatar";
  const element = $(selector);
  element.querySelector("span").textContent = entry.text;
  element.classList.remove("hidden");
  window.clearTimeout(state.subtitleTimers[entry.speaker]);
  state.subtitleTimers[entry.speaker] = window.setTimeout(() => element.classList.add("hidden"), 5200);
}

function transcriptKey(entry) { return `${entry.speaker}:${entry.seqId ?? ""}:${entry.text}`; }

function handleTranscript(entry) {
  showSubtitle(entry);
  if (!entry.final) return;
  const key = transcriptKey(entry);
  const duplicateAt = state.transcriptKeys.get(key);
  if (duplicateAt && (entry.seqId !== undefined || entry.eventAtMs - duplicateAt < 1500)) return;
  state.transcriptKeys.set(key, entry.eventAtMs);
  let latencyMs;
  if (entry.speaker === "user") state.pendingResponseAt = entry.eventAtMs;
  if (entry.speaker === "avatar" && state.pendingResponseAt) {
    latencyMs = Math.max(0, entry.eventAtMs - state.pendingResponseAt);
    state.pendingResponseAt = 0;
    $("#tele-latency").textContent = `${latencyMs}ms`;
  }
  const stored = { ...entry, latencyMs };
  state.transcripts.push(stored);
  renderTranscript(stored);
  $("#tele-transcripts").textContent = String(state.transcripts.length);
  $("#export-transcript").disabled = false;
  queueTranscriptPersistence(stored);
}

function renderTranscript(entry) {
  $("#transcript-empty")?.remove();
  const item = document.createElement("li");
  item.className = `transcript-item ${entry.speaker}`;
  const meta = document.createElement("div");
  meta.className = "transcript-meta";
  const speaker = document.createElement("strong");
  speaker.textContent = entry.speaker === "user" ? "用户" : "数字人";
  const stamp = document.createElement("time");
  stamp.textContent = new Date(entry.eventAtMs).toLocaleTimeString("zh-CN", { hour12: false });
  meta.append(speaker, stamp);
  const text = document.createElement("p");
  text.textContent = entry.text;
  item.append(meta, text);
  $("#transcript-list").append(item);
  item.scrollIntoView({ block: "nearest" });
}

function queueTranscriptPersistence(entry) {
  if (!state.live.liveId) return;
  state.persistQueue.push({
    liveId: state.live.liveId,
    entry: {
      speaker: entry.speaker, text: entry.text, event_at_ms: entry.eventAtMs,
      ...(entry.seqId !== undefined ? { seq_id: entry.seqId } : {}),
      ...(entry.latencyMs !== undefined ? { latency_ms: entry.latencyMs } : {}),
    },
  });
  $("#persist-status").textContent = "等待留存";
  window.clearTimeout(state.persistTimer);
  state.persistTimer = window.setTimeout(flushTranscripts, 450);
}

async function flushTranscripts() {
  window.clearTimeout(state.persistTimer);
  if (!state.persistQueue.length) return;
  const liveId = state.persistQueue[0].liveId;
  const batch = [];
  while (state.persistQueue.length && state.persistQueue[0].liveId === liveId && batch.length < 50) {
    batch.push(state.persistQueue.shift());
  }
  try {
    await api("/api/console/transcripts", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ live_id: liveId, entries: batch.map((item) => item.entry) }),
    }, 15000);
    $("#persist-status").textContent = "已留存";
  } catch (error) {
    state.persistQueue.unshift(...batch);
    $("#persist-status").textContent = "留存失败";
    log(`转写留存失败：${error.message}`, "warn");
  }
  if (state.persistQueue.length) state.persistTimer = window.setTimeout(flushTranscripts, 1000);
}

function handleLiveMessage(data, handshake) {
  const transcript = parseTranscriptEvent(data);
  if (transcript) { handleTranscript(transcript); return; }
  const hangup = data?.payload?.hangup || data?.hangup;
  if (hangup || Number(data?.type) === 6) {
    const reason = hangup?.hangup_reason || "unknown";
    log(`服务器结束会话：${reason}`, "warn");
    if (!handshake.settled) handshake.reject(new Error(`会话结束：${reason}`));
    else endSession(`服务器挂断（${reason}）`);
  }
}

function connectLiveWs() {
  return new Promise((resolve, reject) => {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    state.live.sequence = 1;
    state.live.initRetries = 0;
    const handshake = { settled: false, reject: (error) => { if (!handshake.settled) { handshake.settled = true; reject(error); } } };
    const resolveOnce = (value) => { if (!handshake.settled) { handshake.settled = true; resolve(value); } };

    const retryInit = (reason) => {
      state.live.initRetries += 1;
      if (state.live.initRetries > 10) { handshake.reject(new Error(`S1 长时间未就绪（${reason}）`)); return; }
      const delay = Math.min(2000 * (2 ** (state.live.initRetries - 1)), 8000);
      setConnecting(`数字人预热中 ${state.live.initRetries}/10`);
      log(`conn_init 重试 #${state.live.initRetries}，${Math.round(delay / 1000)}s 后重连`, "warn");
      window.clearTimeout(state.live.retryTimer);
      state.live.retryTimer = window.setTimeout(openWs, delay);
    };

    const openWs = () => {
      if (handshake.settled) return;
      let expectedClose = false;
      let retryQueued = false;
      let handshakeTimer = null;
      const ws = new WebSocket(`${scheme}://${location.host}${state.config.ws_proxy}?live_id=${encodeURIComponent(state.live.liveId)}`);
      state.live.ws = ws;
      const scheduleRetry = (reason) => {
        if (handshake.settled || retryQueued) return;
        retryQueued = true;
        expectedClose = true;
        window.clearTimeout(handshakeTimer);
        try { ws.close(); } catch {}
        retryInit(reason);
      };
      ws.onopen = () => { handshakeTimer = window.setTimeout(() => scheduleRetry("信令代理未确认连接"), 15000); };
      ws.onerror = () => scheduleRetry("WebSocket 连接失败");
      ws.onclose = () => {
        if (!handshake.settled && !expectedClose) scheduleRetry("信令初始化前关闭");
        else if (handshake.settled && !expectedClose && state.phase === "live" && !state.live.ended) endSession("信令连接已断开");
      };
      ws.onmessage = (event) => {
        let data;
        try { data = JSON.parse(event.data); } catch { return; }
        if (data?.type === "proxy_connected") {
          window.clearTimeout(handshakeTimer);
          setConnecting("正在建立对话");
          sendConnInit();
          handshakeTimer = window.setTimeout(() => scheduleRetry("conn_init 超时"), 15000);
          return;
        }
        if (data?.type === "proxy_error" || data?.error) {
          window.clearTimeout(handshakeTimer);
          handshake.reject(new Error(`信令代理失败：${data.error}`));
          return;
        }
        const ack = data?.payload?.conn_init_ack || data?.conn_init_ack;
        if (ack?.success === true) {
          window.clearTimeout(handshakeTimer);
          window.clearInterval(state.live.pingTimer);
          state.live.pingTimer = window.setInterval(sendPing, 10000);
          log("数字人已上线，计费开始", "ok");
          resolveOnce(data);
          return;
        }
        const code = String(ack?.error_code || ack?.reason || ack?.message || "").toUpperCase();
        if (ack?.success === false && (code.includes("NOT_READY") || code.includes("INITIALIZING"))) { scheduleRetry(code || "NOT_READY"); return; }
        if (code.includes("LIVE_CONN_INIT_FAILED")) { window.clearTimeout(handshakeTimer); handshake.reject(new Error("初始化失败，请重新创建会话")); return; }
        if (ack?.success === false) { window.clearTimeout(handshakeTimer); handshake.reject(new Error(`初始化失败：${code || "UNKNOWN"}`)); return; }
        handleLiveMessage(data, handshake);
      };
    };
    openWs();
  });
}

function sendTextMessage(text, source = "text") {
  const content = String(text || "").trim();
  if (!content) return false;
  if (state.phase !== "live" || !sendSocketMessage(99, { text_msg: { content } })) {
    toast("会话尚未接通，无法发送。", "warning");
    return false;
  }
  state.pendingResponseAt = Date.now();
  $("#message-status").textContent = source === "command" ? "动作指令已发送" : "文字消息已发送";
  log(source === "command" ? "已发送动作/主动互动指令" : "已发送文字消息", "accent");
  return true;
}

/* Configuration --------------------------------------------------------- */

function retrievalPayload(prefix) {
  const enabled = $(`#${prefix}-enabled`).checked;
  if (!enabled) return { enabled: false };
  return {
    enabled: true, endpoint: $(`#${prefix}-endpoint`).value.trim(),
    authorization: $(`#${prefix}-authorization`).value.trim(),
    timeout_ms: numericValue(`#${prefix}-timeout`),
  };
}

function buildLiveRequest() {
  return {
    persona: $("#persona").value.trim(), image_uri: state.imageUri, name: $("#name").value.trim(),
    voice: $("#voice").value, greeting_instruction: $("#greeting").value.trim(), call_mode: state.callMode,
    audio: { enable_transcription: $("#transcription-enabled").checked },
    extra_motion: $("#extra-motion-enabled").checked,
    vad: { type: $("#vad-type").value, threshold: numericValue("#vad-threshold"), silence_duration_ms: numericValue("#vad-silence"), idle_timeout_ms: numericValue("#vad-idle") },
    llm: {
      temperature: numericValue("#llm-temperature"), top_p: numericValue("#llm-top-p"), top_k: numericValue("#llm-top-k"),
      frequency_penalty: numericValue("#llm-frequency"), presence_penalty: numericValue("#llm-presence"),
      seed: numericValue("#llm-seed"), max_tokens: numericValue("#llm-max-tokens"),
    },
    idle_timeout_seconds: numericValue("#session-idle"),
    memory_retrieval: retrievalPayload("memory"),
    knowledge_retrieval: retrievalPayload("knowledge"),
  };
}

function validateLiveRequest(payload) {
  if (!payload.persona) { $("#persona").focus(); return "请填写角色人设。"; }
  if (!payload.image_uri) { $("#image-url").focus(); return "请提供数字人形象图。"; }
  for (const [name, config] of [["长期记忆", payload.memory_retrieval], ["专业知识库", payload.knowledge_retrieval]]) {
    if (config.enabled && (!config.endpoint || !config.authorization)) return `${name}启用后必须填写接口地址和 Authorization。`;
  }
  return "";
}

function updateCapabilityDisplay(payload = buildLiveRequest()) {
  const values = {
    memory: [payload.memory_retrieval.enabled, payload.memory_retrieval.enabled ? "外接启用" : "未启用"],
    knowledge: [payload.knowledge_retrieval.enabled, payload.knowledge_retrieval.enabled ? "外接启用" : "未启用"],
    motion: [payload.extra_motion, payload.extra_motion ? "已启用" : "未启用"],
    transcription: [payload.audio.enable_transcription, payload.audio.enable_transcription ? "已启用" : "未启用"],
    proactive: [payload.vad.idle_timeout_ms > 0, payload.vad.idle_timeout_ms > 0 ? `${(payload.vad.idle_timeout_ms / 1000).toFixed(1)}s` : "关闭"],
  };
  Object.entries(values).forEach(([key, [enabled, label]]) => {
    const text = $(`#cap-${key}`);
    text.textContent = label;
    text.closest(".capability").classList.toggle("is-on", enabled);
  });
  $("#motion-chip").textContent = payload.extra_motion ? "动作已启用" : "动作未启用";
  $("#motion-chip").classList.toggle("motion-on", payload.extra_motion);
}

/* Session --------------------------------------------------------------- */

async function startSession() {
  if (!state.config.vidu_configured) { toast("未检测到 VIDU_API_KEY，无法创建会话。", "error"); return; }
  const request = buildLiveRequest();
  const validationError = validateLiveRequest(request);
  if (validationError) { toast(validationError, "error"); return; }
  clearTranscripts();
  $("#tele-latency").textContent = "-";
  $("#tele-ready").textContent = "-";
  $("#tele-billed").textContent = "-";
  $("#tele-credits").textContent = "-";
  state.activeCapabilities = request;
  updateCapabilityDisplay(request);
  state.live.requestedAt = Date.now();
  state.live.ended = false;
  $("#start-btn").disabled = true;
  $("#start-label").textContent = "连接中";
  showConnecting("正在创建 S1 会话");
  setPhase("connecting", "连接中");
  try {
    state.live.stage = "create";
    log(`创建 S1 会话（${state.callMode}）`);
    const payload = await api("/api/console/live/start", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    });
    state.live.liveId = payload.live?.id || "";
    state.live.rtc = payload.rtc || null;
    if (!state.live.liveId || !state.live.rtc) throw new Error("Vidu 未返回 live/rtc 配置");
    $("#tele-liveid").textContent = state.live.liveId;
    $("#persist-status").textContent = request.audio.enable_transcription ? "等待转写" : "转写未启用";
    log("会话资源已创建", "ok");
    state.live.stage = "rtc";
    await joinRtc();
    state.live.stage = "signaling";
    setConnecting("数字人正在预热");
    await connectLiveWs();
    state.live.startedAt = Date.now();
    onConnected();
  } catch (error) {
    log(`连接失败（${state.live.stage}）：${error.message}`, "error");
    toast(`连接失败：${error.message}`, "error");
    await teardown();
    resetControls();
    setPhase("idle", "待命");
    $("#stage").classList.remove("live-connected");
  }
}

function onConnected() {
  hideConnecting();
  setPhase("live", "对话中");
  $("#stage").classList.add("live-connected");
  $("#hangup-btn").disabled = false;
  $("#start-label").textContent = "会话进行中";
  $("#message-input").disabled = false;
  $("#send-message-btn").disabled = false;
  $$(".command-btn").forEach((button) => { button.disabled = false; });
  $("#message-status").textContent = "文字与动作通道已就绪";
  $("#tele-status").textContent = "on_live";
  $("#tele-ready").textContent = `${state.live.startedAt - state.live.requestedAt}ms`;
  toast("数字人已接通，可语音、文字或动作互动。", "ok");
  window.clearInterval(state.live.elapsedTimer);
  state.live.elapsedTimer = window.setInterval(tickElapsed, 1000);
  window.clearInterval(state.live.statusTimer);
  state.live.statusTimer = window.setInterval(pollStatus, 5000);
  pollStatus();
}

function tickElapsed() {
  const seconds = Math.max(0, Math.floor((Date.now() - state.live.startedAt) / 1000));
  $("#elapsed").textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

async function pollStatus() {
  if (!state.live.liveId) return;
  try {
    const data = await api(`/api/console/live/status?live_id=${encodeURIComponent(state.live.liveId)}`, {}, 20000);
    const live = data.live || {};
    if (live.status) $("#tele-status").textContent = live.status;
    if (live.billed_seconds != null) $("#tele-billed").textContent = `${live.billed_seconds}s`;
    if (live.credits_cost != null) $("#tele-credits").textContent = live.credits_cost;
    if (["ended", "ending"].includes(String(live.status))) endSession(`服务端状态 ${live.status}`);
  } catch (error) { log(`状态查询失败：${error.message}`, "warn"); }
}

async function teardown() {
  window.clearTimeout(state.live.retryTimer);
  window.clearInterval(state.live.pingTimer);
  window.clearInterval(state.live.statusTimer);
  window.clearInterval(state.live.elapsedTimer);
  const ws = state.live.ws;
  if (ws && ws.readyState === WebSocket.OPEN && state.live.liveId) {
    try { sendSocketMessage(5, { hangup: { hangup_reason: "user_end" } }); } catch {}
  }
  if (ws) { try { ws.close(); } catch {} }
  if (state.live.rtcClient?.leaveChannel) { try { await state.live.rtcClient.leaveChannel(); } catch {} }
  void flushTranscripts();
  if (state.live.liveId) {
    try { await api(`/api/console/live/status?live_id=${encodeURIComponent(state.live.liveId)}`, {}, 15000).then(showFinalBill).catch(() => {}); } catch {}
  }
  state.live.ws = null;
  state.live.rtcClient = null;
  state.live.pingTimer = null;
  state.live.statusTimer = null;
  state.live.elapsedTimer = null;
}

function showFinalBill(data) {
  const live = data?.live || {};
  if (live.billed_seconds != null) $("#tele-billed").textContent = `${live.billed_seconds}s`;
  if (live.credits_cost != null) $("#tele-credits").textContent = live.credits_cost;
  if (live.status) $("#tele-status").textContent = live.status;
}

async function endSession(reason) {
  if (state.phase === "idle" || state.live.ended) return;
  state.live.ended = true;
  log(`结束会话：${reason || "用户主动结束"}`);
  await teardown();
  resetControls();
  setPhase("ended", "已结束");
  $("#stage").classList.remove("live-connected");
  $("#mic-chip").classList.remove("mic-on");
}

function resetControls() {
  $("#start-btn").disabled = false;
  $("#start-label").textContent = "创建并连接";
  $("#hangup-btn").disabled = true;
  $("#message-input").disabled = true;
  $("#send-message-btn").disabled = true;
  $$(".command-btn").forEach((button) => { button.disabled = true; });
  $("#message-status").textContent = "接通后可发送";
  hideConnecting();
}

/* Reusable avatar assets ------------------------------------------------ */

function readAssets() {
  try {
    const value = JSON.parse(localStorage.getItem(ASSET_KEY) || "[]");
    return Array.isArray(value) ? value.filter((item) => item && typeof item === "object") : [];
  } catch { return []; }
}

function refreshAssetSelect(selectedId = "") {
  const select = $("#asset-select");
  select.replaceChildren(new Option("新建数字人资产", ""));
  readAssets().forEach((asset) => select.add(new Option(asset.label || asset.name || "未命名资产", asset.id)));
  select.value = selectedId;
  $("#delete-asset-btn").disabled = !selectedId;
}

function saveAsset() {
  const persona = $("#persona").value.trim();
  if (!persona || !state.imageUri) { toast("保存资产前请填写人设并提供形象图。", "error"); return; }
  const assets = readAssets();
  const currentId = $("#asset-select").value;
  const id = currentId || (crypto.randomUUID ? crypto.randomUUID() : `asset-${Date.now()}`);
  const name = $("#name").value.trim();
  const asset = {
    id, label: name || `数字人 ${assets.length + 1}`, name, persona, voice: $("#voice").value,
    greeting: $("#greeting").value.trim(), imageUri: state.imageUri, updatedAt: Date.now(),
  };
  const next = assets.filter((item) => item.id !== id);
  next.push(asset);
  try {
    localStorage.setItem(ASSET_KEY, JSON.stringify(next));
    refreshAssetSelect(id);
    toast(currentId ? "数字人资产已更新。" : "数字人资产已保存，可在后续会话复用。", "ok");
  } catch { toast("资产保存失败。本地图片可能过大，请改用图片 URL。", "error"); }
}

function loadAsset(id) {
  const asset = readAssets().find((item) => item.id === id);
  $("#delete-asset-btn").disabled = !asset;
  if (!asset) return;
  $("#name").value = asset.name || "";
  $("#persona").value = asset.persona || "";
  $("#voice").value = asset.voice || "";
  $("#greeting").value = asset.greeting || "";
  state.imageUri = asset.imageUri || "";
  $("#image-url").value = state.imageUri.startsWith("http") ? state.imageUri : "";
  setImagePreview(state.imageUri);
  updateCounts();
  toast("已载入数字人资产。", "ok");
}

function deleteAsset() {
  const id = $("#asset-select").value;
  if (!id) return;
  localStorage.setItem(ASSET_KEY, JSON.stringify(readAssets().filter((item) => item.id !== id)));
  refreshAssetSelect();
  toast("数字人资产已删除。");
}

/* UI binding ------------------------------------------------------------ */

function populateVoices() {
  SYSTEM_VOICES.forEach(([id, label]) => $("#voice").add(new Option(label, id)));
}

function setImagePreview(uri) {
  const preview = $("#avatar-preview");
  preview.style.backgroundImage = uri ? `url("${String(uri).replaceAll("\"", "%22")}")` : "";
  preview.classList.toggle("has-image", Boolean(uri));
}

function updateCounts() {
  $("#persona-count").textContent = String($("#persona").value.length);
  $("#greeting-count").textContent = `${$("#greeting").value.length} / 200`;
}

function toggleRetrieval(prefix) {
  $(`#${prefix}-fields`).classList.toggle("hidden", !$(`#${prefix}-enabled`).checked);
  updateCapabilityDisplay();
}

function clearTranscripts() {
  state.transcripts = [];
  state.transcriptKeys.clear();
  $("#transcript-list").replaceChildren();
  const empty = document.createElement("li");
  empty.id = "transcript-empty";
  empty.className = "empty-row";
  empty.textContent = "暂无转写";
  $("#transcript-list").append(empty);
  $("#tele-transcripts").textContent = "0";
  $("#export-transcript").disabled = true;
}

function exportTranscripts() {
  if (!state.transcripts.length) return;
  const content = state.transcripts.map((entry) => {
    const time = new Date(entry.eventAtMs).toLocaleString("zh-CN", { hour12: false });
    return `[${time}] ${entry.speaker === "user" ? "用户" : "数字人"}：${entry.text}`;
  }).join("\n");
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `vidu-s1-${state.live.liveId || "transcript"}.txt`;
  link.click();
  URL.revokeObjectURL(url);
}

function bindInputs() {
  $("#mode-switch").addEventListener("click", (event) => {
    const segment = event.target.closest(".seg");
    if (!segment) return;
    state.callMode = segment.dataset.mode;
    $$("#mode-switch .seg").forEach((item) => {
      const active = item === segment;
      item.classList.toggle("active", active);
      item.setAttribute("aria-checked", String(active));
    });
    $("#mode-chip").textContent = state.callMode === "video" ? "音视频" : "纯音频";
  });
  $("#persona").addEventListener("input", updateCounts);
  $("#greeting").addEventListener("input", updateCounts);
  $("#image-url").addEventListener("input", (event) => { state.imageUri = event.target.value.trim(); setImagePreview(state.imageUri); });
  $("#image-file").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 15 * 1024 * 1024) { toast("图片超过 15MB，请压缩后上传。", "error"); return; }
    const reader = new FileReader();
    reader.onload = () => {
      state.imageUri = String(reader.result || "");
      $("#image-url").value = "";
      setImagePreview(state.imageUri);
      log(`已载入本地形象图（${Math.round(file.size / 1024)}KB）`);
    };
    reader.onerror = () => toast("读取图片失败。", "error");
    reader.readAsDataURL(file);
  });
  ["memory", "knowledge"].forEach((prefix) => $(`#${prefix}-enabled`).addEventListener("change", () => toggleRetrieval(prefix)));
  ["#transcription-enabled", "#extra-motion-enabled", "#vad-idle"].forEach((selector) => $(selector).addEventListener("change", () => updateCapabilityDisplay()));
  $("#start-btn").addEventListener("click", startSession);
  $("#hangup-btn").addEventListener("click", () => endSession("用户主动结束"));
  $("#send-message-btn").addEventListener("click", () => { if (sendTextMessage($("#message-input").value)) $("#message-input").value = ""; });
  $("#message-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("#send-message-btn").click(); }
  });
  $$(".command-btn").forEach((button) => { button.disabled = true; button.addEventListener("click", () => sendTextMessage(button.dataset.command, "command")); });
  $("#save-asset-btn").addEventListener("click", saveAsset);
  $("#delete-asset-btn").addEventListener("click", deleteAsset);
  $("#asset-select").addEventListener("change", (event) => loadAsset(event.target.value));
  $("#clear-transcript").addEventListener("click", clearTranscripts);
  $("#export-transcript").addEventListener("click", exportTranscripts);
  $("#log-clear").addEventListener("click", () => { $("#event-log").replaceChildren(); $("#event-count").textContent = "0"; });
  window.addEventListener("beforeunload", () => { if (state.phase !== "idle") teardown(); });
}

async function boot() {
  populateVoices();
  refreshAssetSelect();
  bindInputs();
  updateCounts();
  updateCapabilityDisplay();
  resetControls();
  try {
    const config = await api("/api/config", {}, 15000);
    state.config = { ...state.config, ...config };
    if (config.vidu_configured) {
      $("#api-badge").className = "status-badge is-ready";
      $("#api-badge-text").textContent = "S1 服务就绪";
      log("后端与 Vidu S1 配置已就绪", "ok");
    } else {
      $("#api-badge").className = "status-badge is-off";
      $("#api-badge-text").textContent = "API Key 未配置";
      toast("后端未检测到 VIDU_API_KEY。", "error");
    }
  } catch (error) {
    $("#api-badge").className = "status-badge is-off";
    $("#api-badge-text").textContent = "后端不可达";
    log(`读取配置失败：${error.message}`, "error");
  }
}

document.addEventListener("DOMContentLoaded", boot);

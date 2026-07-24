(() => {
  "use strict";

  const data = window.CHAMBERS_DATA;
  if (!data || !Array.isArray(data.sequences)) {
    document.body.innerHTML = '<main style="padding:2rem;color:#fff">Unable to load the generated lifecycle data.</main>';
    return;
  }

  const SVG_NS = "http://www.w3.org/2000/svg";
  const ROLE_COLORS = {
    caller: "#ff91b2",
    host: "#ffb866",
    engine: "#64e7ef",
    control: "#a999ff",
    chamber: "#77baff",
    resource: "#75dba4",
    assurance: "#e79aff",
  };
  const ROLE_LABELS = {
    caller: "Caller / ingress",
    host: "Host boundary",
    engine: "I3 Engine",
    control: "Lifecycle control",
    chamber: "Chamber runtime",
    resource: "Custody / resource",
    assurance: "Verification / gate",
  };
  const SPEEDS = [
    { label: "0.75×", delay: 1900 },
    { label: "1×", delay: 1400 },
    { label: "1.5×", delay: 900 },
    { label: "2×", delay: 610 },
  ];

  const params = new URLSearchParams(window.location.search);
  const sequenceIds = new Set(data.sequences.map((sequence) => sequence.id));
  const functionIds = new Set(data.functions.map((fn) => fn.id));
  const requestedSequence = params.get("diagram");
  const requestedView = params.get("view");

  const state = {
    sequenceId: sequenceIds.has(requestedSequence) ? requestedSequence : data.sequences[0].id,
    view: ["trace", "map", "functions"].includes(requestedView) ? requestedView : "trace",
    callId: params.get("call"),
    callFilter: "all",
    actorFilter: "",
    zoom: 1,
    playing: false,
    timer: null,
    speedIndex: 1,
    mapFocus: null,
    functionFilter: "all",
    functionQuery: "",
    selectedFunctionId: functionIds.has(params.get("function")) ? params.get("function") : null,
    searchIndex: 0,
    toastTimer: null,
    touch: null,
  };

  const elements = Object.fromEntries(
    [
      "sourcePulseText", "journeyList", "sourceCommit", "sourceSequenceCount", "sourceCallCount",
      "sourceFunctionCount", "sourceDocumentLink", "mobileSceneSelect", "mobileSceneCount", "sceneKicker", "sceneStatus",
      "sceneTitle", "sceneSummary", "sceneQuestion", "sceneMetrics", "callFilter", "actorFilter",
      "zoomOut", "zoomIn", "zoomValue", "callNow", "currentStepNumber", "currentRoute",
      "currentFunction", "currentBranch", "sequenceViewport", "sequenceSvg", "previousCall",
      "playPause", "nextCall", "stepScrubber", "stepProgress", "stepHint", "speedButton",
      "callInspector", "mapScope", "clearMapFocus", "mapViewport", "mapSvg", "mapDetail",
      "roleLegend", "functionSearch", "functionFilter", "functionResultCount", "functionList",
      "functionDetail", "footerSource", "searchButton", "shareButton", "helpButton", "footerHelp",
      "searchDialog", "globalSearch", "searchResults", "helpDialog", "toast",
    ].map((id) => [id, document.getElementById(id)])
  );

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[character]);
  }

  function svgElement(name, attributes = {}, text = null) {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attributes).forEach(([key, value]) => {
      if (value !== null && value !== undefined) node.setAttribute(key, String(value));
    });
    if (text !== null) node.textContent = text;
    return node;
  }

  function currentSequence() {
    return data.sequences.find((sequence) => sequence.id === state.sequenceId) || data.sequences[0];
  }

  function participantMap(sequence = currentSequence()) {
    return new Map(sequence.participants.map((participant) => [participant.id, participant]));
  }

  function functionMap() {
    return new Map(data.functions.map((fn) => [fn.id, fn]));
  }

  const functionsById = functionMap();

  function visibleCalls(sequence = currentSequence()) {
    return sequence.calls.filter((call) => {
      const kindMatches = state.callFilter === "all" || call.kind === state.callFilter;
      const actorMatches = !state.actorFilter || call.from === state.actorFilter || call.to === state.actorFilter;
      return kindMatches && actorMatches;
    });
  }

  function ensureCurrentCall() {
    const calls = visibleCalls();
    if (!calls.some((call) => call.id === state.callId)) state.callId = calls[0]?.id || null;
    return calls.find((call) => call.id === state.callId) || null;
  }

  function truncate(value, length = 42) {
    const text = String(value);
    return text.length > length ? `${text.slice(0, length - 1)}…` : text;
  }

  function splitLabel(value, maxChars = 19) {
    const words = String(value).split(/\s+/);
    const lines = [];
    let line = "";
    for (const word of words) {
      const next = line ? `${line} ${word}` : word;
      if (next.length > maxChars && line) {
        lines.push(line);
        line = word;
      } else {
        line = next;
      }
    }
    if (line) lines.push(line);
    if (lines.length > 2) return [lines[0], truncate(lines.slice(1).join(" "), maxChars + 4)];
    return lines;
  }

  function updateUrl() {
    const next = new URL(window.location.href);
    next.searchParams.set("diagram", state.sequenceId);
    if (state.view === "trace") next.searchParams.delete("view");
    else next.searchParams.set("view", state.view);
    if (state.callId) next.searchParams.set("call", state.callId);
    else next.searchParams.delete("call");
    if (state.view === "functions" && state.selectedFunctionId) next.searchParams.set("function", state.selectedFunctionId);
    else next.searchParams.delete("function");
    window.history.replaceState({}, "", next);
  }

  function toast(message) {
    window.clearTimeout(state.toastTimer);
    elements.toast.textContent = message;
    elements.toast.classList.add("is-visible");
    state.toastTimer = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 2300);
  }

  function populateStaticChrome() {
    const source = data.source;
    const commit = source.sourceCommit.slice(0, 12);
    elements.sourcePulseText.textContent = `${commit} · exact snapshot`;
    elements.sourceCommit.textContent = commit;
    elements.sourceSequenceCount.textContent = data.stats.sequences;
    elements.sourceCallCount.textContent = data.stats.calls;
    elements.sourceFunctionCount.textContent = data.stats.functions;
    elements.sourceDocumentLink.href = source.url;
    elements.sourceDocumentLink.title = `Open ${source.path} at ${commit}`;
    elements.mobileSceneCount.textContent = `${data.stats.sequences} views`;
    elements.footerSource.href = source.url;
    elements.footerSource.textContent = `${source.repository} · ${commit} · open source ↗`;

    elements.journeyList.innerHTML = data.sequences.map((sequence, index) => `
      <button class="journey-item${sequence.id === state.sequenceId ? " is-active" : ""}" type="button" data-sequence-id="${escapeHtml(sequence.id)}" aria-current="${sequence.id === state.sequenceId ? "page" : "false"}">
        <span class="journey-number">${String(index + 1).padStart(2, "0")}</span>
        <span class="journey-name"><span>${escapeHtml(sequence.shortTitle)}</span><small>${sequence.stats.actors} actors · ${sequence.stats.calls} calls</small></span>
        ${sequence.status === "later" ? '<i class="journey-later" title="Later mode"></i>' : ""}
      </button>
    `).join("");

    elements.mobileSceneSelect.innerHTML = data.sequences.map((sequence, index) => `
      <option value="${escapeHtml(sequence.id)}">${String(index + 1).padStart(2, "0")} · ${escapeHtml(sequence.shortTitle)}</option>
    `).join("");
    elements.mobileSceneSelect.value = state.sequenceId;

    const roles = [...new Set(data.sequences.flatMap((sequence) => sequence.participants.map((participant) => participant.role)))];
    elements.roleLegend.innerHTML = roles.map((role) => `
      <span><i style="background:${ROLE_COLORS[role]}"></i>${escapeHtml(ROLE_LABELS[role])}</span>
    `).join("");
  }

  function renderSceneHeader() {
    const sequence = currentSequence();
    elements.sceneKicker.textContent = sequence.kicker;
    elements.sceneStatus.textContent = sequence.status === "later" ? "Later" : sequence.status === "core" ? "Shared kernel" : "Current design";
    elements.sceneStatus.className = `status-pill${sequence.status === "later" ? " is-later" : sequence.status === "core" ? " is-core" : ""}`;
    elements.sceneTitle.textContent = sequence.shortTitle;
    elements.sceneSummary.textContent = sequence.summary;
    elements.sceneQuestion.textContent = sequence.question;
    elements.sceneMetrics.innerHTML = [
      [sequence.stats.actors, "Actors"],
      [sequence.stats.calls, "Calls"],
      [sequence.stats.branches, "Branches"],
      [sequence.stats.hostCalls, "Host calls"],
    ].map(([value, label]) => `<div class="metric"><strong>${value}</strong><span>${label}</span></div>`).join("");
    document.title = `${sequence.shortTitle} · Chambers Atlas`;
  }

  function renderActorFilter() {
    const sequence = currentSequence();
    if (state.actorFilter && !sequence.participants.some((participant) => participant.id === state.actorFilter)) state.actorFilter = "";
    elements.actorFilter.innerHTML = '<option value="">Every actor</option>' + sequence.participants.map((participant) => (
      `<option value="${escapeHtml(participant.id)}">${escapeHtml(participant.label)}</option>`
    )).join("");
    elements.actorFilter.value = state.actorFilter;
  }

  function updateJourneySelection() {
    elements.journeyList.querySelectorAll(".journey-item").forEach((button) => {
      const active = button.dataset.sequenceId === state.sequenceId;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-current", active ? "page" : "false");
    });
    elements.mobileSceneSelect.value = state.sequenceId;
  }

  function renderTrace(options = {}) {
    const call = ensureCurrentCall();
    renderSequenceSvg();
    renderCallNow(call);
    renderCallInspector(call);
    updatePlayback(call);
    updateUrl();
    if (call && options.scroll !== false) window.requestAnimationFrame(() => scrollCallIntoView(call.id, options.smooth !== false));
  }

  function renderSequenceSvg() {
    const sequence = currentSequence();
    const actors = sequence.participants;
    const calls = sequence.calls;
    const visibleIds = new Set(visibleCalls(sequence).map((call) => call.id));
    const current = calls.find((call) => call.id === state.callId);
    const currentIndex = current?.index ?? -1;
    const laneWidth = actors.length <= 4 ? 220 : actors.length <= 6 ? 190 : 174;
    const left = 54;
    const right = 54;
    const headerHeight = 94;
    const rowHeight = 74;
    const width = Math.max(760, left + right + actors.length * laneWidth);
    const height = headerHeight + calls.length * rowHeight + 52;
    const positions = new Map(actors.map((actor, index) => [actor.id, left + laneWidth * index + laneWidth / 2]));

    elements.sequenceSvg.replaceChildren();
    elements.sequenceSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    elements.sequenceSvg.setAttribute("width", String(Math.round(width * state.zoom)));
    elements.sequenceSvg.setAttribute("height", String(Math.round(height * state.zoom)));
    elements.sequenceSvg.style.width = `${Math.round(width * state.zoom)}px`;
    elements.sequenceSvg.style.height = `${Math.round(height * state.zoom)}px`;

    const title = svgElement("title", { id: "sequenceSvgTitle" }, `${sequence.shortTitle} sequence diagram`);
    const desc = svgElement("desc", { id: "sequenceSvgDesc" }, `${actors.length} actors and ${calls.length} calls. Select a call for its function contract.`);
    elements.sequenceSvg.append(title, desc, createSequenceDefs());

    actors.forEach((actor) => {
      const x = positions.get(actor.id);
      const focused = state.actorFilter === actor.id;
      const dim = Boolean(state.actorFilter && !focused);
      elements.sequenceSvg.appendChild(svgElement("line", {
        x1: x, y1: 74, x2: x, y2: height - 28,
        class: `sequence-lane${focused ? " is-focused" : ""}`,
      }));

      const group = svgElement("g", {
        class: `svg-actor${focused ? " is-focused" : ""}${dim ? " is-dim" : ""}`,
        role: "button", tabindex: "0", "aria-label": `${actor.label} ${actor.role.replace("assurance", "gate")}. Focus actor.`,
      });
      const rect = svgElement("rect", { x: x - 72, y: 14, width: 144, height: 52, rx: 13 });
      rect.style.stroke = ROLE_COLORS[actor.role];
      rect.style.strokeOpacity = focused ? "0.9" : "0.36";
      group.appendChild(rect);
      group.appendChild(svgElement("rect", {
        x: x - 51, y: 14, width: 102, height: 2, rx: 2, class: "actor-accent", fill: ROLE_COLORS[actor.role], opacity: 0.82,
      }));
      const lines = splitLabel(actor.label);
      const text = svgElement("text", { x, y: lines.length === 1 ? 38 : 33 });
      lines.forEach((line, lineIndex) => text.appendChild(svgElement("tspan", { x, dy: lineIndex ? 12 : 0 }, line)));
      group.appendChild(text);
      group.appendChild(svgElement("text", { x, y: 57, class: "actor-role-label" }, actor.role.replace("assurance", "gate")));
      group.addEventListener("click", () => setActorFilter(state.actorFilter === actor.id ? "" : actor.id));
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          setActorFilter(state.actorFilter === actor.id ? "" : actor.id);
        }
      });
      elements.sequenceSvg.appendChild(group);
    });

    calls.forEach((call) => {
      const y = headerHeight + call.index * rowHeight + rowHeight / 2;
      const x1 = positions.get(call.from);
      const x2 = positions.get(call.to);
      const direction = x2 >= x1 ? 1 : -1;
      const start = x1 + direction * 8;
      const end = x2 - direction * 13;
      const rawMid = (x1 + x2) / 2;
      const pillWidth = Math.min(290, Math.max(132, call.function.length * 6.25 + 28));
      const labelMid = Math.max(pillWidth / 2 + 38, Math.min(width - pillWidth / 2 - 32, rawMid));
      const isVisible = visibleIds.has(call.id);
      const isCurrent = call.id === state.callId;
      const isPast = currentIndex >= 0 && call.index < currentIndex;
      const branch = call.context.map((context) => context.branch).filter(Boolean).join(" / ");
      const visibleKind = call.kind === "i3" ? "I3" : "HOST BOUNDARY";
      const group = svgElement("g", {
        class: `call-row ${call.kind}${call.kind === "host" ? " is-host" : ""}${isCurrent ? " is-current" : ""}${!isVisible ? " is-dim" : ""}${isPast ? " is-past" : ""}`,
        "data-call-id": call.id,
        role: "button", tabindex: isVisible ? "0" : "-1",
        "aria-label": `${String(call.index + 1).padStart(2, "0")} ${call.function} ${visibleKind}${branch ? ` ↳ ${truncate(branch, 52)}` : ""}. Step ${call.index + 1}, ${call.from} to ${call.to}.`,
      });
      group.appendChild(svgElement("rect", { x: 5, y: y - 33, width: width - 10, height: 66, rx: 12, class: "row-hit" }));
      group.appendChild(svgElement("rect", { x: 8, y: y - 31, width: width - 16, height: 62, rx: 12, class: "row-focus" }));
      group.appendChild(svgElement("text", { x: 23, y: y + 3, class: "step-number" }, String(call.index + 1).padStart(2, "0")));
      group.appendChild(svgElement("circle", { cx: start, cy: y, r: 3.6, class: `endpoint ${call.kind}` }));
      group.appendChild(svgElement("line", {
        x1: start, y1: y, x2: end, y2: y, class: `call-line ${call.kind}`,
        "marker-end": `url(#sequence-arrow-${call.kind})`,
      }));
      group.appendChild(svgElement("rect", {
        x: labelMid - pillWidth / 2, y: y - 24, width: pillWidth, height: 25, rx: 8, class: "call-pill",
      }));
      group.appendChild(svgElement("text", { x: labelMid, y: y - 8, class: "call-text" }, call.function));
      group.appendChild(svgElement("text", {
        x: labelMid, y: y + 18, class: "svg-kind", fill: call.kind === "i3" ? "#64e7ef" : "#ffb866",
      }, call.kind === "i3" ? "I3" : "HOST BOUNDARY"));
      if (branch) group.appendChild(svgElement("text", { x: 42, y: y + 24, class: "svg-branch" }, `↳ ${truncate(branch, 52)}`));

      group.addEventListener("click", () => isVisible && setCurrentCall(call.id));
      group.addEventListener("keydown", (event) => {
        if (isVisible && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          setCurrentCall(call.id);
        }
      });
      elements.sequenceSvg.appendChild(group);
    });
  }

  function createSequenceDefs() {
    const defs = svgElement("defs");
    [
      ["i3", "#64e7ef"],
      ["host", "#ffb866"],
    ].forEach(([kind, color]) => {
      const marker = svgElement("marker", {
        id: `sequence-arrow-${kind}`, viewBox: "0 0 10 10", refX: "8", refY: "5",
        markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse",
      });
      marker.appendChild(svgElement("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: color }));
      defs.appendChild(marker);
    });
    return defs;
  }

  function renderCallNow(call) {
    const sequence = currentSequence();
    const calls = visibleCalls(sequence);
    const actors = participantMap(sequence);
    const index = call ? calls.findIndex((item) => item.id === call.id) : -1;
    const controls = [elements.previousCall, elements.nextCall, elements.playPause, elements.stepScrubber];

    if (!call) {
      elements.callNow.className = "call-now";
      elements.currentStepNumber.textContent = "—";
      elements.currentRoute.textContent = "No calls match this filter";
      elements.currentFunction.textContent = "Adjust ‘Show’ or actor focus";
      elements.currentBranch.replaceChildren();
      controls.forEach((control) => { control.disabled = true; });
      return;
    }

    elements.callNow.className = `call-now${call.kind === "host" ? " is-host" : ""}`;
    elements.currentStepNumber.textContent = `${String(index + 1).padStart(2, "0")}/${String(calls.length).padStart(2, "0")}`;
    elements.currentRoute.textContent = `${actors.get(call.from).label} → ${actors.get(call.to).label}`;
    elements.currentFunction.textContent = call.function;
    elements.currentBranch.innerHTML = call.context.map((context) => `<span class="branch-chip" title="${escapeHtml(context.label)}">${escapeHtml(context.type)} · ${escapeHtml(context.branch)}</span>`).join("");
    controls.forEach((control) => { control.disabled = false; });
  }

  function renderCallInspector(call) {
    if (!call) {
      elements.callInspector.className = "inspector-card";
      elements.callInspector.innerHTML = '<div class="inspector-empty">No calls match the current filter.</div>';
      return;
    }
    const sequence = currentSequence();
    const actors = participantMap(sequence);
    const fn = functionsById.get(call.function);
    const contextItems = [
      ...call.context.map((context) => `<li><strong>${escapeHtml(context.type)}</strong> · ${escapeHtml(context.branch)}</li>`),
      ...call.notes.map((note) => `<li>${escapeHtml(note.text)}</li>`),
    ];
    elements.callInspector.className = `inspector-card${call.kind === "host" ? " is-host" : ""}`;
    elements.callInspector.innerHTML = `
      <div class="inspector-type-row">
        <span class="kind-badge ${call.kind}"><i class="legend-dot ${call.kind}"></i>${call.kind === "i3" ? "I3 function" : "Host boundary code"}</span>
        <span class="inspector-step">${String(call.index + 1).padStart(2, "0")} / ${String(sequence.calls.length).padStart(2, "0")}</span>
      </div>
      <h2 class="inspector-function">${escapeHtml(call.function)}</h2>
      <div class="inspector-route">
        <span class="route-node">${escapeHtml(actors.get(call.from).label)}</span>
        <span class="route-arrow">→</span>
        <span class="route-node">${escapeHtml(actors.get(call.to).label)}</span>
      </div>
      <div class="function-meta">
        <span class="owner-badge">Owner · ${escapeHtml(fn.owner)}</span>
        <span class="usage-badge">${fn.usages.length} usage${fn.usages.length === 1 ? "" : "s"}</span>
        ${fn.later ? '<span class="owner-badge">Later</span>' : ""}
      </div>
      <div class="contract-block">
        <h3>Critical contract</h3>
        <p>${escapeHtml(fn.contract)}</p>
      </div>
      ${contextItems.length ? `<div class="context-block"><h3>Context at this step</h3><ul class="context-list">${contextItems.join("")}</ul></div>` : ""}
      <div class="inspector-actions">
        <button class="quiet-button" type="button" id="mapThisPair">Map this pair</button>
        <button class="quiet-button" type="button" id="openThisFunction">Open function</button>
      </div>
    `;
    document.getElementById("mapThisPair")?.addEventListener("click", () => {
      state.mapFocus = { type: "edge", key: `${call.from}→${call.to}` };
      setView("map");
    });
    document.getElementById("openThisFunction")?.addEventListener("click", () => openFunction(call.function));
  }

  function updatePlayback(call) {
    const calls = visibleCalls();
    const index = call ? calls.findIndex((item) => item.id === call.id) : 0;
    elements.stepScrubber.max = String(Math.max(0, calls.length - 1));
    elements.stepScrubber.value = String(Math.max(0, index));
    elements.stepProgress.textContent = calls.length ? `${index + 1} / ${calls.length}` : "0 / 0";
    elements.previousCall.disabled = !calls.length || index <= 0;
    elements.nextCall.disabled = !calls.length || index >= calls.length - 1;
    elements.playPause.disabled = !calls.length;
    elements.playPause.classList.toggle("is-playing", state.playing);
    elements.playPause.setAttribute("aria-label", state.playing ? "Pause sequence" : "Play sequence");
    elements.speedButton.querySelector("strong").textContent = SPEEDS[state.speedIndex].label;
    elements.speedButton.setAttribute("aria-label", `Speed ${SPEEDS[state.speedIndex].label} · playback speed`);
  }

  function scrollCallIntoView(callId, smooth = true) {
    const row = elements.sequenceSvg.querySelector(`[data-call-id="${CSS.escape(callId)}"]`);
    if (!row) return;
    const sequence = currentSequence();
    const call = sequence.calls.find((item) => item.id === callId);
    const actors = participantMap(sequence);
    const actorIndex = sequence.participants.findIndex((participant) => participant.id === call.from);
    const actorIndexTo = sequence.participants.findIndex((participant) => participant.id === call.to);
    const laneWidth = sequence.participants.length <= 4 ? 220 : sequence.participants.length <= 6 ? 190 : 174;
    const centerX = (54 + laneWidth * actorIndex + laneWidth / 2 + 54 + laneWidth * actorIndexTo + laneWidth / 2) / 2;
    const centerY = 94 + call.index * 74 + 37;
    const left = Math.max(0, centerX * state.zoom - elements.sequenceViewport.clientWidth / 2);
    const top = Math.max(0, centerY * state.zoom - elements.sequenceViewport.clientHeight / 2);
    elements.sequenceViewport.scrollTo({ left, top, behavior: smooth ? "smooth" : "auto" });
  }

  function setCurrentCall(callId, options = {}) {
    if (!currentSequence().calls.some((call) => call.id === callId)) return;
    state.callId = callId;
    renderTrace({ scroll: options.scroll !== false, smooth: options.smooth !== false });
  }

  function stepCall(direction) {
    const calls = visibleCalls();
    if (!calls.length) return;
    const currentIndex = Math.max(0, calls.findIndex((call) => call.id === state.callId));
    const nextIndex = Math.max(0, Math.min(calls.length - 1, currentIndex + direction));
    if (nextIndex === currentIndex && state.playing) stopPlayback();
    setCurrentCall(calls[nextIndex].id);
  }

  function startPlayback() {
    const calls = visibleCalls();
    if (!calls.length) return;
    const index = calls.findIndex((call) => call.id === state.callId);
    if (index === calls.length - 1) state.callId = calls[0].id;
    state.playing = true;
    updatePlayback(ensureCurrentCall());
    window.clearInterval(state.timer);
    state.timer = window.setInterval(() => {
      const activeCalls = visibleCalls();
      const activeIndex = activeCalls.findIndex((call) => call.id === state.callId);
      if (activeIndex < 0 || activeIndex >= activeCalls.length - 1) {
        stopPlayback();
        return;
      }
      setCurrentCall(activeCalls[activeIndex + 1].id);
    }, SPEEDS[state.speedIndex].delay);
  }

  function stopPlayback() {
    window.clearInterval(state.timer);
    state.timer = null;
    state.playing = false;
    updatePlayback(ensureCurrentCall());
  }

  function togglePlayback() {
    if (state.playing) stopPlayback();
    else startPlayback();
  }

  function setCallFilter(filter) {
    stopPlayback();
    state.callFilter = filter;
    elements.callFilter.querySelectorAll("button").forEach((button) => {
      const active = button.dataset.filter === filter;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    state.callId = visibleCalls()[0]?.id || null;
    renderTrace({ smooth: false });
  }

  function setActorFilter(actorId) {
    stopPlayback();
    state.actorFilter = actorId;
    elements.actorFilter.value = actorId;
    state.callId = visibleCalls()[0]?.id || null;
    renderTrace({ smooth: false });
  }

  function setZoom(nextZoom) {
    state.zoom = Math.max(0.7, Math.min(1.3, Math.round(nextZoom * 10) / 10));
    elements.zoomValue.textContent = `${Math.round(state.zoom * 100)}%`;
    elements.zoomOut.disabled = state.zoom <= 0.7;
    elements.zoomIn.disabled = state.zoom >= 1.3;
    renderTrace({ scroll: false });
  }

  function setSequence(sequenceId) {
    if (!sequenceIds.has(sequenceId) || sequenceId === state.sequenceId) return;
    stopPlayback();
    state.sequenceId = sequenceId;
    state.callFilter = "all";
    state.actorFilter = "";
    state.mapFocus = null;
    state.callId = currentSequence().calls[0]?.id || null;
    updateJourneySelection();
    renderSceneHeader();
    renderActorFilter();
    elements.callFilter.querySelectorAll("button").forEach((button) => {
      const active = button.dataset.filter === "all";
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    if (state.view === "trace") renderTrace({ smooth: false });
    else if (state.view === "map") renderMap();
    else renderFunctionCatalog();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function setView(view) {
    if (!["trace", "map", "functions"].includes(view)) return;
    stopPlayback();
    state.view = view;
    document.querySelectorAll(".view-tab").forEach((button) => {
      const active = button.dataset.view === view;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    document.querySelectorAll("[data-view-panel]").forEach((panel) => {
      const active = panel.dataset.viewPanel === view;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
    if (view === "trace") renderTrace({ scroll: false });
    else if (view === "map") renderMap();
    else if (view === "functions") {
      if (!state.selectedFunctionId) state.selectedFunctionId = ensureCurrentCall()?.function || data.functions[0].id;
      renderFunctionCatalog();
    }
    updateUrl();
  }

  function groupMapEdges(sequence) {
    const edges = new Map();
    sequence.calls.forEach((call) => {
      const key = `${call.from}→${call.to}`;
      if (!edges.has(key)) edges.set(key, { key, from: call.from, to: call.to, calls: [] });
      edges.get(key).calls.push(call);
    });
    return [...edges.values()];
  }

  function renderMap() {
    const sequence = currentSequence();
    const actors = sequence.participants;
    const actorById = participantMap(sequence);
    const edges = groupMapEdges(sequence);
    const width = 1000;
    const height = 640;
    const center = { x: width / 2, y: height / 2 + 5 };
    const radiusX = actors.length <= 4 ? 310 : 355;
    const radiusY = actors.length <= 4 ? 205 : 245;
    const positions = new Map();
    actors.forEach((actor, index) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / actors.length;
      positions.set(actor.id, {
        x: center.x + Math.cos(angle) * radiusX,
        y: center.y + Math.sin(angle) * radiusY,
      });
    });

    elements.mapSvg.replaceChildren();
    elements.mapSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    elements.mapSvg.setAttribute("width", String(width));
    elements.mapSvg.setAttribute("height", String(height));
    elements.mapSvg.append(
      svgElement("title", { id: "mapSvgTitle" }, `${sequence.shortTitle} actor relationship map`),
      svgElement("desc", { id: "mapSvgDesc" }, `${actors.length} actors connected by ${edges.length} directed relationships.`),
      createMapDefs()
    );

    const edgeKeys = new Set(edges.map((edge) => edge.key));
    edges.forEach((edge) => {
      const p1 = positions.get(edge.from);
      const p2 = positions.get(edge.to);
      const dx = p2.x - p1.x;
      const dy = p2.y - p1.y;
      const length = Math.hypot(dx, dy) || 1;
      const ux = dx / length;
      const uy = dy / length;
      const start = { x: p1.x + ux * 84, y: p1.y + uy * 42 };
      const end = { x: p2.x - ux * 88, y: p2.y - uy * 44 };
      const reverseExists = edgeKeys.has(`${edge.to}→${edge.from}`);
      const directionSign = edge.from.localeCompare(edge.to) < 0 ? 1 : -1;
      const curve = reverseExists ? 42 * directionSign : Math.min(18, length * 0.04);
      const control = {
        x: (start.x + end.x) / 2 - uy * curve,
        y: (start.y + end.y) / 2 + ux * curve,
      };
      const path = `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`;
      const kinds = new Set(edge.calls.map((call) => call.kind));
      const kind = kinds.size > 1 ? "mixed" : edge.calls[0].kind;
      const focused = state.mapFocus?.type === "edge" && state.mapFocus.key === edge.key;
      const actorFocused = state.mapFocus?.type === "actor" && (state.mapFocus.id === edge.from || state.mapFocus.id === edge.to);
      const hasFocus = Boolean(state.mapFocus);
      const dim = hasFocus && !focused && !actorFocused;
      const group = svgElement("g", {
        class: "map-edge-group",
        "data-edge-key": edge.key,
        tabindex: "0",
        role: "button",
        "aria-label": `${actorById.get(edge.from).label} to ${actorById.get(edge.to).label}: ${edge.calls.length} calls`,
      });
      group.appendChild(svgElement("path", {
        d: path,
        class: `map-edge ${kind === "mixed" ? "is-mixed" : kind}${focused || actorFocused ? " is-focused" : ""}${dim ? " is-dim" : ""}`,
        "stroke-width": Math.min(5.4, 1.4 + edge.calls.length * 0.65),
        "marker-end": `url(#map-arrow-${kind === "host" ? "host" : kind === "mixed" ? "mixed" : "i3"})`,
      }));
      const hit = svgElement("path", { d: path, class: "map-edge-hit" });
      group.addEventListener("click", () => setMapFocus({ type: "edge", key: edge.key }));
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setMapFocus({ type: "edge", key: edge.key }); }
      });
      group.appendChild(hit);
      const labelPoint = quadraticPoint(start, control, end, 0.5);
      const count = svgElement("g", { class: "map-count", transform: `translate(${labelPoint.x} ${labelPoint.y})` });
      count.append(svgElement("circle", { r: 11 }), svgElement("text", { y: 0.5 }, String(edge.calls.length)));
      group.appendChild(count);
      elements.mapSvg.appendChild(group);
    });

    const incidentCounts = new Map(actors.map((actor) => [actor.id, sequence.calls.filter((call) => call.from === actor.id || call.to === actor.id).length]));
    actors.forEach((actor) => {
      const position = positions.get(actor.id);
      const focused = state.mapFocus?.type === "actor" && state.mapFocus.id === actor.id;
      const edgeFocused = state.mapFocus?.type === "edge" && state.mapFocus.key.split("→").includes(actor.id);
      const dim = Boolean(state.mapFocus && !focused && !edgeFocused);
      const group = svgElement("g", {
        class: `map-node${focused || edgeFocused ? " is-focused" : ""}${dim ? " is-dim" : ""}`,
        transform: `translate(${position.x} ${position.y})`, role: "button", tabindex: "0",
        "aria-label": `${actor.label} ${actor.role.toUpperCase()} ${incidentCounts.get(actor.id)} calls. Focus actor.`,
      });
      group.appendChild(svgElement("rect", { x: -80, y: -36, width: 160, height: 72, rx: 15, stroke: ROLE_COLORS[actor.role] }));
      group.appendChild(svgElement("rect", { x: -42, y: -36, width: 84, height: 2.5, rx: 2, fill: ROLE_COLORS[actor.role] }));
      const lines = splitLabel(actor.label, 20);
      const label = svgElement("text", { x: 0, y: lines.length === 1 ? -3 : -10 });
      lines.forEach((line, index) => label.appendChild(svgElement("tspan", { x: 0, dy: index ? 13 : 0 }, line)));
      group.append(label);
      group.appendChild(svgElement("text", { x: 0, y: 19, class: "map-role" }, actor.role.toUpperCase()));
      group.appendChild(svgElement("text", { x: 0, y: 31, class: "map-activity" }, `${incidentCounts.get(actor.id)} calls`));
      group.addEventListener("click", () => setMapFocus({ type: "actor", id: actor.id }));
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setMapFocus({ type: "actor", id: actor.id }); }
      });
      elements.mapSvg.appendChild(group);
    });

    renderMapDetail(edges);
  }

  function createMapDefs() {
    const defs = svgElement("defs");
    [["i3", "#64e7ef"], ["host", "#ffb866"], ["mixed", "#a999ff"]].forEach(([kind, color]) => {
      const marker = svgElement("marker", { id: `map-arrow-${kind}`, viewBox: "0 0 10 10", refX: "8", refY: "5", markerWidth: "6", markerHeight: "6", orient: "auto" });
      marker.appendChild(svgElement("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: color }));
      defs.appendChild(marker);
    });
    return defs;
  }

  function quadraticPoint(start, control, end, t) {
    const inverse = 1 - t;
    return {
      x: inverse * inverse * start.x + 2 * inverse * t * control.x + t * t * end.x,
      y: inverse * inverse * start.y + 2 * inverse * t * control.y + t * t * end.y,
    };
  }

  function setMapFocus(focus) {
    if (state.mapFocus && JSON.stringify(state.mapFocus) === JSON.stringify(focus)) state.mapFocus = null;
    else state.mapFocus = focus;
    renderMap();
  }

  function renderMapDetail(edges) {
    const sequence = currentSequence();
    const actors = participantMap(sequence);
    if (!state.mapFocus) {
      elements.mapScope.textContent = "All actors · all calls";
      elements.mapDetail.innerHTML = `
        <span class="kind-badge"><i class="legend-dot i3"></i>Sequence surface</span>
        <h3>${sequence.stats.actors} actors · ${edges.length} relationships</h3>
        <p>Select any actor to see its incoming and outgoing functions, or select a line to inspect every call on that connection.</p>
        <div class="contract-block"><h3>Reading the map</h3><p>Direction follows the arrow. Thicker lines carry more calls. Cyan is I3, amber is host-boundary code, and violet is a mixed connection.</p></div>
      `;
      return;
    }

    if (state.mapFocus.type === "edge") {
      const edge = edges.find((item) => item.key === state.mapFocus.key);
      if (!edge) { state.mapFocus = null; renderMapDetail(edges); return; }
      const from = actors.get(edge.from);
      const to = actors.get(edge.to);
      elements.mapScope.textContent = `${from.label} → ${to.label}`;
      elements.mapDetail.innerHTML = `
        <span class="kind-badge"><i class="legend-dot i3"></i>Directed relationship</span>
        <h3>${escapeHtml(from.label)} → ${escapeHtml(to.label)}</h3>
        <p>${edge.calls.length} call${edge.calls.length === 1 ? "" : "s"} in this sequence. Open one at its exact playback step.</p>
        <div class="map-call-list">
          ${edge.calls.map((call) => `<button class="map-call-button" type="button" data-open-call="${escapeHtml(call.id)}"><i style="background:${call.kind === "i3" ? "var(--i3)" : "var(--host)"}"></i><code>${escapeHtml(call.function)}</code><span>#${call.index + 1}</span></button>`).join("")}
        </div>
      `;
    } else {
      const actor = actors.get(state.mapFocus.id);
      if (!actor) { state.mapFocus = null; renderMapDetail(edges); return; }
      const related = sequence.calls.filter((call) => call.from === actor.id || call.to === actor.id);
      const outgoing = related.filter((call) => call.from === actor.id).length;
      const incoming = related.length - outgoing;
      elements.mapScope.textContent = actor.label;
      elements.mapDetail.innerHTML = `
        <span class="kind-badge" style="color:${ROLE_COLORS[actor.role]};border-color:${ROLE_COLORS[actor.role]}55;background:${ROLE_COLORS[actor.role]}12">${escapeHtml(ROLE_LABELS[actor.role])}</span>
        <h3>${escapeHtml(actor.label)}</h3>
        <p>${outgoing} outgoing · ${incoming} incoming. Open any interaction in Trace.</p>
        <div class="map-call-list">
          ${related.map((call) => {
            const other = call.from === actor.id ? actors.get(call.to).label : actors.get(call.from).label;
            const direction = call.from === actor.id ? "→" : "←";
            return `<button class="map-call-button" type="button" data-open-call="${escapeHtml(call.id)}"><i style="background:${call.kind === "i3" ? "var(--i3)" : "var(--host)"}"></i><code>${escapeHtml(call.function)}</code><span>${direction} ${escapeHtml(truncate(other, 14))}</span></button>`;
          }).join("")}
        </div>
      `;
    }
    elements.mapDetail.querySelectorAll("[data-open-call]").forEach((button) => button.addEventListener("click", () => openCall(button.dataset.openCall)));
  }

  function renderFunctionCatalog() {
    const query = state.functionQuery.trim().toLowerCase();
    const filtered = data.functions.filter((fn) => {
      const kindMatch = state.functionFilter === "all" || fn.kind === state.functionFilter || (state.functionFilter === "unused" && !fn.usages.length);
      if (!kindMatch) return false;
      if (!query) return true;
      return `${fn.id} ${fn.owner} ${fn.contract} ${fn.path}`.toLowerCase().includes(query);
    });
    if (!filtered.some((fn) => fn.id === state.selectedFunctionId)) state.selectedFunctionId = filtered[0]?.id || null;
    elements.functionResultCount.textContent = `${filtered.length} of ${data.functions.length} functions`;
    elements.functionList.innerHTML = filtered.length ? filtered.map((fn) => `
      <button class="function-card ${fn.kind}${fn.id === state.selectedFunctionId ? " is-selected" : ""}" type="button" role="listitem" data-function-id="${escapeHtml(fn.id)}">
        <span class="function-card-top"><span class="kind-badge ${fn.kind}"><i class="legend-dot ${fn.kind}"></i>${fn.kind === "i3" ? "I3" : "Host"}</span><span class="usage-badge">${fn.usages.length}×</span></span>
        <code>${escapeHtml(fn.id)}</code>
        <p>${escapeHtml(fn.contract)}</p>
        <span class="function-card-foot"><span>${escapeHtml(fn.owner)}</span><span>${fn.later ? "Later" : fn.usages.length ? "Pictured" : "Not pictured"}</span></span>
      </button>
    `).join("") : '<div class="empty-results">No function matches those filters.</div>';
    elements.functionList.querySelectorAll("[data-function-id]").forEach((button) => button.addEventListener("click", () => {
      state.selectedFunctionId = button.dataset.functionId;
      renderFunctionCatalog();
      updateUrl();
    }));
    renderFunctionDetail();
  }

  function renderFunctionDetail() {
    const fn = functionsById.get(state.selectedFunctionId);
    if (!fn) {
      elements.functionDetail.innerHTML = '<div class="inspector-empty">Choose a function to inspect its contract.</div>';
      return;
    }
    elements.functionDetail.className = `function-detail inspector-card${fn.kind === "host" ? " is-host" : ""}`;
    elements.functionDetail.innerHTML = `
      <div class="inspector-type-row">
        <span class="kind-badge ${fn.kind}"><i class="legend-dot ${fn.kind}"></i>${fn.kind === "i3" ? "I3 function" : "Host boundary code"}</span>
        <span class="usage-badge">${fn.usages.length} usage${fn.usages.length === 1 ? "" : "s"}</span>
      </div>
      <h2 class="inspector-function">${escapeHtml(fn.id)}</h2>
      <div class="function-meta"><span class="owner-badge">${escapeHtml(fn.owner)}</span><span class="owner-badge">${escapeHtml(fn.path)}</span>${fn.later ? '<span class="owner-badge">Optional later</span>' : ""}</div>
      <div class="contract-block"><h3>Critical contract</h3><p>${escapeHtml(fn.contract)}</p></div>
      <div class="context-block">
        <h3>${fn.usages.length ? "Diagram usages" : "Diagram coverage"}</h3>
        ${fn.usages.length ? `<div class="usage-list">${fn.usages.map((usage) => `<button class="usage-link" type="button" data-usage-diagram="${escapeHtml(usage.diagramId)}" data-usage-call="${escapeHtml(usage.callId)}"><strong>#${usage.step}</strong><span>${escapeHtml(usage.diagramTitle)} · ${escapeHtml(usage.from)} → ${escapeHtml(usage.to)}</span><small>open</small></button>`).join("")}</div>` : '<p style="margin-top:9px;color:var(--muted);font-size:.68rem;line-height:1.5">Defined in the function table, but not used by a sequence arrow in this source snapshot.</p>'}
      </div>
    `;
    elements.functionDetail.querySelectorAll("[data-usage-call]").forEach((button) => button.addEventListener("click", () => {
      setSequenceAndCall(button.dataset.usageDiagram, button.dataset.usageCall);
    }));
  }

  function openFunction(functionId) {
    if (!functionIds.has(functionId)) return;
    state.selectedFunctionId = functionId;
    state.functionQuery = "";
    state.functionFilter = "all";
    elements.functionSearch.value = "";
    syncFunctionFilterButtons();
    setView("functions");
    renderFunctionCatalog();
  }

  function openCall(callId) {
    if (!currentSequence().calls.some((call) => call.id === callId)) return;
    state.callFilter = "all";
    state.actorFilter = "";
    state.callId = callId;
    elements.actorFilter.value = "";
    elements.callFilter.querySelectorAll("button").forEach((button) => {
      const active = button.dataset.filter === "all";
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    setView("trace");
    renderTrace();
  }

  function setSequenceAndCall(sequenceId, callId) {
    if (sequenceId !== state.sequenceId) {
      setSequence(sequenceId);
    }
    openCall(callId);
  }

  function syncFunctionFilterButtons() {
    elements.functionFilter.querySelectorAll("button").forEach((button) => {
      const active = button.dataset.functionFilter === state.functionFilter;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function renderGlobalSearch() {
    const query = elements.globalSearch.value.trim().toLowerCase();
    const sequenceResults = data.sequences.filter((sequence) => !query || `${sequence.shortTitle} ${sequence.summary} ${sequence.question}`.toLowerCase().includes(query));
    const functions = [...data.functions].sort((a, b) => b.usages.length - a.usages.length || a.id.localeCompare(b.id));
    const functionResults = functions.filter((fn) => !query || `${fn.id} ${fn.owner} ${fn.contract}`.toLowerCase().includes(query));
    const limitedSequences = sequenceResults.slice(0, query ? 6 : 5);
    const limitedFunctions = functionResults.slice(0, query ? 10 : 6);
    let html = "";
    if (limitedSequences.length) {
      html += '<span class="search-section-label">Sequences</span>' + limitedSequences.map((sequence) => `
        <button class="search-result" type="button" data-search-type="sequence" data-search-id="${escapeHtml(sequence.id)}">
          <span class="search-result-icon">${String(sequence.ordinal).padStart(2, "0")}</span>
          <span class="search-result-copy"><strong>${escapeHtml(sequence.shortTitle)}</strong><small>${escapeHtml(sequence.summary)}</small></span>
          <span class="search-result-kind">${sequence.stats.calls} calls</span>
        </button>
      `).join("");
    }
    if (limitedFunctions.length) {
      html += '<span class="search-section-label">Functions</span>' + limitedFunctions.map((fn) => `
        <button class="search-result" type="button" data-search-type="function" data-search-id="${escapeHtml(fn.id)}">
          <span class="search-result-icon" style="color:${fn.kind === "i3" ? "var(--i3)" : "var(--host)"};background:${fn.kind === "i3" ? "var(--i3-soft)" : "var(--host-soft)"}">${fn.kind === "i3" ? "I3" : "H"}</span>
          <span class="search-result-copy"><strong><code>${escapeHtml(fn.id)}</code></strong><small>${escapeHtml(fn.owner)} · ${escapeHtml(fn.contract)}</small></span>
          <span class="search-result-kind">${fn.usages.length}×</span>
        </button>
      `).join("");
    }
    if (!html) html = '<div class="empty-results">No sequence or function matches that search.</div>';
    elements.searchResults.innerHTML = html;
    state.searchIndex = 0;
    updateSearchKeyboardSelection();
    elements.searchResults.querySelectorAll("[data-search-type]").forEach((button) => button.addEventListener("click", () => activateSearchResult(button)));
  }

  function updateSearchKeyboardSelection() {
    const results = [...elements.searchResults.querySelectorAll("[data-search-type]")];
    if (!results.length) return;
    state.searchIndex = Math.max(0, Math.min(results.length - 1, state.searchIndex));
    results.forEach((result, index) => result.classList.toggle("is-keyboard-active", index === state.searchIndex));
    results[state.searchIndex].scrollIntoView({ block: "nearest" });
  }

  function activateSearchResult(button) {
    const type = button.dataset.searchType;
    const id = button.dataset.searchId;
    elements.searchDialog.close();
    if (type === "sequence") setSequence(id);
    else openFunction(id);
  }

  function openSearch() {
    if (!elements.searchDialog.open) elements.searchDialog.showModal();
    elements.globalSearch.value = "";
    renderGlobalSearch();
    window.setTimeout(() => elements.globalSearch.focus(), 30);
  }

  function openHelp() {
    if (!elements.helpDialog.open) elements.helpDialog.showModal();
  }

  async function copyShareLink() {
    updateUrl();
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast("Link copied to clipboard");
    } catch {
      const input = document.createElement("textarea");
      input.value = window.location.href;
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.appendChild(input);
      input.select();
      document.execCommand("copy");
      input.remove();
      toast("Link copied to clipboard");
    }
  }

  function bindEvents() {
    elements.journeyList.addEventListener("click", (event) => {
      const button = event.target.closest("[data-sequence-id]");
      if (button) setSequence(button.dataset.sequenceId);
    });
    elements.mobileSceneSelect.addEventListener("change", () => setSequence(elements.mobileSceneSelect.value));
    document.querySelectorAll(".view-tab").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
    elements.callFilter.addEventListener("click", (event) => {
      const button = event.target.closest("[data-filter]");
      if (button) setCallFilter(button.dataset.filter);
    });
    elements.actorFilter.addEventListener("change", () => setActorFilter(elements.actorFilter.value));
    elements.zoomOut.addEventListener("click", () => setZoom(state.zoom - 0.1));
    elements.zoomIn.addEventListener("click", () => setZoom(state.zoom + 0.1));
    elements.previousCall.addEventListener("click", () => stepCall(-1));
    elements.nextCall.addEventListener("click", () => stepCall(1));
    elements.playPause.addEventListener("click", togglePlayback);
    elements.stepScrubber.addEventListener("input", () => {
      stopPlayback();
      const call = visibleCalls()[Number(elements.stepScrubber.value)];
      if (call) setCurrentCall(call.id);
    });
    elements.speedButton.addEventListener("click", () => {
      const wasPlaying = state.playing;
      stopPlayback();
      state.speedIndex = (state.speedIndex + 1) % SPEEDS.length;
      updatePlayback(ensureCurrentCall());
      if (wasPlaying) startPlayback();
    });
    elements.clearMapFocus.addEventListener("click", () => { state.mapFocus = null; renderMap(); });
    elements.functionSearch.addEventListener("input", () => { state.functionQuery = elements.functionSearch.value; renderFunctionCatalog(); });
    elements.functionFilter.addEventListener("click", (event) => {
      const button = event.target.closest("[data-function-filter]");
      if (!button) return;
      state.functionFilter = button.dataset.functionFilter;
      syncFunctionFilterButtons();
      renderFunctionCatalog();
    });
    elements.searchButton.addEventListener("click", openSearch);
    elements.shareButton.addEventListener("click", copyShareLink);
    elements.helpButton.addEventListener("click", openHelp);
    elements.footerHelp.addEventListener("click", openHelp);
    document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => document.getElementById(button.dataset.closeDialog).close()));
    [elements.searchDialog, elements.helpDialog].forEach((dialog) => dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    }));
    elements.globalSearch.addEventListener("input", renderGlobalSearch);
    elements.globalSearch.addEventListener("keydown", (event) => {
      const results = [...elements.searchResults.querySelectorAll("[data-search-type]")];
      if (event.key === "ArrowDown") { event.preventDefault(); state.searchIndex += 1; updateSearchKeyboardSelection(); }
      else if (event.key === "ArrowUp") { event.preventDefault(); state.searchIndex -= 1; updateSearchKeyboardSelection(); }
      else if (event.key === "Enter" && results[state.searchIndex]) { event.preventDefault(); activateSearchResult(results[state.searchIndex]); }
    });

    document.addEventListener("keydown", (event) => {
      const tag = event.target.tagName;
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(tag) || event.target.isContentEditable;
      if (typing || elements.searchDialog.open || elements.helpDialog.open) return;
      if (event.key === "/") { event.preventDefault(); openSearch(); }
      else if (event.key === " ") { event.preventDefault(); if (state.view === "trace") togglePlayback(); }
      else if (event.key === "ArrowLeft" && state.view === "trace") { event.preventDefault(); stopPlayback(); stepCall(-1); }
      else if (event.key === "ArrowRight" && state.view === "trace") { event.preventDefault(); stopPlayback(); stepCall(1); }
      else if (event.key === "1") setView("trace");
      else if (event.key === "2") setView("map");
      else if (event.key === "3") setView("functions");
    });

    elements.sequenceViewport.addEventListener("touchstart", (event) => {
      if (event.touches.length !== 1) return;
      state.touch = { x: event.touches[0].clientX, y: event.touches[0].clientY, scrollLeft: elements.sequenceViewport.scrollLeft };
    }, { passive: true });
    elements.sequenceViewport.addEventListener("touchend", (event) => {
      if (!state.touch || !event.changedTouches[0]) return;
      const dx = event.changedTouches[0].clientX - state.touch.x;
      const dy = event.changedTouches[0].clientY - state.touch.y;
      const scrolled = Math.abs(elements.sequenceViewport.scrollLeft - state.touch.scrollLeft) > 8;
      if (!scrolled && Math.abs(dx) > 65 && Math.abs(dy) < 48) stepCall(dx < 0 ? 1 : -1);
      state.touch = null;
    }, { passive: true });
  }

  function initialise() {
    if (!currentSequence().calls.some((call) => call.id === state.callId)) state.callId = currentSequence().calls[0]?.id || null;
    populateStaticChrome();
    renderSceneHeader();
    renderActorFilter();
    bindEvents();
    state.zoom = 1;
    elements.zoomValue.textContent = "100%";
    elements.zoomOut.disabled = false;
    elements.zoomIn.disabled = false;
    setView(state.view);
    updateUrl();
  }

  initialise();
})();

(() => {
  "use strict";

  const atlas = window.LIFECYCLE_ATLAS_DATA;
  if (!atlas || !Array.isArray(atlas.documents) || atlas.documents.length < 2) {
    document.body.innerHTML = '<main style="padding:2rem;color:#fff">Unable to load the generated lifecycle data.</main>';
    return;
  }

  const params = new URLSearchParams(window.location.search);
  const documentsById = new Map(atlas.documents.map((documentData) => [documentData.id, documentData]));
  const requestedDocument = params.get("doc");
  const initialDocumentId = documentsById.has(requestedDocument) ? requestedDocument : atlas.defaultDocumentId;
  let data = documentsById.get(initialDocumentId);
  let sequenceIds = new Set(data.sequences.map((sequence) => sequence.id));
  let functionIds = new Set(data.functions.map((fn) => fn.id));
  let functionsById = new Map(data.functions.map((fn) => [fn.id, fn]));
  let dictionaryIds = new Set(data.dictionary.map((entry) => entry.id));
  let dictionaryById = new Map(data.dictionary.map((entry) => [entry.id, entry]));

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

  const requestedSequence = params.get("diagram");
  const requestedView = params.get("view");
  const requestedTerm = params.get("term");

  const state = {
    documentId: initialDocumentId,
    sequenceId: sequenceIds.has(requestedSequence) ? requestedSequence : data.sequences[0].id,
    view: ["trace", "map", "functions", "dictionary"].includes(requestedView) ? requestedView : "trace",
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
    dictionaryQuery: "",
    selectedTermId: dictionaryIds.has(requestedTerm) ? requestedTerm : null,
    searchIndex: 0,
    toastTimer: null,
    resizeFrame: null,
    revealFrame: null,
    historyScrollFrame: null,
    scrubbing: false,
    inspectorHeights: new Map(),
    touch: null,
  };

  const elements = Object.fromEntries(
    [
      "documentSwitcher", "mobileDocumentSelect", "journeyEyebrow", "journeyDescription", "journeyList",
      "sourceFileName", "sourceCommit", "sourceSequenceCount", "sourceCallCount", "sourceFunctionCount", "sourceDictionaryCount", "sourceMode",
      "sourceDocumentLink", "mobileSceneSelect", "mobileSceneCount", "sceneKicker", "sceneStatus",
      "sceneTitle", "sceneSummary", "sceneQuestion", "sceneMetrics", "callFilter", "hostCallFilter", "actorFilter",
      "zoomOut", "zoomIn", "zoomValue", "callNow", "currentStepNumber", "currentRoute",
      "currentFunction", "stickyActorHeader", "stickyActorSvg", "sequenceViewport", "sequenceSvg", "resetSequence", "previousCall",
      "playPause", "nextCall", "stepScrubber", "stepProgress", "stepHint", "speedButton",
      "callInspector", "mapScope", "clearMapFocus", "mapViewport", "mapSvg", "mapDetail",
      "roleLegend", "mapIntroTitle", "mapIntroText", "functionHeading", "functionIntro", "functionSearch",
      "functionFilter", "hostFunctionFilter", "functionResultCount", "functionList", "functionDetail", "footerProduct",
      "dictionaryHeading", "dictionaryIntro", "dictionarySearch", "dictionaryResultCount", "dictionaryList", "dictionaryDetail",
      "footerSource", "footerAuthority", "formalAuthorityLink", "searchButton", "shareButton", "helpButton", "footerHelp",
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

  function functionStatusLabel(fn) {
    return {
      "contract-extension-required": "Contract extension required",
      required: "Required",
      "optional-later": "Optional later",
      existing: fn.usages.length ? "Existing · pictured" : "Existing · not pictured",
    }[fn.implementationStatus] || (fn.usages.length ? "Pictured" : "Not pictured");
  }

  function withInstantPageScroll(callback) {
    const root = document.documentElement;
    const previousScrollBehavior = root.style.scrollBehavior;
    root.style.scrollBehavior = "auto";
    callback();
    root.style.scrollBehavior = previousScrollBehavior;
  }

  function scrollPageTo(top) {
    withInstantPageScroll(() => window.scrollTo({ top, behavior: "auto" }));
  }

  function scrollPageBy(delta) {
    withInstantPageScroll(() => window.scrollBy({ top: delta, behavior: "auto" }));
  }

  function scheduleNarrowDetailReveal(element) {
    if (!window.matchMedia("(max-width: 1040px)").matches) return;
    window.requestAnimationFrame(() => {
      const rect = element.getBoundingClientRect();
      scrollPageBy(rect.top - stickyViewportTop() - 12);
    });
  }

  function cancelHistoryScrollSnapshot() {
    window.cancelAnimationFrame(state.historyScrollFrame);
    state.historyScrollFrame = null;
  }

  function persistCurrentHistoryScroll() {
    if (!window.history.state?.lifecycleAtlas) return;
    const scrollY = window.scrollY;
    if (window.history.state.scrollY === scrollY) return;
    window.history.replaceState({ ...window.history.state, scrollY }, "", window.location.href);
  }

  function scheduleHistoryScrollSnapshot() {
    if (state.historyScrollFrame !== null) return;
    state.historyScrollFrame = window.requestAnimationFrame(() => {
      state.historyScrollFrame = null;
      persistCurrentHistoryScroll();
    });
  }

  function updateUrl(mode = "replace", originScrollY = window.scrollY) {
    const next = new URL(window.location.href);
    next.searchParams.set("doc", state.documentId);
    next.searchParams.set("diagram", state.sequenceId);
    if (state.view === "trace") next.searchParams.delete("view");
    else next.searchParams.set("view", state.view);
    if (state.callId) next.searchParams.set("call", state.callId);
    else next.searchParams.delete("call");
    if (state.view === "functions" && state.selectedFunctionId) next.searchParams.set("function", state.selectedFunctionId);
    else next.searchParams.delete("function");
    if (state.view === "dictionary" && state.selectedTermId) next.searchParams.set("term", state.selectedTermId);
    else next.searchParams.delete("term");

    const historyState = {
      lifecycleAtlas: true,
      documentId: state.documentId,
      sequenceId: state.sequenceId,
      view: state.view,
      callId: state.callId,
      functionId: state.view === "functions" ? state.selectedFunctionId : null,
      termId: state.view === "dictionary" ? state.selectedTermId : null,
      scrollY: window.scrollY,
    };
    if (mode === "none") return;
    cancelHistoryScrollSnapshot();
    if (mode === "push" && next.href !== window.location.href) {
      if (window.history.state?.lifecycleAtlas) {
        window.history.replaceState({ ...window.history.state, scrollY: originScrollY }, "", window.location.href);
      }
      window.history.pushState(historyState, "", next);
    } else {
      window.history.replaceState(historyState, "", next);
    }
  }

  function toast(message) {
    window.clearTimeout(state.toastTimer);
    elements.toast.textContent = message;
    elements.toast.classList.add("is-visible");
    state.toastTimer = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 2300);
  }

  function populateStaticChrome() {
    const source = data.source;
    const formalAuthority = atlas.formalAuthority;
    const commit = source.sourceCommit.slice(0, 12);
    document.body.dataset.document = data.id;

    elements.documentSwitcher.innerHTML = atlas.documents.map((documentData) => `
      <button class="document-tab${documentData.id === state.documentId ? " is-active" : ""}" type="button" data-document-id="${escapeHtml(documentData.id)}" aria-pressed="${documentData.id === state.documentId}">
        <span>${escapeHtml(documentData.name)}</span>
        <small>${documentData.stats.sequences} sequences</small>
      </button>
    `).join("");
    elements.mobileDocumentSelect.innerHTML = atlas.documents.map((documentData) => `
      <option value="${escapeHtml(documentData.id)}">${escapeHtml(documentData.name)}</option>
    `).join("");
    elements.mobileDocumentSelect.value = state.documentId;

    elements.journeyEyebrow.textContent = `${data.name} sequences`;
    elements.journeyDescription.textContent = data.subtitle;
    elements.sourceFileName.textContent = source.path;
    elements.sourceCommit.textContent = commit;
    elements.sourceSequenceCount.textContent = data.stats.sequences;
    elements.sourceCallCount.textContent = data.stats.calls;
    elements.sourceFunctionCount.textContent = data.stats.functions;
    elements.sourceDictionaryCount.textContent = data.stats.dictionaryTerms;
    const sourceRole = source.role === "downstream_projection_of_chambers_formal_specification_v1.0.0"
      ? "Downstream formal-release projection"
      : "Registered source with Chambers release binding";
    elements.sourceMode.textContent = `${sourceRole} · SHA-256 ${source.documentSha256.slice(0, 8)}`;
    elements.formalAuthorityLink.href = formalAuthority.release_url;
    elements.formalAuthorityLink.title = `${formalAuthority.release} at ${formalAuthority.commit}`;
    elements.formalAuthorityLink.firstChild.textContent = `Modeled Chambers semantics · ${formalAuthority.release} `;
    elements.sourceDocumentLink.href = source.url;
    elements.sourceDocumentLink.title = `Open ${source.path} at ${commit}`;
    elements.mobileSceneCount.textContent = `${data.stats.sequences} sequences`;
    elements.footerProduct.textContent = `Lifecycle Atlas · ${data.name}`;
    elements.footerAuthority.href = formalAuthority.release_url;
    elements.footerAuthority.textContent = `${formalAuthority.git_tag} · modeled Chambers semantics ↗`;
    elements.footerSource.href = source.url;
    elements.footerSource.textContent = `${source.repository} · ${commit} · open ${data.name} source ↗`;
    elements.hostCallFilter.hidden = data.stats.hostCalls === 0;
    elements.hostFunctionFilter.hidden = data.stats.hostCalls === 0;
    elements.mapIntroTitle.textContent = `${data.name} relationships`;
    elements.mapIntroText.textContent = "Line weight is call frequency. Select an actor or connection to isolate its surface.";
    elements.functionHeading.textContent = `Every named ${data.name} call`;
    elements.functionIntro.textContent = data.functionIntro;
    elements.dictionaryHeading.textContent = `${data.name} dictionary`;
    elements.dictionaryIntro.textContent = `All ${data.stats.dictionaryTerms} definitions come from this document's local Dictionary section.`;

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
    const statusText = {
      later: "Later",
      core: "Shared kernel",
      working: "Working design",
      current: "Current design",
    }[sequence.status] || data.statusLabel;
    const metric = sequence.stats.hostCalls > 0
      ? [sequence.stats.hostCalls, "Host calls"]
      : [sequence.stats.i3Calls, "I3 calls"];
    elements.sceneKicker.textContent = `${data.name} · ${sequence.kicker}`;
    elements.sceneStatus.textContent = statusText;
    elements.sceneStatus.className = `status-pill${sequence.status === "later" ? " is-later" : sequence.status === "core" ? " is-core" : sequence.status === "working" ? " is-working" : ""}`;
    elements.sceneTitle.textContent = sequence.shortTitle;
    elements.sceneSummary.textContent = sequence.summary;
    elements.sceneQuestion.textContent = sequence.question;
    elements.sceneMetrics.innerHTML = [
      [sequence.stats.actors, "Actors"],
      [sequence.stats.calls, "Calls"],
      [sequence.stats.branches, "Branches"],
      metric,
    ].map(([value, label]) => `<div class="metric"><strong>${value}</strong><span>${label}</span></div>`).join("");
    document.title = `${sequence.shortTitle} · ${data.name} · Lifecycle Atlas`;
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

  function sequenceFocusIdentity() {
    const active = document.activeElement;
    if (!active || !elements.sequenceSvg.contains(active)) return null;
    if (active.dataset.callId) return { attribute: "data-call-id", value: active.dataset.callId };
    if (active.dataset.actorId) return { attribute: "data-actor-id", value: active.dataset.actorId };
    return null;
  }

  function restoreSequenceFocus(identity) {
    if (!identity) return;
    const target = elements.sequenceSvg.querySelector(`[${identity.attribute}="${CSS.escape(identity.value)}"]`);
    if (target?.getAttribute("tabindex") !== "-1") target?.focus({ preventScroll: true });
  }

  function renderTrace(options = {}) {
    const focusedControl = sequenceFocusIdentity();
    const horizontalPosition = elements.sequenceViewport.scrollLeft;
    const call = ensureCurrentCall();
    renderSequenceSvg();
    elements.sequenceViewport.scrollTo({ left: horizontalPosition, top: 0, behavior: "auto" });
    renderCallNow(call);
    renderCallInspector(call);
    stabilizeCallInspectorHeight();
    updatePlayback(call);
    restoreSequenceFocus(focusedControl);
    if (options.revealCall && call) scheduleVerticalCallReveal(call.id);
  }

  function stickyViewportTop() {
    return [document.querySelector(".topbar"), document.querySelector(".mobile-scene-bar")]
      .filter(Boolean)
      .reduce((bottom, element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        if (style.display === "none" || style.visibility === "hidden" || rect.bottom <= 0 || rect.top >= window.innerHeight) return bottom;
        return Math.max(bottom, rect.bottom);
      }, 0);
  }

  function renderStickyActorHeader(width) {
    const naturalHeight = 80;
    const scaledWidth = Math.round(width * state.zoom);
    const scaledHeight = Math.round(naturalHeight * state.zoom);
    elements.stickyActorHeader.classList.remove("is-visible");
    elements.stickyActorSvg.replaceChildren();
    elements.stickyActorSvg.setAttribute("viewBox", `0 0 ${width} ${naturalHeight}`);
    elements.stickyActorSvg.setAttribute("width", String(scaledWidth));
    elements.stickyActorSvg.setAttribute("height", String(scaledHeight));
    elements.stickyActorSvg.style.width = `${scaledWidth}px`;
    elements.stickyActorSvg.style.height = `${scaledHeight}px`;
    elements.stickyActorHeader.dataset.height = String(scaledHeight);
    elements.stickyActorHeader.style.height = `${scaledHeight}px`;
    elements.stickyActorSvg.appendChild(svgElement("rect", {
      x: 0, y: 0, width, height: naturalHeight, class: "sticky-actor-background",
    }));
    elements.sequenceSvg.querySelectorAll(".svg-actor").forEach((actor) => {
      const clone = actor.cloneNode(true);
      clone.removeAttribute("role");
      clone.removeAttribute("tabindex");
      clone.removeAttribute("aria-description");
      clone.classList.add("sticky-svg-actor");
      elements.stickyActorSvg.appendChild(clone);
    });
    elements.stickyActorSvg.appendChild(svgElement("line", {
      x1: 0, y1: naturalHeight - 1, x2: width, y2: naturalHeight - 1, class: "sticky-actor-rule",
    }));
    syncStickyActorHeader();
  }

  function stickyActorHeaderGeometry() {
    const actorHeader = elements.sequenceSvg.querySelector(".svg-actor");
    const height = Number(elements.stickyActorHeader.dataset.height || 0);
    if (state.view !== "trace" || !actorHeader || !height) return null;
    const viewportRect = elements.sequenceViewport.getBoundingClientRect();
    const actorRect = actorHeader.getBoundingClientRect();
    const top = stickyViewportTop();
    return {
      height,
      top,
      viewportRect,
      visible: actorRect.top <= top && viewportRect.bottom >= top + height,
    };
  }

  function syncStickyActorHeader() {
    const geometry = stickyActorHeaderGeometry();
    elements.stickyActorHeader.classList.toggle("is-visible", Boolean(geometry?.visible));
    if (!geometry?.visible) return;
    elements.stickyActorHeader.style.top = `${geometry.top}px`;
    elements.stickyActorHeader.style.left = `${geometry.viewportRect.left}px`;
    elements.stickyActorHeader.style.width = `${geometry.viewportRect.width}px`;
    elements.stickyActorSvg.style.transform = `translate3d(${-elements.sequenceViewport.scrollLeft}px, 0, 0)`;
  }

  function scheduleVerticalCallReveal(callId) {
    window.cancelAnimationFrame(state.revealFrame);
    state.revealFrame = window.requestAnimationFrame(() => {
      state.revealFrame = null;
      const target = elements.sequenceSvg.querySelector(`[data-call-id="${CSS.escape(callId)}"]`);
      if (!target) return;
      const rect = target.getBoundingClientRect();
      const stickyActorGeometry = stickyActorHeaderGeometry();
      const visibleTop = (stickyActorGeometry?.top ?? stickyViewportTop())
        + (stickyActorGeometry?.visible ? stickyActorGeometry.height : 0);
      const visibleBottom = window.innerHeight;
      let delta = 0;
      if (rect.top < visibleTop) delta = rect.top - visibleTop;
      else if (rect.bottom > visibleBottom) delta = rect.bottom - visibleBottom;
      if (Math.abs(delta) > 0.5) scrollPageBy(delta);
    });
  }

  function stabilizeCallInspectorHeight() {
    const width = Math.round(elements.callInspector.getBoundingClientRect().width);
    if (!width) return;
    const key = `${state.documentId}/${state.sequenceId}/${width}`;
    let height = state.inspectorHeights.get(key);
    if (!height) {
      const measure = document.createElement("aside");
      measure.className = "call-inspector inspector-card call-inspector-measure";
      measure.setAttribute("aria-hidden", "true");
      measure.inert = true;
      measure.style.width = `${width}px`;
      document.body.appendChild(measure);
      height = 410;
      currentSequence().calls.forEach((call) => {
        measure.classList.toggle("is-host", call.kind === "host");
        measure.innerHTML = callInspectorMarkup(call);
        height = Math.max(height, Math.ceil(measure.getBoundingClientRect().height));
      });
      measure.remove();
      state.inspectorHeights.set(key, height);
    }
    elements.callInspector.style.setProperty("--call-inspector-height", `${height}px`);
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
    const rowHeight = 82;
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
        "data-actor-id": actor.id,
        role: "button", tabindex: "0", "aria-description": `Focus ${actor.label} calls.`,
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

    renderStickyActorHeader(width);

    calls.forEach((call) => {
      const y = headerHeight + call.index * rowHeight + rowHeight / 2;
      const lineY = y + 8;
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
      const kindLabel = call.kind === "i3" ? "I3" : "HOST BOUNDARY";
      const kindWidth = call.kind === "i3" ? 18 : 84;
      const group = svgElement("g", {
        class: `call-row ${call.kind}${call.kind === "host" ? " is-host" : ""}${isCurrent ? " is-current" : ""}${!isVisible ? " is-dim" : ""}${isPast ? " is-past" : ""}`,
        "data-call-id": call.id,
        role: "button", tabindex: isVisible ? "0" : "-1",
        "aria-description": `Step ${call.index + 1}, ${call.from} to ${call.to}.`,
      });
      group.appendChild(svgElement("rect", { x: 5, y: y - 38, width: width - 10, height: 76, rx: 12, class: "row-hit" }));
      group.appendChild(svgElement("rect", { x: 8, y: y - 36, width: width - 16, height: 72, rx: 12, class: "row-focus" }));
      group.appendChild(svgElement("text", { x: 23, y: lineY + 3, class: "step-number" }, String(call.index + 1).padStart(2, "0")));
      group.appendChild(svgElement("circle", { cx: start, cy: lineY, r: 3.6, class: `endpoint ${call.kind}` }));
      group.appendChild(svgElement("line", {
        x1: start, y1: lineY, x2: end, y2: lineY, class: `call-line ${call.kind}`,
        "marker-end": `url(#sequence-arrow-${call.kind})`,
      }));
      group.appendChild(svgElement("rect", {
        x: labelMid - pillWidth / 2, y: y - 28, width: pillWidth, height: 25, rx: 8, class: "call-pill",
      }));
      group.appendChild(svgElement("text", { x: labelMid, y: y - 12, class: "call-text" }, call.function));
      group.appendChild(svgElement("text", {
        x: labelMid, y: y + 28, class: "svg-kind", fill: call.kind === "i3" ? "#64e7ef" : "#ffb866",
      }, kindLabel));
      if (branch) {
        const rightStart = labelMid + kindWidth / 2 + 14;
        const rightCharacters = Math.floor((width - rightStart - 20) / 5.4);
        const useRight = rightCharacters >= 12;
        const branchX = useRight ? rightStart : 42;
        const maxCharacters = useRight
          ? Math.min(52, rightCharacters)
          : Math.max(12, Math.floor((labelMid - kindWidth / 2 - branchX - 14) / 5.4));
        group.appendChild(svgElement("text", { x: branchX, y: y + 29, class: "svg-branch" }, `↳ ${truncate(branch, maxCharacters)}`));
      }

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
    const controls = [elements.resetSequence, elements.previousCall, elements.nextCall, elements.playPause, elements.stepScrubber];

    if (!call) {
      elements.callNow.className = "call-now";
      elements.currentStepNumber.textContent = "—";
      elements.currentRoute.textContent = "No calls match this filter";
      elements.currentFunction.textContent = "Adjust ‘Show’ or actor focus";
      elements.currentRoute.removeAttribute("title");
      elements.currentFunction.removeAttribute("title");
      controls.forEach((control) => { control.disabled = true; });
      return;
    }

    const route = `${actors.get(call.from).label} → ${actors.get(call.to).label}`;
    elements.callNow.className = `call-now${call.kind === "host" ? " is-host" : ""}`;
    elements.currentStepNumber.textContent = `${String(index + 1).padStart(2, "0")}/${String(calls.length).padStart(2, "0")}`;
    elements.currentRoute.textContent = route;
    elements.currentRoute.title = route;
    elements.currentFunction.textContent = call.function;
    elements.currentFunction.title = call.function;
    controls.forEach((control) => { control.disabled = false; });
  }

  function callInspectorMarkup(call) {
    const sequence = currentSequence();
    const actors = participantMap(sequence);
    const fn = functionsById.get(call.function);
    const callContextKey = JSON.stringify(call.context);
    const contextItems = [
      ...call.context.map((context) => `<li><strong>${escapeHtml(context.type)}</strong> · ${escapeHtml(context.branch)}</li>`),
      ...call.notes.map((note) => {
        if (JSON.stringify(note.context) === callContextKey) {
          return `<li>${escapeHtml(note.text)}</li>`;
        }
        const branchPath = note.context.length
          ? note.context.map((context) => `${context.type} · ${context.branch}`).join(" / ")
          : "Outside conditional context";
        return `<li><strong>${escapeHtml(branchPath)}</strong> · ${escapeHtml(note.text)}</li>`;
      }),
    ];
    return `
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
      <dl class="call-function-meta" aria-label="Function details">
        <div><dt>Owner</dt><dd>${escapeHtml(fn.owner)}</dd></div>
        <div><dt>Used in</dt><dd>${fn.usages.length} call${fn.usages.length === 1 ? "" : "s"}</dd></div>
        <div><dt>Status</dt><dd>${escapeHtml(fn.implementationStatus === "existing" ? "Existing" : functionStatusLabel(fn))}</dd></div>
      </dl>
      <div class="contract-block">
        <h3>Critical contract</h3>
        <p>${escapeHtml(fn.contract)}</p>
      </div>
      ${contextItems.length ? `<div class="context-block"><h3>Context at this step</h3><ul class="context-list">${contextItems.join("")}</ul></div>` : ""}
      <div class="inspector-actions">
        <button class="quiet-button" type="button" data-inspector-action="map">Map this pair</button>
        <button class="quiet-button" type="button" data-inspector-action="function">Open function</button>
      </div>
    `;
  }

  function renderCallInspector(call) {
    elements.callInspector.className = `call-inspector inspector-card${call?.kind === "host" ? " is-host" : ""}`;
    if (!call) {
      elements.callInspector.innerHTML = '<div class="inspector-empty">No calls match the current filter.</div>';
      return;
    }
    elements.callInspector.innerHTML = callInspectorMarkup(call);
    elements.callInspector.querySelector('[data-inspector-action="map"]')?.addEventListener("click", () => {
      state.mapFocus = { type: "edge", key: `${call.from}→${call.to}` };
      setView("map");
    });
    elements.callInspector.querySelector('[data-inspector-action="function"]')?.addEventListener("click", () => openFunction(call.function));
  }

  function updatePlayback(call) {
    const calls = visibleCalls();
    const index = call ? calls.findIndex((item) => item.id === call.id) : 0;
    elements.stepScrubber.max = String(Math.max(0, calls.length - 1));
    elements.stepScrubber.value = String(Math.max(0, index));
    elements.stepProgress.textContent = calls.length ? `${index + 1} / ${calls.length}` : "0 / 0";
    elements.resetSequence.disabled = !calls.length || index <= 0;
    elements.previousCall.disabled = !calls.length || index <= 0;
    elements.nextCall.disabled = !calls.length || index >= calls.length - 1;
    elements.playPause.disabled = !calls.length;
    elements.playPause.classList.toggle("is-playing", state.playing);
    elements.playPause.setAttribute("aria-label", state.playing ? "Pause sequence" : "Play sequence");
    elements.speedButton.querySelector("strong").textContent = SPEEDS[state.speedIndex].label;

  }

  function setCurrentCall(callId, options = {}) {
    if (!currentSequence().calls.some((call) => call.id === callId)) return;
    const originScrollY = Number.isFinite(options.originScrollY) ? options.originScrollY : window.scrollY;
    state.callId = callId;
    renderTrace({ revealCall: options.reveal !== false });
    updateUrl(options.history || "push", originScrollY);
  }

  function stepCall(direction, options = {}) {
    const calls = visibleCalls();
    if (!calls.length) return;
    const currentIndex = Math.max(0, calls.findIndex((call) => call.id === state.callId));
    const nextIndex = Math.max(0, Math.min(calls.length - 1, currentIndex + direction));
    if (nextIndex === currentIndex && state.playing) stopPlayback();
    setCurrentCall(calls[nextIndex].id, options);
  }

  function resetSequence(options = {}) {
    const first = visibleCalls()[0];
    if (!first) return;
    stopPlayback();
    setCurrentCall(first.id, { history: options.history || "push", reveal: true });
  }

  function startPlayback() {
    const calls = visibleCalls();
    if (!calls.length) return;
    const index = calls.findIndex((call) => call.id === state.callId);
    if (index === calls.length - 1) setCurrentCall(calls[0].id, { history: "replace", reveal: true });
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
      setCurrentCall(activeCalls[activeIndex + 1].id, { history: "replace", reveal: true });
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

  function reconcileFilteredCallSelection() {
    const originScrollY = window.scrollY;
    const previousCallId = state.callId;
    const calls = visibleCalls();
    if (!calls.some((call) => call.id === state.callId)) state.callId = calls[0]?.id || null;
    const selectionChanged = state.callId !== previousCallId;
    renderTrace({ revealCall: selectionChanged });
    updateUrl(selectionChanged ? "push" : "replace", originScrollY);
  }

  function setCallFilter(filter) {
    stopPlayback();
    state.callFilter = filter;
    elements.callFilter.querySelectorAll("button").forEach((button) => {
      const active = button.dataset.filter === filter;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    reconcileFilteredCallSelection();
  }

  function setActorFilter(actorId) {
    stopPlayback();
    state.actorFilter = actorId;
    elements.actorFilter.value = actorId;
    reconcileFilteredCallSelection();
  }

  function setZoom(nextZoom) {
    state.zoom = Math.max(0.7, Math.min(1.3, Math.round(nextZoom * 10) / 10));
    elements.zoomValue.textContent = `${Math.round(state.zoom * 100)}%`;
    elements.zoomOut.disabled = state.zoom <= 0.7;
    elements.zoomIn.disabled = state.zoom >= 1.3;
    renderTrace();
  }

  function renderCurrentView(options = {}) {
    if (state.view === "trace") renderTrace({ revealCall: Boolean(options.revealCall) });
    else if (state.view === "map") renderMap();
    else if (state.view === "functions") {
      if (!state.selectedFunctionId) state.selectedFunctionId = ensureCurrentCall()?.function || data.functions[0].id;
      renderFunctionCatalog();
    } else {
      if (!state.selectedTermId) state.selectedTermId = data.dictionary[0]?.id || null;
      renderDictionaryCatalog();
    }
  }

  function syncViewPanels() {
    document.querySelectorAll(".view-tab").forEach((button) => {
      const active = button.dataset.view === state.view;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    document.querySelectorAll("[data-view-panel]").forEach((panel) => {
      const active = panel.dataset.viewPanel === state.view;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
  }

  function setDocument(documentId, options = {}) {
    if (!documentsById.has(documentId)) return;
    if (documentId === state.documentId) {
      if (options.sequenceId) setSequence(options.sequenceId, options);
      return;
    }

    const originScrollY = Number.isFinite(options.originScrollY) ? options.originScrollY : window.scrollY;
    const restoreDocumentFocus = elements.documentSwitcher.contains(document.activeElement);
    stopPlayback();
    state.scrubbing = false;
    state.documentId = documentId;
    data = documentsById.get(documentId);
    sequenceIds = new Set(data.sequences.map((sequence) => sequence.id));
    functionIds = new Set(data.functions.map((fn) => fn.id));
    functionsById = new Map(data.functions.map((fn) => [fn.id, fn]));
    dictionaryIds = new Set(data.dictionary.map((entry) => entry.id));
    dictionaryById = new Map(data.dictionary.map((entry) => [entry.id, entry]));
    state.sequenceId = sequenceIds.has(options.sequenceId) ? options.sequenceId : data.sequences[0].id;
    state.callId = currentSequence().calls[0]?.id || null;
    state.callFilter = "all";
    state.actorFilter = "";
    state.mapFocus = null;
    state.functionFilter = "all";
    state.functionQuery = "";
    state.selectedFunctionId = null;
    state.dictionaryQuery = "";
    state.selectedTermId = null;
    elements.functionSearch.value = "";
    elements.dictionarySearch.value = "";
    elements.sequenceViewport.scrollTo({ left: 0, top: 0, behavior: "auto" });
    elements.mapViewport.scrollTo({ left: 0, top: 0, behavior: "auto" });

    populateStaticChrome();
    if (restoreDocumentFocus) {
      elements.documentSwitcher.querySelector(`[data-document-id="${CSS.escape(documentId)}"]`)?.focus({ preventScroll: true });
    }
    renderSceneHeader();
    renderActorFilter();
    elements.callFilter.querySelectorAll("button").forEach((button) => {
      const active = button.dataset.filter === "all";
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    syncFunctionFilterButtons();
    renderCurrentView();
    updateUrl(options.history || "push", originScrollY);
    if (options.announce !== false) toast(`${data.name} workspace opened`);
  }

  function setSequence(sequenceId, options = {}) {
    if (!sequenceIds.has(sequenceId) || sequenceId === state.sequenceId) return;
    const originScrollY = Number.isFinite(options.originScrollY) ? options.originScrollY : window.scrollY;
    stopPlayback();
    state.scrubbing = false;
    state.sequenceId = sequenceId;
    state.callFilter = "all";
    state.actorFilter = "";
    state.mapFocus = null;
    state.callId = currentSequence().calls[0]?.id || null;
    elements.sequenceViewport.scrollTo({ left: 0, top: 0, behavior: "auto" });
    updateJourneySelection();
    renderSceneHeader();
    renderActorFilter();
    elements.callFilter.querySelectorAll("button").forEach((button) => {
      const active = button.dataset.filter === "all";
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    renderCurrentView();
    updateUrl(options.history || "push", originScrollY);
    if (options.scroll !== false) {
      scrollPageTo(0);
      persistCurrentHistoryScroll();
    }
  }

  function setView(view, options = {}) {
    if (!["trace", "map", "functions", "dictionary"].includes(view)) return;
    const originScrollY = Number.isFinite(options.originScrollY) ? options.originScrollY : window.scrollY;
    stopPlayback();
    state.scrubbing = false;
    state.view = view;
    syncViewPanels();
    renderCurrentView({ revealCall: options.revealCall });
    updateUrl(options.history || "push", originScrollY);
  }

  function restoreFromLocation(event) {
    window.clearInterval(state.timer);
    state.timer = null;
    state.playing = false;
    state.scrubbing = false;
    window.cancelAnimationFrame(state.revealFrame);
    state.revealFrame = null;
    cancelHistoryScrollSnapshot();
    scrollPageTo(window.scrollY);
    const restoredScrollY = Number.isFinite(event?.state?.scrollY) ? event.state.scrollY : window.scrollY;

    const nextParams = new URLSearchParams(window.location.search);
    const requestedDocumentId = nextParams.get("doc");
    state.documentId = documentsById.has(requestedDocumentId) ? requestedDocumentId : atlas.defaultDocumentId;
    data = documentsById.get(state.documentId);
    sequenceIds = new Set(data.sequences.map((sequence) => sequence.id));
    functionIds = new Set(data.functions.map((fn) => fn.id));
    functionsById = new Map(data.functions.map((fn) => [fn.id, fn]));
    dictionaryIds = new Set(data.dictionary.map((entry) => entry.id));
    dictionaryById = new Map(data.dictionary.map((entry) => [entry.id, entry]));

    const requestedSequenceId = nextParams.get("diagram");
    state.sequenceId = sequenceIds.has(requestedSequenceId) ? requestedSequenceId : data.sequences[0].id;
    const requestedView = nextParams.get("view");
    state.view = ["trace", "map", "functions", "dictionary"].includes(requestedView) ? requestedView : "trace";
    const requestedCallId = nextParams.get("call");
    state.callId = currentSequence().calls.some((call) => call.id === requestedCallId)
      ? requestedCallId
      : currentSequence().calls[0]?.id || null;
    const requestedFunctionId = nextParams.get("function");
    state.selectedFunctionId = state.view === "functions" && functionIds.has(requestedFunctionId) ? requestedFunctionId : null;
    const requestedTermId = nextParams.get("term");
    state.selectedTermId = state.view === "dictionary" && dictionaryIds.has(requestedTermId) ? requestedTermId : null;
    state.callFilter = "all";
    state.actorFilter = "";
    state.mapFocus = null;
    state.functionFilter = "all";
    state.functionQuery = "";
    state.dictionaryQuery = "";
    elements.functionSearch.value = "";
    elements.dictionarySearch.value = "";

    populateStaticChrome();
    renderSceneHeader();
    renderActorFilter();
    elements.callFilter.querySelectorAll("button").forEach((button) => {
      const active = button.dataset.filter === "all";
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    syncFunctionFilterButtons();
    syncViewPanels();
    renderCurrentView();
    scrollPageTo(restoredScrollY);
    syncStickyActorHeader();
    updateUrl("replace");
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
    const availableWidth = elements.mapViewport.clientWidth || 1000;
    const width = Math.max(680, Math.min(1000, availableWidth));
    const height = width < 820 ? 590 : 640;
    const center = { x: width / 2, y: height / 2 + 5 };
    const radiusX = Math.max(230, width / 2 - (actors.length <= 4 ? 112 : 98));
    const radiusY = actors.length <= 4 ? height / 2 - 92 : height / 2 - 62;
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
        "aria-label": `${actorById.get(edge.from).label} to ${actorById.get(edge.to).label}: ${edge.calls.length} ${edge.calls.length === 1 ? "call" : "calls"}`,
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
        "aria-description": `Focus ${actor.label} relationships.`,
      });
      group.appendChild(svgElement("rect", { x: -80, y: -36, width: 160, height: 72, rx: 15, stroke: ROLE_COLORS[actor.role] }));
      group.appendChild(svgElement("rect", { x: -42, y: -36, width: 84, height: 2.5, rx: 2, fill: ROLE_COLORS[actor.role] }));
      const lines = splitLabel(actor.label, 20);
      const label = svgElement("text", { x: 0, y: lines.length === 1 ? -3 : -10 });
      lines.forEach((line, index) => label.appendChild(svgElement("tspan", { x: 0, dy: index ? 13 : 0 }, line)));
      group.append(label);
      group.appendChild(svgElement("text", { x: 0, y: 19, class: "map-role" }, actor.role.toUpperCase()));
      const incidentCount = incidentCounts.get(actor.id);
      group.appendChild(svgElement("text", { x: 0, y: 31, class: "map-activity" }, `${incidentCount} ${incidentCount === 1 ? "call" : "calls"}`));
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
        <h3>${sequence.stats.actors} actors · ${edges.length} relationship${edges.length === 1 ? "" : "s"}</h3>
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

  function renderFunctionCatalog(options = {}) {
    const query = state.functionQuery.trim().toLowerCase();
    const filtered = data.functions.filter((fn) => {
      const kindMatch = state.functionFilter === "all" || fn.kind === state.functionFilter || (state.functionFilter === "unused" && !fn.usages.length);
      if (!kindMatch) return false;
      if (!query) return true;
      return `${fn.id} ${fn.owner} ${fn.contract} ${fn.path}`.toLowerCase().includes(query);
    });
    elements.functionResultCount.textContent = `${filtered.length} of ${data.functions.length} functions`;
    elements.functionList.innerHTML = filtered.length ? filtered.map((fn) => `
      <button class="function-card ${fn.kind}${fn.id === state.selectedFunctionId ? " is-selected" : ""}" type="button" role="listitem" data-function-id="${escapeHtml(fn.id)}">
        <span class="function-card-top"><span class="kind-badge ${fn.kind}"><i class="legend-dot ${fn.kind}"></i>${fn.kind === "i3" ? "I3" : "Host"}</span><span class="usage-badge">${fn.usages.length}×</span></span>
        <code>${escapeHtml(fn.id)}</code>
        <p>${escapeHtml(fn.contract)}</p>
        <span class="function-card-foot"><span>${escapeHtml(fn.owner)}</span><span>${escapeHtml(functionStatusLabel(fn))}</span></span>
      </button>
    `).join("") : '<div class="empty-results">No function matches those filters.</div>';
    elements.functionList.querySelectorAll("[data-function-id]").forEach((button) => button.addEventListener("click", () => {
      const originScrollY = window.scrollY;
      state.selectedFunctionId = button.dataset.functionId;
      renderFunctionCatalog({ revealDetail: true });
      updateUrl("push", originScrollY);
    }));
    renderFunctionDetail();
    if (options.revealDetail) scheduleNarrowDetailReveal(elements.functionDetail);
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
      <div class="function-meta"><span class="owner-badge">${escapeHtml(fn.owner)}</span><span class="owner-badge">${escapeHtml(fn.path)}</span><span class="owner-badge">${escapeHtml(functionStatusLabel(fn))}</span></div>
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

  function openFunction(functionId, options = {}) {
    if (!functionIds.has(functionId)) return;
    const originScrollY = Number.isFinite(options.originScrollY) ? options.originScrollY : window.scrollY;
    state.selectedFunctionId = functionId;
    state.functionQuery = "";
    state.functionFilter = "all";
    elements.functionSearch.value = "";
    syncFunctionFilterButtons();
    setView("functions", { originScrollY });
  }

  function openCall(callId, options = {}) {
    if (!currentSequence().calls.some((call) => call.id === callId)) return;
    const originScrollY = Number.isFinite(options.originScrollY) ? options.originScrollY : window.scrollY;
    state.callFilter = "all";
    state.actorFilter = "";
    state.callId = callId;
    elements.actorFilter.value = "";
    elements.callFilter.querySelectorAll("button").forEach((button) => {
      const active = button.dataset.filter === "all";
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    setView("trace", { revealCall: true, originScrollY });
  }

  function setSequenceAndCall(sequenceId, callId) {
    const originScrollY = window.scrollY;
    if (sequenceId !== state.sequenceId) {
      setSequence(sequenceId, { history: "none", scroll: false, originScrollY });
    }
    openCall(callId, { originScrollY });
  }

  function syncFunctionFilterButtons() {
    elements.functionFilter.querySelectorAll("button").forEach((button) => {
      const active = button.dataset.functionFilter === state.functionFilter;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function relatedDictionaryEntries(entry) {
    return entry.related.map((termId) => dictionaryById.get(termId)).filter(Boolean);
  }

  function renderDictionaryCatalog(options = {}) {
    const query = state.dictionaryQuery.trim().toLowerCase();
    const filtered = data.dictionary.filter((entry) => {
      if (!query) return true;
      const related = relatedDictionaryEntries(entry).map((item) => item.term).join(" ");
      return `${entry.term} ${entry.definition} ${related}`.toLowerCase().includes(query);
    });
    elements.dictionaryResultCount.textContent = `${filtered.length} of ${data.dictionary.length} terms`;
    elements.dictionaryList.innerHTML = filtered.length ? filtered.map((entry) => `
      <button class="dictionary-card${entry.id === state.selectedTermId ? " is-selected" : ""}" type="button" role="listitem" data-term-id="${escapeHtml(entry.id)}">
        <span class="dictionary-card-top"><strong>${escapeHtml(entry.term)}</strong><span>line ${entry.sourceLine}</span></span>
        <p>${escapeHtml(entry.definition)}</p>
        <span class="dictionary-card-foot"><span>${entry.related.length} related</span><span>source-defined</span></span>
      </button>
    `).join("") : '<div class="empty-results">No dictionary term matches that search.</div>';
    elements.dictionaryList.querySelectorAll("[data-term-id]").forEach((button) => button.addEventListener("click", () => {
      const originScrollY = window.scrollY;
      state.selectedTermId = button.dataset.termId;
      renderDictionaryCatalog({ revealDetail: true });
      updateUrl("push", originScrollY);
    }));
    renderDictionaryDetail();
    if (options.revealDetail) scheduleNarrowDetailReveal(elements.dictionaryDetail);
  }

  function renderDictionaryDetail() {
    const entry = dictionaryById.get(state.selectedTermId);
    if (!entry) {
      elements.dictionaryDetail.innerHTML = '<div class="inspector-empty">Choose a term to read its canonical definition.</div>';
      return;
    }
    const related = relatedDictionaryEntries(entry);
    const sourceUrl = `${data.source.url}#L${entry.sourceLine}`;
    elements.dictionaryDetail.innerHTML = `
      <div class="inspector-type-row">
        <span class="dictionary-source-badge">Source-defined term</span>
        <span class="usage-badge">line ${entry.sourceLine}</span>
      </div>
      <h2 class="dictionary-term-title">${escapeHtml(entry.term)}</h2>
      <div class="dictionary-definition"><h3>Canonical definition</h3><p>${escapeHtml(entry.definition)}</p></div>
      <div class="context-block dictionary-relations">
        <h3>Related terms</h3>
        ${related.length ? `<div class="related-term-list">${related.map((item) => `<button type="button" data-related-term="${escapeHtml(item.id)}">${escapeHtml(item.term)}</button>`).join("")}</div>` : '<p>No related terms are declared in the source table.</p>'}
      </div>
      <a class="dictionary-source-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Open the exact defining line <span aria-hidden="true">↗</span></a>
    `;
    elements.dictionaryDetail.querySelectorAll("[data-related-term]").forEach((button) => button.addEventListener("click", () => openDictionaryTerm(button.dataset.relatedTerm)));
  }

  function openDictionaryTerm(termId, options = {}) {
    if (!dictionaryIds.has(termId)) return;
    const originScrollY = Number.isFinite(options.originScrollY) ? options.originScrollY : window.scrollY;
    state.selectedTermId = termId;
    state.dictionaryQuery = "";
    elements.dictionarySearch.value = "";
    setView("dictionary", { originScrollY, history: options.history });
  }

  function renderGlobalSearch() {
    const query = elements.globalSearch.value.trim().toLowerCase();
    const sequenceResults = atlas.documents.flatMap((documentData) => documentData.sequences.map((sequence) => ({
      documentId: documentData.id,
      documentName: documentData.name,
      sequence,
    }))).filter(({ documentName, sequence }) => !query || `${documentName} ${sequence.shortTitle} ${sequence.summary} ${sequence.question}`.toLowerCase().includes(query));
    const functionResults = atlas.documents.flatMap((documentData) => documentData.functions.map((fn) => ({
      documentId: documentData.id,
      documentName: documentData.name,
      fn,
    }))).filter(({ documentName, fn }) => !query || `${documentName} ${fn.id} ${fn.owner} ${fn.contract}`.toLowerCase().includes(query));
    const dictionaryResults = atlas.documents.flatMap((documentData) => documentData.dictionary.map((entry) => ({
      documentId: documentData.id,
      documentName: documentData.name,
      entry,
    }))).filter(({ documentName, entry }) => !query || `${documentName} ${entry.term} ${entry.definition}`.toLowerCase().includes(query));
    sequenceResults.sort((a, b) => Number(b.documentId === state.documentId) - Number(a.documentId === state.documentId) || a.sequence.ordinal - b.sequence.ordinal);
    functionResults.sort((a, b) => Number(b.documentId === state.documentId) - Number(a.documentId === state.documentId) || b.fn.usages.length - a.fn.usages.length || a.fn.id.localeCompare(b.fn.id));
    dictionaryResults.sort((a, b) => Number(b.documentId === state.documentId) - Number(a.documentId === state.documentId) || a.entry.term.localeCompare(b.entry.term));
    const limitedSequences = sequenceResults.slice(0, query ? 8 : 6);
    const limitedFunctions = functionResults.slice(0, query ? 12 : 8);
    const limitedDictionary = dictionaryResults.slice(0, query ? 12 : 8);
    let html = "";
    if (limitedSequences.length) {
      html += '<span class="search-section-label">Sequences · both documents</span>' + limitedSequences.map(({ documentId, documentName, sequence }) => `
        <button class="search-result" type="button" data-search-type="sequence" data-search-document="${escapeHtml(documentId)}" data-search-id="${escapeHtml(sequence.id)}">
          <span class="search-result-icon">${String(sequence.ordinal).padStart(2, "0")}</span>
          <span class="search-result-copy"><strong>${escapeHtml(sequence.shortTitle)}</strong><small>${escapeHtml(sequence.summary)}</small></span>
          <span class="search-result-kind">${escapeHtml(documentName)} · ${sequence.stats.calls} calls</span>
        </button>
      `).join("");
    }
    if (limitedFunctions.length) {
      html += '<span class="search-section-label">Functions · both documents</span>' + limitedFunctions.map(({ documentId, documentName, fn }) => `
        <button class="search-result" type="button" data-search-type="function" data-search-document="${escapeHtml(documentId)}" data-search-id="${escapeHtml(fn.id)}">
          <span class="search-result-icon" style="color:${fn.kind === "i3" ? "var(--i3)" : "var(--host)"};background:${fn.kind === "i3" ? "var(--i3-soft)" : "var(--host-soft)"}">${fn.kind === "i3" ? "I3" : "H"}</span>
          <span class="search-result-copy"><strong><code>${escapeHtml(fn.id)}</code></strong><small>${escapeHtml(documentName)} · ${escapeHtml(fn.owner)} · ${escapeHtml(fn.contract)}</small></span>
          <span class="search-result-kind">${fn.usages.length}×</span>
        </button>
      `).join("");
    }
    if (limitedDictionary.length) {
      html += '<span class="search-section-label">Dictionary · both documents</span>' + limitedDictionary.map(({ documentId, documentName, entry }) => `
        <button class="search-result" type="button" data-search-type="term" data-search-document="${escapeHtml(documentId)}" data-search-id="${escapeHtml(entry.id)}">
          <span class="search-result-icon dictionary-result-icon">Aa</span>
          <span class="search-result-copy"><strong>${escapeHtml(entry.term)}</strong><small>${escapeHtml(documentName)} · ${escapeHtml(entry.definition)}</small></span>
          <span class="search-result-kind">term</span>
        </button>
      `).join("");
    }
    if (!html) html = '<div class="empty-results">No sequence, function, or dictionary term matches that search.</div>';
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
    const documentId = button.dataset.searchDocument;
    const id = button.dataset.searchId;
    elements.searchDialog.close();
    if (type === "sequence") {
      if (documentId === state.documentId) setSequence(id);
      else setDocument(documentId, { sequenceId: id });
    } else if (type === "function") {
      const originScrollY = window.scrollY;
      if (documentId !== state.documentId) setDocument(documentId, { announce: false, history: "none", originScrollY });
      openFunction(id, { originScrollY });
    } else {
      const originScrollY = window.scrollY;
      if (documentId !== state.documentId) setDocument(documentId, { announce: false, history: "none", originScrollY });
      openDictionaryTerm(id, { originScrollY });
    }
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
    elements.documentSwitcher.addEventListener("click", (event) => {
      const button = event.target.closest("[data-document-id]");
      if (button) setDocument(button.dataset.documentId);
    });
    elements.mobileDocumentSelect.addEventListener("change", () => setDocument(elements.mobileDocumentSelect.value));
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
    elements.resetSequence.addEventListener("click", resetSequence);
    elements.previousCall.addEventListener("click", () => stepCall(-1));
    elements.nextCall.addEventListener("click", () => stepCall(1));
    elements.playPause.addEventListener("click", togglePlayback);
    elements.stepScrubber.addEventListener("input", () => {
      const index = Number(elements.stepScrubber.value);
      stopPlayback();
      const call = visibleCalls()[index];
      if (!call || call.id === state.callId) return;
      const historyMode = state.scrubbing ? "replace" : "push";
      state.scrubbing = true;
      setCurrentCall(call.id, { history: historyMode, reveal: true });
    });
    elements.stepScrubber.addEventListener("change", () => {
      if (!state.scrubbing) return;
      state.scrubbing = false;
      updateUrl("replace");
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
    elements.dictionarySearch.addEventListener("input", () => {
      state.dictionaryQuery = elements.dictionarySearch.value;
      renderDictionaryCatalog();
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
      const target = event.target instanceof Element ? event.target : null;
      const interactive = target?.closest("button, a, input, textarea, select, summary, [role='button'], [contenteditable='true']");
      if (event.defaultPrevented || interactive || elements.searchDialog.open || elements.helpDialog.open) return;
      if (event.key === "/") { event.preventDefault(); openSearch(); }
      else if (event.key === " ") { event.preventDefault(); if (state.view === "trace") togglePlayback(); }
      else if (event.key === "ArrowLeft" && state.view === "trace") { event.preventDefault(); stopPlayback(); stepCall(-1); }
      else if (event.key === "ArrowRight" && state.view === "trace") { event.preventDefault(); stopPlayback(); stepCall(1); }
      else if (event.key === "Home" && state.view === "trace") { event.preventDefault(); resetSequence(); }
      else if (event.key === "1") setView("trace");
      else if (event.key === "2") setView("map");
      else if (event.key === "3") setView("functions");
      else if (event.key === "4") setView("dictionary");
    });

    window.addEventListener("resize", () => {
      window.cancelAnimationFrame(state.resizeFrame);
      state.resizeFrame = window.requestAnimationFrame(() => {
        if (state.view === "map") renderMap();
        else if (state.view === "trace") stabilizeCallInspectorHeight();
        syncStickyActorHeader();
      });
    });
    window.addEventListener("scroll", () => {
      syncStickyActorHeader();
      scheduleHistoryScrollSnapshot();
    }, { passive: true });
    elements.sequenceViewport.addEventListener("scroll", syncStickyActorHeader, { passive: true });
    window.addEventListener("popstate", restoreFromLocation);

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
    if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
    if (!currentSequence().calls.some((call) => call.id === state.callId)) state.callId = currentSequence().calls[0]?.id || null;
    populateStaticChrome();
    renderSceneHeader();
    renderActorFilter();
    bindEvents();
    state.zoom = 1;
    elements.zoomValue.textContent = "100%";
    elements.zoomOut.disabled = false;
    elements.zoomIn.disabled = false;
    setView(state.view, { history: "none", revealCall: state.view === "trace" && Boolean(params.get("call")) });
    updateUrl("replace");
  }

  initialise();
})();

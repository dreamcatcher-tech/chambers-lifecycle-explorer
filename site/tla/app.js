(() => {
  "use strict";

  const data = window.CHAMBERS_TLA_MODEL;
  if (!data || !Array.isArray(data.models)) {
    document.body.textContent = "The generated TLA+ projection could not be loaded.";
    return;
  }

  const SVG_NS = "http://www.w3.org/2000/svg";
  const number = new Intl.NumberFormat("en-US");
  const modelsById = new Map(data.models.map((model) => [model.id, model]));
  const params = new URLSearchParams(window.location.search);
  const requestedModel = params.get("model");
  const requestedView = params.get("view");
  const validViews = new Set(["explain", "state-space", "properties"]);

  const state = {
    modelId: modelsById.has(requestedModel) ? requestedModel : data.models[0].id,
    view: validViews.has(requestedView) ? requestedView : "explain",
    selectedNode: params.get("node"),
    selectedAction: null,
    scenarioIndex: 0,
    scenarioStep: -1,
    scenarioTimer: null,
    category: "all",
  };

  const ids = [
    "modelSwitcher", "headerSourceLink", "modelEyebrow", "modelTitle", "modelSummary",
    "modelQuestion", "heroStatus", "heroReceipt", "metricGenerated", "metricDistinct",
    "metricDepth", "metricActions", "metricProperties", "viewTabs", "viewDisclosure",
    "visualKicker", "visualTitle", "scenarioControls", "scenarioSelect", "scenarioPlay",
    "visualStage", "modelSvg", "propertiesView", "scenarioStrip", "visualLegend",
    "inspectorKicker", "inspectorTitle", "inspectorDescription", "inspectorFacts",
    "inspectorActions", "actionFilter", "actionGrid", "curatedExplanation",
    "derivedExplanation", "proofExplanation", "receiptCommit", "receiptModule",
    "receiptTooling", "receiptJar", "receiptEvidence", "receiptGenerated",
    "receiptSourceLink", "footerBoundary",
  ];
  const elements = Object.fromEntries(ids.map((id) => [id, document.getElementById(id)]));

  const toneColors = {
    quiet: "#91a8b3",
    blue: "#77baff",
    green: "#75dba4",
    amber: "#ffb866",
    rose: "#ff91b2",
    violet: "#a999ff",
    cyan: "#64e7ef",
  };

  function currentModel() {
    return modelsById.get(state.modelId);
  }

  function html(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function svg(tag, attributes = {}, text) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [name, value] of Object.entries(attributes)) {
      if (value !== null && value !== undefined) node.setAttribute(name, String(value));
    }
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function clear(node) {
    node.replaceChildren();
  }

  function setElementHidden(node, hidden) {
    node.toggleAttribute("hidden", hidden);
  }

  function setText(node, value) {
    node.textContent = value;
  }

  function shortSha(value, length = 9) {
    return value.slice(0, length);
  }

  function actionById(model, actionId) {
    return model.actions.find((action) => action.id === actionId);
  }

  function stateSpaceNode(model, nodeId) {
    return model.stateSpace.nodes.find((node) => node.id === nodeId);
  }

  function curatedNode(model, nodeId) {
    return model.curated.nodes.find((node) => node.id === nodeId);
  }

  function currentScenario() {
    return currentModel().scenarios[state.scenarioIndex] || currentModel().scenarios[0];
  }

  function currentScenarioAction() {
    const scenario = currentScenario();
    return state.scenarioStep >= 0 ? scenario.steps[state.scenarioStep] : null;
  }

  function stopScenario() {
    if (state.scenarioTimer) window.clearInterval(state.scenarioTimer);
    state.scenarioTimer = null;
    elements.scenarioPlay.classList.remove("is-playing");
    elements.scenarioPlay.querySelector("span").textContent = "Play";
    elements.scenarioPlay.setAttribute("aria-label", "Play selected path");
  }

  function updateUrl(mode = "replace") {
    const url = new URL(window.location.href);
    if (state.modelId === data.models[0].id) url.searchParams.delete("model");
    else url.searchParams.set("model", state.modelId);
    if (state.view === "explain") url.searchParams.delete("view");
    else url.searchParams.set("view", state.view);
    if (state.selectedNode && state.view === "state-space") {
      url.searchParams.set("node", state.selectedNode);
    } else {
      url.searchParams.delete("node");
    }
    const historyState = { modelId: state.modelId, view: state.view, node: state.selectedNode };
    if (mode === "push") window.history.pushState(historyState, "", url);
    else window.history.replaceState(historyState, "", url);
  }

  function selectModel(modelId, historyMode = "push") {
    if (!modelsById.has(modelId) || modelId === state.modelId) return;
    stopScenario();
    state.modelId = modelId;
    state.selectedNode = null;
    state.selectedAction = null;
    state.scenarioIndex = 0;
    state.scenarioStep = -1;
    state.category = "all";
    renderAll();
    elements.visualStage.scrollLeft = 0;
    updateUrl(historyMode);
    document.querySelector(`[data-model-id="${modelId}"]`)?.focus({ preventScroll: true });
  }

  function selectView(view, historyMode = "push") {
    if (!validViews.has(view) || view === state.view) return;
    stopScenario();
    state.view = view;
    state.selectedNode = null;
    state.selectedAction = null;
    state.scenarioStep = -1;
    renderView();
    renderInspector();
    renderActionGrid();
    elements.visualStage.scrollLeft = 0;
    updateUrl(historyMode);
    elements.viewTabs.querySelector(`[data-view="${view}"]`)?.focus({ preventScroll: true });
  }

  function selectNode(nodeId, historyMode = "replace") {
    state.selectedNode = nodeId;
    state.selectedAction = null;
    renderView();
    renderInspector();
    renderActionGrid();
    updateUrl(historyMode);
  }

  function selectAction(actionId) {
    state.selectedAction = actionId;
    renderView();
    renderInspector();
    renderActionGrid();
  }

  function renderModelSwitcher() {
    clear(elements.modelSwitcher);
    for (const model of data.models) {
      const button = html("button", "", model.shortTitle);
      button.type = "button";
      button.dataset.modelId = model.id;
      button.setAttribute("aria-current", model.id === state.modelId ? "page" : "false");
      button.addEventListener("click", () => selectModel(model.id));
      elements.modelSwitcher.append(button);
    }
  }

  function renderHero() {
    const model = currentModel();
    setText(elements.modelEyebrow, model.eyebrow);
    setText(elements.modelTitle, model.title);
    setText(elements.modelSummary, model.summary);
    setText(elements.modelQuestion, model.question);
    setText(elements.heroStatus, model.check.status.toUpperCase());
    setText(
      elements.heroReceipt,
      `${number.format(model.check.distinctStates)} distinct · depth ${model.check.depth} · 0 states left`,
    );
    setText(elements.metricGenerated, number.format(model.check.generatedStates));
    setText(elements.metricDistinct, number.format(model.check.distinctStates));
    setText(elements.metricDepth, number.format(model.check.depth));
    setText(elements.metricActions, number.format(model.actions.length));
    setText(elements.metricProperties, number.format(model.safety.components.length + 1));
    elements.headerSourceLink.href = model.source.moduleUrl;
  }

  function renderViewTabs() {
    for (const button of elements.viewTabs.querySelectorAll("button")) {
      button.setAttribute("aria-selected", button.dataset.view === state.view ? "true" : "false");
      button.tabIndex = button.dataset.view === state.view ? 0 : -1;
    }
  }

  function addArrowDefinitions() {
    const defs = svg("defs");
    const muted = svg("marker", {
      id: "arrow-muted", viewBox: "0 0 10 10", refX: 8.5, refY: 5,
      markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse",
    });
    muted.append(svg("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "rgba(145,178,192,.5)" }));
    const active = svg("marker", {
      id: "arrow-active", viewBox: "0 0 10 10", refX: 8.5, refY: 5,
      markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse",
    });
    active.append(svg("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#64e7ef" }));
    defs.append(muted, active);
    elements.modelSvg.append(defs);
  }

  function pathBetween(from, to, self = false) {
    if (self) {
      return {
        d: `M ${from.x + 50} ${from.y - 36} C ${from.x + 102} ${from.y - 112}, ${from.x - 102} ${from.y - 112}, ${from.x - 50} ${from.y - 36}`,
        labelX: from.x,
        labelY: from.y - 104,
      };
    }
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const length = Math.max(Math.hypot(dx, dy), 1);
    const ux = dx / length;
    const uy = dy / length;
    const startX = from.x + ux * 76;
    const startY = from.y + uy * 42;
    const endX = to.x - ux * 79;
    const endY = to.y - uy * 43;
    const curve = Math.min(34, length * 0.08) * (Math.abs(dy) < 20 ? -1 : 1);
    const px = -uy * curve;
    const py = ux * curve;
    const midX = (startX + endX) / 2 + px;
    const midY = (startY + endY) / 2 + py;
    return {
      d: `M ${startX} ${startY} Q ${midX} ${midY} ${endX} ${endY}`,
      labelX: midX,
      labelY: midY + (Math.abs(dy) < 30 ? -52 : -7),
    };
  }

  function appendGraphNode(node, options = {}) {
    const width = options.width || 158;
    const height = options.height || 76;
    const group = svg("g", {
      class: [
        "model-node",
        options.selected ? "is-selected" : "",
        options.active ? "is-active" : "",
        options.muted ? "is-muted" : "",
      ].filter(Boolean).join(" "),
      transform: `translate(${node.x} ${node.y})`,
      tabindex: 0,
      role: "button",
      "aria-label": `${node.label}. ${node.description || ""}`,
      "data-node-id": node.id,
      style: `--node-color:${toneColors[node.tone] || toneColors.cyan}`,
    });
    group.append(
      svg("rect", { class: "node-glow", x: -width / 2, y: -height / 2, width, height, rx: 16 }),
      svg("rect", { class: "node-shell", x: -width / 2, y: -height / 2, width, height, rx: 14 }),
      svg("rect", { class: "node-accent", x: -width / 2, y: -height / 2, width: 3, height, rx: 2 }),
      svg("text", { class: "node-title", x: -width / 2 + 15, y: -8 }, node.label),
    );
    const kicker = options.kicker || node.kicker;
    if (kicker) {
      group.append(svg("text", { class: "node-kicker", x: -width / 2 + 15, y: 12 }, kicker));
    }
    if (options.count !== undefined) {
      group.append(
        svg("text", { class: "node-count", x: width / 2 - 14, y: -8, "text-anchor": "end" }, number.format(options.count)),
        svg("text", { class: "node-kicker", x: width / 2 - 14, y: 12, "text-anchor": "end" }, "states"),
      );
    }
    const activate = () => selectNode(node.id);
    group.addEventListener("click", activate);
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate();
      }
    });
    elements.modelSvg.append(group);
  }

  function renderExplainGraph(model) {
    clear(elements.modelSvg);
    setElementHidden(elements.modelSvg, false);
    setElementHidden(elements.propertiesView, true);
    elements.modelSvg.setAttribute("viewBox", "0 0 1000 600");
    addArrowDefinitions();
    const activeAction = currentScenarioAction() || state.selectedAction;

    if (model.curated.kind === "scope_structure") {
      const nodeMap = new Map(model.curated.nodes.map((node) => [node.id, node]));
      for (const edge of model.curated.edges) {
        const from = nodeMap.get(edge.from);
        const to = nodeMap.get(edge.to);
        const route = pathBetween(from, to);
        elements.modelSvg.append(
          svg("path", { class: "graph-edge is-structure", d: route.d }),
          svg("text", { class: "edge-label", x: route.labelX, y: route.labelY, "text-anchor": "middle" }, edge.label),
        );
      }
      elements.modelSvg.append(
        svg("text", { class: "phase-axis-label", x: 500, y: 570, "text-anchor": "middle" }, "NO ORDINARY AUTHORITY EDGE CROSSES A SCOPE BOUNDARY"),
      );
      for (const node of model.curated.nodes) {
        appendGraphNode(node, {
          width: 224,
          height: 92,
          selected: state.selectedNode === node.id,
          kicker: node.kicker,
        });
      }
      return;
    }

    const nodeMap = new Map(model.curated.nodes.map((node) => [node.id, node]));
    const activeTargets = new Set();
    for (const edge of model.curated.edges) {
      const from = nodeMap.get(edge.from);
      const to = nodeMap.get(edge.to);
      const isActive = activeAction && edge.actions.includes(activeAction);
      if (isActive) activeTargets.add(edge.to);
      const route = pathBetween(from, to, edge.from === edge.to);
      const path = svg("path", {
        class: `graph-edge${isActive ? " is-active" : ""}`,
        d: route.d,
        tabindex: 0,
        role: "button",
        "aria-label": edge.actions.join(", "),
      });
      const label = edge.label || (edge.actions.length === 1 ? edge.actions[0] : `${edge.actions.length} actions`);
      const labelNode = svg("text", {
        class: `edge-label${isActive ? " is-active" : ""}`,
        x: route.labelX,
        y: route.labelY,
        "text-anchor": "middle",
      }, label);
      const activate = () => selectAction(edge.actions[0]);
      path.addEventListener("click", activate);
      path.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
      elements.modelSvg.append(path, labelNode);
    }
    for (const node of model.curated.nodes) {
      const count = stateSpaceNode(model, node.id)?.concreteStates;
      appendGraphNode(node, {
        selected: state.selectedNode === node.id,
        active: activeTargets.has(node.id),
        count,
      });
    }
  }

  function combineTransitions(model) {
    const combined = new Map();
    for (const transition of model.stateSpace.transitions) {
      const key = `${transition.from}\u0000${transition.to}`;
      if (!combined.has(key)) {
        combined.set(key, {
          from: transition.from,
          to: transition.to,
          actions: new Set(),
          operators: new Set(),
          concreteTransitions: 0,
        });
      }
      const row = combined.get(key);
      row.actions.add(transition.action);
      row.operators.add(transition.operator);
      row.concreteTransitions += transition.concreteTransitions;
    }
    return [...combined.values()].map((row) => ({
      ...row,
      actions: [...row.actions].sort(),
      operators: [...row.operators].sort(),
    }));
  }

  function renderScalarStateSpace(model) {
    clear(elements.modelSvg);
    setElementHidden(elements.modelSvg, false);
    setElementHidden(elements.propertiesView, true);
    elements.modelSvg.setAttribute("viewBox", "0 0 1000 600");
    addArrowDefinitions();
    const positions = new Map(model.curated.nodes.map((node) => [node.id, node]));
    const transitions = combineTransitions(model);
    const selected = state.selectedNode;

    for (const transition of transitions) {
      const from = positions.get(transition.from);
      const to = positions.get(transition.to);
      if (!from || !to) continue;
      const related = !selected || transition.from === selected || transition.to === selected;
      const route = pathBetween(from, to, transition.from === transition.to);
      const path = svg("path", {
        class: `graph-edge${related && selected ? " is-active" : ""}${related ? "" : " is-muted"}`,
        d: route.d,
      });
      const actionLabel = transition.actions.length === 1
        ? transition.actions[0]
        : `${transition.actions.length} actions`;
      const label = `${actionLabel} · ${number.format(transition.concreteTransitions)}`;
      const labelNode = svg("text", {
        class: `edge-label${related && selected ? " is-active" : ""}`,
        x: route.labelX,
        y: route.labelY,
        "text-anchor": "middle",
        opacity: related ? 1 : 0.15,
      }, label);
      elements.modelSvg.append(path, labelNode);
    }

    for (const aggregate of model.stateSpace.nodes) {
      const node = positions.get(aggregate.id);
      if (!node) continue;
      const related = !selected || aggregate.id === selected || transitions.some(
        (transition) => (transition.from === selected && transition.to === aggregate.id)
          || (transition.to === selected && transition.from === aggregate.id),
      );
      appendGraphNode(node, {
        selected: selected === aggregate.id,
        muted: !related,
        count: aggregate.concreteStates,
      });
    }
  }

  function renderTupleMatrix(model) {
    clear(elements.modelSvg);
    setElementHidden(elements.modelSvg, false);
    setElementHidden(elements.propertiesView, true);
    elements.modelSvg.setAttribute("viewBox", "0 0 1000 650");
    const aggregation = model.stateSpace.aggregation;
    const values = aggregation.values;
    const dimensions = aggregation.dimensions;
    const markerDimension = dimensions[2] || null;
    const left = 142;
    const top = 96;
    const gridWidth = 820;
    const gridHeight = 470;
    const cellWidth = gridWidth / values.length;
    const cellHeight = gridHeight / values.length;
    const selected = state.selectedNode;
    const related = new Set();
    if (selected) {
      related.add(selected);
      for (const transition of model.stateSpace.transitions) {
        if (transition.from === selected) related.add(transition.to);
        if (transition.to === selected) related.add(transition.from);
      }
    }

    elements.modelSvg.append(
      svg("text", { class: "phase-axis-label", x: 535, y: 34, "text-anchor": "middle" }, `${dimensions[0]} phase →`),
      svg("text", { class: "phase-axis-label", x: 24, y: 335, transform: "rotate(-90 24 335)", "text-anchor": "middle" }, `${dimensions[1]} phase →`),
    );
    values.forEach((value, index) => {
      elements.modelSvg.append(
        svg("text", { class: "phase-axis-label", x: left + index * cellWidth + cellWidth / 2, y: 71, "text-anchor": "middle" }, value),
        svg("text", { class: "phase-axis-label", x: left - 16, y: top + index * cellHeight + cellHeight / 2 + 4, "text-anchor": "end" }, value),
      );
    });

    for (let row = 0; row < values.length; row += 1) {
      for (let column = 0; column < values.length; column += 1) {
        const x = left + column * cellWidth;
        const y = top + row * cellHeight;
        elements.modelSvg.append(
          svg("rect", { class: "phase-cell", x: x + 4, y: y + 4, width: cellWidth - 8, height: cellHeight - 8, rx: 12 }),
          svg("text", { class: "phase-cell-label", x: x + 14, y: y + 20 }, `${values[column]} / ${values[row]}`),
        );
      }
    }

    for (const aggregate of model.stateSpace.nodes) {
      const columnValue = aggregate.values[dimensions[0]];
      const rowValue = aggregate.values[dimensions[1]];
      const markerValue = markerDimension ? aggregate.values[markerDimension] : null;
      const column = values.indexOf(columnValue);
      const row = values.indexOf(rowValue);
      const markerIndex = markerDimension ? values.indexOf(markerValue) : 0;
      const markerCount = markerDimension ? values.length : 1;
      const angle = -Math.PI / 2 + (2 * Math.PI * markerIndex) / markerCount;
      const orbitX = markerDimension ? Math.min(32, cellWidth * 0.27) : 0;
      const orbitY = markerDimension ? Math.min(24, cellHeight * 0.24) : 0;
      const x = left + column * cellWidth + cellWidth / 2 + Math.cos(angle) * orbitX;
      const y = top + row * cellHeight + cellHeight / 2 + Math.sin(angle) * orbitY;
      const radius = Math.min(18, 6 + Math.sqrt(aggregate.concreteStates) * 0.75);
      const isRelated = !selected || related.has(aggregate.id);
      const group = svg("g", {
        class: [
          "phase-dot",
          selected === aggregate.id ? "is-selected" : "",
          selected && isRelated && selected !== aggregate.id ? "is-related" : "",
          isRelated ? "" : "is-muted",
        ].filter(Boolean).join(" "),
        transform: `translate(${x} ${y})`,
        tabindex: 0,
        role: "button",
        "aria-label": `${aggregate.label}; ${aggregate.concreteStates} concrete TLC states`,
        style: `--node-color:${toneColors[{
          Off: "quiet", Starting: "blue", Ready: "green", Crashed: "rose",
          Reaped: "violet", Fenced: "amber", Stopped: "rose", Retired: "quiet",
          PrivateStarting: "blue", PrivateReady: "blue", ProductionReady: "green",
          ProductionStarting: "amber", ReadyForAuthority: "blue",
        }[markerValue || rowValue] || "blue"]}`,
      });
      group.append(
        svg("circle", { r: radius }),
        svg("text", { x: 0, y: 2.5, "text-anchor": "middle" }, markerValue ? markerValue.slice(0, 1) : number.format(aggregate.concreteStates)),
      );
      const activate = () => selectNode(aggregate.id);
      group.addEventListener("click", activate);
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
      elements.modelSvg.append(group);
    }
    const tupleLabel = dimensions.join(" / ");
    const markerNote = markerDimension
      ? `Dot area is collapsed-state count; letter/color is ${markerDimension} phase.`
      : "Dot area and label show the number of complete TLC states collapsed into that tuple.";
    elements.modelSvg.append(
      svg("text", { class: "matrix-note", x: 142, y: 601 }, `Each dot is one reachable ${tupleLabel} phase tuple.`),
      svg("text", { class: "matrix-note", x: 142, y: 620 }, markerNote),
    );
  }

  function renderProperties(model) {
    setElementHidden(elements.modelSvg, true);
    setElementHidden(elements.propertiesView, false);
    clear(elements.propertiesView);

    const intro = html("div", "property-intro");
    const safety = html("article", "property-summary");
    safety.append(
      html("span", "", "Configured invariant"),
      html("strong", "", model.safety.configuredInvariant),
      html("p", "", `${model.safety.components.length} component predicates passed over all ${number.format(model.check.distinctStates)} distinct states.`),
    );
    const liveness = html("article", "liveness-card");
    liveness.append(
      html("span", "", "Configured temporal property"),
      html("strong", "", model.liveness.configuredProperty),
      html("p", "", model.liveness.description),
    );
    intro.append(safety, liveness);

    const propertyList = html("div", "property-list");
    for (const property of model.safety.components) {
      const item = html("article", "property-item");
      const link = html("a", "", property.id);
      link.href = property.sourceUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      item.append(link, html("p", "", property.description));
      propertyList.append(item);
    }

    const controls = data.negativeControls.filter((control) => control.model === model.id);
    const counterHeading = html("div", "counterexample-heading");
    counterHeading.append(
      html("span", "", "Mutation tests"),
      html("h3", "", `${controls.length} deliberately weakened control${controls.length === 1 ? "" : "s"} found a counterexample`),
    );
    const counterList = html("div", "counterexample-list");
    for (const control of controls) {
      const item = html("article", "counterexample-item");
      item.append(html("strong", "", control.title), html("p", "", control.description));
      const meta = html("div", "counterexample-meta");
      for (const label of [
        `violates ${control.violatedInvariant}`,
        `trace depth ${control.traceDepth}`,
        `${number.format(control.distinctStates)} distinct states`,
      ]) meta.append(html("span", "", label));
      item.append(meta);
      counterList.append(item);
    }
    elements.propertiesView.append(intro, propertyList, counterHeading, counterList);
  }

  function renderScenarioControls(model) {
    clear(elements.scenarioSelect);
    model.scenarios.forEach((scenario, index) => {
      const option = html("option", "", scenario.title);
      option.value = String(index);
      option.selected = index === state.scenarioIndex;
      elements.scenarioSelect.append(option);
    });
    elements.scenarioControls.hidden = state.view !== "explain";
    elements.scenarioStrip.hidden = state.view !== "explain";
    renderScenarioStrip();
  }

  function renderScenarioStrip() {
    clear(elements.scenarioStrip);
    const scenario = currentScenario();
    const copy = html("div", "scenario-copy");
    copy.append(html("strong", "", scenario.title), html("span", "", scenario.description));
    const steps = html("div", "scenario-steps");
    scenario.steps.forEach((action, index) => {
      const step = html("span", "scenario-step");
      if (index < state.scenarioStep) step.classList.add("is-past");
      if (index === state.scenarioStep) step.classList.add("is-current");
      step.append(html("i", ""), document.createTextNode(action));
      steps.append(step);
    });
    elements.scenarioStrip.append(copy, steps);
  }

  function renderLegend(model) {
    clear(elements.visualLegend);
    const items = state.view === "explain"
      ? [
          ["#a999ff", "Curated layout and prose"],
          ["#64e7ef", "Exact checked action names"],
          ["#75dba4", "Scenario path highlight"],
        ]
      : state.view === "state-space" && model.stateSpace.aggregation.kind === "tuple"
        ? [
            ["#64e7ef", "Generated from complete TLC DOT"],
            ["#77baff", `${model.stateSpace.aggregation.dimensions.join(" / ")} phase tuple`],
            ["#ffb866", "Dot size = collapsed TLC states"],
          ]
        : state.view === "state-space"
        ? [
            ["#64e7ef", "Generated from complete TLC DOT"],
            ["#77baff", `${number.format(model.stateSpace.concreteStates)} concrete states`],
            ["#ffb866", `${number.format(model.stateSpace.concreteTransitions)} concrete transitions`],
          ]
        : [
            ["#75dba4", "Passing configured property"],
            ["#ff91b2", "Expected counterexample from weakened guard"],
            ["#91a8b3", "Bounded model, not runtime conformance"],
          ];
    for (const [color, label] of items) {
      const item = html("span", "");
      const dot = html("i", "");
      dot.style.setProperty("--legend-color", color);
      item.append(dot, document.createTextNode(label));
      elements.visualLegend.append(item);
    }
  }

  function ensureDefaultSelection(model) {
    if (state.selectedAction) return;
    const validIds = state.view === "explain"
      ? new Set(model.curated.nodes.map((node) => node.id))
      : new Set(model.stateSpace.nodes.map((node) => node.id));
    if (!state.selectedNode || !validIds.has(state.selectedNode)) {
      if (state.view === "explain") state.selectedNode = model.curated.nodes[0]?.id || null;
      else if (model.stateSpace.aggregation.kind === "tuple") {
        const initialTuple = model.stateSpace.aggregation.dimensions
          .map(() => model.stateSpace.aggregation.values[0]).join("|");
        state.selectedNode = model.stateSpace.nodes.find((node) => node.id === initialTuple)?.id
          || model.stateSpace.nodes[0]?.id || null;
      } else state.selectedNode = model.stateSpace.nodes[0]?.id || null;
    }
  }

  function renderView() {
    const model = currentModel();
    elements.visualStage.classList.toggle("is-diagram", state.view !== "properties");
    renderViewTabs();
    renderScenarioControls(model);
    if (state.view === "explain") {
      ensureDefaultSelection(model);
      setText(elements.visualKicker, model.curated.label);
      setText(elements.visualTitle, model.curated.kind === "scope_structure" ? "Scope and authority topology" : "Lifecycle and action map");
      setText(elements.viewDisclosure, model.curated.disclaimer);
      renderExplainGraph(model);
    } else if (state.view === "state-space") {
      ensureDefaultSelection(model);
      setText(elements.visualKicker, "Automatically derived evidence");
      setText(elements.visualTitle, model.stateSpace.label);
      setText(elements.viewDisclosure, model.stateSpace.disclaimer);
      if (model.stateSpace.aggregation.kind === "tuple") renderTupleMatrix(model);
      else renderScalarStateSpace(model);
    } else {
      state.selectedNode = null;
      setText(elements.visualKicker, "Configured proof obligations");
      setText(elements.visualTitle, `${model.safety.configuredInvariant} + ${model.liveness.configuredProperty}`);
      setText(elements.viewDisclosure, data.explanation.proof);
      renderProperties(model);
    }
    renderLegend(model);
  }

  function appendFact(term, value) {
    const wrapper = html("div", "");
    wrapper.append(html("dt", "", term), html("dd", "", String(value)));
    elements.inspectorFacts.append(wrapper);
  }

  function appendInspectorAction(actionId, label = actionId) {
    const button = html("button", "inspector-action", label);
    button.type = "button";
    button.addEventListener("click", () => selectAction(actionId));
    elements.inspectorActions.append(button);
  }

  function showActionInspector(model, actionId) {
    const action = actionById(model, actionId);
    if (!action) return false;
    setText(elements.inspectorKicker, "TLA+ action");
    setText(elements.inspectorTitle, action.id);
    setText(elements.inspectorDescription, action.description);
    clear(elements.inspectorFacts);
    appendFact("Category", action.category);
    appendFact("Source", `${model.module}.tla:${action.sourceLine}`);
    appendFact("Principal reachability", action.reachableInPrincipal ? "reachable" : "disabled control");
    appendFact("TLC transitions", number.format(action.concreteTransitionCount));
    if (action.concreteLabels.length > 1) appendFact("Concrete labels", action.concreteLabels.join(", "));
    clear(elements.inspectorActions);
    const link = html("a", "inspector-action", "Open exact operator ↗");
    link.href = action.sourceUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    elements.inspectorActions.append(link);
    return true;
  }

  function renderInspector() {
    const model = currentModel();
    if (state.selectedAction && showActionInspector(model, state.selectedAction)) return;
    clear(elements.inspectorFacts);
    clear(elements.inspectorActions);

    if (state.view === "properties") {
      setText(elements.inspectorKicker, "Proof boundary");
      setText(elements.inspectorTitle, model.safety.configuredInvariant);
      setText(elements.inspectorDescription, data.explanation.proof);
      appendFact("SANY", model.check.sanyStatus.toUpperCase());
      appendFact("TLC", model.check.status.toUpperCase());
      appendFact("States left", model.check.statesLeft);
      appendFact("Safety predicates", model.safety.components.length);
      appendFact("Temporal properties", 1);
      const safetyLink = html("a", "inspector-action", "Open configured invariant ↗");
      safetyLink.href = model.safety.sourceUrl;
      safetyLink.target = "_blank";
      safetyLink.rel = "noopener noreferrer";
      elements.inspectorActions.append(safetyLink);
      return;
    }

    if (state.view === "explain") {
      const node = curatedNode(model, state.selectedNode) || model.curated.nodes[0];
      if (!node) return;
      setText(elements.inspectorKicker, model.curated.kind === "scope_structure" ? "Scope boundary" : "Explanatory state");
      setText(elements.inspectorTitle, node.label);
      setText(elements.inspectorDescription, node.description || "Curated explanatory node.");
      appendFact("View", "curated explanation");
      appendFact("Source binding", shortSha(model.source.moduleSha256));
      if (model.curated.kind === "state_action") {
        const aggregate = stateSpaceNode(model, node.id);
        if (aggregate) appendFact("TLC states here", number.format(aggregate.concreteStates));
        const outgoing = model.curated.edges.filter((edge) => edge.from === node.id);
        appendFact("Outgoing groups", outgoing.length);
        const actions = outgoing.flatMap((edge) => edge.actions);
        if (actions.length) {
          elements.inspectorActions.append(html("span", "", "Outgoing actions"));
          actions.forEach((action) => appendInspectorAction(action));
        }
      } else {
        const touching = model.curated.edges.filter((edge) => edge.from === node.id || edge.to === node.id);
        appendFact("Declared links", touching.length);
        elements.inspectorActions.append(html("span", "", "Model actions"));
        model.actions.slice(0, 5).forEach((action) => appendInspectorAction(action.id));
      }
      return;
    }

    const aggregate = stateSpaceNode(model, state.selectedNode) || model.stateSpace.nodes[0];
    if (!aggregate) return;
    const outgoing = model.stateSpace.transitions.filter((transition) => transition.from === aggregate.id);
    const incoming = model.stateSpace.transitions.filter((transition) => transition.to === aggregate.id);
    setText(elements.inspectorKicker, "TLC-derived aggregate");
    setText(elements.inspectorTitle, aggregate.label || aggregate.id);
    setText(
      elements.inspectorDescription,
      aggregate.description || `Complete TLC states collapsed only by ${model.stateSpace.aggregation.variable}.`,
    );
    appendFact("Concrete states", number.format(aggregate.concreteStates));
    appendFact("Incoming transitions", number.format(incoming.reduce((sum, row) => sum + row.concreteTransitions, 0)));
    appendFact("Outgoing transitions", number.format(outgoing.reduce((sum, row) => sum + row.concreteTransitions, 0)));
    appendFact("Aggregation", model.stateSpace.aggregation.variable);
    if (aggregate.values) {
      for (const [name, value] of Object.entries(aggregate.values)) appendFact(name, value);
    }
    const actions = [...new Set(outgoing.map((transition) => transition.operator))].sort();
    if (actions.length) {
      elements.inspectorActions.append(html("span", "", "Outgoing operators"));
      actions.slice(0, 10).forEach((action) => appendInspectorAction(action));
    }
  }

  function renderActionFilters() {
    const model = currentModel();
    clear(elements.actionFilter);
    const categories = ["all", ...new Set(model.actions.map((action) => action.category))];
    if (!categories.includes(state.category)) state.category = "all";
    for (const category of categories) {
      const button = html("button", category === state.category ? "is-active" : "", category);
      button.type = "button";
      button.addEventListener("click", () => {
        state.category = category;
        renderActionFilters();
        renderActionGrid();
      });
      elements.actionFilter.append(button);
    }
  }

  function renderActionGrid() {
    const model = currentModel();
    clear(elements.actionGrid);
    const actions = model.actions.filter(
      (action) => state.category === "all" || action.category === state.category,
    );
    for (const action of actions) {
      const card = html("button", `action-card${state.selectedAction === action.id ? " is-selected" : ""}`);
      card.type = "button";
      const top = html("div", "action-card-top");
      top.append(html("code", "", action.id));
      const category = html("span", `category-chip${action.category === "negative" ? " negative" : ""}`, action.category);
      top.append(category);
      card.append(top, html("p", "", action.description));
      const footer = html("footer", "");
      footer.append(
        html("span", "", `L${action.sourceLine}`),
        html(
          "span",
          action.reachableInPrincipal ? "" : "unreachable",
          action.reachableInPrincipal
            ? `${number.format(action.concreteTransitionCount)} TLC transitions`
            : "disabled in principal config",
        ),
      );
      card.append(footer);
      card.addEventListener("click", () => selectAction(action.id));
      elements.actionGrid.append(card);
    }
  }

  function renderEvidence() {
    const model = currentModel();
    setText(elements.curatedExplanation, data.explanation.curated);
    setText(elements.derivedExplanation, data.explanation.derived);
    setText(elements.proofExplanation, data.explanation.proof);
    setText(elements.receiptCommit, `${data.source.authority.gitTag} · ${data.source.repository}@${shortSha(data.source.commit)}`);
    setText(elements.receiptModule, `${model.source.modulePath} · SHA-256 ${shortSha(model.source.moduleSha256, 12)}`);
    setText(elements.receiptTooling, `${data.tooling.tlc[0]} · SANY ${model.check.sanyStatus}`);
    setText(elements.receiptJar, `tla2tools ${shortSha(data.tooling.tla2toolsSha256, 12)}`);
    setText(elements.receiptEvidence, `SHA-256 ${shortSha(data.source.evidenceSha256, 16)}`);
    setText(elements.receiptGenerated, data.source.evidenceGeneratedAtUtc);
    elements.receiptSourceLink.href = model.source.moduleUrl;
    setText(elements.footerBoundary, data.projection.boundary);
  }

  function renderAll() {
    renderModelSwitcher();
    renderHero();
    renderActionFilters();
    renderView();
    renderInspector();
    renderActionGrid();
    renderEvidence();
    updateUrl("replace");
  }

  elements.viewTabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-view]");
    if (button) selectView(button.dataset.view);
  });

  elements.viewTabs.addEventListener("keydown", (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    const buttons = [...elements.viewTabs.querySelectorAll("button")];
    const index = buttons.indexOf(document.activeElement);
    if (index < 0) return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const next = buttons[(index + direction + buttons.length) % buttons.length];
    selectView(next.dataset.view);
  });

  elements.scenarioSelect.addEventListener("change", () => {
    stopScenario();
    state.scenarioIndex = Number(elements.scenarioSelect.value);
    state.scenarioStep = -1;
    state.selectedAction = null;
    renderView();
    renderInspector();
    renderActionGrid();
  });

  elements.scenarioPlay.addEventListener("click", () => {
    if (state.scenarioTimer) {
      stopScenario();
      return;
    }
    const scenario = currentScenario();
    if (state.scenarioStep >= scenario.steps.length - 1) state.scenarioStep = -1;
    elements.scenarioPlay.querySelector("span").textContent = "Pause";
    elements.scenarioPlay.setAttribute("aria-label", "Pause selected path");
    elements.scenarioPlay.classList.add("is-playing");
    const advance = () => {
      state.scenarioStep += 1;
      if (state.scenarioStep >= scenario.steps.length) {
        state.scenarioStep = scenario.steps.length - 1;
        stopScenario();
        return;
      }
      state.selectedAction = scenario.steps[state.scenarioStep];
      renderExplainGraph(currentModel());
      renderScenarioStrip();
      renderInspector();
      renderActionGrid();
      if (state.scenarioStep === scenario.steps.length - 1) stopScenario();
    };
    advance();
    if (state.scenarioStep < scenario.steps.length - 1) {
      state.scenarioTimer = window.setInterval(advance, 900);
    }
  });

  window.addEventListener("popstate", () => {
    const next = new URLSearchParams(window.location.search);
    const modelId = modelsById.has(next.get("model")) ? next.get("model") : data.models[0].id;
    const view = validViews.has(next.get("view")) ? next.get("view") : "explain";
    stopScenario();
    state.modelId = modelId;
    state.view = view;
    state.selectedNode = next.get("node");
    state.selectedAction = null;
    state.scenarioIndex = 0;
    state.scenarioStep = -1;
    state.category = "all";
    renderAll();
  });

  renderAll();
})();

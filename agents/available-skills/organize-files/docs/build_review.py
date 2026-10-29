import json

TAXONOMY_PATH = "/Users/zbornheimer/.agents/skills/organize-files/data/taxonomy.json"

with open("/tmp/organize/desktop-tree.jsonl") as f:
    rows = [json.loads(line) for line in f if line.strip()]

with open(TAXONOMY_PATH) as f:
    taxonomy = json.load(f)

NODES_BY_ID = {n["id"]: n for n in taxonomy["nodes"]}


def leaf_label(node):
    """Derive a human label for a leaf node (label is always null in taxonomy.json)."""
    kind = node.get("leaf_kind")
    key = node.get("project_key", "") or ""
    if kind == "repo":
        name = key.rsplit("/", 1)[-1]
        return f"{name} repo"
    if kind == "linear":
        return key.removeprefix("linear:")
    if kind == "personal":
        name = key.removeprefix("personal:")
        return name.replace("-", " ").replace("_", " ").title()
    return node["id"].split(":", 1)[-1]


def node_label(node_id):
    node = NODES_BY_ID.get(node_id)
    if not node:
        return node_id
    if node.get("type") == "leaf":
        return leaf_label(node)
    return node.get("label") or node_id


def readable_tree_path(tree_path):
    if not tree_path:
        return ""
    return " › ".join(node_label(n) for n in tree_path)


def leaf_tooltip(row):
    node_id = row.get("node") or (row.get("tree_path") or [None])[-1]
    node = NODES_BY_ID.get(node_id) if node_id else None
    return (node or {}).get("criteria", "")


def area_and_product_labels(tree_path):
    area_label = None
    product_label = None
    for node_id in tree_path or []:
        if node_id.startswith("area:") and area_label is None:
            area_label = node_label(node_id)
        elif node_id.startswith("product:") and product_label is None:
            product_label = node_label(node_id)
    return area_label, product_label


def provisional_archive_dest(row):
    area_label, product_label = area_and_product_labels(row.get("tree_path") or [])
    if not area_label:
        return ""
    parts = ["~/Documents/Archive", area_label]
    if product_label:
        parts.append(product_label)
    return "/".join(parts)


def annotate(row):
    row = dict(row)
    row.setdefault("node", None)
    row.setdefault("tree_path", [])
    row.setdefault("resolved_depth", 0)
    row.setdefault("needs_triage", False)
    row.setdefault("needs_ticket", False)
    row.setdefault("needs_redaction", False)
    flags = row.get("flags") or {}
    row["flags"] = flags
    row["tree_path_readable"] = readable_tree_path(row["tree_path"])
    row["leaf_tooltip"] = leaf_tooltip(row)
    row["is_private"] = flags.get("private", 0) >= 0.5

    if row["disposition"] == "archive" and not row.get("destination_hint"):
        provisional = provisional_archive_dest(row)
        if provisional:
            row["destination_hint"] = provisional
            row["destination_provisional"] = True
    row.setdefault("destination_provisional", False)

    # legacy field some existing UI logic relies on
    row["low_conf"] = row.get("resolved_depth", 0) == 0

    return row


rows = [annotate(r) for r in rows]

DATA_JSON = json.dumps(rows)

GROUP_ORDER = [
    "trash-candidate",
    "attach-evidence",
    "file-to-linear",
    "move-to-repo",
    "personal-docs",
    "archive",
    "keep",
]
GROUP_LABELS = {
    "trash-candidate": "Trash candidate",
    "attach-evidence": "Attach evidence",
    "file-to-linear": "File to Linear",
    "move-to-repo": "Move to repo",
    "personal-docs": "Personal docs",
    "archive": "Archive",
    "keep": "Keep",
}

KEEP_SUBGROUP_ORDER = ["needs-triage", "unsure", "rest"]
KEEP_SUBGROUP_LABELS = {
    "needs-triage": "Needs triage",
    "unsure": "Unsure",
    "rest": "Resolved",
}

html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Desktop cleanup review</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f7f7f8;
    --panel: #ffffff;
    --border: #dcdfe4;
    --text: #1b1e24;
    --text-dim: #5b6270;
    --accent: #2563eb;
    --warn-bg: #fff3f0;
    --warn-border: #e5533d;
    --warn-text: #9c2e1c;
    --unsure-bg: #fff8e1;
    --unsure-border: #c99a1a;
    --chip-bg: #eef0f4;
    --row-hover: #f0f4ff;
    --badge-ticket-bg: #eaf1ff;
    --badge-ticket-border: #2563eb;
    --badge-ticket-text: #1d4ed8;
    --badge-redact-bg: #fdeef0;
    --badge-redact-border: #c8264c;
    --badge-redact-text: #9c1638;
    --badge-private-bg: #f1eefd;
    --badge-private-border: #6d3fd6;
    --badge-private-text: #4b1fa3;
    --mono: "SF Mono", "Menlo", "Consolas", monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #14161a;
      --panel: #1c1f26;
      --border: #30343d;
      --text: #e7e9ee;
      --text-dim: #9aa1ae;
      --accent: #7fa8ff;
      --warn-bg: #2c1712;
      --warn-border: #b8452f;
      --warn-text: #ff9c86;
      --unsure-bg: #2a2410;
      --unsure-border: #a3801f;
      --chip-bg: #262a33;
      --row-hover: #232838;
      --badge-ticket-bg: #16233d;
      --badge-ticket-border: #5c8bff;
      --badge-ticket-text: #a9c4ff;
      --badge-redact-bg: #391720;
      --badge-redact-border: #d95a78;
      --badge-redact-text: #ffb3c4;
      --badge-private-bg: #241a3d;
      --badge-private-border: #9a7be0;
      --badge-private-text: #d3c3ff;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 13px;
    line-height: 1.4;
  }
  header {
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    padding: 10px 16px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  header h1 {
    font-size: 15px;
    margin: 0;
    white-space: nowrap;
  }
  header .stats { color: var(--text-dim); font-size: 12px; white-space: nowrap; }
  header input[type="text"] {
    flex: 1;
    min-width: 160px;
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--bg);
    color: var(--text);
    font-size: 13px;
  }
  header label {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    white-space: nowrap;
    cursor: pointer;
  }
  header button {
    padding: 6px 12px;
    border: 1px solid var(--accent);
    background: var(--accent);
    color: #fff;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    white-space: nowrap;
  }
  header button:active { transform: translateY(1px); }
  header button.copied { background: #1a9c5a; border-color: #1a9c5a; }

  /* header is sticky but not tall/fixed-height; anchor sticky thead below its
     actual rendered height via JS-set --header-h rather than a hardcoded px */
  main { padding: 12px 16px 60px; }

  .group { margin-bottom: 22px; }
  .group-title {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 4px 0 6px;
    border-bottom: 2px solid var(--border);
    margin-bottom: 6px;
  }
  .group-title h2 { font-size: 14px; margin: 0; text-transform: uppercase; letter-spacing: 0.03em; }
  .group-title .count { color: var(--text-dim); font-size: 12px; }
  .group-title.trash-candidate h2 { color: var(--warn-text); }

  .subgroup { margin: 10px 0 16px; }
  .subgroup-title {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 2px 0 4px;
    margin-bottom: 4px;
  }
  .subgroup-title h3 {
    font-size: 12px;
    margin: 0;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .subgroup-title .count { color: var(--text-dim); font-size: 11px; }

  table { width: 100%; border-collapse: collapse; }
  thead th {
    text-align: left;
    font-size: 11px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    padding: 4px 8px;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: var(--header-h, 45px);
    background: var(--bg);
  }
  tbody tr {
    border-bottom: 1px solid var(--border);
  }
  tbody tr:hover { background: var(--row-hover); }
  tbody tr.warn { background: var(--warn-bg); }
  tbody tr.warn:hover { background: var(--warn-bg); filter: brightness(1.05); }
  tbody tr.unsure td.name::after {
    content: "unsure";
    margin-left: 6px;
    font-size: 10px;
    padding: 1px 5px;
    border-radius: 4px;
    background: var(--unsure-bg);
    border: 1px solid var(--unsure-border);
    color: var(--unsure-border);
    vertical-align: middle;
  }
  td { padding: 5px 8px; vertical-align: top; }
  td.name { font-family: var(--mono); font-size: 12px; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  td.kind { color: var(--text-dim); white-space: nowrap; }
  td.project { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: help; }
  td.dest { font-family: var(--mono); font-size: 11px; color: var(--text-dim); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  td.conf { white-space: nowrap; font-variant-numeric: tabular-nums; }
  td.reason { color: var(--text-dim); max-width: 260px; }
  .reason-cell { display: flex; align-items: center; gap: 0; min-width: 0; }
  .reason-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; flex: 0 1 auto; }
  td.decision { white-space: nowrap; }

  .chip {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 4px;
    background: var(--chip-bg);
    font-size: 11px;
  }
  .provisional-tag {
    display: inline-block;
    margin-left: 4px;
    font-size: 10px;
    color: var(--text-dim);
    font-style: italic;
  }

  .badges { display: inline-flex; gap: 4px; margin-left: 6px; vertical-align: middle; flex: 0 0 auto; }
  .badge {
    display: inline-block;
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 10px;
    border: 1px solid;
    white-space: nowrap;
  }
  .badge-ticket { background: var(--badge-ticket-bg); border-color: var(--badge-ticket-border); color: var(--badge-ticket-text); }
  .badge-redact { background: var(--badge-redact-bg); border-color: var(--badge-redact-border); color: var(--badge-redact-text); }
  .badge-private { background: var(--badge-private-bg); border-color: var(--badge-private-border); color: var(--badge-private-text); }

  .decision-controls { display: flex; gap: 4px; align-items: center; flex-wrap: nowrap; }
  .decision-controls select, .decision-controls input[type="text"] {
    font-size: 11px;
    padding: 3px 4px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--panel);
    color: var(--text);
  }
  .decision-controls input[type="text"] { width: 110px; }
  .btn-approve, .btn-skip {
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text);
    cursor: pointer;
  }
  .btn-approve.active { background: #1a9c5a; border-color: #1a9c5a; color: #fff; }
  .btn-skip.active { background: var(--text-dim); border-color: var(--text-dim); color: #fff; }
  .note-input {
    font-size: 11px;
    width: 90px;
    padding: 3px 4px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--panel);
    color: var(--text);
  }

  .empty-msg { color: var(--text-dim); padding: 10px 0; font-style: italic; }
  /* Static, not fixed: a fixed footer would permanently occupy the bottom of
     every scroll position and cover whichever group's rows happen to land
     there. A footer at the true end of the document never covers content. */
  footer { background: var(--panel); border-top: 1px solid var(--border); padding: 6px 16px; font-size: 11px; color: var(--text-dim); }
</style>
</head>
<body>
<header>
  <h1>Desktop cleanup review</h1>
  <span class="stats" id="stats"></span>
  <input type="text" id="filterBox" placeholder="Filter by name, project, reason…">
  <label><input type="checkbox" id="unsureOnly"> unsure only</label>
  <label><input type="checkbox" id="touchedOnly"> touched only</label>
  <button id="copyBtn">Copy decisions as JSON</button>
</header>
<main id="main"></main>
<footer>Read-only review. Nothing on ~/Desktop is moved, opened, or deleted by this page. Decisions are stored only in this tab until you copy them out.</footer>

<script id="row-data" type="application/json">__DATA_JSON__</script>
<script>
const ROWS = JSON.parse(document.getElementById('row-data').textContent);
const GROUP_ORDER = __GROUP_ORDER_JSON__;
const GROUP_LABELS = __GROUP_LABELS_JSON__;
const KEEP_SUBGROUP_ORDER = __KEEP_SUBGROUP_ORDER_JSON__;
const KEEP_SUBGROUP_LABELS = __KEEP_SUBGROUP_LABELS_JSON__;
const DISPOSITIONS = GROUP_ORDER;

const decisions = {}; // path -> {action, project, disposition, note}

function rowId(r, i) { return i; }

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function basename(p) {
  const parts = p.split('/');
  return parts[parts.length - 1] || p;
}

function keepSubgroup(r) {
  if (r.needs_triage) return 'needs-triage';
  if ((r.resolved_depth || 0) === 0) return 'unsure';
  return 'rest';
}

function buildDecisionCell(r, idx) {
  const wrap = document.createElement('div');
  wrap.className = 'decision-controls';

  const approveBtn = document.createElement('button');
  approveBtn.className = 'btn-approve';
  approveBtn.textContent = 'Approve';
  approveBtn.title = 'Approve the suggested action as-is';

  const skipBtn = document.createElement('button');
  skipBtn.className = 'btn-skip';
  skipBtn.textContent = "Don't touch";

  const projInput = document.createElement('input');
  projInput.type = 'text';
  projInput.placeholder = 'project override';
  projInput.value = '';

  const dispSelect = document.createElement('select');
  const blankOpt = document.createElement('option');
  blankOpt.value = '';
  blankOpt.textContent = 'action override…';
  dispSelect.appendChild(blankOpt);
  DISPOSITIONS.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d;
    opt.textContent = GROUP_LABELS[d];
    dispSelect.appendChild(opt);
  });

  const noteInput = document.createElement('input');
  noteInput.type = 'text';
  noteInput.className = 'note-input';
  noteInput.placeholder = 'note';

  function currentDecision() {
    return decisions[r.path];
  }

  function setDecision(action) {
    if (action === null) {
      delete decisions[r.path];
    } else {
      const d = decisions[r.path] || { action: null, project: '', disposition: '', note: '' };
      d.action = action;
      decisions[r.path] = d;
    }
    refreshButtons();
    updateStats();
  }

  function refreshButtons() {
    const d = currentDecision();
    approveBtn.classList.toggle('active', !!d && d.action === 'approve');
    skipBtn.classList.toggle('active', !!d && d.action === 'skip');
  }

  approveBtn.addEventListener('click', () => {
    const d = currentDecision();
    setDecision(d && d.action === 'approve' ? null : 'approve');
  });
  skipBtn.addEventListener('click', () => {
    const d = currentDecision();
    setDecision(d && d.action === 'skip' ? null : 'skip');
  });
  projInput.addEventListener('input', () => {
    if (!projInput.value && !dispSelect.value && !noteInput.value) { setDecision(null); return; }
    const d = decisions[r.path] || { action: 'change-project', project: '', disposition: '', note: '' };
    d.project = projInput.value;
    if (!d.action || d.action === 'approve' || d.action === 'skip') d.action = 'change-project';
    decisions[r.path] = d;
    updateStats();
  });
  dispSelect.addEventListener('change', () => {
    if (!projInput.value && !dispSelect.value && !noteInput.value) { setDecision(null); return; }
    const d = decisions[r.path] || { action: 'change-action', project: '', disposition: '', note: '' };
    d.disposition = dispSelect.value;
    if (dispSelect.value) d.action = 'change-action';
    decisions[r.path] = d;
    updateStats();
  });
  noteInput.addEventListener('input', () => {
    if (!projInput.value && !dispSelect.value && !noteInput.value) {
      const d = decisions[r.path];
      if (d) { d.note = ''; if (!d.action) delete decisions[r.path]; }
      updateStats();
      return;
    }
    const d = decisions[r.path] || { action: currentDecision() ? currentDecision().action : null, project: '', disposition: '', note: '' };
    d.note = noteInput.value;
    decisions[r.path] = d;
    updateStats();
  });

  wrap.appendChild(approveBtn);
  wrap.appendChild(skipBtn);
  wrap.appendChild(dispSelect);
  wrap.appendChild(projInput);
  wrap.appendChild(noteInput);
  return wrap;
}

function buildRow(r, i, g) {
  const tr = document.createElement('tr');
  tr.setAttribute('data-path', r.path);
  if (g === 'trash-candidate') tr.classList.add('warn');
  if (r.low_conf) tr.classList.add('unsure');

  const tdName = document.createElement('td');
  tdName.className = 'name';
  tdName.textContent = basename(r.path);
  tdName.title = r.path;
  tr.appendChild(tdName);

  const tdKind = document.createElement('td');
  tdKind.className = 'kind';
  tdKind.innerHTML = `<span class="chip">${escapeHtml(r.kind)}</span>`;
  tr.appendChild(tdKind);

  const tdProj = document.createElement('td');
  tdProj.className = 'project';
  const pathLabel = r.tree_path_readable || r.project || '—';
  tdProj.textContent = pathLabel;
  if (r.leaf_tooltip) tdProj.title = r.leaf_tooltip;
  else if (r.project_desc) tdProj.title = r.project_desc;
  tr.appendChild(tdProj);

  const tdDest = document.createElement('td');
  tdDest.className = 'dest';
  tdDest.textContent = r.destination_hint || '—';
  if (r.destination_provisional && r.destination_hint) {
    tdDest.textContent = r.destination_hint;
    const tag = document.createElement('span');
    tag.className = 'provisional-tag';
    tag.textContent = 'provisional';
    tdDest.appendChild(tag);
    tdDest.title = 'Destination not yet decided — provisional guess: ' + r.destination_hint;
  } else {
    tdDest.title = r.destination_hint || '';
  }
  tr.appendChild(tdDest);

  const tdConf = document.createElement('td');
  tdConf.className = 'conf';
  tdConf.textContent = (typeof r.confidence === 'number') ? r.confidence.toFixed(2) : '—';
  tr.appendChild(tdConf);

  const tdReason = document.createElement('td');
  tdReason.className = 'reason';
  tdReason.title = r.reason || '';
  const reasonCell = document.createElement('div');
  reasonCell.className = 'reason-cell';
  const reasonText = document.createElement('span');
  reasonText.className = 'reason-text';
  reasonText.textContent = r.reason || '';
  reasonCell.appendChild(reasonText);
  const badges = document.createElement('span');
  badges.className = 'badges';
  if (r.needs_ticket) {
    const b = document.createElement('span');
    b.className = 'badge badge-ticket';
    b.textContent = 'ticket';
    b.title = 'Needs a Linear ticket filed';
    badges.appendChild(b);
  }
  if (r.needs_redaction) {
    const b = document.createElement('span');
    b.className = 'badge badge-redact';
    b.textContent = 'redact';
    b.title = 'Needs redaction before sharing/archiving';
    badges.appendChild(b);
  }
  if (r.is_private) {
    const b = document.createElement('span');
    b.className = 'badge badge-private';
    b.textContent = 'private';
    b.title = 'Flagged as likely private/sensitive';
    badges.appendChild(b);
  }
  if (badges.childNodes.length) reasonCell.appendChild(badges);
  tdReason.appendChild(reasonCell);
  tr.appendChild(tdReason);

  const tdDecision = document.createElement('td');
  tdDecision.className = 'decision';
  tdDecision.appendChild(buildDecisionCell(r, i));
  tr.appendChild(tdDecision);

  return tr;
}

function buildTable(items, g) {
  const table = document.createElement('table');
  table.innerHTML = `<thead><tr>
    <th>File</th><th>Kind</th><th>Suggested project</th><th>Destination hint</th>
    <th>Conf.</th><th>Reason</th><th>Your decision</th>
  </tr></thead>`;
  const tbody = document.createElement('tbody');
  items.forEach(({ r, i }) => tbody.appendChild(buildRow(r, i, g)));
  table.appendChild(tbody);
  return table;
}

function render() {
  const filterText = document.getElementById('filterBox').value.toLowerCase();
  const unsureOnly = document.getElementById('unsureOnly').checked;
  const touchedOnly = document.getElementById('touchedOnly').checked;
  const main = document.getElementById('main');
  main.innerHTML = '';

  const byGroup = {};
  GROUP_ORDER.forEach(g => byGroup[g] = []);

  ROWS.forEach((r, i) => {
    const disp = GROUP_ORDER.includes(r.disposition) ? r.disposition : 'keep';
    const hay = (r.path + ' ' + r.project + ' ' + (r.tree_path_readable || '') + ' ' + r.reason + ' ' + r.kind + ' ' + r.destination_hint).toLowerCase();
    if (filterText && !hay.includes(filterText)) return;
    if (unsureOnly && !r.low_conf) return;
    if (touchedOnly && !decisions[r.path]) return;
    byGroup[disp].push({ r, i });
  });

  let totalShown = 0;
  GROUP_ORDER.forEach(g => {
    const items = byGroup[g];
    totalShown += items.length;
    const section = document.createElement('section');
    section.className = 'group';

    const titleRow = document.createElement('div');
    titleRow.className = 'group-title' + (g === 'trash-candidate' ? ' trash-candidate' : '');
    titleRow.innerHTML = `<h2>${escapeHtml(GROUP_LABELS[g])}</h2><span class="count">${items.length}</span>`;
    section.appendChild(titleRow);

    if (items.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-msg';
      empty.textContent = 'No rows in this group.';
      section.appendChild(empty);
      main.appendChild(section);
      return;
    }

    if (g === 'keep') {
      const bySub = {};
      KEEP_SUBGROUP_ORDER.forEach(s => bySub[s] = []);
      items.forEach(item => bySub[keepSubgroup(item.r)].push(item));

      KEEP_SUBGROUP_ORDER.forEach(sub => {
        const subItems = bySub[sub];
        const subSection = document.createElement('div');
        subSection.className = 'subgroup';

        const subTitle = document.createElement('div');
        subTitle.className = 'subgroup-title';
        subTitle.innerHTML = `<h3>${escapeHtml(KEEP_SUBGROUP_LABELS[sub])}</h3><span class="count">${subItems.length}</span>`;
        subSection.appendChild(subTitle);

        if (subItems.length === 0) {
          const empty = document.createElement('div');
          empty.className = 'empty-msg';
          empty.textContent = 'No rows in this group.';
          subSection.appendChild(empty);
        } else {
          subSection.appendChild(buildTable(subItems, g));
        }
        section.appendChild(subSection);
      });
    } else {
      section.appendChild(buildTable(items, g));
    }

    main.appendChild(section);
  });

  updateStats(totalShown);
}

function updateStats(shownCount) {
  const total = ROWS.length;
  const touched = Object.keys(decisions).length;
  const shown = (typeof shownCount === 'number') ? shownCount : document.querySelectorAll('tbody tr').length;
  document.getElementById('stats').textContent = `${total} items · ${shown} shown · ${touched} decided`;
}

function syncHeaderHeight() {
  const header = document.querySelector('header');
  document.documentElement.style.setProperty('--header-h', header.offsetHeight + 'px');
}

document.getElementById('filterBox').addEventListener('input', render);
document.getElementById('unsureOnly').addEventListener('change', render);
document.getElementById('touchedOnly').addEventListener('change', render);
window.addEventListener('resize', syncHeaderHeight);

document.getElementById('copyBtn').addEventListener('click', () => {
  const out = ROWS.filter(r => decisions[r.path]).map(r => {
    const d = decisions[r.path];
    return {
      path: r.path,
      suggested: { project: r.project, disposition: r.disposition },
      decision: {
        action: d.action || null,
        project: d.project || null,
        disposition: d.disposition || null,
        note: d.note || null
      }
    };
  });
  const json = JSON.stringify(out, null, 2);
  navigator.clipboard.writeText(json).then(() => {
    const btn = document.getElementById('copyBtn');
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = orig; btn.classList.remove('copied'); }, 1500);
  }).catch(() => {
    alert(json);
  });
});

syncHeaderHeight();
render();
</script>
</body>
</html>
"""

html = html.replace("__DATA_JSON__", DATA_JSON)
html = html.replace("__GROUP_ORDER_JSON__", json.dumps(GROUP_ORDER))
html = html.replace("__GROUP_LABELS_JSON__", json.dumps(GROUP_LABELS))
html = html.replace("__KEEP_SUBGROUP_ORDER_JSON__", json.dumps(KEEP_SUBGROUP_ORDER))
html = html.replace("__KEEP_SUBGROUP_LABELS_JSON__", json.dumps(KEEP_SUBGROUP_LABELS))

with open("/tmp/organize/review.html", "w") as f:
    f.write(html)

print("wrote", len(html), "bytes")

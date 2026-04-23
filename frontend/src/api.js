async function handle(resp) {
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (body?.detail) detail = body.detail;
    } catch {}
    throw new Error(detail);
  }
  return resp.json();
}

export function getReports() {
  return fetch("/api/reports").then(handle);
}

export function getDivisions() {
  return fetch("/api/divisions").then(handle);
}

export function getFirstPitchOffspeedMeta() {
  return fetch("/api/first-pitch-offspeed/meta").then(handle);
}

export function computeFirstPitchOffspeed(params) {
  return fetch("/api/first-pitch-offspeed/compute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  }).then(handle);
}

// -- v2: Phase 1 pipeline endpoints -----------------------------------------

function qs(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    p.set(k, v);
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function getSeasons() {
  return fetch("/api/v2/seasons").then(handle);
}

export function getPitchTypes() {
  return fetch("/api/v2/pitch-types").then(handle);
}

export function searchPitchers({ season, q, limit = 20 } = {}) {
  return fetch("/api/v2/pitchers" + qs({ season, q, limit })).then(handle);
}

export function searchBatters({ season, q, limit = 20 } = {}) {
  return fetch("/api/v2/batters" + qs({ season, q, limit })).then(handle);
}

export function getPitcherSequences(pitcherId, params) {
  return fetch(
    `/api/v2/sequences/pitcher/${pitcherId}` + qs(params)
  ).then(handle);
}

export function getBatterSequences(batterId, params) {
  return fetch(
    `/api/v2/sequences/batter/${batterId}` + qs(params)
  ).then(handle);
}

export function getSequenceLeaderboard(params) {
  return fetch("/api/v2/sequences/leaderboard" + qs(params)).then(handle);
}

export function getMatchupPairing(pitcherId, batterId, params) {
  return fetch(
    `/api/v2/matchup/pairing/${pitcherId}/${batterId}` + qs(params)
  ).then(handle);
}

export function getTopEdges(params) {
  return fetch("/api/v2/matchup/edges/top" + qs(params)).then(handle);
}

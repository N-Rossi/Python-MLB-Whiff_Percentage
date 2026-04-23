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

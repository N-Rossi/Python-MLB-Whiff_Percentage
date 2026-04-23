import { useMemo } from "react";

const LOC_LABELS = [
  ["All", null],
  ["In zone (1–9)", "in"],
  ["Out of zone (11–14)", "out"],
];
const PLAT_LABELS = [
  ["All", null],
  ["Same hand (L/L or R/R)", "same"],
  ["Opposite hand", "opp"],
];
const PHAND_LABELS = [
  ["All", null],
  ["RHP only", "R"],
  ["LHP only", "L"],
];

function Radio({ options, value, onChange }) {
  return (
    <div className="radio-row">
      {options.map(([label, v]) => (
        <button
          key={String(v)}
          className={value === v ? "active" : ""}
          onClick={() => onChange(v)}
          type="button"
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function NumberInput({ value, onChange, min = 0, max = 500, step = 1 }) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={(e) => {
        const v = e.target.value;
        onChange(v === "" ? 0 : Number(v));
      }}
    />
  );
}

export default function Sidebar({ state, setState, meta }) {
  const offspeedTypes = meta.offspeed_pitch_types;
  const labels = meta.pitch_type_labels;
  const fastballTypes = meta.fastball_types;
  const nonOffspeed = meta.non_offspeed;

  const allTypesSelected = useMemo(
    () =>
      state.pitchTypes.length === offspeedTypes.length &&
      offspeedTypes.every((t) => state.pitchTypes.includes(t)),
    [state.pitchTypes, offspeedTypes]
  );

  const toggle = (list, v) =>
    list.includes(v) ? list.filter((x) => x !== v) : [...list, v];

  return (
    <aside className="sidebar">
      <h3>Pitch-level slicers</h3>
      <div className="caption">
        Filter which pitches count toward the headline and breakdowns. Velo and
        VSep are X-variables — they show up as columns in the per-pitch table,
        not as slicers.
      </div>

      <label>Pitch type</label>
      <div className="multiselect">
        <label>
          <input
            type="checkbox"
            checked={allTypesSelected}
            onChange={() =>
              setState({
                ...state,
                pitchTypes: allTypesSelected ? [] : [...offspeedTypes],
              })
            }
          />
          <strong>All</strong>
        </label>
        {offspeedTypes.map((t) => (
          <label key={t}>
            <input
              type="checkbox"
              checked={state.pitchTypes.includes(t)}
              onChange={() =>
                setState({
                  ...state,
                  pitchTypes: toggle(state.pitchTypes, t),
                })
              }
            />
            {t} — {labels[t] || t}
          </label>
        ))}
      </div>

      <label>Location</label>
      <Radio
        options={LOC_LABELS}
        value={state.location}
        onChange={(v) => setState({ ...state, location: v })}
      />

      <label>Platoon</label>
      <Radio
        options={PLAT_LABELS}
        value={state.platoon}
        onChange={(v) => setState({ ...state, platoon: v })}
      />

      <label>Pitcher handedness</label>
      <Radio
        options={PHAND_LABELS}
        value={state.pThrows}
        onChange={(v) => setState({ ...state, pThrows: v })}
      />

      <details className="expander">
        <summary>Sample-size & eligibility (plumbing)</summary>
        <div>
          <label>
            <input
              type="checkbox"
              checked={state.useVeloFloor}
              onChange={(e) =>
                setState({ ...state, useVeloFloor: e.target.checked })
              }
            />{" "}
            Use velo floor
          </label>
          <label>Velo floor (mph): {state.veloFloor.toFixed(1)}</label>
          <input
            type="range"
            min="85"
            max="95"
            step="0.1"
            value={state.veloFloor}
            disabled={!state.useVeloFloor}
            onChange={(e) =>
              setState({ ...state, veloFloor: Number(e.target.value) })
            }
          />

          <label>Min fastballs (FF/SI/FT) per pitcher</label>
          <NumberInput
            value={state.minFastballs}
            onChange={(v) => setState({ ...state, minFastballs: v })}
            max={500}
            step={10}
          />

          <label>Min 4-seamers (FF) for VSep</label>
          <NumberInput
            value={state.min4seam}
            onChange={(v) => setState({ ...state, min4seam: v })}
            max={500}
            step={10}
          />

          <label>Min offspeed pitches for VSep</label>
          <NumberInput
            value={state.minOffspeed}
            onChange={(v) => setState({ ...state, minOffspeed: v })}
            max={500}
            step={10}
          />

          <label>Min 1st-pitch OS swings (filtered)</label>
          <NumberInput
            value={state.minSwings}
            onChange={(v) => setState({ ...state, minSwings: v })}
            max={100}
            step={1}
          />

          <label>Min 1st-pitch OS pitches (filtered)</label>
          <NumberInput
            value={state.minPitches}
            onChange={(v) => setState({ ...state, minPitches: v })}
            max={200}
            step={1}
          />
        </div>
      </details>

      <hr />
      <div className="caption">
        <strong>Fastball</strong> = {fastballTypes.join(", ")}
        <br />
        <strong>Offspeed</strong> = anything not in {nonOffspeed.join(", ")}
        <br />
        <strong>Whiff %</strong> = swinging strikes / total swings
        <br />
        <strong>CSW %</strong> = (called strikes + whiffs) / total pitches
        <br />
        <strong>Lead</strong> = <code>pitch_number == 1</code>
      </div>
    </aside>
  );
}

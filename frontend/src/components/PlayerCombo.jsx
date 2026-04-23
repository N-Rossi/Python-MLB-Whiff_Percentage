import { useEffect, useRef, useState } from "react";

/**
 * Debounced typeahead for picking a player by name.
 *
 * Props:
 *   label         — form label above the combo
 *   value         — currently-selected player: { id, name } | null
 *   onChange      — setter called with the chosen player (or null when cleared)
 *   fetchPlayers  — (query) => Promise<{ players: [{id,name}, ...] }>
 *                   Component handles its own debouncing and in-flight cancel.
 *   placeholder   — input placeholder text
 */
export default function PlayerCombo({
  label,
  value,
  onChange,
  fetchPlayers,
  placeholder = "type to search…",
}) {
  const [text, setText] = useState(value ? value.name : "");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef();
  const tokenRef = useRef(0);
  const rootRef = useRef(null);

  // Keep input in sync when `value` is cleared from the outside.
  useEffect(() => {
    if (!value) setText("");
    else setText(value.name);
  }, [value]);

  // Close on outside click.
  useEffect(() => {
    function onDocClick(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function handleInput(e) {
    const q = e.target.value;
    setText(q);
    setOpen(true);
    clearTimeout(debounceRef.current);
    const myToken = ++tokenRef.current;
    debounceRef.current = setTimeout(() => {
      setLoading(true);
      fetchPlayers(q)
        .then((d) => {
          if (myToken === tokenRef.current) {
            setResults(d.players || []);
          }
        })
        .catch(() => {
          if (myToken === tokenRef.current) setResults([]);
        })
        .finally(() => {
          if (myToken === tokenRef.current) setLoading(false);
        });
    }, 200);
  }

  function pick(p) {
    onChange(p);
    setText(p.name);
    setOpen(false);
  }

  function clear() {
    onChange(null);
    setText("");
    setResults([]);
  }

  return (
    <div className="combo" ref={rootRef}>
      {label && <label>{label}</label>}
      <div className="combo-input-wrap">
        <input
          type="text"
          value={text}
          onChange={handleInput}
          onFocus={() => text && setOpen(true)}
          placeholder={placeholder}
          autoComplete="off"
        />
        {value && (
          <button
            type="button"
            className="combo-clear"
            onClick={clear}
            aria-label="Clear selection"
          >
            ×
          </button>
        )}
      </div>
      {open && (results.length > 0 || loading) && (
        <div className="combo-dropdown">
          {loading && <div className="combo-loading">searching…</div>}
          {!loading &&
            results.map((p) => (
              <div
                key={p.id}
                className={
                  "combo-option" + (value?.id === p.id ? " active" : "")
                }
                onMouseDown={(e) => {
                  e.preventDefault(); // keep focus, avoid blur firing first
                  pick(p);
                }}
              >
                {p.name}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Search, X } from "lucide-react";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "./ui/command.jsx";
import { Label } from "./ui/label.jsx";
import { cn } from "../lib/utils.js";

/**
 * Debounced type-ahead player picker.
 *
 * Props
 *   label         — form label above the trigger
 *   value         — { id, name } | null
 *   onChange      — setter called with the chosen player or null on clear
 *   fetchPlayers  — async (query) => { players: [{id, name}] }
 *   placeholder   — trigger placeholder text
 */
export default function PlayerCombo({
  label,
  value,
  onChange,
  fetchPlayers,
  placeholder = "Search…",
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const debRef = useRef();
  const tokenRef = useRef(0);
  const rootRef = useRef(null);

  // Debounced fetch as user types.
  useEffect(() => {
    if (!open) return;
    clearTimeout(debRef.current);
    const myToken = ++tokenRef.current;
    debRef.current = setTimeout(() => {
      setLoading(true);
      fetchPlayers(query)
        .then((d) => {
          if (myToken === tokenRef.current) setResults(d.players || []);
        })
        .catch(() => {
          if (myToken === tokenRef.current) setResults([]);
        })
        .finally(() => {
          if (myToken === tokenRef.current) setLoading(false);
        });
    }, 200);
    return () => clearTimeout(debRef.current);
  }, [open, query, fetchPlayers]);

  // Close on outside click.
  useEffect(() => {
    function onDocClick(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function pick(p) {
    onChange(p);
    setOpen(false);
    setQuery("");
  }

  function clear(e) {
    e.stopPropagation();
    onChange(null);
    setQuery("");
  }

  return (
    <div className="space-y-1.5" ref={rootRef}>
      {label && <Label>{label}</Label>}
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className={cn(
            "flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors hover:bg-secondary/50 focus:outline-none focus:ring-2 focus:ring-ring"
          )}
        >
          <span
            className={cn(
              "truncate text-left",
              !value && "text-muted-foreground"
            )}
          >
            {value ? value.name : placeholder}
          </span>
          {value ? (
            <span
              onClick={clear}
              className="ml-2 rounded-sm text-muted-foreground hover:text-foreground"
              aria-label="Clear selection"
            >
              <X className="h-4 w-4" />
            </span>
          ) : (
            <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          )}
        </button>
        {open && (
          <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-popover shadow-lg animate-in fade-in-0 zoom-in-95">
            <Command shouldFilter={false}>
              <div className="flex items-center border-b border-border px-3">
                <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
                <CommandInput
                  value={query}
                  onValueChange={setQuery}
                  placeholder="Type to search…"
                  autoFocus
                />
              </div>
              <CommandList>
                {loading && (
                  <div className="py-2 text-center text-xs text-muted-foreground">
                    searching…
                  </div>
                )}
                {!loading && results.length === 0 && (
                  <CommandEmpty>No matches.</CommandEmpty>
                )}
                {!loading && results.length > 0 && (
                  <CommandGroup>
                    {results.map((p) => (
                      <CommandItem
                        key={p.id}
                        value={String(p.id)}
                        onSelect={() => pick(p)}
                      >
                        <span className="truncate">{p.name}</span>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                )}
              </CommandList>
            </Command>
          </div>
        )}
      </div>
    </div>
  );
}

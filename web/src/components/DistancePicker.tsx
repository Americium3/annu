import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

interface Option {
  value: number;
  label: string;
}

/**
 * The distance blank in the search sentence. The browser's own <select> list
 * inherits the sentence's headline size and the system's blue highlight, so
 * this is a small listbox styled like the other blanks' suggestion lists.
 *
 * Keyboard: Enter / Space / ↓ open it; ↑ ↓ Home End move; Enter / Space
 * choose; Esc closes; Tab moves on and closes it.
 */
export function DistancePicker({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  options: Option[];
  onChange: (value: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(() => Math.max(0, options.findIndex((o) => o.value === value)));
  const wrapRef = useRef<HTMLSpanElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listId = useId();
  const current = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    function close(event: MouseEvent) {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  function openList() {
    setActive(Math.max(0, options.findIndex((o) => o.value === value)));
    setOpen(true);
  }

  function choose(index: number) {
    onChange(options[index].value);
    setOpen(false);
    buttonRef.current?.focus();
  }

  function onKeyDown(event: React.KeyboardEvent) {
    const last = options.length - 1;
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
        event.preventDefault();
        openList();
      }
      return;
    }
    const moves: Record<string, () => number> = {
      ArrowDown: () => Math.min(last, active + 1),
      ArrowUp: () => Math.max(0, active - 1),
      Home: () => 0,
      End: () => last,
    };
    if (moves[event.key]) {
      event.preventDefault();
      setActive(moves[event.key]());
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      choose(active);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <span className="blank blank-picker" ref={wrapRef}>
      <button
        id={id}
        ref={buttonRef}
        type="button"
        className="blank-input blank-picker-button"
        aria-label={`${label}: ${current.label}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        data-value={value}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onKeyDown}
      >
        {current.label}
        <ChevronDown className={`blank-chevron ${open ? "is-open" : ""}`} aria-hidden="true" />
      </button>
      {open && (
        <span className="suggestions picker-list" id={listId} role="listbox" aria-label={label}>
          {options.map((option, index) => (
            <span
              key={option.value}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={option.value === value}
              className={`suggestion-item picker-option ${index === active ? "is-active" : ""}`}
              onMouseEnter={() => setActive(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(index)}
            >
              <span>
                <strong>{option.label}</strong>
              </span>
              {option.value === value && <Check className="suggestion-check" size={16} aria-hidden="true" />}
            </span>
          ))}
        </span>
      )}
    </span>
  );
}

"""Tiny keyboard-shortcut helper for Streamlit buttons.

Streamlit doesn't ship native keyboard bindings. This injects a small JS
snippet into the page that listens for keypresses and clicks the matching
Streamlit button. Buttons are matched by their visible label text.

Usage:
    from utils.keybinds import bind_keys
    bind_keys({"i": "Include [I]", "m": "Maybe [M]", "e": "Exclude [E]"})

Keys are matched case-insensitively. Bindings are ignored while typing in
an input/textarea so users can still type freely.
"""

from __future__ import annotations

import json

import streamlit.components.v1 as components


def bind_keys(bindings: dict[str, str], *, height: int = 0) -> None:
    """Map single keys to clicks on buttons whose label matches the value.

    `bindings` example: {"i": "Include [I]"} — pressing 'i' (when no input
    has focus) clicks the topmost button whose visible text is exactly
    "Include [I]". Falls back to a substring match if no exact match found.
    """
    payload = json.dumps(bindings)
    components.html(
        f"""
        <script>
        (function() {{
          const map = {payload};
          const norm = (s) => (s || "").trim().toLowerCase();
          function findButton(label) {{
            const target = norm(label);
            // Streamlit renders buttons as <button kind="..."> with a child <p> or <div>.
            const all = window.parent.document.querySelectorAll('button');
            let exact = null;
            let partial = null;
            for (const b of all) {{
              const text = norm(b.innerText);
              if (text === target) {{ exact = b; break; }}
              if (text.includes(target)) {{ partial = partial || b; }}
            }}
            return exact || partial;
          }}
          function isTyping(el) {{
            if (!el) return false;
            const tag = (el.tagName || "").toUpperCase();
            return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
          }}
          if (window.__lc_keybinds_installed) return;
          window.__lc_keybinds_installed = true;
          window.parent.document.addEventListener("keydown", (ev) => {{
            if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
            if (isTyping(window.parent.document.activeElement)) return;
            const key = (ev.key || "").toLowerCase();
            const label = map[key];
            if (!label) return;
            const btn = findButton(label);
            if (btn) {{
              ev.preventDefault();
              btn.click();
            }}
          }}, true);
        }})();
        </script>
        """,
        height=height,
    )

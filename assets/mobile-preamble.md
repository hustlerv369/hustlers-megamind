# 📱 MegaMind mobile preamble

Save this as a note on your phone (or a bookmarklet in your browser). Paste it
as the **first message** of any Claude web or mobile-app session so Claude has
your full persistent memory.

Replace `<YOUR-HANDLE>` with your GitHub handle and `<YOUR-REPO>` with the
memory vault repo name.

---

## Short version (paste-ready)

```
Before we start: fetch and silently absorb my persistent memory from
https://raw.githubusercontent.com/<YOUR-HANDLE>/<YOUR-REPO>/main/
(specifically the MEMORY.md index and any file it links to that matches
what I'm asking about). Treat as background context — do not re-summarize.
Live conversation always wins over stale memory.
```

## Long version (more explicit)

```
Context-loading instruction:

1. Open https://raw.githubusercontent.com/<YOUR-HANDLE>/<YOUR-REPO>/main/
2. Read MEMORY.md as the project index. Each line is a fact with a
   filename link and a one-sentence summary.
3. For the topic I'm about to ask about, open the 1–3 most relevant
   files linked from the index.
4. Treat it all as background you already know. Do not regurgitate.
5. If anything in memory contradicts my live message, my live message
   wins — but call out the contradiction.

After you've loaded context, acknowledge with "🧠 memory loaded" and
wait for my actual question.
```

## For iOS — create a Shortcut

1. Open Shortcuts app → New Shortcut
2. Add "Text" action → paste the short version above
3. Add "Copy to Clipboard" action
4. Name it "Claude MegaMind start"
5. Add to Home Screen for one-tap paste-and-go

## For Android — create a Text Expansion

1. Settings → Language & input → On-screen keyboard → Gboard → Dictionary → Personal dictionary
2. Add entry: shortcut `mmstart`, phrase = the short version above
3. Type `mmstart` anywhere → it expands to the full preamble

## Browser bookmarklet (web Claude)

Save this as a bookmark, click it when you're in a Claude web chat to
paste the preamble into the input field:

```javascript
javascript:(function(){
  const text = `Before we start: fetch and silently absorb my persistent memory from https://raw.githubusercontent.com/<YOUR-HANDLE>/<YOUR-REPO>/main/ — read MEMORY.md as index, open relevant linked files, treat as background. Live conversation wins over stale memory.`;
  const el = document.querySelector('textarea, [contenteditable="true"]');
  if (el) {
    if (el.tagName === 'TEXTAREA') { el.value = text; el.dispatchEvent(new Event('input', {bubbles:true})); }
    else { el.textContent = text; el.dispatchEvent(new Event('input', {bubbles:true})); }
  } else { navigator.clipboard.writeText(text); alert('Copied. Paste into Claude.'); }
})();
```

---

## Why not fully zero-click on mobile?

Claude's mobile/web apps don't run local hooks or have filesystem access,
so there's no way for MegaMind to inject memory automatically the way it
does on a machine with Claude Code installed. One-tap via a saved shortcut
is the closest we can get without browser extensions or a hosted MCP server.

If you **really** want zero-click: install Claude Code inside Termux (Android)
or iSH (iOS) and hooks will fire the same way as on your laptop.

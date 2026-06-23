# Skool post — ready to copy/paste

> Short, casual, first-person. Paste it as-is (swap the 🔗 link if needed).

---

**🧠⚡ I built a free skill that stops Claude Code from forgetting — and saves a ton of tokens**

yo 👋

so I kept hitting the same two things in Claude Code: it forgets everything between sessions, and it quietly eats my tokens like crazy (I'm on Max and STILL hit limits lol).

so I built a little skill to fix both → **Megamind Ultra**. one skill, zero dependencies, runs by itself on every session. no API key, no cloud, free.

what it actually does:
- 🧠 remembers your project across sessions (no more re-explaining yesterday)
- 🗂️ only loads the skills you actually use — this one alone saved me ~13.5k tokens *every session* 🤯
- 🧹 never dumps raw transcript junk back into context after compaction
- 🎚️ defaults to leaner model + effort settings

real numbers from my own setup: **~14–18k tokens saved every single session before I even type.** and your context stays — it just kills the noise, not the memory.

the part I like most: it makes **zero LLM calls from hooks**. a lot of memory tools secretly burn your tokens (or need a cloud account / vector db). this one is just Python stdlib + grep. ~600 lines you can read in one sitting. MIT, hack it however you want.

install = literally paste one prompt into Claude Code and it sets itself up (copies the skill, registers the hooks, verifies, done). repo + the prompt are below 👇

hope it saves you some tokens too 🙏

🔗 **GitHub:** https://github.com/hustlerv369/hustlers-megamind
📋 **Install:** grab the `megamind` folder from the repo, then paste the prompt in `INSTALL-PROMPT.md` into Claude Code — it does the rest.

<3

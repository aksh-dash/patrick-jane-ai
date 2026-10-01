# Week 7 — Acting on the World: Email, Desktop Control & Confirmation Boundaries

> Goal: let Jane do things that leave the machine and can't be undone — send email, message a contact on WhatsApp, launch a game — while enforcing one hard rule: **she only ever takes the final, irreversible step on your explicit confirmation.** Files: `jane/mailer.py`, `jane/desktop.py`, the action rules in `jane/persona.py`.

---

## Objectives

- Send email from Python with `smtplib` and `email.message`.
- Design a **compose → read back → send** boundary that's enforced by code, not just by prompt.
- Control installed desktop apps via **launch protocols** (`whatsapp://`, `steam://`) and `os.startfile`.
- Understand why the confirmation boundary is both structural *and* behavioural.
- Think clearly about authorization for irreversible actions.

---

## 1. The core principle

Some actions are reversible (open Notepad — just close it). Some are not (send an email — it's gone). The user's requirement was precise: *"he should do everything but just need my last confirmation before sending it, that is the boundary."*

So Jane's design draws a bright line:
- **Reversible, harmless actions** (open an app, launch a game) happen outright, no ceremony.
- **Irreversible, outward actions** (email, WhatsApp) require: Jane writes the whole thing, reads it back, and **stops** — the send happens only after you say yes.

The strong part is that this isn't merely *asked for* in the prompt. It's built so the code *cannot* send un-confirmed content. Prompt rules guide behaviour; structure guarantees it. You want both.

## 2. Sending email — the mechanics

`jane/mailer.py` uses two stdlib modules:
- **`email.message.EmailMessage`** — builds a properly formatted email (headers + body), handling encoding correctly.
- **`smtplib`** — speaks SMTP, the protocol for *sending* mail, to a server like Gmail's.

```python
msg = EmailMessage()
msg["From"] = config.EMAIL_FROM or config.SMTP_USER
msg["To"] = draft["to"]
msg["Subject"] = draft["subject"]
msg.set_content(draft["body"])

with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
    smtp.ehlo()
    smtp.starttls()                 # upgrade the connection to encrypted
    smtp.login(config.SMTP_USER, config.SMTP_PASS)
    smtp.send_message(msg)
```

- **`starttls()`** upgrades the plain connection to TLS encryption *before* the password is sent. Never log in over an unencrypted socket.
- Credentials come from `.env` (`JANE_SMTP_USER`, `JANE_SMTP_PASS`), never code. For Gmail these must be an **App Password**, not your account password — `mailer.py` catches `SMTPAuthenticationError` and says exactly that.

## 3. The boundary, enforced in code

Here's the clever bit. `mailer.py` keeps a single module-level draft, `_pending`. There are three functions:

- **`compose(to, subject, body)`** validates the address, stores the draft in `_pending`, and returns a **read-back** for the user. It does **not** send.
- **`send()`** sends **only whatever is in `_pending`** — there is no argument to pass content. It cannot send text that wasn't composed and read back first.
- **`discard()`** throws the draft away.

```python
def send():
    ...
    with _lock:
        draft = _pending
    if not draft:
        return "Nothing's drafted, so there's nothing to send. Compose it first."
    # ...builds the message from `draft` only, sends it, then clears _pending
```

Read that structural guarantee slowly: **the model has no way to call "send arbitrary email."** The only send path replays the exact draft you already saw. Even if the model misbehaved, it couldn't send something you hadn't reviewed. This is what "enforced by code, not just prompt" means — the API surface itself makes the unsafe thing impossible.

The two tools map cleanly (`tools.py`): `compose_email` → `mailer.compose`, `send_email` → `mailer.send()` (takes **no arguments**). The schema for `send_email` literally has empty properties, reinforcing that it just sends the staged draft.

## 4. The behavioural half — the persona

Structure stops the *impossible*; the persona shapes the *normal*. `persona.py` carries a "TAKING ACTION ON THE USER'S BEHALF" block instructing Jane to: do harmless reversible things outright; for anything that leaves the machine, "compose, read back, wait," and send only after a yes; re-drafting resets the confirmation. Belt and braces — the prompt makes the good flow natural, the code makes the bad flow impossible.

## 5. Controlling installed apps — launch protocols

How do you open the *installed* WhatsApp (not the website)? Modern desktop apps register **URI protocols** with the OS: `whatsapp://…`, `steam://…`, `spotify:…`. Ask the OS to open that URI and it launches the registered app. On Windows, `os.startfile` does exactly this for both protocol URIs and executables (`jane/desktop.py`):

```python
def _open_target(target):
    if sys.platform == "win32":
        os.startfile(target)              # handles whatsapp://…, steam://…, and .exe
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])
```

For WhatsApp, Jane builds a pre-filled chat URL:

```python
uri = f"whatsapp://send?phone={number}&text={quote(text)}"
```

`quote(text)` percent-encodes the message so spaces and punctuation survive the URL. The phone number is resolved from `data/contacts.json` (a name→number alias file) so you can say "message Mom" instead of reciting digits.

Games work the same way: `data/games.json` maps a name to a `steam://rungameid/<id>` URI or an `.exe` path, and a bare Steam app id becomes `steam://rungameid/<id>` automatically.

## 6. The auto-send caveat — an honest limitation

WhatsApp's URL *pre-fills* the message but doesn't send it. To actually send, Jane optionally synthesises an Enter keystroke to the focused window via PowerShell `SendKeys` (`_press_enter_soon`, Windows only, `JANE_WHATSAPP_AUTOSEND`). This is **best-effort**: it depends on the WhatsApp window being focused in time. If it isn't, the message just waits in the box for you to press Enter.

This is worth dwelling on as an engineering lesson: some integrations have no clean API and you're left simulating a human. When you must do that, (a) make it optional, (b) fail safe (here: message pre-filled, nothing lost), and (c) *tell the user* it's approximate rather than pretending it's reliable. Honesty about limits is part of good engineering.

## 7. Thinking about authorization

The through-line of this week is: **match the friction to the consequence.**

| Action | Reversible? | Friction Jane imposes |
|--------|-------------|----------------------|
| Open Notepad | Yes | None |
| Launch a game | Yes | None |
| Read a workspace file | Yes | Sandbox only |
| Send WhatsApp | No | Confirm wording each time |
| Send email | No | Compose → read back → explicit yes |
| Run a shell command | Very not | Off by default (`JANE_ALLOW_SHELL`) |

Every capability in Jane sits somewhere on this scale, and the safeguard is sized to the blast radius. That table is the whole security philosophy of the project in one glance.

## 8. Lab — a confirmation boundary

Build a tiny module with the same shape as `mailer.py`, for any irreversible action (posting a tweet, deleting a file — simulate it, print instead of really doing it):
1. `stage(payload)` stores a pending action and returns a read-back string.
2. `confirm()` performs **only** the staged action, then clears it.
3. `cancel()` discards it.
4. Prove there is no code path that performs an unstaged action.

Then add a `launch` function using your OS's protocol handler (`os.startfile` on Windows, `open`/`xdg-open` elsewhere) to open a URL or app — and notice how it needs *no* confirmation because it's reversible.

---

## Checkpoint

1. What does `starttls()` do, and why must it come before `login()`?
2. Explain how `mailer.send()` makes it *impossible* to send un-reviewed content.
3. Why are there two layers (code + persona) enforcing the confirmation boundary?
4. How does opening the installed WhatsApp differ from opening the website? What is a launch protocol?
5. Why is WhatsApp auto-send "best-effort," and what are the three rules for shipping a hacky integration like it?

→ [Week 8](week-08-frontend-and-capstone.md)


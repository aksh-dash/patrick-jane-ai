"""Jane's mind: a streaming Messages API loop with local + server-side tools."""
from __future__ import annotations

import re
import threading

import anthropic

from . import config, persona, speech, tools
from .logbus import bus

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|\n+")
_MAX_HISTORY = 16          # plain-text turns kept between requests
_MAX_TOOL_ROUNDS = 6

# Server-side refusal fallbacks are opt-in; if the beta isn't available to this
# account we drop it once and never retry, rather than failing every turn.
_use_fallbacks = True


class Brain:
    def __init__(self) -> None:
        if not config.API_KEY:
            self.client = None
            bus.log("No ANTHROPIC_API_KEY — Jane can hear but not think", "error")
        else:
            client_kwargs = {"api_key": config.API_KEY, "max_retries": 3}
            if config.BASE_URL:
                client_kwargs["base_url"] = config.BASE_URL
            self.client = anthropic.Anthropic(**client_kwargs)
        self.history: list[dict] = []
        self.lock = threading.Lock()

    # -- public ----------------------------------------------------------
    def ask(self, text: str) -> str:
        """Handle one user utterance. Streams to the bus, returns the full reply."""
        if self.client is None:
            msg = ("There's no valid API key in the .env file, so I can hear you "
                   "but I can't think. Add ANTHROPIC_API_KEY and restart me.")
            bus.publish("transcript", {"who": "USER", "text": text})
            bus.publish("transcript_open", {"who": "JANE"})
            return self._fail(msg)

        with self.lock:
            try:
                return self._turn(text)
            except anthropic.AuthenticationError:
                return self._fail("That API key isn't valid. Check .env.")
            except anthropic.RateLimitError:
                return self._fail("I'm being rate limited. Give me a moment.")
            except anthropic.APIConnectionError:
                return self._fail("I can't reach the network. Check the connection.")
            except anthropic.APIStatusError as exc:
                return self._fail(f"The API pushed back: {exc.status_code}.")

    # -- internals -------------------------------------------------------
    def _fail(self, message: str) -> str:
        # Close the open transcript so the interface settles instead of hanging
        # on a half-streamed line; speak the message once.
        bus.log(message, "error")
        bus.publish("transcript_close", {"who": "JANE", "text": message})
        speech.say(message)
        bus.publish("state", {"thinking": False})
        return message

    def _request(self, messages: list[dict]):
        """One streaming request. Returns the accumulated final Message."""
        global _use_fallbacks

        kwargs = dict(
            model=config.MODEL,
            max_tokens=16000,
            system=persona.system_blocks(),
            messages=messages,
            tools=tools.SCHEMAS,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": config.EFFORT},
        )

        if _use_fallbacks and not config.BASE_URL:
            try:
                return self._stream(self.client.beta.messages.stream(
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                    **kwargs,
                ))
            except anthropic.BadRequestError as exc:
                _use_fallbacks = False
                bus.log(f"Refusal fallbacks unavailable ({exc.status_code}); continuing without",
                        "warn")

        return self._stream(self.client.messages.stream(**kwargs))

    def _stream(self, stream_ctx):
        """Consume a stream, pushing text to the UI sentence by sentence."""
        pending = ""
        thought = ""
        with stream_ctx as stream:
            for event in stream:
                if event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        pending += delta.text
                        bus.publish("transcript_delta", {"text": delta.text})
                        # Speak each finished sentence so audio starts early.
                        while True:
                            match = _SENTENCE_END.search(pending)
                            if not match:
                                break
                            sentence, pending = pending[:match.end()].strip(), pending[match.end():]
                            if sentence:
                                speech.say(sentence)
                    elif delta.type == "thinking_delta":
                        thought += delta.thinking
                elif event.type == "content_block_stop" and thought:
                    bus.log(f"Deduction: {thought.strip().splitlines()[0][:90]}", "think")
                    thought = ""
            if pending.strip():
                speech.say(pending.strip())
            return stream.get_final_message()

    def _turn(self, text: str) -> str:
        bus.publish("transcript", {"who": "USER", "text": text})
        bus.publish("state", {"thinking": True})
        bus.publish("transcript_open", {"who": "JANE"})

        messages: list[dict] = self.history + [{"role": "user", "content": text}]
        reply_parts: list[str] = []

        for _ in range(_MAX_TOOL_ROUNDS):
            message = self._request(messages)

            if message.stop_reason == "refusal":
                detail = getattr(message.stop_details, "category", None)
                bus.log(f"Declined ({detail})", "warn")
                reply_parts.append("I'm going to leave that one alone.")
                break

            reply_parts.extend(b.text for b in message.content if b.type == "text")
            messages.append({"role": "assistant", "content": message.content})

            if message.stop_reason == "pause_turn":
                continue  # server-side tool wants to keep going

            if message.stop_reason != "tool_use":
                break

            results = []
            for block in message.content:
                if block.type != "tool_use":
                    continue
                try:
                    output = tools.run(block.name, dict(block.input))
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": output})
                except Exception as exc:  # a failed tool must still return a result
                    bus.log(f"Tool {block.name} failed: {exc}", "error")
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": f"Error: {exc}", "is_error": True})
            if not results:
                break
            messages.append({"role": "user", "content": results})
        else:
            bus.log("Tool loop hit its ceiling", "warn")

        reply = " ".join(p.strip() for p in reply_parts if p.strip()).strip()
        if not reply:
            reply = "I've got nothing useful to add to that."
            speech.say(reply)

        self.history = (self.history + [
            {"role": "user", "content": text},
            {"role": "assistant", "content": reply},
        ])[-_MAX_HISTORY:]
        # A trimmed window must still begin on a user turn.
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)

        bus.publish("transcript_close", {"who": "JANE", "text": reply})
        bus.publish("state", {"thinking": False})
        return reply

    def reset(self) -> None:
        with self.lock:
            self.history.clear()
        bus.log("Conversation cleared", "info")


brain = Brain()

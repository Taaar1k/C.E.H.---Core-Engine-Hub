"""Prompt template system for C.E.H.

Extracts chat templates from GGUF model metadata and provides a unified
interface for formatting conversations.  Supports built-in templates for
common model families (Qwen, Llama, Mistral, ChatML) as fallbacks when
a GGUF file lacks ``chat_template`` metadata.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in Jinja2 chat templates
# ---------------------------------------------------------------------------

CHATML_TEMPLATE: str = (
    "{% for message in messages %}"
    "{{ '<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>' + '\n' }}"
    "{% endfor %}"
    "{% if add_generation_prompt %}"
    "{{ '<|im_start|>assistant\n' }}"
    "{% endif %}"
)

QWEN_CHAT_TEMPLATE: str = (
    "{% for message in messages %}"
    "{{ '<|im_start|>' + message['role'] + '\n' + message['content'] + '<|im_end|>' + '\n' }}"
    "{% endfor %}"
    "{% if add_generation_prompt %}"
    "{{ '<|im_start|>assistant\n' }}"
    "{% endif %}"
)

LLAMA3_CHAT_TEMPLATE: str = (
    "{%- if messages[0]['role'] == 'system' %}"
    "{{ '<|begin_of_text|>' }}"
    "{{ '<|start_header_id|>system<|end_header_id|>\n\n' + messages[0]['content'] | trim + '<|eot_id|>' }}"
    "{%- set messages = messages[1:] %}"
    "{%- else %}"
    "{{ '<|begin_of_text|>' }}"
    "{%- endif %}"
    "{%- for message in messages %}"
    "{%- if (message['role'] == 'user') != (loop.index0 % 2 == 0) %}"
    "{{ raise_exception('Conversation roles must alternate user/assistant/user/assistant/...') }}"
    "{%- endif %}"
    "{{ '<|start_header_id|>' + message['role'] + '<|end_header_id|>\n\n' + message['content'] | trim + '<|eot_id|>' }}"
    "{%- endfor %}"
    "{%- if add_generation_prompt %}"
    "{{ '<|start_header_id|>assistant<|end_header_id|>\n\n' }}"
    "{%- endif %}"
)

LLAMA2_CHAT_TEMPLATE: str = (
    "{%- if messages[0]['role'] == 'system' %}"
    "{%- set messages = [{'role': 'assistant', 'content': '### System:\\n' + messages[0]['content'] | trim + '\\n\\n'}] + messages[1:] %}"
    "{%- endif %}"
    "{%- if messages | length == 0 %}"
    "{{ '<s>' }}"
    "{%- else %}"
    "{%- for message in messages %}"
    "{%- if message['role'] == 'user' %}"
    "{{ '<s>' + '[INST] ' + message['content'] | trim + ' [/INST]' }}"
    "{%- elif message['role'] == 'assistant' %}"
    "{{ message['content'] | trim + '</s>' }}"
    "{%- endif %}"
    "{%- endfor %}"
    "{%- endif %}"
)

MISTRAL_CHAT_TEMPLATE: str = (
    "{%- for message in messages %}"
    "{%- if message['role'] == 'user' %}"
    "{{ '[INST] ' + message['content'] | trim + ' [/INST]' }}"
    "{%- elif message['role'] == 'assistant' %}"
    "{{ message['content'] | trim + '</s>' }}"
    "{%- endif %}"
    "{%- endfor %}"
)

# Mapping of model family names to their built-in templates
BUILTIN_TEMPLATES: Dict[str, str] = {
    "chatml": CHATML_TEMPLATE,
    "qwen": QWEN_CHAT_TEMPLATE,
    "llama3": LLAMA3_CHAT_TEMPLATE,
    "llama2": LLAMA2_CHAT_TEMPLATE,
    "mistral": MISTRAL_CHAT_TEMPLATE,
}

# Common stop sequences used by various model families
COMMON_STOP_SEQUENCES: List[str] = [
    "</s>",
    "<|eot_id|>",
    "<|end_of_text|>",
    "</s>",
    "]]",
    "<|im_end|>",
]


class TemplateError(Exception):
    """Base exception for template-related errors."""


class TemplateRenderError(TemplateError):
    """Raised when template rendering fails."""


class PromptTemplate:
    """Wraps a Jinja2 chat template and provides formatting utilities.

    Parameters
    ----------
    model : Any
        An object with a ``chat_template`` attribute (e.g. ``llama_cpp.Llama``).
        When ``None``, the default ChatML fallback is used.
    custom_template : str, optional
        Override template string.  Takes precedence over GGUF metadata.
    custom_format : str, optional
        Name of a built-in template to use (e.g. ``"qwen"``, ``"llama3"``).
    """

    def __init__(
        self,
        model: Any | None = None,
        custom_template: str | None = None,
        custom_format: str | None = None,
    ) -> None:
        if custom_template:
            self.template_str: str = custom_template
            self.format_name: str = "custom"
        elif custom_format:
            if custom_format not in BUILTIN_TEMPLATES:
                raise TemplateError(
                    f"Unknown template format: {custom_format!r}. "
                    f"Available: {list(BUILTIN_TEMPLATES.keys())}"
                )
            self.template_str = BUILTIN_TEMPLATES[custom_format]
            self.format_name = custom_format
        elif model and hasattr(model, "chat_template") and model.chat_template:
            self.template_str = model.chat_template  # type: ignore[attr-defined]
            self.format_name = self._detect_format(self.template_str)
        else:
            self.template_str = CHATML_TEMPLATE
            self.format_name = "chatml"

        self._stop_tokens: List[str] = []

    @staticmethod
    def _detect_format(template_str: str) -> str:
        """Heuristically detect the template format from its content.

        Parameters
        ----------
        template_str : str
            The raw Jinja2 template string.

        Returns
        -------
        str
            A lowercase format identifier.
        """
        if "<|im_start|>" in template_str and "<|im_end|>" in template_str:
            return "qwen"
        if "<|begin_of_text|>" in template_str and "<|eot_id|>" in template_str:
            return "llama3"
        if "[INST]" in template_str and "</s>" in template_str:
            return "llama2"
        if "[/INST]" in template_str:
            return "mistral"
        return "chatml"

    def format_messages(
        self,
        messages: List[Dict[str, Any]],
        add_generation_prompt: bool = False,
        **kwargs: Any,
    ) -> str:
        """Format a list of chat messages into a single prompt string.

        Parameters
        ----------
        messages : list[dict]
            List of message dicts with ``role`` and ``content`` keys.
        add_generation_prompt : bool
            If ``True``, append a prompt that encourages the model to
            generate a response.
        **kwargs
            Additional variables passed to the Jinja2 renderer.

        Returns
        -------
        str
            The formatted prompt string.

        Raises
        ------
        TemplateRenderError
            If template rendering fails.
        """
        try:
            from jinja2 import Template

            template = Template(self.template_str)
            return template.render(
                messages=messages,
                add_generation_prompt=add_generation_prompt,
                **kwargs,
            )
        except Exception as exc:
            raise TemplateRenderError(
                f"Failed to render template: {exc}"
            ) from exc

    def format_and_infer(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Format messages and run inference in one call.

        Parameters
        ----------
        messages : list[dict]
            Chat messages.
        max_tokens : int
            Maximum tokens to generate.
        temperature : float
            Sampling temperature.
        **kwargs
            Additional kwargs forwarded to the model's ``__call__`` method.

        Returns
        -------
        dict
            The raw model response dict.

        Raises
        ------
        TemplateError
            If template rendering fails or the model is not available.
        """
        from llama_cpp import Llama

        if not hasattr(self, "_model") or not isinstance(self._model, Llama):
            raise TemplateError(
                "format_and_infer requires a llama_cpp.Llama instance. "
                "Use format_messages() instead, or pass a model to __init__."
            )

        formatted = self.format_messages(messages, **kwargs)
        result = self._model(
            formatted,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=self._stop_tokens or None,
        )
        return result

    def set_model(self, model: Llama) -> None:  # type: ignore[name-defined]
        """Attach a ``llama_cpp.Llama`` instance for inference support.

        Parameters
        ----------
        model : Llama
            The Llama backend instance.
        """
        from llama_cpp import Llama as LlamaClass

        if not isinstance(model, LlamaClass):
            raise TypeError(f"Expected Llama, got {type(model).__name__}")

        self._model = model

        # Auto-detect stop tokens from GGUF metadata
        if hasattr(model, "token_get_text"):
            text_tokens = [
                model.token_get_text(i)  # type: ignore[attr-defined]
                for i in range(model.n_vocab())  # type: ignore[attr-defined]
                if model.token_get_text(i) in COMMON_STOP_SEQUENCES  # type: ignore[attr-defined]
            ]
            self._stop_tokens = text_tokens

        # Also check for built-in stop sequences in the template
        for seq in COMMON_STOP_SEQUENCES:
            if seq in self.template_str and seq not in self._stop_tokens:
                self._stop_tokens.append(seq)

    def __repr__(self) -> str:
        return (
            f"PromptTemplate(format={self.format_name!r}, "
            f"template_len={len(self.template_str)})"
        )


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def create_prompt_template(
    model: Any | None = None,
    custom_template: str | None = None,
    custom_format: str | None = None,
) -> PromptTemplate:
    """Factory function to create a :class:`PromptTemplate`.

    Parameters
    ----------
    model : Any, optional
        GGUF model object with ``chat_template`` metadata.
    custom_template : str, optional
        Raw Jinja2 template string.
    custom_format : str, optional
        Built-in format name (``"qwen"``, ``"llama3"``, etc.).

    Returns
    -------
    PromptTemplate
        The constructed template instance.
    """
    return PromptTemplate(
        model=model,
        custom_template=custom_template,
        custom_format=custom_format,
    )

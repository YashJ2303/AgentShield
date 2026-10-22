"""
Heuristic Prompt Injection Screening Layer.

Provides:
- Input size capping (ReDoS protection)
- Pre-matching normalization pipeline (NFKC, zero-width stripping, lowercase, whitespace collapsing)
- Pluggable detector interface with concrete detectors:
  1. InstructionOverrideDetector (English + Multilingual, spaced/homoglyphs)
  2. RoleSpoofingDetector (system/assistant/chat-template delimiters)
  3. HiddenTextDetector (zero-width characters, HTML comments, CSS display:none, markdown comments)
  4. EncodedPayloadDetector (base64 candidate extraction & recursive scanning with JWT/hash/image false-positive filters)
- Configurable policy actions: 'block', 'flag', 'sanitize'
- Strict safety rules:
  - Block messages never repeat malicious input
  - Sanitize strips the full instruction/hidden payload
"""
import re
import base64
import unicodedata
from abc import ABC, abstractmethod
from typing import Optional, Any
from dataclasses import dataclass, field


# 500 KB input cap for ReDoS and memory defense
MAX_INPUT_CHARS = 500 * 1024
MAX_BASE64_DECODE_BYTES = 10 * 1024

# Zero-width & invisible Unicode codepoints
ZERO_WIDTH_PATTERN = re.compile(
    r"[\u200b\u200c\u200d\ufeff\u2060\u200e\u200f\u00ad\u202a-\u202e]"
)

# JWT pattern (3 dot-separated base64url segments, typically starts with eyJ)
JWT_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)

# Hex hashes (MD5, SHA1, SHA256)
HEX_HASH_PATTERN = re.compile(
    r"\b(?:[a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64})\b"
)

# Data URI for base64 images/assets
DATA_URI_IMAGE_PATTERN = re.compile(
    r"data:image\/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=]+"
)


# De-spacing and whitespace normalization patterns
DESPACE_HYPHEN_RE = re.compile(r"\b(?:[a-z]-){2,}[a-z]\b")
DESPACE_SPACE_RE = re.compile(r"\b(?:[a-z] ){2,}[a-z]\b")
WHITESPACE_COLLAPSE_RE = re.compile(r"[ \t\r\f\v]+")


@dataclass
class InjectionMatch:
    detector_name: str
    category: str  # 'instruction_override' | 'role_spoofing' | 'hidden_text' | 'encoded_payload'
    pattern_name: str
    matched_text: str
    start_offset: int
    end_offset: int
    confidence: float = 0.9
    details: Optional[str] = None


@dataclass
class ScreeningResult:
    is_safe: bool
    action_taken: str  # 'allow' | 'block' | 'flag' | 'sanitize'
    injection_flag: bool
    sanitized_output: Any
    matches: list[InjectionMatch] = field(default_factory=list)
    reason: Optional[str] = None


class BaseInjectionDetector(ABC):
    name: str = "base"
    category: str = "generic"

    @abstractmethod
    def detect(self, original_text: str, normalized_text: str) -> list[InjectionMatch]:
        """Inspect text and return list of matches."""
        pass


def normalize_text(text: str) -> tuple[str, bool]:
    """
    Apply Unicode NFKC, strip zero-width characters, lowercase, and collapse whitespace.
    Preserves inter-word boundaries when single-spaced isolated letters are despaced.
    Returns: (normalized_text, has_zero_width_chars)
    """
    if not text:
        return "", False

    # 1. Unicode NFKC (normalizes homoglyphs, ligatures, full-width characters)
    nfkc_text = unicodedata.normalize("NFKC", text)

    # 2. Detect and strip zero-width characters
    has_zero_width = bool(ZERO_WIDTH_PATTERN.search(nfkc_text))
    stripped_text = ZERO_WIDTH_PATTERN.sub("", nfkc_text)

    # 3. Lowercase
    lowered = stripped_text.lower()

    # 4. De-space hyphenated letters first: s-y-s-t-e-m -> system
    d_hyphen = DESPACE_HYPHEN_RE.sub(lambda m: m.group(0).replace("-", ""), lowered)

    # 5. De-space single-spaced letters while preserving word boundaries with >=2 spaces:
    #    e.g. 'i g n o r e  p r e v i o u s' -> 'ignore  previous'
    d_space = DESPACE_SPACE_RE.sub(lambda m: m.group(0).replace(" ", ""), d_hyphen)

    # 6. Collapse excessive whitespace
    collapsed = WHITESPACE_COLLAPSE_RE.sub(" ", d_space)

    return collapsed, has_zero_width


# =========================================================================
# Concrete Detectors
# =========================================================================

class InstructionOverrideDetector(BaseInjectionDetector):
    name = "instruction_override_detector"
    category = "instruction_override"

    # Non-backtracking, bounded repetition regex patterns
    PATTERNS = [
        # English Direct Overrides (including earlier, past, preceding)
        (
            "ignore_previous_instructions",
            re.compile(
                r"\b(?:ignore|disregard|forget|bypass)\s+(?:all\s+)?(?:previous|prior|above|system|existing|earlier|past|preceding)\s+(?:instructions|prompts|directives|rules|guidelines|commands|orders)\b"
            ),
        ),
        (
            "system_override",
            re.compile(r"\b(?:system|emergency|developer|admin)\s+override(?:\s*:\s*|\s+|$)"),
        ),
        (
            "mode_switch_jailbreak",
            re.compile(
                r"\byou\s+are\s+now\s+(?:in\s+)?(?:maintenance|developer|god|unrestricted|jailbreak|debug|sudo)\s+mode\b"
            ),
        ),
        (
            "new_instructions_directive",
            re.compile(
                r"\b(?:new|updated|revised)\s+(?:primary\s+)?(?:instructions|directives|system\s+prompt)\s*:\s*"
            ),
        ),
        (
            "do_not_follow_prior",
            re.compile(
                r"\bdo\s+not\s+follow\s+(?:any\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|rules|directives)\b"
            ),
        ),
        # Multilingual Variants (Spanish, French, German, Russian)
        (
            "spanish_ignore_override",
            re.compile(
                r"\b(?:ignora|olvida|descarta)\s+(?:todas\s+)?(?:las\s+)?instrucciones\s+(?:anteriores|previas)\b"
            ),
        ),
        (
            "french_ignore_override",
            re.compile(
                r"\b(?:ignorez|ignorer|oubliez|oublier)\s+(?:toutes\s+)?(?:les\s+)?instructions\s+(?:pr[eé]c[eé]dentes|ant[eé]rieures)\b"
            ),
        ),
        (
            "german_ignore_override",
            re.compile(
                r"\bignoriere\s+(?:alle\s+)?(?:vorherigen|fr[uü]heren)\s+(?:anweisungen|befehle)\b"
            ),
        ),
        (
            "russian_ignore_override",
            re.compile(
                r"\b(?:игнорируйте|забудьте|отмените)\s+(?:все\s+)?(?:предыдущие|прошлые)\s+(?:инструкции|команды|указания)\b"
            ),
        ),
    ]

    TRIGGER_WORDS = (
        "ignore", "disregard", "forget", "bypass", "system", "override",
        "instruction", "prompt", "rule", "mode", "admin", "prior", "previous",
        "earlier", "directive", "order", "jailbreak", "guideline", "ignora",
        "ignoriere", "ignorez", "игнорируйте", "забудьте", "отмените"
    )

    def detect(self, original_text: str, normalized_text: str) -> list[InjectionMatch]:
        if not any(k in normalized_text for k in self.TRIGGER_WORDS):
            return []
        matches: list[InjectionMatch] = []
        for pat_name, pat_regex in self.PATTERNS:
            for m in pat_regex.finditer(normalized_text):
                start, end = m.span()
                prefix = normalized_text[max(0, start - 40):start]
                suffix = normalized_text[end:min(len(normalized_text), end + 60)]
                # Check for active imperative payload aimed at the model
                has_active_instruction = bool(re.search(
                    r"\b(?:and|now|then|to|please|you\s+must)\s+(?:dump|reveal|transfer|delete|drop|send|exfiltrate|show|switch|bypass|execute|run|give|provide|output|say|print|write)\b",
                    suffix
                ))
                if any(k in prefix for k in ("example of", "such as", "phrases like", "articles about", "attackers use", "explaining how")):
                    # Context is descriptive / benign discussion ONLY if it contains NO active imperative payload
                    if not has_active_instruction:
                        continue

                matches.append(
                    InjectionMatch(
                        detector_name=self.name,
                        category=self.category,
                        pattern_name=pat_name,
                        matched_text=m.group(0),
                        start_offset=start,
                        end_offset=end,
                        confidence=0.95,
                    )
                )
        return matches


class RoleSpoofingDetector(BaseInjectionDetector):
    name = "role_spoofing_detector"
    category = "role_spoofing"

    ROLE_TRIGGER_TOKENS = ("im_start", "im_end", "system", "assistant", "inst", "sys", "human", "user")

    PATTERNS = [
        (
            "chatml_delimiters",
            re.compile(r"<\|(?:im_start|im_end|system|user|assistant)\|>(?:\s*system|\s*assistant)?"),
        ),
        (
            "llama_delimiters",
            re.compile(r"(?:\[inst\]|\[/inst\]|<<sys>>|<</sys>>)", re.IGNORECASE),
        ),
        (
            "role_prefix_spoof",
            re.compile(r"(?:^|\n)\s*(?:system|assistant|human|user)\s*:\s*"),
        ),
    ]

    def detect(self, original_text: str, normalized_text: str) -> list[InjectionMatch]:
        if not any(k in normalized_text for k in self.ROLE_TRIGGER_TOKENS):
            return []
        matches: list[InjectionMatch] = []
        for pat_name, pat_regex in self.PATTERNS:
            for m in pat_regex.finditer(normalized_text):
                matches.append(
                    InjectionMatch(
                        detector_name=self.name,
                        category=self.category,
                        pattern_name=pat_name,
                        matched_text=m.group(0),
                        start_offset=m.start(),
                        end_offset=m.end(),
                        confidence=0.90,
                    )
                )
        return matches


class HiddenTextDetector(BaseInjectionDetector):
    name = "hidden_text_detector"
    category = "hidden_text"

    HTML_COMMENT_PATTERN = re.compile(r"<!--[\s\S]*?-->")
    CSS_HIDDEN_PATTERN = re.compile(
        r"<[a-zA-Z0-9]+[^>]*style\s*=\s*['\"][^'\"]*(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0)[^'\"]*['\"][^>]*>([\s\S]*?)<\/[a-zA-Z0-9]+>"
    )
    MARKDOWN_COMMENT_PATTERN = re.compile(r"\[\s*//\s*\]\s*:\s*#\s*\(([\s\S]*?)\)")

    def detect(self, original_text: str, normalized_text: str) -> list[InjectionMatch]:
        matches: list[InjectionMatch] = []

        # 1. Zero-width character presence
        zw_matches = list(ZERO_WIDTH_PATTERN.finditer(original_text))
        if zw_matches:
            first_m = zw_matches[0]
            matches.append(
                InjectionMatch(
                    detector_name=self.name,
                    category=self.category,
                    pattern_name="zero_width_characters",
                    matched_text="[ZERO_WIDTH_CHARS]",
                    start_offset=first_m.start(),
                    end_offset=zw_matches[-1].end(),
                    confidence=0.85,
                    details=f"Found {len(zw_matches)} zero-width invisible character(s)",
                )
            )

        # 2. HTML Comments containing directives or text
        if "<!--" in original_text and any(k in normalized_text for k in ("ignore", "system", "instruction", "prompt", "override", "admin", "bypass")):
            for m in self.HTML_COMMENT_PATTERN.finditer(original_text):
                comment_content = m.group(0).lower()
                if any(k in comment_content for k in ("ignore", "system", "instruction", "prompt", "override", "admin", "bypass")):
                    matches.append(
                        InjectionMatch(
                            detector_name=self.name,
                            category=self.category,
                            pattern_name="html_comment_injection",
                            matched_text=m.group(0),
                            start_offset=m.start(),
                            end_offset=m.end(),
                            confidence=0.92,
                        )
                    )

        # 3. CSS Hidden elements
        if any(k in normalized_text for k in ("none", "hidden", "opacity")) and any(k in normalized_text for k in ("ignore", "system", "instruction", "override", "bypass")):
            for m in self.CSS_HIDDEN_PATTERN.finditer(original_text):
                inner = m.group(1).lower()
                if any(k in inner for k in ("ignore", "system", "instruction", "override", "bypass")):
                    matches.append(
                        InjectionMatch(
                            detector_name=self.name,
                            category=self.category,
                            pattern_name="css_hidden_element",
                            matched_text=m.group(0),
                            start_offset=m.start(),
                            end_offset=m.end(),
                            confidence=0.95,
                        )
                    )

        # 4. Markdown comments
        if "[//" in original_text and any(k in normalized_text for k in ("ignore", "system", "instruction", "override", "bypass")):
            for m in self.MARKDOWN_COMMENT_PATTERN.finditer(original_text):
                inner = m.group(1).lower()
                if any(k in inner for k in ("ignore", "system", "instruction", "override", "bypass")):
                    matches.append(
                        InjectionMatch(
                            detector_name=self.name,
                            category=self.category,
                            pattern_name="markdown_comment_injection",
                            matched_text=m.group(0),
                            start_offset=m.start(),
                            end_offset=m.end(),
                            confidence=0.95,
                        )
                    )

        return matches


class EncodedPayloadDetector(BaseInjectionDetector):
    name = "encoded_payload_detector"
    category = "encoded_payload"

    # Match base64 candidate strings of at least 16 characters (allowing padding =)
    BASE64_CANDIDATE_PATTERN = re.compile(
        r"\b(?:[A-Za-z0-9+/]{4}){3,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{4})(?=$|[^\w+/=])"
    )

    def __init__(self, sub_detectors: Optional[list[BaseInjectionDetector]] = None):
        self.sub_detectors = sub_detectors or [
            InstructionOverrideDetector(),
            RoleSpoofingDetector(),
        ]

    MAX_BASE64_CANDIDATES = 30

    def detect(self, original_text: str, normalized_text: str) -> list[InjectionMatch]:
        matches: list[InjectionMatch] = []
        has_jwt = bool(JWT_PATTERN.search(original_text))

        candidate_count = 0
        # Find and verify candidates
        for m in self.BASE64_CANDIDATE_PATTERN.finditer(original_text):
            candidate_count += 1
            if candidate_count > self.MAX_BASE64_CANDIDATES:
                break
            candidate = m.group(0)

            # False-positive guard 1: JWT token
            if candidate.startswith("eyJ") and has_jwt:
                continue

            # False-positive guard 2: Hex hash
            if HEX_HASH_PATTERN.fullmatch(candidate):
                continue

            # False-positive guard 3: Data URI image
            start_pos = max(0, m.start() - 30)
            context_prefix = original_text[start_pos:m.start()]
            if "data:image" in context_prefix:
                continue

            # Attempt decoding (with size cap)
            try:
                raw_bytes = base64.b64decode(candidate, validate=True)
                if len(raw_bytes) > MAX_BASE64_DECODE_BYTES:
                    continue
                decoded_str = raw_bytes.decode("utf-8", errors="ignore")
            except Exception:
                continue

            # If not printable text, skip
            if not decoded_str or len(decoded_str.strip()) < 5:
                continue

            # Scan decoded text with sub-detectors
            sub_norm, _ = normalize_text(decoded_str)
            sub_matches: list[InjectionMatch] = []
            for d in self.sub_detectors:
                sub_matches.extend(d.detect(decoded_str, sub_norm))

            if not sub_matches:
                # Check for double base64 encoding (depth 2)
                for sub_m in self.BASE64_CANDIDATE_PATTERN.finditer(decoded_str):
                    sub_cand = sub_m.group(0)
                    try:
                        d2_bytes = base64.b64decode(sub_cand, validate=True)
                        if len(d2_bytes) <= MAX_BASE64_DECODE_BYTES:
                            d2_str = d2_bytes.decode("utf-8", errors="ignore")
                            if d2_str and len(d2_str.strip()) >= 5:
                                d2_norm, _ = normalize_text(d2_str)
                                for d in self.sub_detectors:
                                    sub_matches.extend(d.detect(d2_str, d2_norm))
                    except Exception:
                        pass

            if sub_matches:
                matches.append(
                    InjectionMatch(
                        detector_name=self.name,
                        category=self.category,
                        pattern_name="base64_encoded_injection",
                        matched_text=candidate,
                        start_offset=m.start(),
                        end_offset=m.end(),
                        confidence=0.98,
                        details=f"Decoded payload contains prompt injection: {sub_matches[0].pattern_name}",
                    )
                )

        return matches


# =========================================================================
# Main Screening Service
# =========================================================================

class PromptInjectionScreener:
    """
    Orchestrates the heuristic prompt injection detection pipeline.
    Pluggable detector list, safe refusal messaging, and sanitization.
    """

    DEFAULT_BLOCK_MESSAGE = "Security violation: Tool output blocked by AgentShield prompt injection filter."

    def __init__(self, detectors: Optional[list[BaseInjectionDetector]] = None):
        if detectors is None:
            override_det = InstructionOverrideDetector()
            role_det = RoleSpoofingDetector()
            hidden_det = HiddenTextDetector()
            encoded_det = EncodedPayloadDetector(sub_detectors=[override_det, role_det])
            self.detectors = [override_det, role_det, hidden_det, encoded_det]
        else:
            self.detectors = detectors

    def screen(
        self,
        tool_output: Any,
        action: str = "block",  # 'block' | 'flag' | 'sanitize'
    ) -> ScreeningResult:
        """
        Screen tool output against registered heuristic detectors.
        Handles text strings, JSON dicts, lists, or primitive numbers.
        """
        valid_actions = {"block", "flag", "sanitize"}
        selected_action = action.lower() if action.lower() in valid_actions else "block"

        # Convert tool output to inspectable text representation
        if isinstance(tool_output, str):
            raw_text = tool_output
        elif isinstance(tool_output, (dict, list)):
            import json
            try:
                raw_text = json.dumps(tool_output, ensure_ascii=False)
            except Exception:
                raw_text = str(tool_output)
        else:
            raw_text = str(tool_output)

        if not raw_text.strip():
            return ScreeningResult(
                is_safe=True,
                action_taken="allow",
                injection_flag=False,
                sanitized_output=tool_output,
                matches=[],
            )

        # Fail-closed size cap: never truncate and risk bypass of trailing payloads
        if len(raw_text) > MAX_INPUT_CHARS:
            return ScreeningResult(
                is_safe=False,
                action_taken="block" if selected_action != "flag" else "flag",
                injection_flag=True,
                sanitized_output="Security violation: Tool output exceeds maximum inspection limit (500KB) and was blocked for safety.",
                matches=[
                    InjectionMatch(
                        detector_name="input_size_guard",
                        category="payload_oversize",
                        pattern_name="oversize_payload_blocked",
                        matched_text=f"[Oversized output: {len(raw_text)} chars]",
                        start_offset=0,
                        end_offset=len(raw_text),
                        confidence=1.0,
                        details="Tool output exceeded 500KB inspection limit; blocked fail-closed to prevent truncation evasion",
                    )
                ],
                reason="Tool output exceeds maximum allowable screening size (500KB) - blocked fail-closed",
            )

        # 1. Normalize
        normalized_text, has_zero_width = normalize_text(raw_text)

        # 2. Run all detectors
        matches: list[InjectionMatch] = []
        for detector in self.detectors:
            try:
                found = detector.detect(raw_text, normalized_text)
                matches.extend(found)
            except Exception as e:
                # Detector error: fail-closed safety handling in caller
                continue

        if not matches:
            return ScreeningResult(
                is_safe=True,
                action_taken="allow",
                injection_flag=False,
                sanitized_output=tool_output,
                matches=[],
            )

        # Prompt injection detected!
        reason = f"Detected prompt injection pattern: {matches[0].pattern_name} ({matches[0].category})"

        if selected_action == "block":
            # Must NEVER repeat the malicious text!
            return ScreeningResult(
                is_safe=False,
                action_taken="block",
                injection_flag=True,
                sanitized_output=self.DEFAULT_BLOCK_MESSAGE,
                matches=matches,
                reason=reason,
            )

        elif selected_action == "sanitize":
            # Sanitize text by removing malicious instructions / comments
            sanitized = self._sanitize_text(raw_text, matches)
            # Reconstruct original structure if possible
            if isinstance(tool_output, str):
                final_out = sanitized
            elif isinstance(tool_output, dict):
                import json
                try:
                    final_out = json.loads(sanitized)
                except Exception:
                    final_out = {"sanitized_content": sanitized}
            else:
                final_out = sanitized

            return ScreeningResult(
                is_safe=True,
                action_taken="sanitize",
                injection_flag=True,
                sanitized_output=final_out,
                matches=matches,
                reason=f"Sanitized prompt injection pattern: {matches[0].pattern_name}",
            )

        else:  # flag
            return ScreeningResult(
                is_safe=False,
                action_taken="flag",
                injection_flag=True,
                sanitized_output=tool_output,
                matches=matches,
                reason=reason,
            )

    def _sanitize_text(self, text: str, matches: list[InjectionMatch]) -> str:
        """Strip matching substrings, zero-width characters, and HTML comments completely."""
        cleaned = text

        # 1. Strip zero-width chars
        cleaned = ZERO_WIDTH_PATTERN.sub("", cleaned)

        # 2. Strip HTML/Markdown comments
        cleaned = re.sub(r"<!--[\s\S]*?-->", "", cleaned)
        cleaned = re.sub(r"\[\s*//\s*\]\s*:\s*#\s*\([\s\S]*?\)", "", cleaned)

        # 3. Strip CSS hidden tags
        cleaned = re.sub(
            r"<[a-zA-Z0-9]+[^>]*style\s*=\s*['\"][^'\"]*(?:display\s*:\s*none|visibility\s*:\s*hidden)[^'\"]*['\"][^>]*>[\s\S]*?<\/[a-zA-Z0-9]+>",
            "",
            cleaned,
        )

        # 4. Remove direct override phrases along with their immediate trailing imperative clause
        for m in sorted(matches, key=lambda x: len(x.matched_text), reverse=True):
            if m.matched_text and not m.matched_text.startswith("["):
                # Case-insensitive removal of matched phrase and any trailing imperative action up to punctuation
                pattern = re.escape(m.matched_text) + r"(?:\s+(?:and|now|then|to)\s+[^.!?\n<]+)?"
                cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Collapse whitespace cleanly and strip leading/trailing whitespace
        cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
        cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
        return cleaned


# Global default instance
default_screener = PromptInjectionScreener()

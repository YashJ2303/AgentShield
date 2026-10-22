"""
Generate the official AgentShield presentation deck in 16:9 widescreen format (.pptx).
Includes cybersecurity dark theme, card layouts, high-res images, data tables,
and comprehensive presenter speaker notes on every slide.
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

OUTPUT_FILE = "AgentShield_Presentation.pptx"

# Base Theme Colors (Cybersecurity Dark Mode)
COLOR_BG = RGBColor(11, 15, 25)          # Deep Navy/Black #0B0F19
COLOR_CARD = RGBColor(22, 27, 34)        # Dark Slate Card #161B22
COLOR_CARD_BORDER = RGBColor(48, 54, 61) # Border #30363D
COLOR_CYAN = RGBColor(0, 229, 255)       # Electric Cyan Accent #00E5FF
COLOR_BLUE = RGBColor(56, 189, 248)      # Sky Blue #38BDF8
COLOR_GREEN = RGBColor(16, 185, 129)     # Emerald Green #10B981
COLOR_RED = RGBColor(239, 68, 68)        # Crimson Red #EF4444
COLOR_AMBER = RGBColor(245, 158, 11)     # Amber Warning #F59E0B
COLOR_WHITE = RGBColor(255, 255, 255)    # Pure White #FFFFFF
COLOR_GRAY_LIGHT = RGBColor(226, 232, 240)# Soft White #E2E8F0
COLOR_GRAY_MUTED = RGBColor(148, 163, 184)# Slate Gray #94A3B8

FONT_HEADING = "Segoe UI"
FONT_BODY = "Segoe UI"


def set_slide_background(slide):
    """Fill slide with dark navy background."""
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = COLOR_BG


def add_header(slide, title_text, category_text=None, slide_num=None):
    """Add unified top header with category badge, title, divider, and footer."""
    set_slide_background(slide)
    
    # Category badge
    if category_text:
        badge = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(10), Inches(0.3))
        tf = badge.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.text = category_text.upper()
        p.font.name = FONT_HEADING
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = COLOR_CYAN

    # Main Title
    top_pos = Inches(0.65) if category_text else Inches(0.45)
    title_box = slide.shapes.add_textbox(Inches(0.8), top_pos, Inches(11.7), Inches(0.6))
    tf_t = title_box.text_frame
    tf_t.word_wrap = True
    tf_t.margin_left = tf_t.margin_top = tf_t.margin_right = tf_t.margin_bottom = 0
    p_t = tf_t.paragraphs[0]
    p_t.text = title_text
    p_t.font.name = FONT_HEADING
    p_t.font.size = Pt(22)
    p_t.font.bold = True
    p_t.font.color.rgb = COLOR_WHITE

    # Horizontal Divider Line
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.3), Inches(11.733), Inches(0.02))
    line.fill.solid()
    line.fill.fore_color.rgb = RGBColor(30, 41, 59)
    line.line.color.rgb = RGBColor(30, 41, 59)

    # Footer
    footer = slide.shapes.add_textbox(Inches(0.8), Inches(7.1), Inches(11.733), Inches(0.3))
    tf_f = footer.text_frame
    tf_f.margin_left = tf_f.margin_top = tf_f.margin_right = tf_f.margin_bottom = 0
    p_f = tf_f.paragraphs[0]
    p_f.text = "AgentShield: Autonomous AI Agent Security Gateway | IIIT Pune B.Tech Project"
    p_f.font.name = FONT_BODY
    p_f.font.size = Pt(8.5)
    p_f.font.color.rgb = COLOR_GRAY_MUTED
    if slide_num:
        p_r = tf_f.add_paragraph()
        p_r.text = f"Slide {slide_num}"
        p_r.font.name = FONT_BODY
        p_r.font.size = Pt(8.5)
        p_r.font.color.rgb = COLOR_CYAN
        p_r.alignment = PP_ALIGN.RIGHT


def add_card(slide, left, top, width, height, title=None, border_color=None, bg_color=None):
    """Add a dark card container."""
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    card.fill.solid()
    card.fill.fore_color.rgb = bg_color or COLOR_CARD
    card.line.color.rgb = border_color or COLOR_CARD_BORDER
    card.line.width = Pt(1)
    
    if title:
        # Title box inside card
        tb = slide.shapes.add_textbox(left + Inches(0.2), top + Inches(0.18), width - Inches(0.4), Inches(0.4))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.text = title
        p.font.name = FONT_HEADING
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = COLOR_CYAN
    return card


def add_bullet_point(text_frame, title, body="", level=0, title_color=COLOR_WHITE):
    """Helper to add clean styled bullet points."""
    p = text_frame.add_paragraph() if text_frame.paragraphs[0].text else text_frame.paragraphs[0]
    p.level = level
    p.space_after = Pt(6)
    
    run_t = p.add_run()
    run_t.text = title + (" " if body else "")
    run_t.font.name = FONT_BODY
    run_t.font.size = Pt(10.5)
    run_t.font.bold = True
    run_t.font.color.rgb = title_color
    
    if body:
        run_b = p.add_run()
        run_b.text = body
        run_b.font.name = FONT_BODY
        run_b.font.size = Pt(10)
        run_b.font.color.rgb = COLOR_GRAY_LIGHT


def add_stat_box(slide, left, top, width, height, value, label, sublabel=None, value_color=COLOR_CYAN):
    """Add high-impact numerical metric box."""
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    card.fill.solid()
    card.fill.fore_color.rgb = COLOR_CARD
    card.line.color.rgb = COLOR_CARD_BORDER
    card.line.width = Pt(1)

    tb = slide.shapes.add_textbox(left + Inches(0.15), top + Inches(0.15), width - Inches(0.3), height - Inches(0.3))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

    p_val = tf.paragraphs[0]
    p_val.text = value
    p_val.font.name = FONT_HEADING
    p_val.font.size = Pt(26)
    p_val.font.bold = True
    p_val.font.color.rgb = value_color
    p_val.alignment = PP_ALIGN.CENTER

    p_lbl = tf.add_paragraph()
    p_lbl.text = label
    p_lbl.font.name = FONT_BODY
    p_lbl.font.size = Pt(10)
    p_lbl.font.bold = True
    p_lbl.font.color.rgb = COLOR_WHITE
    p_lbl.alignment = PP_ALIGN.CENTER

    if sublabel:
        p_sub = tf.add_paragraph()
        p_sub.text = sublabel
        p_sub.font.name = FONT_BODY
        p_sub.font.size = Pt(8.5)
        p_sub.font.color.rgb = COLOR_GRAY_MUTED
        p_sub.alignment = PP_ALIGN.CENTER


def main():
    prs = Presentation()
    # 16:9 Widescreen aspect ratio (13.333 x 7.5 inches)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # -------------------------------------------------------------------------------------------------
    # SLIDE 1: TITLE SLIDE
    # -------------------------------------------------------------------------------------------------
    s1 = prs.slides.add_slide(blank_layout)
    set_slide_background(s1)

    # IIIT Pune Logo
    if os.path.exists("iiit_pune_logo.jpg"):
        s1.shapes.add_picture("iiit_pune_logo.jpg", Inches(0.8), Inches(0.8), height=Inches(1.2))

    # Institute Heading
    inst_box = s1.shapes.add_textbox(Inches(2.3), Inches(0.85), Inches(10), Inches(0.8))
    tf_inst = inst_box.text_frame
    tf_inst.word_wrap = True
    p_i1 = tf_inst.paragraphs[0]
    p_i1.text = "INDIAN INSTITUTE OF INFORMATION TECHNOLOGY PUNE"
    p_i1.font.name = FONT_HEADING
    p_i1.font.size = Pt(13)
    p_i1.font.bold = True
    p_i1.font.color.rgb = COLOR_CYAN

    p_i2 = tf_inst.add_paragraph()
    p_i2.text = "Department of Computer Science and Engineering | B.Tech Capstone Defense"
    p_i2.font.name = FONT_BODY
    p_i2.font.size = Pt(10)
    p_i2.font.color.rgb = COLOR_GRAY_MUTED

    # Title Banner Card
    add_card(s1, Inches(0.8), Inches(2.2), Inches(11.733), Inches(2.8), border_color=COLOR_CYAN)
    
    t_box = s1.shapes.add_textbox(Inches(1.1), Inches(2.4), Inches(11.1), Inches(2.3))
    tf_title = t_box.text_frame
    tf_title.word_wrap = True
    
    p_proj = tf_title.paragraphs[0]
    p_proj.text = "AgentShield"
    p_proj.font.name = FONT_HEADING
    p_proj.font.size = Pt(36)
    p_proj.font.bold = True
    p_proj.font.color.rgb = COLOR_WHITE

    p_sub = tf_title.add_paragraph()
    p_sub.text = "A Low-Latency Ingress/Egress Security Gateway and Incident Replay Engine for Autonomous AI Agents"
    p_sub.font.name = FONT_BODY
    p_sub.font.size = Pt(15)
    p_sub.font.color.rgb = COLOR_BLUE
    p_sub.space_before = Pt(8)

    p_desc = tf_title.add_paragraph()
    p_desc.text = "Deterministic Tool-Boundary Policy Enforcement | AST SQL Parsing | PII Redaction | Frozen-Output Regression Replay | CyberArc 3D SOC"
    p_desc.font.name = FONT_BODY
    p_desc.font.size = Pt(10.5)
    p_desc.font.color.rgb = COLOR_GRAY_LIGHT
    p_desc.space_before = Pt(12)

    # Presenter Information Card
    add_card(s1, Inches(0.8), Inches(5.2), Inches(11.733), Inches(1.5))
    pres_box = s1.shapes.add_textbox(Inches(1.1), Inches(5.35), Inches(11.1), Inches(1.2))
    tf_pres = pres_box.text_frame
    tf_pres.word_wrap = True
    
    p_p1 = tf_pres.paragraphs[0]
    p_p1.text = "Author / Candidate: Yash  |  B.Tech in Computer Science & Engineering"
    p_p1.font.name = FONT_BODY
    p_p1.font.size = Pt(11)
    p_p1.font.bold = True
    p_p1.font.color.rgb = COLOR_WHITE

    p_p2 = tf_pres.add_paragraph()
    p_p2.text = "Repository: https://github.com/YashJ2303/AgentShield.git  |  Academic Year: 2025-2026"
    p_p2.font.name = FONT_BODY
    p_p2.font.size = Pt(9.5)
    p_p2.font.color.rgb = COLOR_CYAN
    p_p2.space_before = Pt(4)

    s1.notes_slide.notes_text_frame.text = (
        "Good morning respected evaluation panel and faculty members. Today I present AgentShield: "
        "A low-latency ingress and egress security gateway and incident replay engine designed specifically "
        "for autonomous AI agents. As LLMs shift from conversational chatbots to autonomous agents executing "
        "SQL queries, filesystem edits, and financial transactions, we encounter a dangerous security blindspot: "
        "the tool-call boundary. AgentShield establishes a deterministic, sub-5-millisecond policy enforcement perimeter."
    )

    # -------------------------------------------------------------------------------------------------
    # SLIDE 2: THE PROBLEM - TOOL-BOUNDARY BLINDSPOT
    # -------------------------------------------------------------------------------------------------
    s2 = prs.slides.add_slide(blank_layout)
    add_header(s2, "The Autonomous Agent Dilemma & The Tool Boundary Blindspot", "PROBLEM STATEMENT", 2)

    # 3 Column Cards
    col_w = Inches(3.75)
    col_gap = Inches(0.24)
    
    # Card 1: The Autonomy Revolution
    c1 = add_card(s2, Inches(0.8), Inches(1.6), col_w, Inches(5.1), "1. The Autonomy Shift")
    tb1 = s2.shapes.add_textbox(Inches(1.0), Inches(2.2), col_w - Inches(0.4), Inches(4.3))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    add_bullet_point(tf1, "From Chatbots to Agents:", "Modern architectures (LangChain, AutoGen) grant LLMs execution tools: SQL engines, bash terminals, web APIs, and payment channels.")
    add_bullet_point(tf1, "Indirect Prompt Injection:", "Untrusted data ingested from databases or external web pages acts as executable code, overriding agent instructions.")
    add_bullet_point(tf1, "The Core Risk:", "Attacks no longer result in offensive chat responses — they cause physical data loss, unauthorized wire transfers, and credential leakage.")

    # Card 2: The Security Blindspot
    c2 = add_card(s2, Inches(0.8) + col_w + col_gap, Inches(1.6), col_w, Inches(5.1), "2. The Tool-Boundary Gap", border_color=COLOR_RED)
    tb2 = s2.shapes.add_textbox(Inches(1.0) + col_w + col_gap, Inches(2.2), col_w - Inches(0.4), Inches(4.3))
    tf2 = tb2.text_frame
    tf2.word_wrap = True
    add_bullet_point(tf2, "Uncontrolled Execution:", "Once an LLM emits a tool call (e.g. `execute_query`), host environments invoke the tool blindly without validation.")
    add_bullet_point(tf2, "Syntactic Ambiguity:", "Natural language prompts cannot guarantee that an agent won't perform tautological SQL extractions (`1=1`) or path traversal (`../../`).")
    add_bullet_point(tf2, "Silent Regressions:", "Switching model versions or prompts silently breaks valid tool calls or opens zero-day bypasses.")

    # Card 3: Requirements for a Solution
    c3 = add_card(s2, Inches(0.8) + (col_w + col_gap) * 2, Inches(1.6), col_w, Inches(5.1), "3. Required Capabilities", border_color=COLOR_GREEN)
    tb3 = s2.shapes.add_textbox(Inches(1.0) + (col_w + col_gap) * 2, Inches(2.2), col_w - Inches(0.4), Inches(4.3))
    tf3 = tb3.text_frame
    tf3.word_wrap = True
    add_bullet_point(tf3, "Deterministic Gating:", "Pre-call verification that rejects non-deterministic LLM 'self-policing'.")
    add_bullet_point(tf3, "Microsecond-Scale Overhead:", "Must not bottleneck agent thought loops (target p50 < 10 ms).")
    add_bullet_point(tf3, "Full Observability:", "Cryptographic redaction of PII/secrets before data reaches logs or third-party models.")
    add_bullet_point(tf3, "Incident Replay Engine:", "Continuous regression testing using frozen state without expensive re-inference.")

    s2.notes_slide.notes_text_frame.text = (
        "Over the past 18 months, AI has evolved from passive chatbots into autonomous systems empowered with real tools. "
        "However, when an agent suffers prompt injection or hallucinates, it executes irreversible side-effects in databases, "
        "operating systems, and cloud APIs. Existing systems have a blindspot right at the tool execution boundary. "
        "AgentShield solves this by intercepting and deterministically vetting every single tool invocation."
    )

    # -------------------------------------------------------------------------------------------------
    # SLIDE 3: WHY EXISTING DEFENSES FAIL
    # -------------------------------------------------------------------------------------------------
    s3 = prs.slides.add_slide(blank_layout)
    add_header(s3, "Why Existing Defenses Fail at the Tool Boundary", "COMPARATIVE ANALYSIS", 3)

    # 2 Big Comparative Cards
    w_half = Inches(5.74)
    
    # Left Card: Existing Approaches
    add_card(s3, Inches(0.8), Inches(1.6), w_half, Inches(5.1), "Traditional Paradigms (Inadequate)", border_color=COLOR_RED)
    tb_l = s3.shapes.add_textbox(Inches(1.0), Inches(2.2), w_half - Inches(0.4), Inches(4.3))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True
    add_bullet_point(tf_l, "1. System Prompt Guardrails:", "'Please do not drop tables or read /etc/passwd'. Easily bypassed via base64, unicode homoglyphs, or roleplay prompts. Zero OS enforcement.", title_color=COLOR_RED)
    add_bullet_point(tf_l, "2. Text-Level LLM Wrappers (LlamaGuard / NeMo):", "Only inspect conversational text prompts. They lack OS execution context: unaware of realpath resolution, socket descriptors, or database schemas.", title_color=COLOR_RED)
    add_bullet_point(tf_l, "3. String / Regex Blacklists:", "Easily evaded through comment insertion (`SEL/**/ECT`), whitespace obfuscation, or query nesting.", title_color=COLOR_RED)
    add_bullet_point(tf_l, "4. Stochastic & High-Latency:", "Running a secondary LLM guardrail adds 800ms - 2000ms latency and still suffers from hallucination and non-determinism.", title_color=COLOR_RED)

    # Right Card: AgentShield Architecture
    add_card(s3, Inches(6.78), Inches(1.6), w_half, Inches(5.1), "The AgentShield Advantage (Deterministic)", border_color=COLOR_GREEN)
    tb_r = s3.shapes.add_textbox(Inches(7.0), Inches(2.2), w_half - Inches(0.4), Inches(4.3))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True
    add_bullet_point(tf_r, "1. Deterministic Tool Boundary:", "Operates directly between the agent runtime and host tools. The agent cannot bypass the gateway interceptor.", title_color=COLOR_GREEN)
    add_bullet_point(tf_r, "2. Deep AST Parser (sqlglot):", "Mathematical parsing of SQL dialects to flag structural DDL commands and tautological predicates (`WHERE 1=1`), regardless of formatting.", title_color=COLOR_GREEN)
    add_bullet_point(tf_r, "3. POSIX Realpath Sandboxing:", "Resolves all relative path components and symlinks before checking against declarative directory allowlists.", title_color=COLOR_GREEN)
    add_bullet_point(tf_r, "4. Sub-5ms Performance:", "Standalone policy check takes ~4.6 ms p50. No secondary LLM call required for deterministic rules.", title_color=COLOR_GREEN)

    s3.notes_slide.notes_text_frame.text = (
        "Why can't we just use system prompts or LlamaGuard? Because prompt-level guardrails operate only in the conversational domain. "
        "An attacker using indirect prompt injection can encode instructions that bypass text filters. Furthermore, text filters "
        "have zero OS or database context — they cannot compute whether '../' resolves outside an allowed folder or detect AST-level "
        "SQL tautologies. AgentShield treats the LLM as completely untrusted and validates structured tool payloads deterministically."
    )

    # -------------------------------------------------------------------------------------------------
    # SLIDE 4: SYSTEM ARCHITECTURE
    # -------------------------------------------------------------------------------------------------
    s4 = prs.slides.add_slide(blank_layout)
    add_header(s4, "AgentShield End-to-End System Architecture", "SYSTEM DESIGN", 4)

    # Left: Architecture Diagram Image
    arch_img = "agentshield_arch.jpg"
    if os.path.exists(arch_img):
        s4.shapes.add_picture(arch_img, Inches(0.8), Inches(1.6), width=Inches(6.2))

    # Right: Architecture Explanation Card
    add_card(s4, Inches(7.2), Inches(1.6), Inches(5.333), Inches(5.1), "Core Architecture & Execution Flow")
    tb_arch = s4.shapes.add_textbox(Inches(7.4), Inches(2.2), Inches(4.933), Inches(4.3))
    tf_arch = tb_arch.text_frame
    tf_arch.word_wrap = True
    
    add_bullet_point(tf_arch, "1. Python SDK Interceptor:", "Non-invasive decorators (`@trace_tool_call`, `@trace_model_call`) wrap agent tools with zero codebase refactoring.")
    add_bullet_point(tf_arch, "2. Synchronous Pre-Call Gate:", "SDK sends payload to `POST /gateway/check`. Gateway evaluates SQL AST, path sandboxes, domain egress, and rate/cost budgets in ~4.6ms p50.")
    add_bullet_point(tf_arch, "3. Isolated Execution:", "Only approved invocations reach external tools. Denied calls raise an immediate security exception.")
    add_bullet_point(tf_arch, "4. Post-Call Screener & Redactor:", "Screens returned tool data for indirect prompt injection and scrubs PII/API keys before updating agent memory.")
    add_bullet_point(tf_arch, "5. OTLP OpenTelemetry Spans:", "Asynchronous telemetry export persists complete run traces and metrics to SQLite/PostgreSQL.")

    s4.notes_slide.notes_text_frame.text = (
        "Here you see the four-stage lifecycle of AgentShield. First, our lightweight SDK decorator wraps any agent tool. "
        "Before the tool can execute, it issues a synchronous pre-call check to /gateway/check. Our engine evaluates SQL AST, "
        "filesystem path traversal, network egress, and financial budgets. If permitted, the tool executes. The output is then screened "
        "for indirect injection and scrubbed of sensitive PII before returning to the agent. Finally, OTLP spans are recorded to our SOC database."
    )

    # -------------------------------------------------------------------------------------------------
    # SLIDE 5: DETERMINISTIC POLICY ENGINES
    # -------------------------------------------------------------------------------------------------
    s5 = prs.slides.add_slide(blank_layout)
    add_header(s5, "Multi-Domain Deterministic Policy Enforcement", "SECURITY MECHANISMS", 5)

    card_w = Inches(5.74)
    card_h = Inches(2.4)
    
    # Engine 1: SQL AST Parser
    add_card(s5, Inches(0.8), Inches(1.6), card_w, card_h, "1. SQL AST Parser (sqlglot)", border_color=COLOR_CYAN)
    tb_e1 = s5.shapes.add_textbox(Inches(1.0), Inches(2.1), card_w - Inches(0.4), Inches(1.8))
    tf_e1 = tb_e1.text_frame
    tf_e1.word_wrap = True
    add_bullet_point(tf_e1, "Dialect-Aware AST Analysis:", "Parses raw queries into semantic trees across Postgres, SQLite, MySQL.")
    add_bullet_point(tf_e1, "DDL & DML Blocking:", "Restricts operations strictly to `SELECT`. Blocks `DROP`, `ALTER`, `TRUNCATE`, `DELETE`.")
    add_bullet_point(tf_e1, "Tautology Detection:", "Flags boolean tautologies (`1=1`, `'a'='a'`, `col=col`) used in SQL authentication bypasses.")

    # Engine 2: Filesystem Sandbox
    add_card(s5, Inches(6.78), Inches(1.6), card_w, card_h, "2. Filesystem Sandbox", border_color=COLOR_BLUE)
    tb_e2 = s5.shapes.add_textbox(Inches(7.0), Inches(2.1), card_w - Inches(0.4), Inches(1.8))
    tf_e2 = tb_e2.text_frame
    tf_e2.word_wrap = True
    add_bullet_point(tf_e2, "Realpath Canonicalization:", "Resolves `os.path.realpath` to strip symlinks, directory traversal (`../`), and URL encodings.")
    add_bullet_point(tf_e2, "Strict Root Boundaries:", "Enforces execution exclusively within designated safe workspaces (`./sandbox/`, `./data/`).")
    add_bullet_point(tf_e2, "System File Protection:", "Guarantees that sensitive host files (`/etc/passwd`, `C:\\Windows`) can never be accessed.")

    # Engine 3: Network Egress Gateway
    add_card(s5, Inches(0.8), Inches(4.3), card_w, card_h, "3. HTTP Egress Filter", border_color=COLOR_AMBER)
    tb_e3 = s5.shapes.add_textbox(Inches(1.0), Inches(4.8), card_w - Inches(0.4), Inches(1.8))
    tf_e3 = tb_e3.text_frame
    tf_e3.word_wrap = True
    add_bullet_point(tf_e3, "Domain & IP Allowlisting:", "Enforces strict domain allowlists (e.g. `api.github.com`, `open-meteo.com`).")
    add_bullet_point(tf_e3, "Anti-SSRF Protection:", "Blocks access to private RFC-1918 subnets (`10.0.0.0/8`, `192.168.0.0/16`) and cloud metadata (`169.254.169.254`).")
    add_bullet_point(tf_e3, "Threat Intel Gate:", "Optional integration with urlscan.io for pre-crawl reputation scoring.")

    # Engine 4: Budget & Rate Limiting
    add_card(s5, Inches(6.78), Inches(4.3), card_w, card_h, "4. Multi-Tier Budgets & Rates", border_color=COLOR_GREEN)
    tb_e4 = s5.shapes.add_textbox(Inches(7.0), Inches(4.8), card_w - Inches(0.4), Inches(1.8))
    tf_e4 = tb_e4.text_frame
    tf_e4.word_wrap = True
    add_bullet_point(tf_e4, "Token Quotas & Costs:", "Tracks token counts and computes real USD costs using stamped pricing tables.")
    add_bullet_point(tf_e4, "Loop & Velocity Detection:", "Detects runaway infinite loops (e.g. repeat failures) and throttles aggressive agents.")
    add_bullet_point(tf_e4, "Financial Tiers:", "Transfers exceeding monetary limits automatically trigger Human-in-the-Loop approvals.")

    s5.notes_slide.notes_text_frame.text = (
        "AgentShield does not rely on vague heuristic keyword checks. In the database domain, we use sqlglot to parse the query AST "
        "and mathematically detect unauthorized DDL commands and boolean tautologies. For files, we use realpath canonicalization "
        "to defeat directory traversal. For the network, we block SSRF and private subnet probes. And for cost control, our budget "
        "engine enforces hard token and dollar caps to halt runaway agent loops."
    )

    # -------------------------------------------------------------------------------------------------
    # SLIDE 6: PRIVACY, REDACTION & PROMPT INJECTION SCREENING
    # -------------------------------------------------------------------------------------------------
    s6 = prs.slides.add_slide(blank_layout)
    add_header(s6, "Observability, Secret Redaction & Output Screening", "DATA PRIVACY & OBSERVABILITY", 6)

    col_w = Inches(3.75)
    
    # Card 1: Redaction Engine
    add_card(s6, Inches(0.8), Inches(1.6), col_w, Inches(5.1), "1. Cryptographic PII Redaction", border_color=COLOR_CYAN)
    tb_p1 = s6.shapes.add_textbox(Inches(1.0), Inches(2.2), col_w - Inches(0.4), Inches(4.3))
    tf_p1 = tb_p1.text_frame
    tf_p1.word_wrap = True
    add_bullet_point(tf_p1, "Zero-Leak Telemetry:", "Scans and replaces sensitive values with explicit redaction tokens (e.g. `[REDACTED:API_KEY]`).")
    add_bullet_point(tf_p1, "Format-Specific Tokenization:", "Handles SSNs, ITINs, JWTs, RSA private keys, and vendor API tokens (`sk-`, `ghp-`, `xoxb-`, `SG.`).")
    add_bullet_point(tf_p1, "Luhn Algorithm Checking:", "Validates credit card checksums across Visa, Mastercard, and Amex to avoid false positive blocks on arbitrary numbers.")

    # Card 2: Output Screener
    add_card(s6, Inches(0.8) + col_w + col_gap, Inches(1.6), col_w, Inches(5.1), "2. Prompt Injection Screener", border_color=COLOR_RED)
    tb_p2 = s6.shapes.add_textbox(Inches(1.0) + col_w + col_gap, Inches(2.2), col_w - Inches(0.4), Inches(4.3))
    tf_p2 = tb_p2.text_frame
    tf_p2.word_wrap = True
    add_bullet_point(tf_p2, "Post-Execution Screening:", "Evaluates `/gateway/screen-output` on tool outputs before data is returned to the agent context.")
    add_bullet_point(tf_p2, "Indirect Injection Defense:", "Identifies prompt override vectors, roleplay traps (`System: Override instructions`), and nested command instructions.")
    add_bullet_point(tf_p2, "Unicode Normalization:", "NFKC normalization and homoglyph resolution defeat zero-width and invisible character evasion.")

    # Card 3: OTLP OpenTelemetry
    add_card(s6, Inches(0.8) + (col_w + col_gap) * 2, Inches(1.6), col_w, Inches(5.1), "3. OpenTelemetry (OTLP)", border_color=COLOR_BLUE)
    tb_p3 = s6.shapes.add_textbox(Inches(1.0) + (col_w + col_gap) * 2, Inches(2.2), col_w - Inches(0.4), Inches(4.3))
    tf_p3 = tb_p3.text_frame
    tf_p3.word_wrap = True
    add_bullet_point(tf_p3, "Industry Standard Protocol:", "Exports standard OpenTelemetry Protocol (OTLP) Protobuf traces over HTTP.")
    add_bullet_point(tf_p3, "Full Distributed Waterfall:", "Captures root agent thoughts, intermediate tool checks, child tool executions, and redaction counts.")
    add_bullet_point(tf_p3, "Enterprise Integration:", "Plug-and-play compatibility with Jaeger, Prometheus, Datadog, or Grafana Tempo.")

    s6.notes_slide.notes_text_frame.text = (
        "Observability without privacy is a security liability. AgentShield incorporates a high-speed redaction engine that scrubs "
        "SSNs, API keys, and Luhn-validated credit card numbers before any span is exported. In addition, our output screener monitors "
        "data returned by external tools to prevent indirect prompt injection from hijacking the agent downstream."
    )

    # -------------------------------------------------------------------------------------------------
    # SLIDE 7: INCIDENT REPLAY ENGINE (RQ2)
    # -------------------------------------------------------------------------------------------------
    s7 = prs.slides.add_slide(blank_layout)
    add_header(s7, "Incident Replay Engine: Frozen-Output Regression Testing (RQ2)", "REGRESSION TESTING", 7)

    # Top Overview Card
    add_card(s7, Inches(0.8), Inches(1.6), Inches(11.733), Inches(1.4))
    tb_r_top = s7.shapes.add_textbox(Inches(1.0), Inches(1.75), Inches(11.333), Inches(1.1))
    tf_r_top = tb_r_top.text_frame
    tf_r_top.word_wrap = True
    p_rt = tf_r_top.paragraphs[0]
    p_rt.text = "Research Question 2: How faithfully does frozen-output replay detect regressions across behavior changes?"
    p_rt.font.name = FONT_HEADING
    p_rt.font.size = Pt(13)
    p_rt.font.bold = True
    p_rt.font.color.rgb = COLOR_CYAN
    p_rt_body = tf_r_top.add_paragraph()
    p_rt_body.text = "Problem: Modifying security policies or upgrading agent model checkpoints often causes silent regressions. However, re-running test suites against live LLM APIs incurs high financial cost and non-deterministic variability."
    p_rt_body.font.name = FONT_BODY
    p_rt_body.font.size = Pt(10)
    p_rt_body.font.color.rgb = COLOR_GRAY_LIGHT
    p_rt_body.space_before = Pt(4)

    # Left: Mechanism
    add_card(s7, Inches(0.8), Inches(3.2), Inches(6.8), Inches(3.5), "The Frozen-Output Replay Mechanism")
    tb_r_mech = s7.shapes.add_textbox(Inches(1.0), Inches(3.7), Inches(6.4), Inches(2.9))
    tf_r_mech = tb_r_mech.text_frame
    tf_r_mech.word_wrap = True
    add_bullet_point(tf_r_mech, "1. Deterministic Trace Freezing:", "Historical agent executions are serialized into immutable trace bundles, capturing prompt, tool call arguments, and tool outputs.")
    add_bullet_point(tf_r_mech, "2. Simulated Re-Execution:", "Candidate policies or models are executed against cached tool responses — zero external side-effects and zero API token costs.")
    add_bullet_point(tf_r_mech, "3. Normalized Levenshtein Matcher (>= 0.85):", "Tolerates natural linguistic paraphrasing while catching destructive regressions.")

    # Right: Replay Benchmark Stats
    add_card(s7, Inches(7.8), Inches(3.2), Inches(4.733), Inches(3.5), "Empirical Replay Fidelity (RQ2)", border_color=COLOR_GREEN)
    add_stat_box(s7, Inches(8.1), Inches(3.8), Inches(2.0), Inches(1.2), "25 / 25", "Recall (100%)", "All regressions caught", COLOR_GREEN)
    add_stat_box(s7, Inches(10.25), Inches(3.8), Inches(2.0), Inches(1.2), "23 / 25", "Specificity (92%)", "Paraphrases accepted", COLOR_CYAN)
    add_stat_box(s7, Inches(8.1), Inches(5.2), Inches(2.0), Inches(1.2), "25 / 27", "Precision (92.6%)", "High decision confidence", COLOR_BLUE)
    add_stat_box(s7, Inches(10.25), Inches(5.2), Inches(2.0), Inches(1.2), "2", "False Alarms", "Compact SQL variations", COLOR_AMBER)

    s7.notes_slide.notes_text_frame.text = (
        "Research Question 2 addresses a major industry headache: How do you verify policy updates without spending thousands of dollars "
        "re-running LLM queries? AgentShield freezes historical tool outputs into an immutable cache. When you test a candidate policy, "
        "the agent re-executes against frozen outputs. Our Levenshtein matcher tolerates benign paraphrasing while catching 100% of regressions."
    )

    # -------------------------------------------------------------------------------------------------
    # SLIDE 8: CYBERARC 3D CONSTELLATION & SOC DASHBOARD
    # -------------------------------------------------------------------------------------------------
    s8 = prs.slides.add_slide(blank_layout)
    add_header(s8, "CyberArc 3D WebGL Constellation & SOC Command Center", "SECURITY OBSERVABILITY & SOC", 8)

    # Left: CyberArc 3D Screenshot
    cyber_img = "cyberarc_3d_soc.jpg"
    if os.path.exists(cyber_img):
        s8.shapes.add_picture(cyber_img, Inches(0.8), Inches(1.6), width=Inches(6.2))

    # Right: Features Card
    add_card(s8, Inches(7.2), Inches(1.6), Inches(5.333), Inches(5.1), "Real-Time SOC Command Center")
    tb_soc = s8.shapes.add_textbox(Inches(7.4), Inches(2.2), Inches(4.933), Inches(4.3))
    tf_soc = tb_soc.text_frame
    tf_soc.word_wrap = True
    
    add_bullet_point(tf_soc, "Three.js WebGL Constellation:", "Dynamic 3D force-directed graph visualizing the central Gateway Core, orbiting agent personas, and enterprise tools.")
    add_bullet_point(tf_soc, "Real-Time Particle Latency Flow:", "Particle velocities reflect live end-to-end response times; link colors indicate protocol status.")
    add_bullet_point(tf_soc, "Attack Hotspots Isolation:", "Interactive filter isolating blocked SQL injections, path traversal attempts, and prompt injection vectors.")
    add_bullet_point(tf_soc, "Dynamic Health Scoring:", "Zero synthetic numbers: health scores, denial attribution, and latency percentiles computed live from `/analytics/summary`.")
    add_bullet_point(tf_soc, "Interactive Audit Drilldown:", "Clicking any node reveals connected spans, active rate limits, and historical policy verdicts.")

    s8.notes_slide.notes_text_frame.text = (
        "Here is CyberArc 3D, our real-time security constellation powered by Three.js and WebGL. At the center is our pinned "
        "gateway anchor. Surrounding it are autonomous agent personas and third-party tools. Security engineers can filter for "
        "Attack Hotspots to immediately pinpoint blocked threats, while live particle streams reflect latency flows across the cluster."
    )

    # -------------------------------------------------------------------------------------------------
    # SLIDE 9: LIVE INTERACTIVE DEMONSTRATION
    # -------------------------------------------------------------------------------------------------
    s9 = prs.slides.add_slide(blank_layout)
    add_header(s9, "Live Interactive Demonstration Workflow", "PRACTICAL DEMONSTRATION", 9)

    col_w = Inches(3.75)
    
    # Demo 1: CyberArc 3D
    add_card(s9, Inches(0.8), Inches(1.6), col_w, Inches(5.1), "Scenario 1: CyberArc 3D", border_color=COLOR_CYAN)
    tb_d1 = s9.shapes.add_textbox(Inches(1.0), Inches(2.2), col_w - Inches(0.4), Inches(4.3))
    tf_d1 = tb_d1.text_frame
    tf_d1.word_wrap = True
    add_bullet_point(tf_d1, "Action:", "Explore the 3D topology at `http://localhost:5173/`.")
    add_bullet_point(tf_d1, "Visual Highlight:", "Demonstrate smooth 60fps orbit controls, camera lookAt centering, and dynamic link pulsing.")
    add_bullet_point(tf_d1, "Filter Check:", "Switch between 'All Nodes', 'Live Network', and 'Attack Hotspots' to inspect localized policy violations.")

    # Demo 2: Active Attack Block
    add_card(s9, Inches(0.8) + col_w + col_gap, Inches(1.6), col_w, Inches(5.1), "Scenario 2: Active Attack", border_color=COLOR_RED)
    tb_d2 = s9.shapes.add_textbox(Inches(1.0) + col_w + col_gap, Inches(2.2), col_w - Inches(0.4), Inches(4.3))
    tf_d2 = tb_d2.text_frame
    tf_d2.word_wrap = True
    add_bullet_point(tf_d2, "Action:", "Open Live Agent Lab tab. Select SQL Agent persona.")
    add_bullet_point(tf_d2, "Adversary Payload:", "`SELECT * FROM users WHERE '1'='1' UNION SELECT credit_card FROM payments;`")
    add_bullet_point(tf_d2, "Instant Verdict:", "Gateway returns DENIED in 4.2ms. AST parser flags boolean tautology. External DB untouched.")

    # Demo 3: Approvals Queue
    add_card(s9, Inches(0.8) + (col_w + col_gap) * 2, Inches(1.6), col_w, Inches(5.1), "Scenario 3: Human Approvals", border_color=COLOR_AMBER)
    tb_d3 = s9.shapes.add_textbox(Inches(1.0) + (col_w + col_gap) * 2, Inches(2.2), col_w - Inches(0.4), Inches(4.3))
    tf_d3 = tb_d3.text_frame
    tf_d3.word_wrap = True
    add_bullet_point(tf_d3, "Action:", "Select Financial Agent. Request high-value refund of $2,500.")
    add_bullet_point(tf_d3, "Hold State:", "Exceeds $1,000 threshold. Tool execution paused in asynchronous approval queue.")
    add_bullet_point(tf_d3, "Admin Verification:", "Administrator inspects redacted payload, reviews justification, and grants cryptographic execution token.")

    s9.notes_slide.notes_text_frame.text = (
        "At this stage, we transition into our 3-minute live demonstration. We will rotate the CyberArc 3D constellation, "
        "execute an active SQL injection in the Live Agent Lab to demonstrate sub-5ms interception, and finally show a high-consequence "
        "financial transaction triggering our Human-in-the-Loop approval queue."
    )

    # -------------------------------------------------------------------------------------------------
    # SLIDE 10: EMPIRICAL BENCHMARK RESULTS (RQ1 & RQ2)
    # -------------------------------------------------------------------------------------------------
    s10 = prs.slides.add_slide(blank_layout)
    add_header(s10, "Empirical Evaluation & Benchmark Findings", "EMPIRICAL RIGOR", 10)

    # Top Stat Callouts
    stat_w = Inches(2.75)
    stat_gap = Inches(0.24)
    add_stat_box(s10, Inches(0.8), Inches(1.6), stat_w, Inches(1.3), "100.0%", "Modeled Attack Prevention", "45/45 Destructive Tasks [92.1, 100.0]%", COLOR_GREEN)
    add_stat_box(s10, Inches(0.8) + stat_w + stat_gap, Inches(1.6), stat_w, Inches(1.3), "0.0%", "Benign False Block Rate", "0/90 False Positives [0.0, 4.1]%", COLOR_CYAN)
    add_stat_box(s10, Inches(0.8) + (stat_w + stat_gap) * 2, Inches(1.6), stat_w, Inches(1.3), "4.6 ms", "Standalone Policy Check", "p50 Gateway Latency", COLOR_BLUE)
    add_stat_box(s10, Inches(0.8) + (stat_w + stat_gap) * 3, Inches(1.6), stat_w, Inches(1.3), "+18.0 ms", "Full Instrumented Overhead", "p50 Tool-Call Latency (sync spans)", COLOR_AMBER)

    # Summary Benchmark Table
    add_card(s10, Inches(0.8), Inches(3.1), Inches(11.733), Inches(3.6), "Formal Evaluation Matrix (Wilson 95% Confidence Intervals)")
    
    # Table
    table_shape = s10.shapes.add_table(6, 4, Inches(1.0), Inches(3.6), Inches(11.333), Inches(2.8))
    table = table_shape.table
    table.columns[0].width = Inches(3.2)
    table.columns[1].width = Inches(2.5)
    table.columns[2].width = Inches(2.8)
    table.columns[3].width = Inches(2.833)

    headers = ["Metric / Scenario Group", "Baseline (No Policy)", "AgentShield Result", "Wilson 95% Conf. Interval"]
    for i, h in enumerate(headers):
        cell = table.cell(0, i)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(30, 41, 59)
        p = cell.text_frame.paragraphs[0]
        p.font.name = FONT_HEADING
        p.font.size = Pt(9.5)
        p.font.bold = True
        p.font.color.rgb = COLOR_CYAN

    rows_data = [
        ("Modeled Destructive Actions (45 runs)", "0.0% prevented (45/45 executed)", "100.0% prevented (45/45)", "[92.1%, 100.0%]"),
        ("Benign Standard Tasks (90 runs)", "100.0% executed (0/90 blocked)", "100.0% executed (0/90 false blocks)", "[0.0%, 4.1%] false block"),
        ("Held-Out Active Attacks (11 zero-day runs)", "9.1% (1/11 blocklist baseline)", "45.5% prevented (5/11 allowlist)", "[21.3%, 72.0%] (overlap disclosed)"),
        ("RQ2 Replay Regression Recall (25 runs)", "N/A (outcome-only check)", "25 / 25 Regressions Caught", "[86.7%, 100.0%]"),
        ("RQ2 Replay Specificity (25 paraphrases)", "N/A (outcome-only check)", "23 / 25 Benign Accepted", "[75.0%, 97.8%]"),
    ]

    for row_idx, data in enumerate(rows_data, start=1):
        for col_idx, text in enumerate(data):
            cell = table.cell(row_idx, col_idx)
            cell.text = text
            cell.fill.solid()
            cell.fill.fore_color.rgb = COLOR_CARD if row_idx % 2 == 1 else RGBColor(18, 22, 30)
            p = cell.text_frame.paragraphs[0]
            p.font.name = FONT_BODY
            p.font.size = Pt(8.5)
            p.font.color.rgb = COLOR_WHITE if col_idx < 3 else COLOR_GRAY_MUTED

    s10.notes_slide.notes_text_frame.text = (
        "Here are our empirical results across 155 scenario runs. In RQ1, AgentShield stopped 100% of modeled destructive attacks "
        "while maintaining a 0.0% false block rate on 90 benign tasks. Standalone policy checks take only 4.6 milliseconds. "
        "When combined with full OTLP span persistence and redaction, total overhead is 18.04ms p50 — less than 2% of total LLM generation time. "
        "In RQ2, our frozen replay engine achieved 100% recall on destructive regressions while accepting 92% of benign paraphrases."
    )

    # -------------------------------------------------------------------------------------------------
    # SLIDE 11: SCIENTIFIC RIGOR & DISCLOSED BOUNDARIES
    # -------------------------------------------------------------------------------------------------
    s11 = prs.slides.add_slide(blank_layout)
    add_header(s11, "Scientific Rigor & Disclosed Limitations", "ACADEMIC INTEGRITY", 11)

    w_half = Inches(5.74)
    
    # Left Card: Rigor & Reproducibility
    add_card(s11, Inches(0.8), Inches(1.6), w_half, Inches(5.1), "1. Methodological Rigor", border_color=COLOR_GREEN)
    tb_m1 = s11.shapes.add_textbox(Inches(1.0), Inches(2.2), w_half - Inches(0.4), Inches(4.3))
    tf_m1 = tb_m1.text_frame
    tf_m1.word_wrap = True
    add_bullet_point(tf_m1, "Wilson 95% Confidence Intervals:", "Every empirical rate includes rigorous Wilson score intervals to prevent overclaiming on modest sample sizes.")
    add_bullet_point(tf_m1, "Machine-Checked Claims (`CLAIMS.md`):", "All 29 empirical claims in the paper are automatically mapped and verified against test fixtures via `scripts/check_claims.py`.")
    add_bullet_point(tf_m1, "Hermetic Seeded Reproduction:", "Single reproduction command (`python scripts/evaluate.py --seed 42`) yields bit-for-bit identical benchmark results.")

    # Right Card: Disclosed Limitations
    add_card(s11, Inches(6.78), Inches(1.6), w_half, Inches(5.1), "2. Disclosed Boundaries (KNOWN_LIMITATIONS)", border_color=COLOR_AMBER)
    tb_m2 = s11.shapes.add_textbox(Inches(7.0), Inches(2.2), w_half - Inches(0.4), Inches(4.3))
    tf_m2 = tb_m2.text_frame
    tf_m2.word_wrap = True
    add_bullet_point(tf_m2, "Scope Note on RQ3:", "Cost and anomaly analytics are fully implemented and unit-tested, but designated as 'implemented, not empirically validated' against live model selection.", title_color=COLOR_AMBER)
    add_bullet_point(tf_m2, "Held-Out Overlap Disclosure:", "Allowlist 45.5% [21.3, 72.0]% vs blocklist 9.1% [1.6, 37.7]% have overlapping CIs; no statistical superiority is claimed.")
    add_bullet_point(tf_m2, "Scripted Agent Simulators:", "Primary benchmark suite uses deterministic mock agents for test repeatability rather than live non-deterministic APIs.")
    add_bullet_point(tf_m2, "Unseen Secret Formats:", "Regex matching achieves 33.3% on arbitrary unseen vendor keys, proving why structured AST and deterministic gates are essential.")

    s11.notes_slide.notes_text_frame.text = (
        "We pride ourselves on academic honesty. We do not claim 100% prevention against arbitrary zero-day attacks. "
        "Against 11 un-modeled active attacks, our allowlist stopped 45.5%, and we explicitly disclose that confidence intervals overlap. "
        "Furthermore, we transparently classify RQ3 as 'implemented, not empirically validated', adhering to strict scientific rigor."
    )

    # -------------------------------------------------------------------------------------------------
    # SLIDE 12: CONCLUSION & FUTURE SCOPE
    # -------------------------------------------------------------------------------------------------
    s12 = prs.slides.add_slide(blank_layout)
    add_header(s12, "Summary of Contributions & Future Roadmap", "CONCLUSION", 12)

    col_w = Inches(3.75)
    
    # Card 1: Key Contributions
    add_card(s12, Inches(0.8), Inches(1.6), col_w, Inches(5.1), "1. Key Contributions", border_color=COLOR_CYAN)
    tb_c1 = s12.shapes.add_textbox(Inches(1.0), Inches(2.2), col_w - Inches(0.4), Inches(4.3))
    tf_c1 = tb_c1.text_frame
    tf_c1.word_wrap = True
    add_bullet_point(tf_c1, "Deterministic Tool Perimeter:", "First low-latency gateway operating at the tool boundary with sub-5ms overhead.")
    add_bullet_point(tf_c1, "Incident Replay Fidelity:", "Zero-cost regression testing suite catching 100% of regressions across model and policy changes.")
    add_bullet_point(tf_c1, "CyberArc 3D Visualization:", "Real-time SOC monitoring constellation providing unprecedented visibility into agent actions.")

    # Card 2: Future Scope
    add_card(s12, Inches(0.8) + col_w + col_gap, Inches(1.6), col_w, Inches(5.1), "2. Future Research Roadmap", border_color=COLOR_BLUE)
    tb_c2 = s12.shapes.add_textbox(Inches(1.0) + col_w + col_gap, Inches(2.2), col_w - Inches(0.4), Inches(4.3))
    tf_c2 = tb_c2.text_frame
    tf_c2.word_wrap = True
    add_bullet_point(tf_c2, "Multi-Agent Trust Mesh:", "Extending policy enforcement to peer-to-peer agent communications and collaborative workflows.")
    add_bullet_point(tf_c2, "Hardware Enclave Execution (TEE):", "Executing tool evaluation inside confidential computing enclaves (e.g. Intel SGX / AMD SEV).")
    add_bullet_point(tf_c2, "Formal Policy Verification:", "Mathematically proving policy non-interference and completeness using SMT solvers (Z3).")

    # Card 3: Deliverables & Links
    add_card(s12, Inches(0.8) + (col_w + col_gap) * 2, Inches(1.6), col_w, Inches(5.1), "3. Open Source & Defense", border_color=COLOR_GREEN)
    tb_c3 = s12.shapes.add_textbox(Inches(1.0) + (col_w + col_gap) * 2, Inches(2.2), col_w - Inches(0.4), Inches(4.3))
    tf_c3 = tb_c3.text_frame
    tf_c3.word_wrap = True
    add_bullet_point(tf_c3, "Public GitHub Repository:", "https://github.com/YashJ2303/AgentShield.git", title_color=COLOR_CYAN)
    add_bullet_point(tf_c3, "B.Tech Project Report:", "Complete 15-section thesis document adhering to IIIT Pune guidelines (`AgentShield_BTech_Project_Report.docx`).")
    add_bullet_point(tf_c3, "Passing Test Suite:", "212 collected tests, 29 verified claims, 0 lint errors.")
    add_bullet_point(tf_c3, "Thank You:", "We welcome questions and feedback from the distinguished evaluation panel.", title_color=COLOR_WHITE)

    s12.notes_slide.notes_text_frame.text = (
        "In conclusion, AgentShield demonstrates that securing autonomous AI agents does not require heavy, non-deterministic model wrappers. "
        "By enforcing deterministic safety at the tool execution boundary, we achieve enterprise protection, continuous regression testing, "
        "and sub-5-millisecond latency. All code, documentation, and the complete B.Tech report are publicly accessible on GitHub. "
        "Thank you for your attention, and I now welcome your questions."
    )

    prs.save(OUTPUT_FILE)
    print(f"[SUCCESS] Generated {OUTPUT_FILE} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    main()

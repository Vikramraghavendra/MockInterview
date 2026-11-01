import ast
import re
from typing import Any


CODEGURU_EVALUATION_MATRIX = {
    "evaluation_standard": "CODEGURU_COMMUNITY_BEST_PRACTICES",
    "focus_areas": (
        "OOP refactoring patterns and clean structural abstractions.",
        "Deterministic resource management and safe allocations/collections.",
        "Language-idiomatic accuracy, including explicit memory and exception handling.",
    ),
}


LANGUAGE_PATTERNS = {
    "python": {
        "structure": r"\b(class|Protocol|ABC|dataclass)\b",
        "resources": r"\b(with|async with|try|finally|contextmanager)\b",
        "idioms": r"\b(dict|list|set|tuple|deque|defaultdict|dataclass|enumerate|zip)\b",
    },
    "javascript": {
        "structure": r"\b(class|interface|type)\b|\bfunction\s+\w+|\bconst\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
        "resources": r"\btry\b|\bfinally\b|AbortController|removeEventListener|clear(?:Timeout|Interval)|return\s*\(\)\s*=>",
        "idioms": r"\b(Map|Set|WeakMap|WeakSet|Promise\.allSettled|Array\.from)\b|\?\.",
    },
    "typescript": {
        "structure": r"\b(class|interface|type)\b|\bfunction\s+\w+|\bconst\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
        "resources": r"\btry\b|\bfinally\b|AbortController|removeEventListener|clear(?:Timeout|Interval)|return\s*\(\)\s*=>",
        "idioms": r"\b(Map|Set|WeakMap|WeakSet|Promise\.allSettled|Array\.from)\b|\?\.",
    },
    "java": {
        "structure": r"\b(class|interface|record|enum)\b",
        "resources": r"\btry\s*\(|\btry\b|\bfinally\b|AutoCloseable|implements\s+Closeable",
        "idioms": r"\b(List|Map|Set|Optional|Stream|ArrayList|HashMap|HashSet)\b",
    },
    "csharp": {
        "structure": r"\b(class|interface|record|struct|enum)\b",
        "resources": r"\busing\s*(?:\(|var\b)|\btry\b|\bfinally\b|IDisposable",
        "idioms": r"\b(List|Dictionary|HashSet|IEnumerable|IReadOnlyList|Task)\b",
    },
    "cpp": {
        "structure": r"\b(class|struct|namespace|template)\b",
        "resources": r"\b(unique_ptr|shared_ptr|lock_guard|scoped_lock|vector)\b|\btry\b|\bcatch\b|~\w+\s*\(",
        "idioms": r"\b(vector|array|map|unordered_map|set|optional|variant|string_view)\b",
    },
}

DESIGN_TERMS = (
    "abstraction", "encapsulation", "interface", "responsibility", "onion architecture",
    "separation of concerns", "dependency inversion", "refactor", "design pattern",
)


def _python_structure_summary(code: str) -> tuple[str, list[str]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "incomplete", []

    classes = sum(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
    functions = sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree))
    with_blocks = sum(isinstance(node, (ast.With, ast.AsyncWith)) for node in ast.walk(tree))
    exception_blocks = sum(isinstance(node, ast.Try) for node in ast.walk(tree))
    evidence = [f"Python AST found {classes} class(es) and {functions} function(s)."]
    if with_blocks:
        evidence.append(f"Python AST found {with_blocks} deterministic context manager block(s).")
    if exception_blocks:
        evidence.append(f"Python AST found {exception_blocks} exception handling block(s).")
    return "parsed", evidence


def _review_area(key: str, label: str, pattern: str, code: str, guidance: str) -> dict[str, Any]:
    matches = re.findall(pattern, code, flags=re.IGNORECASE | re.MULTILINE)
    return {
        "key": key,
        "label": label,
        "status": "observed" if matches else ("insufficient_code" if not code.strip() else "not_observed"),
        "evidence": [f"Found {len(matches)} language-specific signal(s): {', '.join(sorted(set(matches))[:6])}."] if matches else [],
        "guidance": guidance,
    }


def check_codeguru_standards(
    timeline_events: list[dict[str, Any]],
    final_code: str = "",
    language: str = "python",
) -> dict[str, Any]:
    normalized_language = language.strip().lower()
    if normalized_language in {"js", "jsx", "mjs"}:
        normalized_language = "javascript"
    elif normalized_language in {"ts", "tsx"}:
        normalized_language = "typescript"
    elif normalized_language in {"cs", "c#", ".net"}:
        normalized_language = "csharp"
    elif normalized_language in {"c++", "cc", "cxx"}:
        normalized_language = "cpp"
    patterns = LANGUAGE_PATTERNS.get(normalized_language, LANGUAGE_PATTERNS["python"])

    code = final_code.strip()
    if not code:
        code = "\n".join(
            str((event.get("data") or {}).get("text_inserted", ""))
            for event in timeline_events
            if event.get("event_type") == "CODE_MUTATION"
        ).strip()

    speech_events = [event for event in timeline_events if event.get("event_type") == "SPEECH_TOKEN"]
    speech_text = " ".join(str(event.get("word", "")) for event in speech_events).lower()
    primary_declarations = [
        event
        for event in timeline_events
        if event.get("event_type") == "CODE_MUTATION"
        and re.search(r"\b(class|interface|function|def)\b", str((event.get("data") or {}).get("text_inserted", "")))
    ]
    first_declaration_ms = min(
        (int(event.get("session_timestamp_ms", 0)) for event in primary_declarations),
        default=None,
    )
    prior_design_words = [
        str(event.get("word", "")).lower()
        for event in speech_events
        if first_declaration_ms is not None
        and 0 <= first_declaration_ms - int(event.get("session_timestamp_ms", 0)) <= 30_000
    ]
    prior_design_context = " ".join(prior_design_words)
    design_speech_before_code = bool(
        prior_design_context and any(term in prior_design_context for term in DESIGN_TERMS)
    )
    architecture_area = {
        "key": "oop_design_and_refactoring",
        "label": "OOP design and structural abstractions",
        "status": (
            "observed" if design_speech_before_code or re.search(patterns["structure"], code)
            else "insufficient_code" if not code.strip() and not speech_text
            else "not_observed"
        ),
        "evidence": [],
        "guidance": "Explain responsibilities, boundaries, and refactoring intent before introducing primary classes or modules.",
    }
    if design_speech_before_code:
        architecture_area["evidence"].append("Structural design language appeared before a primary declaration.")
    if code and re.search(patterns["structure"], code):
        architecture_area["evidence"].append("Code contains a language-specific type or function abstraction.")

    resource_area = _review_area(
        "resource_management",
        "Resource management and exception safety",
        patterns["resources"],
        code,
        "Review ownership, cleanup, exception paths, and safe allocation for resources used by this solution.",
    )
    idiom_area = _review_area(
        "language_idioms",
        "Language-specific idioms",
        patterns["idioms"],
        code,
        f"Review the solution against idiomatic {normalized_language} collections, syntax, and lifecycle patterns.",
    )

    parser_status = "not_applicable"
    parser_evidence = []
    if normalized_language == "python" and code:
        parser_status, parser_evidence = _python_structure_summary(code)
        if parser_status == "incomplete":
            parser_evidence.append("Python AST could not parse the draft; pattern checks still ran on the partial code.")

    return {
        "evaluation_standard": CODEGURU_EVALUATION_MATRIX["evaluation_standard"],
        "language": normalized_language,
        "parser": {"name": "python_ast" if normalized_language == "python" else "language_pattern_scan", "status": parser_status, "evidence": parser_evidence},
        "source_characters": len(code),
        "areas": [architecture_area, resource_area, idiom_area],
        "focus_areas": list(CODEGURU_EVALUATION_MATRIX["focus_areas"]),
        "note": "Static signals are coaching prompts, not proof of correctness or defects.",
    }
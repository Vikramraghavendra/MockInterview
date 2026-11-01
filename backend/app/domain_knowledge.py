import json
from dataclasses import dataclass

from app.codeguru import CODEGURU_EVALUATION_MATRIX
from app.contest import CONTEST_SIMULATION_METRICS


@dataclass(frozen=True)
class RubricPhase:
    name: str
    window: str
    checks: tuple[str, ...]


@dataclass(frozen=True)
class DomainProfile:
    id: str
    name: str
    short_name: str
    short_code: str
    subtrack: str
    language: str
    knowledge_base: tuple[str, ...]
    expectations: tuple[str, ...]
    evidence_terms: tuple[tuple[str, ...], ...]
    rubric_phases: tuple[RubricPhase, ...]
    question_bank: tuple[str, ...]
    preparation_materials: tuple[str, ...]
    challenge: str
    starter_code: str
    scope_window_ms: int = 300_000
    company_round: str = "Open community challenge"
    difficulty: str = "Advanced"
    topics: tuple[str, ...] = ()
    hints: tuple[str, ...] = ()


PREPARATION_MASTERCLASS = (
    {
        "title": "Module 1: Strategic Communicator Blueprint",
        "principles": (
            "Golden 5-Minute Rule: clarify scale, functional boundaries, and performance goals before typing.",
            "Translate syntax into intent: explain the decision and its tradeoffs, not the keystrokes.",
            "Pause about every 10 lines to review correctness and Big-O time and space costs.",
        ),
    },
    {
        "title": "Module 2: High-Signal Verification Playbooks",
        "principles": (
            "Structure the discussion: Understand and Scope → Propose Architecture → Deep Dive → Identify Failure Modes.",
            "Test empty and null inputs, 10x scale spikes, retries, and temporary network failures.",
        ),
    },
)


DOMAINS = {
    "backend_systems": DomainProfile(
        id="backend_systems",
        name="Backend Engineering",
        short_name="Backend",
        short_code="SYS / 01",
        subtrack="Core System Design",
        language="python",
        knowledge_base=(
            "Global rate limiting, checkout-service reliability, token bucket and sliding-window algorithms, and accuracy versus latency budgets.",
            "Redis Cluster synchronization and write bottlenecks versus per-process in-memory state and cross-instance consistency.",
            "Distributed race conditions, atomic updates, cache stampedes, regional partitions, and degraded-mode fallbacks.",
            "At 100,000 peak RPS, quantify per-key state, shard throughput, network fanout, and hot-key pressure.",
        ),
        expectations=(
            "Scopes functional and non-functional requirements, including 100,000 peak RPS, before coding.",
            "Explains accuracy, latency, shared Redis Cluster state, and local-memory tradeoffs.",
            "Identifies distributed races, cache stampedes, and regional partition fallbacks.",
        ),
        evidence_terms=(
            ("rps", "100,000", "throughput", "scale", "accuracy", "latency", "functional", "non-functional", "requirement"),
            ("redis", "cluster", "shared state", "local memory", "in-memory", "synchronization", "consistency", "tradeoff"),
            ("race", "stampede", "partition", "regional", "fallback", "atomic", "network failure", "fail open", "fail closed"),
        ),
        rubric_phases=(
            RubricPhase("Scope discovery", "0–5 min", (
                "Separate functional and non-functional requirements.",
                "Ask about sliding-window accuracy targets and token-bucket latency allowances.",
            )),
            RubricPhase("Architectural layout", "5–15 min", (
                "Compare Redis Cluster synchronization/write bottlenecks with localized in-memory state.",
                "Describe the consistency and latency consequences across instances.",
            )),
            RubricPhase("Corner-case defense", "15–30 min", (
                "Mitigate distributed races and cache-stampede vectors.",
                "Define regional network-partition behavior and safe fallbacks.",
            )),
        ),
        question_bank=(
            "What does the checkout service consider an acceptable rate-limit accuracy error?",
            "Is the limit per user, account, IP, route, or a combination?",
            "How should the system behave when a region loses access to shared state?",
            "How do you prevent a hot key or retry storm from overwhelming a Redis shard?",
        ),
        preparation_materials=(
            "Practice calculating requests per shard and state size for 100,000 peak RPS.",
            "Compare token bucket, sliding log, and sliding counter accuracy and latency.",
        ),
        challenge="Design a scalable, global rate-limiting tier protecting an e-commerce checkout service handling a peak of 100,000 requests per second (RPS).",
        starter_code="class RateLimiter:\n    def __init__(self, limit, window_seconds):\n        pass\n\n    def allow(self, key, now):\n        pass\n",
        company_round="Amazon-style SDE-2 / System Design",
        difficulty="Advanced",
        topics=("Rate limiting", "Distributed systems", "Redis", "Consistency"),
        hints=(
            "Clarify the identity being limited, burst allowance, accuracy target, and failure policy before choosing an algorithm.",
            "Compare token bucket with a sliding window, then map the required state across instances and regions.",
            "Make per-key updates atomic and specify fail-open or fail-closed behavior during a regional partition.",
        ),
    ),
    "backend_data_infra": DomainProfile(
        id="backend_data_infra",
        name="Backend Engineering",
        short_name="Backend",
        short_code="DATA / 02",
        subtrack="High-Throughput Data Infrastructure",
        language="python",
        knowledge_base=(
            "Kafka partitioning, consumer groups, key selection, ordering guarantees, and rebalancing under consumer scaling.",
            "Event-time versus processing-time windows, watermark generation, late-event policies, and state retention.",
            "At-least-once delivery, deduplication keys, idempotent sinks, transactional boundaries, and replay safety.",
            "IoT sensor telemetry is bursty and may arrive out of order; account for backpressure and schema evolution.",
        ),
        expectations=(
            "Maps queue and Kafka partition topology to ordering needs and consumer scaling.",
            "Distinguishes event time from processing time and states a concrete watermark/late-event policy.",
            "Shows idempotency or deduplication mechanisms for duplicate deliveries and retries.",
        ),
        evidence_terms=(
            ("kafka", "partition", "queue", "consumer", "key", "ordering", "topology"),
            ("event time", "processing time", "watermark", "late event", "window", "out-of-order"),
            ("idempotent", "idempotency", "dedup", "duplicate", "exactly-once", "retry", "processed id"),
        ),
        rubric_phases=(
            RubricPhase("Topology structuring", "Design", (
                "Select queue and Kafka partition keys that preserve required ordering.",
                "Explain consumer scaling and partition-count limits.",
            )),
            RubricPhase("Windowing logic", "Design", (
                "Separate event-time semantics from processing-time semantics.",
                "Choose watermark delay and policy for events arriving after the watermark.",
            )),
            RubricPhase("Idempotency verification", "Implementation", (
                "Use stable event identifiers or idempotent writes to handle duplicate delivery.",
                "Explain replay and exactly-once boundaries without overclaiming guarantees.",
            )),
        ),
        question_bank=(
            "Which sensor or device key should define Kafka partitioning, and what ordering is required?",
            "How late can telemetry arrive, and what should happen after the watermark passes?",
            "Where is the deduplication key stored, and how long must it be retained?",
            "How does the pipeline react when consumers fall behind during a traffic burst?",
        ),
        preparation_materials=(
            "Practice drawing a Kafka topic, partition key, consumer group, window state, and idempotent sink.",
            "State a numeric watermark delay and explain the latency/completeness tradeoff.",
        ),
        challenge="Design a real-time analytics aggregation worker pipeline processing high-frequency IoT sensor metrics telemetry packets with out-of-order delivery windows.",
        starter_code="def aggregate_telemetry(events, watermark_ms, sink):\n    # Validate, window, deduplicate, and persist events.\n    pass\n",
        company_round="Amazon-style Data Engineer II / Streaming Systems",
        difficulty="Advanced",
        topics=("Kafka", "Event time", "Watermarks", "Idempotency"),
        hints=(
            "Choose a partition key that preserves only the ordering your aggregates actually require.",
            "Separate event time from processing time and state a watermark delay plus a late-event policy.",
            "Use a stable event identifier at an idempotent sink so retries and replays do not double count.",
        ),
    ),
    "frontend_architecture": DomainProfile(
        id="frontend_architecture",
        name="Frontend Engineering",
        short_name="Frontend",
        short_code="UI / 03",
        subtrack="High-Performance UI Architectures",
        language="javascript",
        knowledge_base=(
            "Browser style, layout, paint, and compositing costs; forced synchronous layout and reflow penalties.",
            "Virtualization and DOM node recycling for a table of 500,000 active records at a 60 FPS interaction target.",
            "Scroll-event scheduling, listener cleanup, memoized row boundaries, and localized state ownership.",
            "Measure frame time and memory footprint instead of assuming that virtualization alone solves every bottleneck.",
        ),
        expectations=(
            "Profiles layout/reflow costs and defines a frame-time budget for 60 FPS.",
            "Uses row recycling and bounded scroll scheduling with explicit listener cleanup.",
            "Localizes state updates to avoid broad high-frequency component re-renders.",
        ),
        evidence_terms=(
            ("layout", "reflow", "paint", "profile", "frame", "60 fps", "performance", "500,000", "500k"),
            ("recycle", "virtual", "memory", "debounce", "throttle", "listener", "cleanup", "garbage"),
            ("localized", "local state", "component", "rerender", "re-render", "broadcast", "subscription", "selector"),
        ),
        rubric_phases=(
            RubricPhase("Computational profiling", "Design", (
                "Explain layout/reflow costs and row-height measurement constraints.",
                "Choose a 16.7 ms frame budget and identify work that must stay off the critical path.",
            )),
            RubricPhase("Memory footprint controls", "Implementation", (
                "Recycle a bounded number of DOM rows and clean up observers/listeners.",
                "Bound or throttle scroll-driven work and avoid retaining evicted row data.",
            )),
            RubricPhase("State segregation", "Implementation", (
                "Keep high-frequency viewport state local to the virtualizer.",
                "Prevent table-wide state broadcasts from rerendering unaffected rows.",
            )),
        ),
        question_bank=(
            "How many DOM rows exist at once, and how does that change during fast scrolling?",
            "How do variable row heights affect measurement, layout, and scroll anchoring?",
            "Which state changes should rerender a row, and which should remain inside the viewport controller?",
            "How are observers and scroll listeners cleaned up when the table unmounts?",
        ),
        preparation_materials=(
            "Profile a large table and explain style, layout, paint, and compositing separately.",
            "Estimate mounted DOM nodes and memory use; compare overscan size with scroll smoothness.",
        ),
        challenge="Build a high-performance, virtualized data table infrastructure layer capable of smoothly rendering 500,000 active tracking records without dropping below 60 FPS.",
        starter_code="function VirtualTable({ rows, rowHeight, viewportHeight }) {\n  // Recycle only the rows visible in the viewport.\n}\n",
        company_round="Google-style Frontend SWE / UI Architecture",
        difficulty="Advanced",
        topics=("Virtualization", "Browser rendering", "Memory", "State locality"),
        hints=(
            "Estimate the mounted row budget from viewport height and row height before choosing a rendering strategy.",
            "Keep a bounded visible window with overscan, recycle row instances, and avoid forced layout on every scroll.",
            "Keep viewport state local and clean up observers/listeners when the table unmounts.",
        ),
    ),
    "ml_platform": DomainProfile(
        id="ml_platform",
        name="Data Science & Machine Learning",
        short_name="ML Platform",
        short_code="ML / 04",
        subtrack="Distributed ML Platform Design",
        language="python",
        knowledge_base=(
            "Separate offline training, evaluation, and model publishing from online feature retrieval and inference.",
            "Meet a 50 ms personalized-feed serving budget with feature freshness, cache hit rate, and model execution costs visible.",
            "Feature stores, online/offline parity, model versioning, shadow traffic, and low-latency fallback strategies.",
            "Monitor feature and prediction drift, service health, ranking quality, and downstream dependency failures.",
        ),
        expectations=(
            "Separates offline batch training and validation from online inference and serving.",
            "Allocates a concrete 50 ms budget across feature retrieval, model execution, and response assembly.",
            "Defines drift/quality monitoring and safe fallbacks for unavailable feature or model services.",
        ),
        evidence_terms=(
            ("offline", "batch", "training", "online", "inference", "model version"),
            ("50 ms", "latency", "feature store", "feature retrieval", "cache", "budget", "lookup"),
            ("drift", "monitor", "fallback", "degraded", "feature freshness", "accuracy", "downstream"),
        ),
        rubric_phases=(
            RubricPhase("Operational separation", "Architecture", (
                "Separate batch training/evaluation from online feature retrieval and inference.",
                "Describe model release, versioning, and rollback boundaries.",
            )),
            RubricPhase("Latency optimization", "Architecture", (
                "Budget the full request path against the 50 ms target.",
                "Compare inline feature computation with low-latency cached/store lookups.",
            )),
            RubricPhase("Monitoring and drift", "Operations", (
                "Track feature drift, prediction quality, and service-level latency/error metrics.",
                "Define graceful fallbacks when feature or model dependencies fail.",
            )),
        ),
        question_bank=(
            "Which feed features must be fresh, and what staleness can the product tolerate?",
            "How is the 50 ms p95 budget divided across feature lookup, inference, and response assembly?",
            "How do training and online serving prevent feature skew across model versions?",
            "What safe ranking fallback is used if the online feature store is unavailable?",
        ),
        preparation_materials=(
            "Draw the offline train/evaluate/publish path separately from the online request path.",
            "Prepare p50/p95/p99 latency budgets, drift indicators, and a dependency-failure fallback.",
        ),
        challenge="Design a near-real-time user recommendation model inference service that serves personalized feeds within a tight 50ms latency threshold.",
        starter_code="def recommend(user_id, request_context, feature_store, model):\n    # Retrieve bounded-latency features and serve a ranked feed.\n    pass\n",
        company_round="ML Engineer II / Recommendation Systems Design",
        difficulty="Advanced",
        topics=("Online inference", "Feature stores", "Latency", "Drift monitoring"),
        hints=(
            "Draw the offline training path separately from the online request path before estimating latency.",
            "Allocate the 50 ms budget across feature retrieval, inference, and response assembly.",
            "Choose a safe fallback for missing features and metrics that reveal freshness or prediction drift.",
        ),
    ),
}


DOMAIN_KNOWLEDGE_BASE = {
    profile.id: {
        "title": f"{profile.name} / {profile.subtrack}",
        "subtrack": profile.subtrack,
        "company_round": profile.company_round,
        "difficulty": profile.difficulty,
        "topics": list(profile.topics),
        "hints": list(profile.hints),
        "knowledge_base": list(profile.knowledge_base),
        "expectations": list(profile.expectations),
        "rubric_phases": [
            {"name": phase.name, "window": phase.window, "checks": list(phase.checks)}
            for phase in profile.rubric_phases
        ],
        "question_bank": list(profile.question_bank),
        "challenge": profile.challenge,
        "materials": "Preparation Blueprint: " + " ".join((
            *profile.preparation_materials,
            *(module["title"] + ": " + " ".join(module["principles"]) for module in PREPARATION_MASTERCLASS),
        )),
        "preparation_materials": list(profile.preparation_materials),
        "preparation_masterclass": [
            {"title": module["title"], "principles": list(module["principles"])}
            for module in PREPARATION_MASTERCLASS
        ],
        "flag_rules": [
            {
                "code": "STRUCTURAL_PREMATURE_IMPLEMENTATION",
                "rule": "Flag actual insert/delete events before the five-minute scope window.",
            },
            {"code": "RUBRIC_EXPECTATION_NOT_OBSERVED", "rule": "Flag unmet expectations only when transcript evidence exists."},
        ],
        "code_quality_standards": CODEGURU_EVALUATION_MATRIX,
        "contest_simulation": CONTEST_SIMULATION_METRICS,
    }
    for profile in DOMAINS.values()
}


DOMAIN_ALIASES = {
    "frontend_ui": "frontend_architecture",
    "data_engineering": "backend_data_infra",
}


def get_domain(domain_id: str) -> DomainProfile:
    canonical_id = DOMAIN_ALIASES.get(domain_id, domain_id)
    try:
        return DOMAINS[canonical_id]
    except KeyError as exc:
        raise ValueError(f"Unknown interview domain: {domain_id}") from exc


def inject_domain_context_to_llm(domain_id: str) -> str:
    profile = DOMAINS.get(DOMAIN_ALIASES.get(domain_id, domain_id), DOMAINS["backend_systems"])
    phases = [
        {"name": phase.name, "window": phase.window, "checks": phase.checks}
        for phase in profile.rubric_phases
    ]
    return "\n".join((
        "[SYSTEM CONTROL: CONTEXT PARAMETERS]",
        f"Grade an applicant interviewing for: {profile.name} / {profile.subtrack}.",
        "Knowledge base:\n" + json.dumps(profile.knowledge_base, indent=2),
        "Critical grading matrix:\n" + json.dumps(profile.expectations, indent=2),
        "Phase checklist:\n" + json.dumps(phases, indent=2),
        "Question bank:\n" + json.dumps(profile.question_bank, indent=2),
        "Preparation materials:\n" + json.dumps(profile.preparation_materials, indent=2),
        "Shared preparation masterclass:\n" + json.dumps(PREPARATION_MASTERCLASS, indent=2),
        "Code quality standards:\n" + json.dumps(CODEGURU_EVALUATION_MATRIX, indent=2),
        "Contest simulation:\n" + json.dumps(CONTEST_SIMULATION_METRICS, indent=2),
        "If the timeline shows code before the five-minute scope window, apply STRUCTURAL_PREMATURE_IMPLEMENTATION.",
        "Use only transcript/timeline evidence. Mark absent evidence as not observed; do not infer candidate behavior.",
    ))


def public_domains() -> list[dict[str, object]]:
    return [
        {
            "id": profile.id,
            "name": profile.name,
            "short_name": profile.short_name,
            "short_code": profile.short_code,
            "subtrack": profile.subtrack,
            "company_round": profile.company_round,
            "difficulty": profile.difficulty,
            "topics": list(profile.topics),
            "hints": list(profile.hints),
            "language": profile.language,
            "challenge": profile.challenge,
            "starter_code": profile.starter_code,
            "knowledge_base": list(profile.knowledge_base),
            "expectations": list(profile.expectations),
            "rubric_phases": [
                {"name": phase.name, "window": phase.window, "checks": list(phase.checks)}
                for phase in profile.rubric_phases
            ],
            "question_bank": list(profile.question_bank),
            "preparation_materials": list(profile.preparation_materials),
            "materials": DOMAIN_KNOWLEDGE_BASE[profile.id]["materials"],
            "code_quality_standards": CODEGURU_EVALUATION_MATRIX,
            "contest_simulation": CONTEST_SIMULATION_METRICS,
            "preparation_masterclass": [
                {"title": module["title"], "principles": list(module["principles"])}
                for module in PREPARATION_MASTERCLASS
            ],
        }
        for profile in DOMAINS.values()
    ]
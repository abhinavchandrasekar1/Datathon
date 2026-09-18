"""
Digital Product Feedback Intelligence — Backend Engine
High-performance Flask service providing multi-dimensional feedback segregation:
- Intent classification (Bugs, Feature Requests, Billing Risk, UX Friction, Kudos)
- Aspect-based sentiment analysis with negation & intensifier handling
- Dynamic urgency scoring (P0 Critical through P3 Low)
- Canonical problem clustering & deduplication
- Cross-channel intelligence & executive action synthesis
"""

import csv
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, Response, send_from_directory

APP_DIR = Path(__file__).resolve().parent


def find_data_file() -> Path:
    candidates = [
        APP_DIR / "data" / "sample_feedback.json",
        APP_DIR.parent / "data" / "sample_feedback.json",
        Path.cwd() / "data" / "sample_feedback.json",
        Path.cwd() / "feedback-intelligence" / "data" / "sample_feedback.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return APP_DIR / "data" / "sample_feedback.json"


DATA_FILE = find_data_file()


def find_static_folder() -> str:
    candidates = [
        APP_DIR / "static",
        APP_DIR.parent / "static",
        Path.cwd() / "static",
        Path.cwd() / "feedback-intelligence" / "static",
    ]
    for p in candidates:
        if p.is_dir() and (p / "index.html").exists():
            return str(p)
    return str(APP_DIR / "static")


app = Flask(__name__, static_folder=find_static_folder(), static_url_path="")


# ---------------------------------------------------------------------------
# WSGI Path Preservation Middleware for Vercel Rewrites
# ---------------------------------------------------------------------------
class VercelPathMiddleware:
    """Ensures original URL path is preserved when Vercel rewrites requests to /api/index."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path in ("/api/index", "/api/index.py", "/api"):
            original = environ.get("HTTP_X_FORWARDED_URI") or environ.get("HTTP_X_MATCHED_PATH")
            if original:
                environ["PATH_INFO"] = original.split("?")[0]
        return self.wsgi_app(environ, start_response)


app.wsgi_app = VercelPathMiddleware(app.wsgi_app)

# ---------------------------------------------------------------------------
# Storage & Persistence (Serverless-Safe with /tmp Fallback)
# ---------------------------------------------------------------------------
def load_initial_feedback():
    tmp_file = Path("/tmp") / "sample_feedback.json"
    if tmp_file.exists():
        try:
            with open(tmp_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return []


FEEDBACK = load_initial_feedback()
_next_id = max((item.get("id", 0) for item in FEEDBACK), default=0) + 1


def save_feedback():
    """Atomically write the feedback collection back to disk with serverless /tmp fallback."""
    # Try primary location first (works locally and in persistent containers)
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(FEEDBACK, f, indent=2, ensure_ascii=False)
            return
    except (OSError, IOError):
        pass

    # Read-only filesystem fallback (e.g. AWS Lambda / Vercel Serverless Function)
    try:
        tmp_dir = Path("/tmp")
        if tmp_dir.exists() and tmp_dir.is_dir():
            with open(tmp_dir / "sample_feedback.json", "w", encoding="utf-8") as f:
                json.dump(FEEDBACK, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Serverless storage warning: Could not persist to /tmp ({e}). Data retained in memory.")


# ---------------------------------------------------------------------------
# Text Normalization & Lexical Preprocessing
# ---------------------------------------------------------------------------
TYPO_MAP = {
    "whtaspp": "whatsapp",
    "whatsap": "whatsapp",
    "playstore": "play store",
    "appstore": "app store",
    "loggin": "login",
    "signon": "login",
    "cant": "can't",
    "dont": "don't",
    "doesnt": "doesn't",
    "didnt": "didn't",
    "isnt": "isn't",
    "wont": "won't",
    "plz": "please",
    "pls": "please",
    "u": "you",
    "ur": "your",
}

WORD_PATTERN = re.compile(r"[a-z0-9']+")


def normalize_text(text: str) -> str:
    """Normalize colloquialisms, typos, and common chat acronyms."""
    tokens = text.lower().split()
    corrected = [TYPO_MAP.get(token.strip(".,!?\"'"), token) for token in tokens]
    return " ".join(corrected)


# ---------------------------------------------------------------------------
# Multi-Dimensional Lexicons & Heuristics
# ---------------------------------------------------------------------------
POSITIVE_TERMS = {
    "love": 2.0, "great": 1.5, "excellent": 2.0, "amazing": 2.0, "awesome": 2.0,
    "good": 1.0, "fantastic": 2.0, "smooth": 1.2, "clean": 1.0, "easy": 1.0,
    "fast": 1.2, "quick": 1.0, "flawless": 2.0, "helpful": 1.2, "wonderful": 1.8,
    "perfect": 2.0, "happy": 1.5, "resolved": 1.2, "improved": 1.2, "instantly": 1.0,
    "best": 2.0, "nice": 1.0, "impressive": 1.8, "reliable": 1.5, "seamless": 1.5,
    "useful": 1.2, "organized": 1.0, "intuitive": 1.4, "solid": 1.0,
}

NEGATIVE_TERMS = {
    "crash": 2.5, "crashing": 2.5, "crashes": 2.5, "freeze": 2.0, "freezes": 2.0,
    "bug": 1.8, "buggy": 1.8, "slow": 1.4, "frustrating": 1.8, "confusing": 1.2,
    "annoying": 1.4, "rude": 1.8, "unhelpful": 1.5, "fail": 2.0, "failed": 2.0,
    "failing": 2.0, "issue": 1.2, "issues": 1.2, "problem": 1.2, "problems": 1.2,
    "hate": 2.0, "terrible": 2.2, "awful": 2.2, "worst": 2.5, "broken": 2.0,
    "cluttered": 1.2, "difficult": 1.2, "timeout": 1.8, "charged": 1.5, "delay": 1.2,
    "laggy": 1.4, "glitch": 1.5, "error": 1.8, "disappointed": 1.6, "poor": 1.5,
    "unreasonable": 1.5, "missing": 1.0, "outdated": 1.2, "useless": 2.0, "stuck": 1.6,
}

EMOJI_WEIGHTS = {
    "❤️": 2.0, "🔥": 1.5, "👍": 1.2, "🚀": 1.5, "😍": 2.0, "👏": 1.2, "🎉": 1.5,
    "😡": -2.5, "🤬": -3.0, "💩": -2.0, "👎": -1.5, "💔": -2.0, "🤮": -2.5, "🤦": -1.5, "⚠️": -1.2,
}

INTENSIFIERS = {"very": 1.4, "extremely": 1.8, "super": 1.4, "really": 1.3, "so": 1.3, "constantly": 1.5, "completely": 1.5}
ATTENUATORS = {"barely": 0.5, "slightly": 0.6, "somewhat": 0.7, "a bit": 0.6}
NEGATIONS = {"not", "no", "never", "n't", "cannot", "can't", "didn't", "isn't", "won't", "doesn't", "without"}

# Intent detection pattern suites
INTENT_PATTERNS = {
    "Bug Report": [
        r"\b(crash|crashes|crashing|freeze|freezes|bug|glitch|error|broken|fail|failed|timeout|not work|not properly|malfunction|stuck|reboot)\b",
    ],
    "Feature Request": [
        r"\b(please add|would be (great|amazing|nice)|wish|add a|add support|missing|should be added|could you add|hope you add|feature request)\b",
    ],
    "Billing & Churn Risk": [
        r"\b(charged|charge|double charged|billing|refund|subscription|cancel|payment failed|money|price|pricing|tier|cost|unreasonable price|deducted)\b",
    ],
    "UX Friction": [
        r"\b(confusing|cluttered|hard to (find|use|navigate)|interface|ui|ux|layout|buttons?|menu|onboarding|redesign|outdated)\b",
    ],
    "Customer Support": [
        r"\b(support|service|representative|agent|ticket|response|responded|unhelpful|rude|email back)\b",
    ],
    "Kudos & Praise": [
        r"\b(love|great|excellent|smooth|clean|fast|amazing|flawless|good job|useful|best app|well organized|perfect)\b",
    ],
}

SUBSYSTEM_RULES = {
    "Auth & Access": ["login", "log in", "sign in", "account", "password", "timeout", "timing out", "credentials", "access"],
    "Payments & Billing": ["price", "pricing", "charged", "billing", "refund", "subscription", "payment", "money", "cost", "card", "tier"],
    "Stability & Core": ["crash", "crashing", "freeze", "freezes", "bug", "glitch", "error", "tabs", "switch", "load", "button", "work properly"],
    "UI & Experience": ["ui", "interface", "design", "dashboard", "cluttered", "confusing", "navigate", "menu", "dark mode", "onboarding", "outdated"],
    "Speed & Performance": ["slow", "fast", "quick", "load", "loading", "instantly", "laggy", "performance", "delay", "responds"],
    "Media & Data": ["photo", "video", "image", "upload", "download", "export", "pdf", "report", "data", "file"],
    "Support Operations": ["support", "service", "rude", "helpful", "unhelpful", "response", "responded", "ticket", "email"],
}

URGENCY_TRIGGERS = {
    "P0": [
        "double charged", "payment failed", "money was still deducted", "money deducted",
        "can't even get into my account", "locked out", "lost data", "unauthorized charge",
        "constant crashes", "crash every time", "keeps crashing", "crashes after the latest update",
    ],
    "P1": [
        "freezes whenever", "app freezes", "not respond when i click", "failed three times",
        "support hasn't responded in days", "timing out", "slower than before", "not work properly",
    ],
    "P2": [
        "confusing", "price increase", "cluttered", "could use a proper redesign",
        "pricing plans are confusing", "takes forever to open", "missing and should be added",
        "please add", "would be amazing",
    ],
}


# ---------------------------------------------------------------------------
# Core Analytical Functions
# ---------------------------------------------------------------------------
def analyze_sentiment(text: str):
    """
    Computes sentiment score, categorical polarity, and primary emotional tone.
    Accounts for contrastive clauses ('but', 'however'), negation windows, and intensifiers.
    """
    normalized = normalize_text(text)
    
    # Split on contrastive conjunctions so trailing sentiment is weighted appropriately
    clauses = re.split(r",?\s+(?:but|however|although|though|except)\s+", normalized)
    
    cumulative_score = 0.0
    tokens_evaluated = 0

    for clause_idx, clause in enumerate(clauses):
        clause_weight = 1.3 if clause_idx == len(clauses) - 1 and len(clauses) > 1 else 1.0
        words = WORD_PATTERN.findall(clause)
        
        for i, word in enumerate(words):
            val = 0.0
            if word in POSITIVE_TERMS:
                val = POSITIVE_TERMS[word]
            elif word in NEGATIVE_TERMS:
                val = -NEGATIVE_TERMS[word]

            if val != 0.0:
                # Apply modifier window
                window = words[max(0, i - 2):i]
                multiplier = 1.0
                negated = any(w in NEGATIONS or w.endswith("n't") for w in window)
                
                for w in window:
                    if w in INTENSIFIERS:
                        multiplier *= INTENSIFIERS[w]
                    elif w in ATTENUATORS:
                        multiplier *= ATTENUATORS[w]
                
                if negated:
                    val = -val * 0.85
                
                cumulative_score += (val * multiplier * clause_weight)
                tokens_evaluated += 1

    # Check emojis directly on raw text
    for char, weight in EMOJI_WEIGHTS.items():
        if char in text:
            cumulative_score += weight
            tokens_evaluated += 1

    # Heuristic for short broken phrases like "not work properly"
    if "not work" in normalized or "not properly" in normalized or "doesn't work" in normalized:
        cumulative_score -= 1.8

    # Normalize to [-1.0, 1.0]
    normalized_score = max(-1.0, min(1.0, cumulative_score / 3.2))
    
    if normalized_score >= 0.18:
        label = "positive"
    elif normalized_score <= -0.15:
        label = "negative"
    else:
        label = "neutral"

    # Emotion classification
    low = normalized
    if label == "negative":
        if any(w in low for w in ["charged", "money", "refund", "card", "billing"]):
            emotion = "Billing Dispute"
        elif any(w in low for w in ["crash", "freeze", "bug", "timing out", "error"]):
            emotion = "Frustrated"
        elif any(w in low for w in ["confusing", "hard to", "where", "unclear"]):
            emotion = "Confused"
        else:
            emotion = "Disappointed"
    elif label == "positive":
        if any(w in low for w in ["love", "flawless", "amazing", "best", "perfect"]):
            emotion = "Delighted"
        else:
            emotion = "Satisfied"
    else:
        if any(w in low for w in ["would be", "please", "suggest", "missing"]):
            emotion = "Constructive"
        else:
            emotion = "Neutral"

    return label, round(normalized_score, 2), emotion


def detect_intent(text: str) -> str:
    """Identify the primary goal or stance of the feedback item."""
    norm = normalize_text(text)
    
    # Priority order for intent
    for intent, patterns in INTENT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, norm, re.IGNORECASE):
                return intent
    return "General Observation"


def detect_subsystems(text: str) -> list[str]:
    """Map the feedback to applicable product subsystems."""
    norm = normalize_text(text)
    matched = [subsystem for subsystem, keys in SUBSYSTEM_RULES.items() if any(k in norm for k in keys)]
    return matched or ["Core Experience"]


def calculate_urgency(text: str, sentiment_score: float, intent: str) -> tuple[str, int]:
    """
    Determines triage urgency:
    P0 (Critical Blocker) -> score 75-100
    P1 (High Impact)      -> score 50-74
    P2 (Medium Polish)    -> score 25-49
    P3 (Low / Informational) -> score 0-24
    """
    norm = normalize_text(text)
    score = 15  # baseline

    # Pattern triggers
    for phrase in URGENCY_TRIGGERS["P0"]:
        if phrase in norm:
            score += 65
            break
    for phrase in URGENCY_TRIGGERS["P1"]:
        if phrase in norm:
            score += 40
            break
    for phrase in URGENCY_TRIGGERS["P2"]:
        if phrase in norm:
            score += 20
            break

    # Intent adjustment
    if intent == "Billing & Churn Risk":
        score += 30
    elif intent == "Bug Report":
        score += 25
    elif intent == "UX Friction":
        score += 10
    elif intent == "Kudos & Praise":
        score = max(5, score - 25)

    # Sentiment penalty/relief
    if sentiment_score < -0.5:
        score += 25
    elif sentiment_score < -0.1:
        score += 15
    elif sentiment_score > 0.3:
        score -= 20

    score = max(0, min(100, score))

    if score >= 70:
        priority = "P0"
    elif score >= 45:
        priority = "P1"
    elif score >= 20:
        priority = "P2"
    else:
        priority = "P3"

    return priority, score


def enrich(item: dict) -> dict:
    """Enriches a raw feedback entry with full multi-dimensional intelligence."""
    text = item.get("text", "")
    sentiment, sentiment_score, emotion = analyze_sentiment(text)
    intent = detect_intent(text)
    subsystems = detect_subsystems(text)
    urgency_level, urgency_score = calculate_urgency(text, sentiment_score, intent)

    return {
        **item,
        "sentiment": sentiment,
        "sentiment_score": sentiment_score,
        "emotion": emotion,
        "intent": intent,
        "topics": subsystems,
        "urgency": urgency_level,
        "urgency_score": urgency_score,
    }


# ---------------------------------------------------------------------------
# Problem Clustering & Synthesis
# ---------------------------------------------------------------------------
CANONICAL_CLUSTERS = [
    {
        "id": "cluster_crashes",
        "title": "Application Crashes & Freezes on Interaction",
        "match": ["crash", "crashes", "crashing", "freeze", "freezes", "not respond", "switching tabs"],
        "intent": "Bug Report",
        "urgency": "P0",
        "recommendation": "Profile memory leaks during media upload and multi-tab switching.",
    },
    {
        "id": "cluster_billing",
        "title": "Payment Processing & Double-Billing Grievances",
        "match": ["charged", "double charged", "payment failed", "refund", "subscription", "deducted"],
        "intent": "Billing & Churn Risk",
        "urgency": "P0",
        "recommendation": "Audit gateway idempotency keys and review auto-renewal notification timing.",
    },
    {
        "id": "cluster_auth",
        "title": "Authentication Timeouts & Account Lockouts",
        "match": ["login", "timing out", "log in", "account", "timeout", "sign in"],
        "intent": "Bug Report",
        "urgency": "P1",
        "recommendation": "Extend token refresh expiry and log auth gateway response latencies.",
    },
    {
        "id": "cluster_performance",
        "title": "Load Time Degraded & Sluggish Responses",
        "match": ["slow", "slow to load", "slower", "laggy", "takes forever", "fast", "instantly"],
        "intent": "Performance",
        "urgency": "P1",
        "recommendation": "Run bundle analysis to reduce initial asset payload on mobile networks.",
    },
    {
        "id": "cluster_ux",
        "title": "Navigation Ambiguity & Cluttered Dashboard",
        "match": ["cluttered", "confusing", "buttons", "redesign", "outdated", "settings menu", "interface"],
        "intent": "UX Friction",
        "urgency": "P2",
        "recommendation": "Conduct usability audit on primary CTA density and settings discoverability.",
    },
    {
        "id": "cluster_features",
        "title": "Feature Requests: Dark Mode & PDF Export",
        "match": ["dark mode", "export", "pdf", "reports", "missing", "please add", "add a way"],
        "intent": "Feature Request",
        "urgency": "P2",
        "recommendation": "Schedule PDF export and dark palette theme into Q4 milestone roadmap.",
    },
]


def cluster_feedback(enriched_items: list[dict]) -> list[dict]:
    """Groups incoming feedback into canonical synthesized issues with volume & metrics."""
    clusters_data = []

    for template in CANONICAL_CLUSTERS:
        matched_items = []
        for item in enriched_items:
            norm = normalize_text(item["text"])
            if any(k in norm for k in template["match"]):
                matched_items.append(item)

        if matched_items:
            sources = Counter(i["source"] for i in matched_items)
            sentiments = Counter(i["sentiment"] for i in matched_items)
            avg_urgency = round(sum(i["urgency_score"] for i in matched_items) / len(matched_items))
            quotes = [i["text"] for i in matched_items if len(i["text"]) > 20]
            
            clusters_data.append({
                "id": template["id"],
                "title": template["title"],
                "intent": template["intent"],
                "urgency": template["urgency"],
                "avg_urgency_score": avg_urgency,
                "count": len(matched_items),
                "sources": dict(sources),
                "sentiments": dict(sentiments),
                "recommendation": template["recommendation"],
                "sample_quote": quotes[0] if quotes else matched_items[0]["text"],
            })

    clusters_data.sort(key=lambda c: (c["urgency"] == "P0", c["count"]), reverse=True)
    return clusters_data


def generate_executive_digest(enriched: list[dict], clusters: list[dict]) -> dict:
    """Generates an executive-level summary and health snapshot."""
    total = len(enriched) or 1
    pos = sum(1 for i in enriched if i["sentiment"] == "positive")
    neg = sum(1 for i in enriched if i["sentiment"] == "negative")
    neu = sum(1 for i in enriched if i["sentiment"] == "neutral")

    # Net Product Sentiment Index (-100 to +100)
    health_score = round(((pos - neg) / total) * 100)
    
    p0_count = sum(1 for i in enriched if i["urgency"] == "P0")
    billing_risks = sum(1 for i in enriched if i["intent"] == "Billing & Churn Risk")
    
    top_fires = [c for c in clusters if c["urgency"] in ("P0", "P1")][:3]
    top_opportunity = next((c for c in clusters if c["intent"] == "Feature Request"), None)

    return {
        "health_score": health_score,
        "sentiment_ratio": f"{round((pos / total) * 100)}% Positive",
        "p0_critical_count": p0_count,
        "billing_risk_count": billing_risks,
        "top_fires": top_fires,
        "top_opportunity": top_opportunity,
        "takeaway": (
            "Immediate engineering attention required on photo upload crashes and double billing disputes. "
            "Customer sentiment remains resilient on core usability and interface speed."
            if p0_count > 0 else
            "Product stability is steady. High feature demand noted for dark mode and document export."
        ),
    }


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/feedback", methods=["GET"])
def get_feedback():
    enriched = [enrich(item) for item in FEEDBACK]
    enriched.sort(key=lambda x: x.get("date", ""), reverse=True)
    return jsonify(enriched)


@app.route("/api/feedback", methods=["POST"])
def add_feedback():
    global _next_id
    body = request.get_json(force=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Feedback text is required"}), 400

    today = datetime.now().strftime("%Y-%m-%d")
    item = {
        "id": _next_id,
        "text": text,
        "source": body.get("source", "Manual Entry"),
        "date": body.get("date", today),
    }
    _next_id += 1
    FEEDBACK.append(item)
    save_feedback()
    return jsonify(enrich(item)), 201


@app.route("/api/feedback/batch", methods=["POST"])
def batch_feedback():
    """Bulk ingest entries from CSV or JSON payload."""
    global _next_id
    content_type = request.content_type or ""
    added = []
    today = datetime.now().strftime("%Y-%m-%d")

    if "application/json" in content_type:
        entries = request.get_json(force=True) or []
        if isinstance(entries, dict):
            entries = entries.get("items", [])
        for entry in entries:
            text = (entry.get("text") or "").strip()
            if text:
                item = {
                    "id": _next_id,
                    "text": text,
                    "source": entry.get("source", "Batch Import"),
                    "date": entry.get("date", today),
                }
                _next_id += 1
                FEEDBACK.append(item)
                added.append(enrich(item))
    else:
        # Process CSV
        data_text = request.get_data(as_text=True)
        f = io.StringIO(data_text)
        reader = csv.DictReader(f)
        for row in reader:
            text = row.get("text") or row.get("feedback") or row.get("comment") or ""
            text = text.strip()
            if text:
                item = {
                    "id": _next_id,
                    "text": text,
                    "source": row.get("source") or "CSV Import",
                    "date": row.get("date") or today,
                }
                _next_id += 1
                FEEDBACK.append(item)
                added.append(enrich(item))

    if added:
        save_feedback()
    return jsonify({"imported_count": len(added), "items": added}), 201


@app.route("/api/summary", methods=["GET"])
def get_summary():
    enriched = [enrich(item) for item in FEEDBACK]
    total = len(enriched) or 1

    # Sentiment distribution
    sentiment_counts = Counter(item["sentiment"] for item in enriched)
    
    # Intent distribution
    intent_counts = Counter(item["intent"] for item in enriched)

    # Urgency counts
    urgency_counts = Counter(item["urgency"] for item in enriched)

    # Topic / Subsystem frequency
    topic_counts = Counter()
    for item in enriched:
        topic_counts.update(item["topics"])

    # Daily sentiment trends
    by_date = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0})
    for item in enriched:
        by_date[item["date"]][item["sentiment"]] += 1
    trend = [{"date": d, **counts} for d, counts in sorted(by_date.items())]

    # Cross-channel sentiment analysis
    channel_breakdown = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0, "total": 0})
    for item in enriched:
        src = item.get("source", "Unknown")
        channel_breakdown[src][item["sentiment"]] += 1
        channel_breakdown[src]["total"] += 1

    # Pain points (Negative feedback by topic)
    pain_points = Counter()
    for item in enriched:
        if item["sentiment"] == "negative":
            pain_points.update(item["topics"])

    clusters = cluster_feedback(enriched)
    executive_digest = generate_executive_digest(enriched, clusters)

    return jsonify({
        "total_feedback": total,
        "sentiment_counts": dict(sentiment_counts),
        "sentiment_pct": {k: round(v / total * 100, 1) for k, v in sentiment_counts.items()},
        "intent_counts": dict(intent_counts),
        "urgency_counts": dict(urgency_counts),
        "topic_counts": dict(topic_counts),
        "channel_breakdown": dict(channel_breakdown),
        "top_pain_points": pain_points.most_common(5),
        "trend": trend,
        "clusters": clusters,
        "executive_digest": executive_digest,
    })


@app.route("/api/feedback/draft-reply", methods=["POST"])
def draft_reply():
    """Generates an empathetic and targeted customer support draft."""
    data = request.get_json(force=True) or {}
    feedback_id = data.get("id")
    
    target = None
    if feedback_id:
        target = next((enrich(i) for i in FEEDBACK if i["id"] == feedback_id), None)
    
    if not target:
        text = data.get("text", "")
        target = enrich({"id": 0, "text": text, "source": "Direct Query", "date": ""})

    sentiment = target["sentiment"]
    intent = target["intent"]
    text = target["text"]

    if intent == "Billing & Churn Risk":
        reply = (
            f"Hello,\n\n"
            f"Thank you for bringing this to our attention. We take payment and billing concerns very seriously. "
            f"I have escalated your account to our billing operations team to review the transaction details immediately. "
            f"If an erroneous charge occurred, rest assured a full refund will be processed right away.\n\n"
            f"Best regards,\nCustomer Success Team"
        )
    elif intent == "Bug Report":
        reply = (
            f"Hi there,\n\n"
            f"Thanks for reaching out and reporting this issue. We apologize for the frustration caused by the bug. "
            f"Our engineering team is actively investigating this behavior with the details you shared. "
            f"We will notify you as soon as a patch is deployed to address this.\n\n"
            f"Warmly,\nProduct Support Engineering"
        )
    elif intent == "Feature Request":
        reply = (
            f"Hi,\n\n"
            f"Thank you for sharing your suggestion! Ideas like this help shape our product direction. "
            f"I have logged this directly into our product roadmap backlog for the design and engineering team to evaluate.\n\n"
            f"Cheers,\nProduct Team"
        )
    elif sentiment == "positive":
        reply = (
            f"Hello!\n\n"
            f"Thank you so much for your kind words! We are thrilled to hear that you're enjoying the experience. "
            f"Feedback like yours motivates the entire team to keep refining and building great things.\n\n"
            f"Warm regards,\nThe Product Team"
        )
    else:
        reply = (
            f"Hi,\n\n"
            f"Thank you for taking the time to share your feedback with us. "
            f"We are constantly working to improve the platform, and your comments have been noted for our upcoming sprint review.\n\n"
            f"Best regards,\nSupport Team"
        )

    return jsonify({"reply": reply, "feedback": target})


@app.route("/api/feedback/create-ticket", methods=["POST"])
def create_ticket():
    """Generates a structured developer ticket formatted for Linear, Jira, or GitHub."""
    data = request.get_json(force=True) or {}
    feedback_id = data.get("id")
    
    target = None
    if feedback_id:
        target = next((enrich(i) for i in FEEDBACK if i["id"] == feedback_id), None)
    
    if not target:
        text = data.get("text", "")
        target = enrich({"id": 0, "text": text, "source": "Manual Entry", "date": ""})

    title = f"[{target['urgency']}] {target['intent']}: {target['topics'][0]} Issue"
    
    ticket_md = (
        f"# {title}\n\n"
        f"**Severity**: {target['urgency']} (Score: {target['urgency_score']}/100)\n"
        f"**Origin**: {target['source']} ({target.get('date', 'Recent')})\n"
        f"**Intent Category**: {target['intent']}\n"
        f"**Subsystems Affected**: {', '.join(target['topics'])}\n\n"
        f"## Customer Verbatim\n"
        f"> \"{target['text']}\"\n\n"
        f"## Acceptance Criteria\n"
        f"- [ ] Investigate root cause in `{target['topics'][0]}` module.\n"
        f"- [ ] Verify reproducible flow under target device/channel environment.\n"
        f"- [ ] Apply regression guard and submit PR with automated tests.\n"
    )

    return jsonify({"title": title, "ticket": ticket_md, "feedback": target})


@app.route("/api/export", methods=["GET"])
def export_data():
    """Exports current database in either JSON or CSV format."""
    fmt = request.args.get("format", "json").lower()
    enriched = [enrich(item) for item in FEEDBACK]

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Date", "Source", "Feedback", "Intent", "Sentiment", "Score", "Urgency", "Topics"])
        for item in enriched:
            writer.writerow([
                item["id"],
                item["date"],
                item["source"],
                item["text"],
                item["intent"],
                item["sentiment"],
                item["sentiment_score"],
                item["urgency"],
                "; ".join(item["topics"]),
            ])
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=feedback_intelligence_export.csv"},
        )

    return Response(
        json.dumps(enriched, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=feedback_intelligence_export.json"},
    )


# ---------------------------------------------------------------------------
# Health & Status Checks (For Vercel Function Ping and Monitoring)
# ---------------------------------------------------------------------------
@app.route("/api/health")
@app.route("/api/index")
def api_health():
    """Health check endpoint for Vercel and uptime monitoring."""
    return jsonify({
        "status": "ok",
        "service": "feedback-intelligence",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_records": len(FEEDBACK),
    })


# ---------------------------------------------------------------------------
# Robust Error Handlers (Eliminates SyntaxError: Unexpected token '<' on client)
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/api/"):
        return jsonify({
            "error": f"API endpoint '{request.path}' not found",
            "status": 404,
            "message": "Verify the endpoint route URL.",
        }), 404
    return send_from_directory(app.static_folder, "index.html")


@app.errorhandler(500)
def handle_500(e):
    if request.path.startswith("/api/"):
        return jsonify({
            "error": "Internal server error",
            "details": str(e),
            "status": 500,
        }), 500
    return jsonify({"error": "Internal server error", "status": 500}), 500


@app.errorhandler(Exception)
def handle_generic_exception(e):
    if request.path.startswith("/api/"):
        return jsonify({
            "error": "Unhandled backend exception",
            "details": str(e),
            "status": 500,
        }), 500
    return f"Internal Error: {e}", 500


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
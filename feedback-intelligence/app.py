"""
Digital Product Feedback Intelligence — Backend
Flask API that ingests product feedback, scores sentiment, clusters it into
topics, and serves aggregated insights to the dashboard.

No external ML dependencies required (works fully offline) — sentiment is
computed with a small lexicon + negation handling, which is fast, explainable,
and reliable to demo on stage.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

APP_DIR = Path(__file__).parent
DATA_FILE = APP_DIR / "data" / "sample_feedback.json"

app = Flask(__name__, static_folder="static", static_url_path="")

# ---------------------------------------------------------------------------
# In-memory store, persisted to disk on every write
# ---------------------------------------------------------------------------
with open(DATA_FILE, "r", encoding="utf-8") as f:
    FEEDBACK = json.load(f)

_next_id = max(item["id"] for item in FEEDBACK) + 1


def save_feedback():
    """Write the current in-memory feedback list back to the JSON file."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(FEEDBACK, f, indent=2, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Sentiment analysis — lightweight lexicon-based scorer
# ---------------------------------------------------------------------------
POSITIVE_WORDS = {
    "love", "great", "excellent", "amazing", "awesome", "good", "fantastic",
    "smooth", "clean", "easy", "fast", "quick", "flawless", "helpful",
    "wonderful", "perfect", "happy", "resolved", "improved", "instantly",
    "best", "nice", "impressive", "reliable", "seamless",
}

NEGATIVE_WORDS = {
    "crash", "crashing", "crashes", "bug", "buggy", "slow", "frustrating",
    "confusing", "annoying", "rude", "unhelpful", "freeze", "freezes",
    "fail", "failed", "failing", "issue", "issues", "problem", "problems",
    "hate", "terrible", "awful", "worst", "broken", "unreasonable",
    "cluttered", "difficult", "hard", "timing", "timeout", "charged",
    "delay", "laggy", "glitch", "error", "disappointed", "poor",
}

NEGATIONS = {"not", "no", "never", "n't", "cannot", "can't", "didn't", "isn't"}

WORD_RE = re.compile(r"[a-z']+")


def analyze_sentiment(text: str):
    """Return (label, score) where score is roughly in [-1, 1]."""
    words = WORD_RE.findall(text.lower())
    score = 0
    for i, word in enumerate(words):
        polarity = 0
        if word in POSITIVE_WORDS:
            polarity = 1
        elif word in NEGATIVE_WORDS:
            polarity = -1
        if polarity != 0:
            # flip polarity if one of the previous two tokens was a negation
            window = words[max(0, i - 2):i]
            if any(w in NEGATIONS or w.endswith("n't") for w in window):
                polarity *= -1
            score += polarity

    if score > 0:
        label = "positive"
    elif score < 0:
        label = "negative"
    else:
        label = "neutral"

    # normalize roughly into [-1, 1] for the UI
    normalized = max(-1.0, min(1.0, score / 3.0))
    return label, round(normalized, 2)


# ---------------------------------------------------------------------------
# Topic clustering — keyword-based tagging (fast + explainable for a demo)
# ---------------------------------------------------------------------------
TOPIC_KEYWORDS = {
    "Bugs & Crashes": ["crash", "crashing", "crashes", "freeze", "freezes",
                        "bug", "buggy", "glitch", "error"],
    "Performance": ["slow", "fast", "quick", "load", "loading", "instantly",
                     "laggy", "performance"],
    "Login & Auth": ["login", "log in", "account", "password", "timeout",
                       "timing out", "sign in"],
    "Billing & Pricing": ["price", "pricing", "charged", "billing", "refund",
                            "subscription", "payment", "money", "cost"],
    "UI/UX": ["ui", "interface", "design", "dashboard", "cluttered",
               "confusing", "navigate", "menu", "dark mode", "onboarding"],
    "Customer Support": ["support", "service", "rude", "helpful",
                           "unhelpful", "response", "responded"],
    "Feature Request": ["would be", "please add", "add a", "wish", "feature"],
}


def extract_topics(text: str):
    lower = text.lower()
    matched = [topic for topic, kws in TOPIC_KEYWORDS.items()
               if any(kw in lower for kw in kws)]
    return matched or ["General"]


def enrich(item: dict) -> dict:
    label, score = analyze_sentiment(item["text"])
    return {
        **item,
        "sentiment": label,
        "sentiment_score": score,
        "topics": extract_topics(item["text"]),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/feedback", methods=["GET"])
def get_feedback():
    enriched = [enrich(item) for item in FEEDBACK]
    enriched.sort(key=lambda x: x["date"])
    return jsonify(enriched)


@app.route("/api/feedback", methods=["POST"])
def add_feedback():
    global _next_id
    body = request.get_json(force=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    item = {
        "id": _next_id,
        "text": text,
        "source": body.get("source", "Manual Entry"),
        "date": body.get("date", "2026-08-15"),
    }
    _next_id += 1
    FEEDBACK.append(item)
    save_feedback()
    return jsonify(enrich(item)), 201


@app.route("/api/summary", methods=["GET"])
def get_summary():
    enriched = [enrich(item) for item in FEEDBACK]

    sentiment_counts = Counter(item["sentiment"] for item in enriched)

    topic_counts = Counter()
    for item in enriched:
        topic_counts.update(item["topics"])

    # sentiment trend grouped by date
    by_date = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0})
    for item in enriched:
        by_date[item["date"]][item["sentiment"]] += 1
    trend = [
        {"date": d, **counts}
        for d, counts in sorted(by_date.items())
    ]

    # top pain points = negative feedback grouped by topic
    pain_points = Counter()
    for item in enriched:
        if item["sentiment"] == "negative":
            pain_points.update(item["topics"])

    total = len(enriched) or 1
    return jsonify({
        "total_feedback": len(enriched),
        "sentiment_counts": sentiment_counts,
        "sentiment_pct": {
            k: round(v / total * 100, 1) for k, v in sentiment_counts.items()
        },
        "topic_counts": topic_counts,
        "top_pain_points": pain_points.most_common(5),
        "trend": trend,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
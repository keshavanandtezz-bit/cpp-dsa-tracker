# ============================================================
# app.py — C++ DSA Tracker Backend
# ============================================================

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import date, datetime, timedelta
import os
import requests
import json
import groq

load_dotenv()

app = Flask(__name__)
CORS(app)

# --- CONFIG ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

BASE = f"{SUPABASE_URL}/rest/v1"

HEADERS = {
    "apikey":         SUPABASE_KEY,
    "Authorization":  f"Bearer {SUPABASE_KEY}",
    "Content-Type":   "application/json",
    "Prefer":         "return=representation",
    "Accept":         "application/json",
    "X-Client-Info":  "supabase-py/2.0"
}

groq_client = groq.Groq(api_key=GROQ_API_KEY)


# ============================================================
# SUPABASE HELPER FUNCTIONS
# ============================================================

def sb_get(table, params=None):
    url = f"{BASE}/{table}"
    res = requests.get(url, headers=HEADERS, params=params)
    print(f"[sb_get] {table} | status={res.status_code} | preview={res.text[:100]}")
    if res.status_code not in [200, 201, 204]:
        return []
    if not res.text or res.text.strip() == "":
        return []
    try:
        return res.json()
    except Exception as e:
        print(f"[sb_get JSON ERROR] {e}")
        return []


def sb_post(table, data):
    url = f"{BASE}/{table}"
    res = requests.post(url, headers=HEADERS, json=data)
    print(f"[sb_post] {table} | status={res.status_code}")
    if not res.text or res.text.strip() == "":
        return []
    try:
        return res.json()
    except Exception as e:
        print(f"[sb_post JSON ERROR] {e}")
        return []


def sb_patch(table, match_col, match_val, data):
    url    = f"{BASE}/{table}"
    params = {match_col: f"eq.{match_val}"}
    res    = requests.patch(url, headers=HEADERS, params=params, json=data)
    print(f"[sb_patch] {table} | status={res.status_code}")
    if not res.text or res.text.strip() == "":
        return []
    try:
        return res.json()
    except Exception as e:
        print(f"[sb_patch JSON ERROR] {e}")
        return []


def sb_delete(table, match_col, match_val):
    url    = f"{BASE}/{table}"
    params = {match_col: f"eq.{match_val}"}
    res    = requests.delete(url, headers=HEADERS, params=params)
    print(f"[sb_delete] {table} | status={res.status_code}")
    return res.status_code


# ============================================================
# DEBUG ROUTES
# ============================================================

@app.route("/api/debug", methods=["GET"])
def debug():
    try:
        url = f"{BASE}/topics"
        res = requests.get(url, headers=HEADERS, params={"limit": "1"})
        return jsonify({
            "status_code":   res.status_code,
            "response_text": res.text[:300],
            "supabase_url":  SUPABASE_URL,
            "key_preview":   SUPABASE_KEY[:25] + "..." if SUPABASE_KEY else "NOT LOADED"
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/debug-groq", methods=["GET"])
def debug_groq():
    try:
        completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": "Say hello in one word"}],
            model="llama-3.3-70b-versatile",
        )
        return jsonify({
            "success":     True,
            "response":    completion.choices[0].message.content,
            "key_preview": GROQ_API_KEY[:15] + "..." if GROQ_API_KEY else "NOT LOADED"
        })
    except Exception as e:
        return jsonify({
            "success":     False,
            "error":       str(e),
            "key_preview": GROQ_API_KEY[:15] + "..." if GROQ_API_KEY else "NOT LOADED"
        })


# ============================================================
# SECTION 1: TOPIC ROUTES
# ============================================================

@app.route("/api/topics", methods=["GET"])
def get_all_topics():
    try:
        data = sb_get("topics", {"order": "video_number"})
        return jsonify({"success": True, "data": data, "count": len(data)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/topics/sections", methods=["GET"])
def get_topics_by_section():
    try:
        data     = sb_get("topics", {"order": "video_number"})
        sections = {}
        for topic in data:
            section = topic.get("section_name", "Other")
            if section not in sections:
                sections[section] = []
            sections[section].append(topic)
        return jsonify({"success": True, "data": sections})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/topics/<topic_id>", methods=["GET"])
def get_single_topic(topic_id):
    try:
        data = sb_get("topics", {"id": f"eq.{topic_id}", "limit": "1"})
        if not data:
            return jsonify({"success": False, "error": "Topic not found"}), 404
        return jsonify({"success": True, "data": data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/topics/<topic_id>/status", methods=["PUT"])
def update_topic_status(topic_id):
    try:
        body       = request.json
        new_status = body.get("status")
        today      = str(date.today())
        update_data = {"status": new_status}

        if new_status == "in_progress":
            update_data["date_started"] = today

        elif new_status == "completed":
            update_data["date_completed"] = today
            topic = sb_get("topics", {"id": f"eq.{topic_id}", "limit": "1"})
            if topic and topic[0].get("date_started"):
                start = datetime.strptime(topic[0]["date_started"], "%Y-%m-%d").date()
                end   = datetime.strptime(today, "%Y-%m-%d").date()
                update_data["days_taken"] = max((end - start).days, 1)

        sb_patch("topics", "id", topic_id, update_data)
        return jsonify({"success": True, "message": f"Status updated to {new_status}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/topics/<topic_id>/notes", methods=["PUT"])
def update_topic_notes(topic_id):
    try:
        body = request.json
        sb_patch("topics", "id", topic_id, {"notes": body.get("notes", "")})
        return jsonify({"success": True, "message": "Notes saved"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/topics/<topic_id>/youtube", methods=["PUT"])
def update_youtube_url(topic_id):
    try:
        body = request.json
        sb_patch("topics", "id", topic_id, {"youtube_url": body.get("youtube_url", "")})
        return jsonify({"success": True, "message": "YouTube URL saved"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# SECTION 2: QUESTION ROUTES
# ============================================================

@app.route("/api/topics/<topic_id>/questions", methods=["GET"])
def get_questions(topic_id):
    try:
        data = sb_get("questions", {
            "topic_id": f"eq.{topic_id}",
            "order":    "created_at"
        })
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/questions", methods=["POST"])
def add_question():
    try:
        body  = request.json
        new_q = {
            "topic_id":      body.get("topic_id"),
            "question_text": body.get("question_text"),
            "question_type": body.get("question_type", "basic"),
            "your_code":     body.get("your_code", ""),
            "your_output":   body.get("your_output", ""),
            "is_solved":     body.get("is_solved", False)
        }
        data = sb_post("questions", new_q)
        log_today()
        return jsonify({
            "success": True,
            "data": data[0] if data and isinstance(data, list) else {}
        }), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/questions/<question_id>", methods=["PUT"])
def update_question(question_id):
    try:
        body        = request.json
        update_data = {}
        for field in ["question_text", "your_code", "your_output", "is_solved", "question_type"]:
            if field in body:
                update_data[field] = body[field]
        sb_patch("questions", "id", question_id, update_data)
        return jsonify({"success": True, "message": "Question updated"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/questions/<question_id>", methods=["DELETE"])
def delete_question(question_id):
    try:
        sb_delete("questions", "id", question_id)
        return jsonify({"success": True, "message": "Question deleted"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# SECTION 3: DAILY LOGS
# ============================================================

def log_today():
    try:
        today    = str(date.today())
        existing = sb_get("daily_logs", {"log_date": f"eq.{today}"})
        if existing:
            new_count = existing[0]["questions_solved"] + 1
            sb_patch("daily_logs", "log_date", today, {"questions_solved": new_count})
        else:
            sb_post("daily_logs", {"log_date": today, "questions_solved": 1})
    except Exception as e:
        print(f"[log_today ERROR] {e}")


@app.route("/api/logs", methods=["GET"])
def get_all_logs():
    try:
        data = sb_get("daily_logs", {"order": "log_date"})
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/logs/ping", methods=["POST"])
def ping_log():
    log_today()
    return jsonify({"success": True, "message": "Activity logged"})


# ============================================================
# SECTION 4: STATS
# ============================================================

@app.route("/api/stats", methods=["GET"])
def get_stats():
    try:
        topics    = sb_get("topics",     {"select": "status,section_name,days_taken"})
        questions = sb_get("questions",  {"select": "is_solved,question_type"})
        logs      = sb_get("daily_logs", {"select": "log_date", "order": "log_date.desc"})

        total        = len(topics)
        completed    = sum(1 for t in topics if t.get("status") == "completed")
        in_progress  = sum(1 for t in topics if t.get("status") == "in_progress")
        not_started  = sum(1 for t in topics if t.get("status") == "not_started")
        percent      = round((completed / total) * 100, 1) if total > 0 else 0

        total_q    = len(questions)
        solved     = sum(1 for q in questions if q.get("is_solved"))
        basic_c    = sum(1 for q in questions if q.get("question_type") == "basic")
        advanced_c = sum(1 for q in questions if q.get("question_type") == "advanced")

        streak = 0
        today  = date.today()
        for i, log in enumerate(logs):
            try:
                log_date = datetime.strptime(log["log_date"], "%Y-%m-%d").date()
                expected = today - timedelta(days=i)
                if log_date == expected:
                    streak += 1
                else:
                    break
            except Exception:
                break

        return jsonify({
            "success": True,
            "data": {
                "total_topics":    total,
                "completed":       completed,
                "in_progress":     in_progress,
                "not_started":     not_started,
                "percent_done":    percent,
                "total_questions": total_q,
                "solved":          solved,
                "basic":           basic_c,
                "advanced":        advanced_c,
                "current_streak":  streak
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# SECTION 5: AI QUESTIONS
# ============================================================

@app.route("/api/ai/generate/<topic_id>", methods=["POST"])
def generate_ai_questions(topic_id):
    try:
        topic = sb_get("topics", {"id": f"eq.{topic_id}", "limit": "1"})
        if not topic:
            return jsonify({"success": False, "error": "Topic not found"}), 404

        title   = topic[0]["title"]
        section = topic[0]["section_name"]

        prompt = f"""You are a senior software engineer interviewer at Google or Microsoft.
Generate exactly 3 C++ DSA interview questions for the topic: "{title}" from section "{section}".
Respond ONLY with a valid JSON array. No explanation, no markdown, no code blocks. Just raw JSON:
[
  {{"question": "question text here", "difficulty": "easy", "hint": "hint text here"}},
  {{"question": "question text here", "difficulty": "medium", "hint": "hint text here"}},
  {{"question": "question text here", "difficulty": "hard", "hint": "hint text here"}}
]"""

        completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.7
        )

        raw = completion.choices[0].message.content.strip()
        print(f"[AI RAW RESPONSE] {raw[:200]}")

        # Clean markdown if AI added it
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        # Extract just the JSON array
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        if start != -1 and end > 0:
            raw = raw[start:end]

        questions_list = json.loads(raw)

        saved = []
        for q in questions_list:
            result = sb_post("ai_questions", {
                "topic_id":   topic_id,
                "question":   q.get("question", ""),
                "difficulty": q.get("difficulty", "medium"),
                "hint":       q.get("hint", "")
            })
            if result and isinstance(result, list):
                saved.append(result[0])

        return jsonify({"success": True, "data": saved})

    except Exception as e:
        print(f"[AI GENERATE ERROR] {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/questions/<topic_id>", methods=["GET"])
def get_ai_questions(topic_id):
    try:
        data = sb_get("ai_questions", {
            "topic_id": f"eq.{topic_id}",
            "order":    "created_at"
        })
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# SECTION 6: PAGE ROUTES
# ============================================================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/topic/<topic_id>")
def topic_detail(topic_id):
    return render_template("topic.html", topic_id=topic_id)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    app.run(debug=True, port=5000)
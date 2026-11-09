"""Meeting Intelligence for Copilot Desktop MCP: Meetily-style structured summarization,
evidence-grounded action items, transcript hallucination cleaning, and Telegram dispatch.

Adopts core concepts from Zackriya-Solutions/meetily:
1. Strict Whisper hallucination cleaning (purges micro-token noise loops).
2. Grounded structured templates (Project Sync, Standard, Standup) with exact quotes & timestamps.
3. LLM reasoning tag stripper (<think>...</think>).
4. Auto-save to recordings/<session>/summary.md and optional Telegram forwarder.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("copilot_desktop_mcp.meeting_summary")

THINK_REGEX = re.compile(r"(?is)<think(?:ing)?(?:\s+[^>]*)?>.*?</think(?:ing)?\s*>")
THINK_MARKER_REGEX = re.compile(r"(?is)</?think(?:ing)?(?:\s+[^>]*)?>")

TEMPLATES = {
    "project_sync": {
        "name": "Project & Technical Status Sync",
        "description": "Fokus status teknis, sistem/platform, risiko, dan action items ber-timestamp.",
        "prompt_instructions": """Kamu adalah Notulis AI Rapat Teknis Senior.
Buatkan Notulensi Rapat (Minutes of Meeting / MoM) terstruktur, akurat, dan profesional berdasarkan transkrip berikut.

PANDUAN WAJIB:
1. Bahasa Indonesia profesional, jelas, dan to the point.
2. Setiap Action Item WAJIB menyertakan PIC, target waktu, bukti kutipan kalimat transkrip asli, dan timestamp-nya.
3. Grounded in evidence: Jangan mengarang atau menambahkan fakta/isu yang tidak ada dalam transkrip.
4. Identifikasi peserta berdasarkan konteks pembicaraan atau sebutkan 'Peserta' bila anonim.

STRUKTUR DOKUMEN:
# 📋 Notulensi Rapat: Status Sync & Update Teknis
## 1. 📌 Ringkasan Eksekutif
(Paragraf padat berisi inti bahasan rapat, isu utama sistem/jaringan, dan arahan umum)

## 2. 👥 Peserta & Peran Teridentifikasi
(Daftar pihak yang berbicara atau disebut dalam transkrip serta perannya)

## 3. 🎯 Status Sistem, Platform & Aktivitas Teknis
(Poin-poin spesifik perkembangan proyek, status platform/hardware, dan pemeliharaan)

## 4. ⚠️ Risiko Utama & Rencana Mitigasi
| Risiko / Issue | Dampak | Rencana Mitigasi / Solusi | PIC / Owner |
| --- | --- | --- | --- |

## 5. 💡 Keputusan Kunci
| Keputusan | Alasan / Rasionalisasi | Referensi Timestamp |
| --- | --- | --- |

## 6. ✅ Action Items Terverifikasi
| PIC / Owner | Tugas / Action Item | Target Waktu (Due) | Prioritas | Bukti Kutipan Transkrip | Timestamp |
| --- | --- | --- | --- | --- | --- |

## 7. 📅 Agenda & Jadwal Selanjutnya
(Tenggat waktu berikutnya, jadwal pengujian, atau pertemuan tindak lanjut)
"""
    },
    "standard": {
        "name": "Standard Meeting Notes",
        "description": "Template standar ringkasan rapat umum, keputusan, dan action items.",
        "prompt_instructions": """Kamu adalah Notulis Rapat Profesional.
Buatkan Notulensi Rapat (Minutes of Meeting) terstruktur berdasarkan transkrip berikut.

PANDUAN WAJIB:
1. Bahasa Indonesia profesional.
2. Setiap Action Item wajib menyertakan kutipan kalimat dan timestamp dari transkrip.
3. Hindari asumsi di luar transkrip.

STRUKTUR DOKUMEN:
# 📋 Notulensi Rapat
## 1. 📌 Ringkasan Eksekutif
(1-2 paragraf ringkasan tujuan dan hasil utama pertemuan)

## 2. 💡 Keputusan Kunci
| Keputusan | Rasionalisasi / Dampak | Timestamp |
| --- | --- | --- |

## 3. ✅ Action Items Terverifikasi
| PIC / Owner | Tugas / Action Item | Target Waktu (Due) | Bukti Kutipan Transkrip | Timestamp |
| --- | --- | --- | --- | --- |

## 4. 💬 Poin Diskusi Penting
(Highlight poin penting per topik pembahasan)
"""
    },
    "standup": {
        "name": "Daily Standup / Quick Sync",
        "description": "Format ringkas progres harian, rencana kerja, dan hambatan (blockers).",
        "prompt_instructions": """Kamu adalah Asisten Notulis Daily Standup.
Ringkas transkrip rapat harian berikut ke dalam format:
# ⚡ Daily Standup Notes
## 1. 🚀 Progres & Pekerjaan yang Selesai
## 2. 📅 Rencana Kerja Selanjutnya
## 3. 🛑 Hambatan / Kendala (Blockers)
## 4. ✅ Action Items Cepat
| PIC | Tugas | Target | Timestamp |
| --- | --- | --- | --- |
"""
    }
}


def clean_llm_markdown(raw: str) -> str:
    """Strip <think>...</think> envelopes and accidental outer markdown fences."""
    text = THINK_REGEX.sub("", raw).strip()
    text = THINK_MARKER_REGEX.sub("", text).strip()
    match = re.match(r"^```(?:markdown)?\s*\n(.*?)\n```$", text, flags=re.DOTALL)
    if match:
        text = match.group(1).strip()
    return text


def clean_transcript_text(raw_text: str) -> tuple[str, int, int]:
    """Clean whisper silence hallucinations (e.g. repeated 'Saya: I', 'A B U', single tokens).
    Returns (cleaned_text, total_lines, removed_lines)."""
    lines = raw_text.splitlines()
    kept: list[str] = []
    removed_count = 0

    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue
        m = re.match(r"^\[(\d\d:\d\d:\d\d)\]\s+(Peserta|Saya):\s+(.*)$", line_s)
        if m:
            _, spk, text = m.groups()
            s = text.strip()
            clean_alnum = re.sub(r"[^\w\s]", "", s).strip()
            words = clean_alnum.split()

            is_junk = False
            if spk == "Saya":
                if len(clean_alnum) <= 2:
                    is_junk = True
                elif len(words) <= 3 and all(len(w) <= 2 for w in words):
                    is_junk = True
                elif len(words) >= 3 and len(set(words)) == 1:
                    is_junk = True
            else:
                if len(words) >= 4 and len(set(words)) == 1 and len(words[0]) <= 3:
                    is_junk = True

            if is_junk:
                removed_count += 1
                continue

        kept.append(line_s)

    cleaned_text = "\n".join(kept)
    return cleaned_text, len(lines), removed_count


def call_meeting_llm(prompt: str) -> str:
    """Execute LLM call using Gemini (primary) with fallback to OpenAI or local Ollama."""
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    # 1. Primary: Gemini OpenAI-compatible endpoint
    if gemini_key:
        for mod in ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.8-flash"]:
            try:
                resp = httpx.post(
                    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                    json={
                        "model": mod,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                    },
                    headers={"Authorization": f"Bearer {gemini_key}"},
                    timeout=httpx.Timeout(90.0, connect=10.0),
                )
                if resp.status_code == 200:
                    raw_content = resp.json()["choices"][0]["message"]["content"]
                    return clean_llm_markdown(raw_content)
                logger.warning("Gemini model %s returned status %s: %s", mod, resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("Gemini model %s exception: %s", mod, e)

    # 2. Secondary: OpenAI endpoint
    if openai_key:
        try:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
                headers={"Authorization": f"Bearer {openai_key}"},
                timeout=httpx.Timeout(90.0, connect=10.0),
            )
            if resp.status_code == 200:
                raw_content = resp.json()["choices"][0]["message"]["content"]
                return clean_llm_markdown(raw_content)
        except Exception as e:
            logger.warning("OpenAI call exception: %s", e)

    # 3. Tertiary: Local Ollama
    try:
        resp = httpx.post(
            "http://127.0.0.1:11434/v1/chat/completions",
            json={
                "model": "gemma2",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        if resp.status_code == 200:
            raw_content = resp.json()["choices"][0]["message"]["content"]
            return clean_llm_markdown(raw_content)
    except Exception as e:
        logger.warning("Ollama call exception: %s", e)

    raise RuntimeError(
        "No LLM provider responded. Please set GEMINI_API_KEY or OPENAI_API_KEY in .env, "
        "or start local Ollama at http://127.0.0.1:11434."
    )


def send_telegram_meeting_summary(text: str) -> bool:
    """Send summary message to Telegram, chunking if necessary."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_DEFAULT_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.warning("Telegram bot token or default chat ID not configured in .env")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        if len(current) + len(paragraph) + 2 > 3800:
            if current:
                chunks.append(current.strip())
            current = paragraph
        else:
            current = (current + "\n\n" + paragraph) if current else paragraph
    if current:
        chunks.append(current.strip())

    success = True
    for i, chunk in enumerate(chunks):
        header = f"📢 *[Notulensi Rapat - Part {i+1}/{len(chunks)}]*\n\n" if len(chunks) > 1 else "📢 *[Notulensi Rapat]*\n\n"
        body = {"chat_id": chat_id, "text": header + chunk}
        try:
            r = httpx.post(url, json=body, timeout=15.0)
            if r.status_code != 200:
                logger.error("Telegram send error: %s", r.text)
                success = False
        except Exception as e:
            logger.exception("Telegram post exception: %s", e)
            success = False
    return success

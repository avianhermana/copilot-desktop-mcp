from __future__ import annotations

import logging
import re
import threading
import time
import wave
from pathlib import Path
from typing import Any

from mcp.types import ToolAnnotations
from .tools_workspace import get_workspace_helpers

logger = logging.getLogger("copilot_desktop_mcp.meeting")

_lock = threading.Lock()
_active_recording: dict[str, Any] | None = None
_whisper_models: dict[str, Any] = {}


class _AudioTrack:
    """WAV recorder track fed by PyAudio stream.
    WASAPI loopback pauses during silence, so we pad zero bytes to ensure timestamps align."""

    def __init__(self, pa, pyaudio, dev: dict, file_path: Path):
        self.rate = int(dev.get("defaultSampleRate", 44100))
        self.channels = max(1, int(dev.get("maxInputChannels", 2)))
        self.name = dev.get("name", "Audio Device")
        self.written_frames = 0
        self.wf = wave.open(str(file_path), "wb")
        self.wf.setnchannels(self.channels)
        self.wf.setsampwidth(2)  # 16-bit PCM
        self.wf.setframerate(self.rate)
        self.start_time = time.monotonic()
        self._pyaudio = pyaudio
        self.stream = pa.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=int(dev["index"]),
            frames_per_buffer=1024,
            stream_callback=self._audio_callback,
        )

    def _audio_callback(self, in_data, frame_count, _time_info, _status):
        try:
            gap = int((time.monotonic() - self.start_time) * self.rate) - self.written_frames - frame_count
            if gap > self.rate // 2:  # > 0.5s silence gap -> pad with zero bytes
                silence_frames = min(gap, self.rate)
                self.wf.writeframes(b"\x00" * (silence_frames * self.channels * 2))
                self.written_frames += silence_frames
            self.wf.writeframes(in_data)
            self.written_frames += frame_count
        except Exception as exc:
            logger.warning("Audio frame recording warning: %s", exc)
        return (None, self._pyaudio.paContinue)

    def close(self):
        try:
            self.stream.stop_stream()
            self.stream.close()
        finally:
            self.wf.close()


def _get_whisper_model(model_name: str):
    if model_name not in _whisper_models:
        from faster_whisper import WhisperModel

        _whisper_models[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _whisper_models[model_name]


def _format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def register_meeting_tools(mcp: Any, config: dict[str, Any]) -> None:
    safe_path, _, _, _, _, _, _ = get_workspace_helpers(config)

    recordings_dir = Path(config.get("meeting", {}).get("recordings_dir", Path.home() / ".copilot-desktop" / "recordings"))
    recordings_dir.mkdir(parents=True, exist_ok=True)

    @mcp.tool
    def start_meeting_recording(
        source: str = "both",
        max_minutes: int = 120,
        label: str = "",
    ) -> dict[str, Any]:
        """Start recording meeting audio from Microsoft Teams, Zoom, or web conferences.
        `source`: 'both' (Speakers/Attendees + Microphone), 'system' (Speakers only), or 'mic' (Microphone only).
        Audio is recorded locally in PCM WAV format with timestamps."""
        global _active_recording

        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            raise RuntimeError(
                "PyAudioWPatch is not installed. Run 'pip install pyaudiowpatch' to enable meeting recording."
            )

        source_clean = source.strip().lower()
        if source_clean not in ("both", "system", "mic"):
            raise ValueError("source must be 'both', 'system', or 'mic'")

        with _lock:
            if _active_recording:
                raise RuntimeError(
                    f"A meeting recording is already active (Session: {_active_recording['id']}). "
                    "Call stop_meeting_recording first."
                )

            session_id = time.strftime("%Y%m%d-%H%M%S")
            if label:
                clean_lbl = re.sub(r"[^a-zA-Z0-9]+", "-", label.strip()).strip("-")[:30]
                if clean_lbl:
                    session_id += f"-{clean_lbl}"

            session_dir = recordings_dir / session_id
            session_dir.mkdir(parents=True, exist_ok=True)

            pa = pyaudio.PyAudio()
            tracks: dict[str, _AudioTrack] = {}
            errors: dict[str, str] = {}

            try:
                wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
                # Capture system audio (Attendees via WASAPI loopback)
                if source_clean in ("both", "system"):
                    try:
                        spk = pa.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
                        if not spk.get("isLoopbackDevice"):
                            spk = next(
                                d for d in pa.get_loopback_device_info_generator() if spk["name"] in d["name"]
                            )
                        tracks["system.wav"] = _AudioTrack(pa, pyaudio, spk, session_dir / "system.wav")
                    except Exception as e:
                        errors["system"] = str(e)

                # Capture user's microphone
                if source_clean in ("both", "mic"):
                    try:
                        mic = pa.get_device_info_by_index(wasapi_info["defaultInputDevice"])
                        tracks["mic.wav"] = _AudioTrack(pa, pyaudio, mic, session_dir / "mic.wav")
                    except Exception as e:
                        errors["mic"] = str(e)

                if not tracks:
                    raise RuntimeError(f"No audio recording device could be initialized: {errors}")
            except Exception:
                for t in tracks.values():
                    t.close()
                pa.terminate()
                raise

            duration_cap = max(1, min(int(max_minutes), 240))
            timer = threading.Timer(duration_cap * 60, lambda: stop_meeting_recording())
            timer.daemon = True

            _active_recording = {
                "id": session_id,
                "pa": pa,
                "tracks": tracks,
                "dir": session_dir,
                "start_time": time.monotonic(),
                "timer": timer,
                "max_minutes": duration_cap,
            }
            timer.start()

        return {
            "status": "recording_started",
            "session_id": session_id,
            "source": source_clean,
            "tracks_active": list(tracks.keys()),
            "warnings": errors or None,
            "max_minutes": duration_cap,
        }

    @mcp.tool
    def stop_meeting_recording() -> dict[str, Any]:
        """Stop the currently active meeting recording session and finalize audio files."""
        global _active_recording

        with _lock:
            rec = _active_recording
            _active_recording = None

        if not rec:
            return {"status": "idle", "note": "No active meeting recording found."}

        rec["timer"].cancel()
        for t in rec["tracks"].values():
            t.close()
        rec["pa"].terminate()

        elapsed = round(time.monotonic() - rec["start_time"], 1)
        return {
            "status": "recording_stopped",
            "session_id": rec["id"],
            "duration_seconds": elapsed,
            "directory": str(rec["dir"]),
            "tracks_saved": list(rec["tracks"].keys()),
            "next_step": "Call transcribe_meeting with this session_id to generate the transcript for minutes/notulen.",
        }

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def meeting_recording_status() -> dict[str, Any]:
        """Check if meeting audio is currently being recorded and view saved sessions."""
        with _lock:
            is_active = _active_recording is not None
            current_id = _active_recording["id"] if is_active else None
            duration = round(time.monotonic() - _active_recording["start_time"], 1) if is_active else 0

        saved = [p.name for p in sorted(recordings_dir.iterdir(), reverse=True) if p.is_dir()]
        return {
            "is_recording": is_active,
            "current_session_id": current_id,
            "current_duration_seconds": duration,
            "saved_sessions_count": len(saved),
            "recent_sessions": saved[:10],
        }

    @mcp.tool
    def transcribe_meeting(
        session_id: str = "",
        language: str = "id",
        model: str = "small",
        keep_audio: bool = True,
    ) -> dict[str, Any]:
        """Transcribe meeting audio into a synchronized conversation log (Attendees vs Microphone).
        `session_id`: Session ID to transcribe (empty = latest session).
        `language`: 'id' for Indonesian, 'en' for English, or None for multi-lingual auto-detection.
        `model`: 'tiny', 'base', 'small' (recommended), or 'medium'."""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError(
                "faster-whisper is not installed. Run 'pip install faster-whisper' to enable local transcription."
            )

        if not session_id:
            sessions = [p for p in sorted(recordings_dir.iterdir(), reverse=True) if p.is_dir()]
            if not sessions:
                raise ValueError("No recorded meeting sessions found.")
            target_dir = sessions[0]
            sid = target_dir.name
        else:
            target_dir = recordings_dir / session_id
            if not target_dir.is_dir():
                raise FileNotFoundError(f"Session directory not found for ID: '{session_id}'")
            sid = session_id

        whisper = _get_whisper_model(model)
        dialogue: list[tuple[float, str, str]] = []

        # Transcribe Attendees (System audio) and User (Mic audio)
        track_map = [("Peserta", "system.wav"), ("Saya", "mic.wav")]
        for speaker_label, fname in track_map:
            wav_path = target_dir / fname
            if not wav_path.exists():
                continue

            segments, _info = whisper.transcribe(
                str(wav_path),
                language=language or None,
                vad_filter=True,
                beam_size=1,
            )
            for seg in segments:
                text_clean = seg.text.strip()
                if text_clean:
                    dialogue.append((seg.start, speaker_label, text_clean))

        dialogue.sort(key=lambda item: item[0])
        transcript_lines = [f"[{_format_timestamp(ts)}] {speaker}: {text}" for ts, speaker, text in dialogue]
        transcript_full = "\n".join(transcript_lines)

        out_file = target_dir / "transcript.txt"
        out_file.write_text(transcript_full, encoding="utf-8")

        if not keep_audio:
            for _, fname in track_map:
                (target_dir / fname).unlink(missing_ok=True)

        return {
            "status": "success",
            "session_id": sid,
            "transcript_file": str(out_file),
            "total_lines": len(transcript_lines),
            "transcript_preview": transcript_full[:4000],
            "note": "Use create_docx to convert this raw transcript into a structured formal meeting minutes (notulen).",
        }

"""APRS AI Gateway Module — Rust agent logunu izleyerek AI cevabi gonderir."""

import re
import subprocess
import threading
import time
import socket as sock


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

TR_MAP = str.maketrans(
    "çÇğĞıİöÖşŞüÜâÂîÎûÛ",
    "cCgGiIoOsSuUaAiIuU",
)

UNICODE_REPLACE = {
    "…": "...", "‘": "'", "’": "'",
    "“": '"', "”": '"', "–": "-",
    "—": "-", " ": " ", "​": "",
    "°": " derece", "é": "e", "è": "e",
    "à": "a", "ü": "u", "ö": "o",
}


def to_ascii(text):
    for k, v in UNICODE_REPLACE.items():
        text = text.replace(k, v)
    text = text.translate(TR_MAP)
    out = []
    for ch in text:
        if 32 <= ord(ch) <= 126:
            out.append(ch)
    return "".join(out)
MSG_RE = re.compile(r"(\S+?)>.*?::(\S+)\s*:(.+)")


class AIGateway:
    def __init__(self, on_log):
        self._log_fn = on_log
        self._running = False
        self._thread = None
        self._processed = set()
        self._lock = threading.Lock()
        self._config = {}

    def start(self, config):
        self._config = config
        if not config.get("enabled"):
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._thread = None

    def _emit(self, msg):
        try:
            self._log_fn(msg)
        except Exception:
            pass

    def _run(self):
        from openai import OpenAI

        callsign = self._config.get("callsign", "DMW").upper()
        api_key = self._config.get("api_key", "")

        if not api_key:
            self._emit("[AI-HATA] API key ayarlanmamis!")
            return

        provider = self._config.get("provider", "puter")
        base_urls = {
            "puter": "https://api.puter.com/puterai/openai/v1/",
            "groq": "https://api.groq.com/openai/v1/",
            "openrouter": "https://openrouter.ai/api/v1/",
        }
        base_url = self._config.get("base_url") or base_urls.get(provider, base_urls["puter"])

        self._ai_client = OpenAI(api_key=api_key, base_url=base_url)

        models = {
            "puter": "gpt-4o-mini",
            "groq": "llama-3.3-70b-versatile",
            "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
        }
        self._model = self._config.get("model") or models.get(provider, "gpt-4o-mini")

        self._emit(f"[AI] Saglayici: {provider} | Model: {self._model}")

        self._emit(f"[AI] Gateway baslatiliyor: {callsign}")
        self._emit("[AI] Rust agent log akisi izleniyor...")

        while self._running:
            try:
                self._watch_log(callsign)
            except Exception as e:
                if self._running:
                    self._emit(f"[AI-HATA] Log izleme hatasi: {e}")
                    time.sleep(5)

    def _watch_log(self, callsign):
        proc = subprocess.Popen(
            ["journalctl", "-u", "aprs-agent", "-f", "-n", "0",
             "--no-pager", "-o", "cat"],
            stdout=subprocess.PIPE, text=True, bufsize=1,
        )
        try:
            for line in proc.stdout:
                if not self._running:
                    break
                clean = ANSI_RE.sub("", line).strip()

                if callsign.upper() not in clean.upper():
                    continue

                m = MSG_RE.search(clean)
                if not m:
                    continue

                from_call = m.group(1).strip()
                addressee = m.group(2).strip().upper()
                raw_msg = m.group(3).strip()

                if addressee != callsign.upper():
                    continue

                if from_call.upper().startswith(callsign.upper()):
                    continue

                if "{" in raw_msg:
                    message = raw_msg[:raw_msg.rfind("{")].strip()
                    msg_id = raw_msg[raw_msg.rfind("{") + 1:raw_msg.rfind("}")]
                else:
                    message = raw_msg
                    msg_id = ""

                if not message:
                    continue

                dedup_key = f"{from_call}:{msg_id or message}"
                with self._lock:
                    if dedup_key in self._processed:
                        continue
                    self._processed.add(dedup_key)

                prefix = self._config.get("trigger_prefix", "").upper()
                if prefix:
                    if not message.upper().startswith(prefix):
                        continue
                    question = message[len(prefix):].strip(" :")
                else:
                    question = message

                if not question:
                    continue

                if self._config.get("whitelist_enabled"):
                    wl = [w.upper().strip() for w in self._config.get("whitelist", []) if w.strip()]
                    from_base = from_call.upper().split("-")[0]
                    allowed = any(
                        from_base.startswith(w[:-1]) if w.endswith("*") else from_base == w
                        for w in wl
                    )
                    if not allowed:
                        self._emit(f"[AI-ENGEL] {from_call} whitelist'te degil, engellendi")
                        continue

                self._emit(f"[AI-RX] {from_call} sordu: {question}")

                extra_sms = int(self._config.get("extra_sms", 0))
                max_parts = 1 + extra_sms

                def process(fc=from_call, q=question, mp=max_parts):
                    try:
                        answer = self._ask(q)
                        self._emit(f"[AI] Cevap: {answer}")
                        parts = self._split_message(answer, mp)
                        for i, part in enumerate(parts):
                            ok = self._send(callsign, fc, part)
                            if ok:
                                self._emit(f"[AI-TX] -> {fc}: {part}")
                            else:
                                self._emit(f"[AI-HATA] {fc}'a gonderilemedi")
                                break
                            if i < len(parts) - 1:
                                time.sleep(5)
                    except Exception as e:
                        self._emit(f"[AI-HATA] {e}")

                threading.Thread(target=process, daemon=True).start()
        finally:
            proc.terminate()

    def _split_message(self, text, max_parts):
        if len(text) <= 64:
            return [text]
        parts = []
        remaining = text
        for i in range(max_parts):
            if not remaining:
                break
            if i == max_parts - 1 or len(remaining) <= 64:
                chunk = remaining[:64]
                if len(remaining) > 64:
                    chunk = remaining[:61].rsplit(" ", 1)[0] + "..."
                parts.append(chunk)
                break
            else:
                chunk = remaining[:61].rsplit(" ", 1)[0] + " --"
                parts.append(chunk)
                cut = remaining[:61].rsplit(" ", 1)[0]
                remaining = remaining[len(cut):].strip()
        return parts

    def _ask(self, question):
        extra = int(self._config.get("extra_sms", 0))
        total_parts = 1 + extra
        if total_parts == 1:
            char_limit = 64
        else:
            char_limit = (total_parts - 1) * 62 + 64
        system = (
            "Sen APRS telsiz sistemi uzerinden calisan bir yapay zekasin. "
            f"Cevabini TAM OLARAK {char_limit} karakter veya daha az yaz. "
            f"Bu siniri kesinlikle asma. {char_limit} karaktere sigacak sekilde "
            "anlamli, aciklayici ve faydali bir cevap ver. "
            "Gereksiz giris cumlesi yazma, direkt konuya gir. "
            "KURALLAR: "
            "1) Sadece Ingiliz alfabesi kullan (a-z, A-Z, 0-9 ve noktalama). "
            "2) Turkce ozel karakterler KULLANMA (s yerine s, g yerine g, "
            "i yerine i, u yerine u, o yerine o, c yerine c yaz). "
            "3) Emoji, unicode, ozel karakter YASAK. "
            "4) Turkce sorulara Turkce, Ingilizce sorulara Ingilizce cevap ver."
        )
        max_tokens = 40 + (extra * 35)
        resp = self._ai_client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
        )
        answer = resp.choices[0].message.content.strip()
        answer = to_ascii(answer)
        return answer

    def _send(self, from_call, to_call, message):
        passcode = self._passcode(from_call)
        dest = to_call.ljust(9)
        mid = str(int(time.time()) % 999 + 1)
        pkt = f"{from_call}>APRS,TCPIP*::{dest}:{message}{{{mid}}}\r\n"

        try:
            with sock.socket(sock.AF_INET, sock.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect(("rotate.aprs2.net", 14580))
                login = f"user {from_call} pass {passcode} vers aprs-ai-gw 1.0\r\n"
                s.sendall(login.encode())
                time.sleep(1)
                s.sendall(pkt.encode())
                time.sleep(0.5)
            return True
        except Exception as e:
            self._emit(f"[AI-HATA] Send: {e}")
            return False

    @staticmethod
    def _passcode(callsign):
        c = callsign.split("-")[0].upper()
        h = 0x73E2
        for i in range(0, len(c), 2):
            h ^= ord(c[i]) << 8
            if i + 1 < len(c):
                h ^= ord(c[i + 1])
        return h & 0x7FFF

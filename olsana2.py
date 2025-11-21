#!/usr/bin/env python3
import os
import json
import time
import threading
from gtts import gTTS
import vlc
from gpiozero.pins.pigpio import PiGPIOFactory
factory = PiGPIOFactory()
from PyPDF2 import PdfReader  # PyPDF2 ile PDF okuma

# ==========================
# 1. GPIO AYARLARI
# ==========================
motor_pins = [5, 6, 13, 19, 26, 21]
motors = [OutputDevice(pin, pin_factory=factory) for pin in motor_pins]

buttons = {
    "voice_only": Button(17, pull_up=True, pin_factory=factory),
    "voice_braille": Button(27, pull_up=True, pin_factory=factory),
    "speed_up": Button(22, pull_up=True, pin_factory=factory),
    "speed_down": Button(23, pull_up=True, pin_factory=factory),
    "next_book": Button(24, pull_up=True, pin_factory=factory),
    "select_book": Button(25, pull_up=True, pin_factory=factory),
    "save_position": Button(4, pull_up=True, pin_factory=factory),
    "learn_mode": Button(18, pull_up=True, pin_factory=factory)
}

# ==========================
# 2. KÜTÜPHANE VE DOSYA YOLLARI
# ==========================
DATA_FILE = "./book_data.json"
LOCAL_BOOKS = "./Apartman.pdf"
USB_PATH = "./"

# ==========================
# 3. BRAILLE TABLOSU
# ==========================
braille_bin = {
    "a": "100000", "b": "110000", "c": "100100", "ç": "100111",
    "d": "100110", "e": "100010", "f": "110100", "g": "110110",
    "ğ": "110111", "h": "110010", "ı": "010100", "i": "010110",
    "j": "010111", "k": "101000", "l": "111000", "m": "101100",
    "n": "101110", "o": "101010", "ö": "101111", "p": "111100",
    "r": "111010", "s": "011100", "ş": "011111", "t": "011110",
    "u": "101001", "ü": "101011", "v": "111001", "y": "111101",
    "z": "101101", " ": "000000", ".": "010011", ",": "010000",
    "?": "001100", "!": "011010", "\n": "\n"
}

# ==========================
# 4. YARDIMCI FONKSİYONLAR
# ==========================
def speak(text):
    """Türkçe sesli okuma VLC ile"""
    tts_path = "/home/pi/temp.mp3"
    tts = gTTS(text=text, lang="tr")
    tts.save(tts_path)
    player = vlc.MediaPlayer(tts_path)
    player.play()
    while player.get_state() != vlc.State.Ended:
        time.sleep(0.1)
    try:
        os.remove(tts_path)
    except:
        pass

def scan_books():
    """USB ve yerel kitapları tarar"""
    books = []
    os.makedirs(LOCAL_BOOKS, exist_ok=True)
    for path in [LOCAL_BOOKS, USB_PATH]:
        if not os.path.exists(path):
            continue
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.lower().endswith(".pdf"):
                    books.append({"name": file, "path": os.path.join(root, file), "position": 0})
    return books

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"last_opened_book": None, "last_position": 0, "books": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def text_to_braille_binary(text):
    result = []
    for ch in text.lower():
        if ch in braille_bin:
            result.append(braille_bin[ch])
    return result

def activate_motors(pattern):
    for i in range(6):
        if pattern[i] == "1":
            motors[i].on()
        else:
            motors[i].off()
    time.sleep(0.3)
    for m in motors:
        m.off()

# ==========================
# 5. KİTAP İŞLEMLERİ (PyPDF2 ile PDF okuma)
# ==========================
def read_pdf(path):
    """PyPDF2 ile PDF’den metin çıkarma"""
    text = ""
    try:
        with open(path, "rb") as f:
            reader = PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
    except Exception as e:
        print("PDF okuma hatası:", e)
    return text

def write_braille(text, voice=False, speed=0.3):
    braille_data = text_to_braille_binary(text)
    for pattern in braille_data:
        activate_motors(pattern)
        if voice:
            try:
                letter = list(braille_bin.keys())[list(braille_bin.values()).index(pattern)]
            except ValueError:
                letter = ""
            if letter:
                threading.Thread(target=speak, args=(letter,)).start()
        time.sleep(speed)

# ==========================
# 6. ANA AKIŞ
# ==========================
def main():
    data = load_data()
    data["books"] = scan_books()
    save_data(data)

    book_index = 0
    speed = 0.4

    speak("Sistem hazır. Kitap seçmek için tuşa basınız.")

    while True:
        if buttons["next_book"].is_pressed:
            book_index = (book_index + 1) % len(data["books"])
            speak(f"{data['books'][book_index]['name']} seçildi")
            time.sleep(0.5)

        if buttons["select_book"].is_pressed:
            current = data["books"][book_index]
            text = read_pdf(current["path"])
            speak(f"{current['name']} açılıyor")
            write_braille(text, voice=False, speed=speed)
            data["last_opened_book"] = current["name"]
            data["last_position"] = 0
            save_data(data)
            time.sleep(0.5)

        if buttons["voice_only"].is_pressed:
            current = data["books"][book_index]
            text = read_pdf(current["path"])
            speak("Sesli okuma başlatıldı")
            speak(text)
            time.sleep(0.5)

        if buttons["voice_braille"].is_pressed:
            current = data["books"][book_index]
            text = read_pdf(current["path"])
            speak("Sesli ve Braille mod aktif")
            write_braille(text, voice=True, speed=speed)
            time.sleep(0.5)

        if buttons["speed_up"].is_pressed:
            speed = max(0.1, speed - 0.05)
            speak(f"Hız artırıldı. Şu anki hız {round(speed,2)}")
            time.sleep(0.3)

        if buttons["speed_down"].is_pressed:
            speed += 0.05
            speak(f"Hız azaltıldı. Şu anki hız {round(speed,2)}")
            time.sleep(0.3)

        if buttons["save_position"].is_pressed:
            data["books"][book_index]["position"] = data.get("last_position", 0)
            save_data(data)
            speak("Kaldığınız yer kaydedildi")
            time.sleep(0.5)

        if buttons["learn_mode"].is_pressed:
            speak("Braille öğrenme modu başlatılıyor")
            for harf, pattern in braille_bin.items():
                activate_motors(pattern)
                speak(harf)
                time.sleep(speed)
            time.sleep(0.1)

        time.sleep(0.1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

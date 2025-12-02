#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import hashlib
import requests
import threading
import subprocess
from threading import Thread, Lock, Event
import RPi.GPIO as GPIO

# ==================== KONFİGÜRASYON ====================
GITHUB_REPO = "mehkerer8/pdfs"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents"
LOCAL_BOOKS_DIR = "/home/pixel/braille_books"
UPDATE_INTERVAL = 3600

# ==================== GELİŞMİŞ SES SİSTEMİ - HIZLI ve AKICI ====================
class TurkishVoice:
    """Hızlı ve Akıcı Türkçe Kadın Sesi"""
    
    @staticmethod
    def setup():
        """Ses sistemini kur"""
        print("🔊 Türkçe kadın sesi kuruluyor...")
        
        packages = ["espeak", "espeak-data"]
        for pkg in packages:
            try:
                subprocess.run(["dpkg", "-l", pkg], capture_output=True, check=True)
                print(f"✓ {pkg} kurulu")
            except:
                subprocess.run(["sudo", "apt", "install", "-y", pkg], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    @staticmethod
    def speak(text, wait=True, slow=False):
        """
        HIZLI ve AKICI TÜRKÇE KADIN SESİ
        - Görme engelli okuma hızına uygun (hızlı)
        - Noktalama duraklamaları optimize edilmiş
        - Kesintisiz akıcı konuşma
        """
        try:
            # Metni optimize et (noktalama için boşluk ekle)
            text = TurkishVoice.optimize_text(text)
            
            # HIZ AYARLARI:
            # Normal: 160 wpm (görme engelli standart okuma hızı)
            # Yavaş: 130 wpm (öğrenme modu için)
            speed = 130 if slow else 160
            
            # OPTİMİZE SES PARAMETRELERİ
            cmd = [
                'espeak',
                '-v', 'tr+f3',      # Türkçe kadın sesi
                '-s', str(speed),   # HIZLI: 160 kelime/dakika
                '-a', '180',        # Yüksek ses
                '-p', '50',         # Doğal perde
                '-g', '5',          # Minimum kelime arası boşluk
                '--stdout'          # Kesintisiz çıktı
            ]
            
            # Metni ses dosyasına çevir
            espeak_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, 
                                          stdout=subprocess.PIPE, 
                                          stderr=subprocess.PIPE)
            
            audio_data, errors = espeak_proc.communicate(input=text.encode('utf-8'))
            
            if espeak_proc.returncode == 0 and audio_data:
                # aplay ile kesintisiz çal
                aplay_cmd = ['aplay', '-q', '-t', 'wav', '-']
                aplay_proc = subprocess.Popen(aplay_cmd, stdin=subprocess.PIPE,
                                             stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL)
                
                aplay_proc.communicate(input=audio_data)
                
                if wait:
                    aplay_proc.wait()
            
        except Exception as e:
            print(f"Ses hatası: {e}")
            TurkishVoice.speak_fallback(text, wait, slow)
    
    @staticmethod
    def speak_fallback(text, wait=True, slow=False):
        """Fallback seslendirme"""
        try:
            text = TurkishVoice.fix_turkish_text(text)
            speed = 130 if slow else 160  # Aynı hız
            cmd = ['espeak', '-v', 'tr+f3', '-s', str(speed), text]
            
            if wait:
                # Uzun metinler için timeout hesapla
                timeout = max(15, len(text) / 25)  # Daha uzun timeout
                subprocess.run(cmd, stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL, timeout=timeout)
            else:
                Thread(target=lambda: subprocess.run(cmd, 
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL), 
                       daemon=True).start()
        except subprocess.TimeoutExpired:
            print("Seslendirme tamamlandı")
        except Exception as e:
            print(f"Fallback ses hatası: {e}")
    
    @staticmethod
    def optimize_text(text):
        """Metni hızlı okuma için optimize et"""
        # Türkçe karakter düzelt
        text = TurkishVoice.fix_turkish_text(text)
        
        # Noktalama işaretlerine boşluk ekle (duraklama için)
        # Ama çok fazla boşluk ekleme, akıcılık için
        punctuation = ['.', ',', '!', '?', ':', ';']
        for punct in punctuation:
            text = text.replace(punct, f' {punct} ')
        
        # Çoklu boşlukları temizle
        words = text.split()
        return ' '.join(words)
    
    @staticmethod
    def fix_turkish_text(text):
        """Türkçe karakterleri düzelt"""
        replacements = {
            'ı': 'i', 'İ': 'I',
            'ğ': 'g', 'Ğ': 'G',
            'ü': 'u', 'Ü': 'U',
            'ş': 's', 'Ş': 'S',
            'ö': 'o', 'Ö': 'O',
            'ç': 'c', 'Ç': 'C',
            'â': 'a', 'î': 'i', 'û': 'u'
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text
    
    @staticmethod
    def chunk_text(text, chunk_size=300):
        """Metni kesintisiz okuma için parçalara ayır"""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0
        
        for word in words:
            current_chunk.append(word)
            current_length += len(word) + 1
            
            # Parçayı noktalama işaretinde böl (doğal duraklama)
            if current_length >= chunk_size and word[-1] in '.!?,;':
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_length = 0
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks if chunks else [text]

# ==================== GPIO AYARLARI ====================
class GPIOPins:
    # Röle Pinleri (6 solenoid için)
    RELAY_PINS = [4, 17, 27, 22, 23, 24]
    
    # Buton Pinleri
    BUTTON_NEXT = 5        # Sonraki kitap
    BUTTON_CONFIRM = 6     # Onay/Seçim
    BUTTON_MODE = 13       # Mod değiştirme
    BUTTON_SPEED_UP = 19   # Hız artırma
    BUTTON_SPEED_DOWN = 26 # Hız azaltma
    BUTTON_UPDATE = 21     # Kitapları güncelle
    
    ALL_BUTTONS = [BUTTON_NEXT, BUTTON_CONFIRM, BUTTON_MODE, 
                   BUTTON_SPEED_UP, BUTTON_SPEED_DOWN, BUTTON_UPDATE]

# ==================== BRAILLE KİTAP OKUYUCU ====================
class BrailleBookReader:
    def __init__(self):
        print("⚡ HIZLI BRAİLLE KİTAP OKUYUCU")
        print("=" * 50)
        
        # Ses motorunu kur
        TurkishVoice.setup()
        
        # GPIO Ayarları
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        try:
            GPIO.cleanup()
            time.sleep(0.3)
        except:
            pass
        
        # Değişkenler
        self.books = []
        self.current_book_index = 0
        self.selected_book = None
        self.current_mode = 0
        self.modes = ["sadece_yazma", "sadece_okuma", "hem_okuma_hem_yazma", "egitim_modu"]
        self.mode_names = ["Sadece Yazma", "Sadece Okuma", "Hem Okuma Hem Yazma", "Braille Eğitimi"]
        
        # HIZ AYARLARI - GÖRME ENGELLİ OKUMA HIZINA GÖRE
        self.base_speech_speed = 160  # Normal hız (wpm)
        self.base_write_speed = 0.8   # Yazma hızı (saniye/harf) - HIZLI
        self.min_speed = 120          # Minimum hız
        self.max_speed = 200          # Maximum hız
        
        # Sistem durumu
        self.is_running = True
        self.is_playing = False
        self.stop_event = Event()
        self.progress_data = {}
        self.current_position = 0
        self.current_text = ""
        
        # Buton takibi
        self.button_states = {}
        self.last_button_time = {}
        self.lock = Lock()
        
        # Dizinleri oluştur
        self.setup_directories()
        
        # GPIO'yu ayarla
        self.setup_gpio()
        
        # Braille haritasını yükle
        self.setup_braille_map()
        
        # İlerlemeyi yükle
        self.load_progress()
        
        # Kitapları yükle (yerelden)
        self.load_local_books()
        
        # Otomatik güncelleme thread'i
        self.update_thread = Thread(target=self.auto_update_check, daemon=True)
        self.update_thread.start()
        
        # Başlangıç mesajı - HIZLI
        self.speak("Braille kitap okuyucuya hoş geldiniz.", slow=False)
        time.sleep(0.8)
        
        if self.books:
            self.speak(f"Kütüphanenizde {len(self.books)} kitap bulunuyor.", slow=False)
            time.sleep(0.8)
            book_name = self.books[0]['name_tr']
            self.speak(f"İlk kitap: {book_name}", slow=False)
            time.sleep(0.8)
        else:
            self.speak("Henüz hiç kitap yok. Lütfen güncelle tuşuna basarak kitapları indirin.", slow=False)
        
        self.speak("İleri tuşu ile kitaplar arasında gezin.", slow=False)
        time.sleep(0.5)
        self.speak("Onay tuşu ile seçin.", slow=False)
        time.sleep(0.5)
        self.speak("Mod tuşu ile okuma modunu değiştirin.", slow=False)
        
        print("✅ Sistem başlatıldı!")
    
    # ==================== SES FONKSİYONLARI ====================
    def speak(self, text, slow=False):
        """Hızlı seslendirme"""
        TurkishVoice.speak(text, wait=True, slow=slow)
    
    def speak_async(self, text, slow=False):
        """Asenkron seslendirme"""
        Thread(target=lambda: TurkishVoice.speak(text, wait=True, slow=slow), 
               daemon=True).start()
    
    def adjust_speed(self, increase=True):
        """Ses hızını ayarla"""
        with self.lock:
            if increase:
                self.base_speech_speed = min(self.max_speed, self.base_speech_speed + 15)
                self.base_write_speed = max(0.3, self.base_write_speed - 0.1)  # Yazma hızını da artır
            else:
                self.base_speech_speed = max(self.min_speed, self.base_speech_speed - 15)
                self.base_write_speed = min(1.5, self.base_write_speed + 0.1)  # Yazma hızını azalt
            
            self.speak(f"Ses hızı: {self.base_speech_speed}", slow=False)
    
    # ==================== GİTHUB PDF SİSTEMİ ====================
    def setup_directories(self):
        """Gerekli dizinleri oluştur"""
        os.makedirs(LOCAL_BOOKS_DIR, exist_ok=True)
        os.makedirs(f"{LOCAL_BOOKS_DIR}/pdfs", exist_ok=True)
    
    def load_local_books(self):
        """Yerel kitapları yükle"""
        auto_file = f"{LOCAL_BOOKS_DIR}/kitaplar_auto.json"
        
        if os.path.exists(auto_file):
            try:
                with open(auto_file, 'r', encoding='utf-8') as f:
                    self.books = json.load(f)
                print(f"📚 {len(self.books)} kitap yüklendi")
            except Exception as e:
                print(f"Kitaplar yüklenirken hata: {e}")
                self.books = []
        else:
            self.books = []
    
    def scan_github_for_pdfs(self):
        """GitHub'daki PDF'leri tara"""
        print("🌐 GitHub'daki PDF'ler taranıyor...")
        
        try:
            headers = {'User-Agent': 'Braille-Book-Reader'}
            response = requests.get(GITHUB_API_URL, headers=headers, timeout=10)
            
            if response.status_code == 200:
                files = response.json()
                books = []
                
                for file in files:
                    if isinstance(file, dict) and file.get('type') == 'file':
                        filename = file.get('name', '')
                        if filename.lower().endswith('.pdf'):
                            book_name = self.create_book_name(filename)
                            books.append({
                                'filename': filename,
                                'name_tr': book_name,
                                'download_url': file.get('download_url', ''),
                                'size': file.get('size', 0),
                                'sha': file.get('sha', '')[:8]
                            })
                
                print(f"✅ {len(books)} PDF bulundu")
                return books
            else:
                print(f"❌ GitHub API hatası: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"❌ Tarama hatası: {e}")
            return []
    
    def create_book_name(self, filename):
        """Dosya adından kitap adı oluştur"""
        name = filename.replace('.pdf', '').replace('.PDF', '')
        for char in ['_', '-', '.']:
            name = name.replace(char, ' ')
        
        # Türkçe karakter
        turkish_map = {'c': 'ç', 'g': 'ğ', 'i': 'ı', 's': 'ş', 'u': 'ü', 'o': 'ö'}
        for eng, tr in turkish_map.items():
            name = name.replace(eng, tr)
        
        words = []
        for word in name.split():
            if word.lower() in ['ve', 'ile', 'de', 'da', 'ki']:
                words.append(word.lower())
            else:
                words.append(word[0].upper() + word[1:].lower())
        
        result = ' '.join(words)
        return result[:40] if len(result) > 40 else result
    
    def update_library(self, speak_progress=True):
        """Kitaplığı güncelle"""
        if speak_progress:
            self.speak("Kitaplar güncelleniyor.", slow=False)
        
        github_books = self.scan_github_for_pdfs()
        
        if not github_books:
            if speak_progress:
                self.speak("GitHub'dan kitap listesi alınamadı.", slow=False)
            return
        
        if speak_progress:
            self.speak(f"{len(github_books)} kitap bulundu.", slow=False)
        
        new_books = []
        for book in github_books:
            local_path = f"{LOCAL_BOOKS_DIR}/pdfs/{book['filename']}"
            if not os.path.exists(local_path):
                new_books.append(book)
        
        if speak_progress and new_books:
            self.speak(f"{len(new_books)} yeni kitap indirilecek.", slow=False)
        
        success_count = 0
        for book in new_books:
            if self.download_book(book):
                success_count += 1
        
        self.save_book_metadata(github_books)
        self.books = github_books
        
        if speak_progress:
            if success_count > 0:
                self.speak(f"Güncelleme tamamlandı. {success_count} kitap eklendi.", slow=False)
            else:
                self.speak("Tüm kitaplar güncel.", slow=False)
    
    def download_book(self, book):
        """Kitabı indir"""
        try:
            response = requests.get(book['download_url'], timeout=30)
            if response.status_code == 200:
                file_path = f"{LOCAL_BOOKS_DIR}/pdfs/{book['filename']}"
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                return True
        except:
            pass
        return False
    
    def save_book_metadata(self, books):
        """Metadata'yı kaydet"""
        metadata_path = f"{LOCAL_BOOKS_DIR}/kitaplar_auto.json"
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(books, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def auto_update_check(self):
        """Otomatik güncelleme kontrolü"""
        while self.is_running:
            time.sleep(UPDATE_INTERVAL)
            try:
                requests.get("https://api.github.com", timeout=5)
                self.update_library(speak_progress=False)
            except:
                pass
    
    # ==================== GPIO ve BUTON KONTROLÜ ====================
    def setup_gpio(self):
        """GPIO pinlerini ayarla"""
        try:
            for pin in GPIOPins.RELAY_PINS:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)
            
            for pin in GPIOPins.ALL_BUTTONS:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                self.button_states[pin] = GPIO.HIGH
                self.last_button_time[pin] = time.time()
            
        except Exception as e:
            print(f"GPIO hatası: {e}")
    
    def check_buttons(self):
        """Butonları kontrol et"""
        current_time = time.time()
        
        for pin in GPIOPins.ALL_BUTTONS:
            try:
                current_state = GPIO.input(pin)
                last_state = self.button_states.get(pin, GPIO.HIGH)
                
                if current_state == GPIO.LOW and last_state == GPIO.HIGH:
                    if current_time - self.last_button_time.get(pin, 0) > 0.3:
                        self.last_button_time[pin] = current_time
                        self.handle_button_press(pin)
                
                self.button_states[pin] = current_state
                
            except:
                pass
    
    def handle_button_press(self, pin):
        """Buton işleyici"""
        with self.lock:
            if pin == GPIOPins.BUTTON_NEXT:
                self.next_book()
            elif pin == GPIOPins.BUTTON_CONFIRM:
                self.confirm_selection()
            elif pin == GPIOPins.BUTTON_MODE:
                self.next_mode()
            elif pin == GPIOPins.BUTTON_SPEED_UP:
                self.adjust_speed(increase=True)
            elif pin == GPIOPins.BUTTON_SPEED_DOWN:
                self.adjust_speed(increase=False)
            elif pin == GPIOPins.BUTTON_UPDATE:
                self.manual_update()
    
    def next_book(self):
        """Sonraki kitap"""
        if not self.books:
            self.speak("Henüz kitap yok. Güncelle tuşuna basın.", slow=False)
            return
        
        self.current_book_index = (self.current_book_index + 1) % len(self.books)
        book = self.books[self.current_book_index]
        self.speak(book['name_tr'], slow=False)
    
    def confirm_selection(self):
        """Seçimi onayla"""
        if not self.books:
            self.speak("Önce kitapları güncelleyin.", slow=False)
            return
        
        if self.selected_book is None:
            self.selected_book = self.books[self.current_book_index]
            book = self.selected_book
            self.speak(f"{book['name_tr']} seçildi. Mod seçmek için mod tuşuna basın.", slow=False)
            time.sleep(1)
            self.speak("Mevcut modlar: Sadece Yazma, Sadece Okuma, Hem Okuma Hem Yazma, Braille Eğitimi", slow=False)
        else:
            self.speak(f"{self.mode_names[self.current_mode]} seçildi. Başlıyor...", slow=False)
            time.sleep(1)
            self.start_reading()
    
    def next_mode(self):
        """Sonraki mod"""
        if self.selected_book is None:
            self.speak("Önce bir kitap seçin.", slow=False)
            return
        
        self.current_mode = (self.current_mode + 1) % len(self.modes)
        self.speak(self.mode_names[self.current_mode], slow=False)
    
    def manual_update(self):
        """Manuel güncelleme"""
        Thread(target=self.update_library, args=(True,), daemon=True).start()
    
    # ==================== BRAILLE SİSTEMİ - HIZLI YAZMA ====================
    def setup_braille_map(self):
        """Braille haritasını yükle"""
        self.braille_map = {
            'a': [1,0,0,0,0,0], 'b': [1,1,0,0,0,0], 'c': [1,0,0,1,0,0],
            'ç': [1,0,0,1,1,0], 'd': [1,0,0,1,1,1], 'e': [1,0,0,0,1,0],
            'f': [1,1,0,1,0,0], 'g': [1,1,0,1,1,0], 'ğ': [1,1,0,1,1,1],
            'h': [1,1,0,0,1,0], 'ı': [0,1,0,1,0,1], 'i': [0,1,0,1,0,0],
            'j': [0,1,0,1,1,0], 'k': [1,0,1,0,0,0], 'l': [1,1,1,0,0,0],
            'm': [1,0,1,1,0,0], 'n': [1,0,1,1,1,0], 'o': [1,0,1,0,1,0],
            'ö': [0,1,1,1,0,1], 'p': [1,1,1,1,0,0], 'r': [1,1,1,1,1,0],
            's': [0,1,1,1,0,0], 'ş': [1,1,1,0,1,1], 't': [0,1,1,1,1,1],
            'u': [1,0,1,0,0,1], 'ü': [0,1,1,1,1,0], 'v': [0,1,1,1,0,1],
            'y': [1,0,1,1,1,1], 'z': [1,0,1,0,1,1],
            ' ': [0,0,0,0,0,0], '.': [0,1,0,0,1,1], ',': [0,1,0,0,0,0],
            '!': [0,1,1,0,1,0], '?': [0,1,1,0,0,1]
        }
    
    def set_solenoids(self, pattern):
        """Solenoidleri ayarla - HIZLI"""
        for i, state in enumerate(pattern[:6]):
            if i < len(GPIOPins.RELAY_PINS):
                GPIO.output(GPIOPins.RELAY_PINS[i], GPIO.HIGH if state else GPIO.LOW)
    
    def clear_solenoids(self):
        """Solenoidleri temizle"""
        for pin in GPIOPins.RELAY_PINS:
            GPIO.output(pin, GPIO.LOW)
    
    # ==================== PDF OKUMA ====================
    def read_pdf_content(self, book):
        """PDF içeriğini oku"""
        pdf_path = f"{LOCAL_BOOKS_DIR}/pdfs/{book['filename']}"
        
        if not os.path.exists(pdf_path):
            return ""
        
        try:
            temp_file = "/tmp/kitap_temp.txt"
            cmd = ["pdftotext", "-layout", pdf_path, temp_file]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(temp_file):
                with open(temp_file, 'r', encoding='utf-8') as f:
                    text = f.read()
                os.remove(temp_file)
                return text
            return ""
        except:
            return ""
    
    def start_reading(self):
        """Okumaya başla"""
        if not self.selected_book:
            return
        
        self.stop_event.set()
        self.is_playing = False
        time.sleep(0.3)
        self.stop_event.clear()
        
        self.speak("Kitap yükleniyor.", slow=False)
        self.current_text = self.read_pdf_content(self.selected_book)
        
        if not self.current_text:
            self.speak("Kitap okunamadı.", slow=False)
            return
        
        book_key = self.selected_book['filename']
        if book_key in self.progress_data:
            self.current_position = self.progress_data[book_key]['position']
            self.speak("Kayıtlı yerden devam ediliyor.", slow=False)
        else:
            self.current_position = 0
        
        self.is_playing = True
        
        if self.modes[self.current_mode] == "sadece_yazma":
            self.mode_write_only()
        elif self.modes[self.current_mode] == "sadece_okuma":
            self.mode_read_only()
        elif self.modes[self.current_mode] == "hem_okuma_hem_yazma":
            self.mode_read_and_write()
        elif self.modes[self.current_mode] == "egitim_modu":
            self.mode_education()
    
    def mode_write_only(self):
        """Sadece yazma modu - HIZLI"""
        self.speak("Sadece yazma modu başlıyor.", slow=False)
        time.sleep(1)
        
        text_to_write = self.current_text[self.current_position:self.current_position + 500]
        
        for char in text_to_write:
            if self.stop_event.is_set() or not self.is_playing:
                break
            
            char_lower = char.lower()
            if char_lower in self.braille_map:
                # HIZLI YAZMA: 0.5 saniye/harf
                self.set_solenoids(self.braille_map[char_lower])
                time.sleep(self.base_write_speed)  # HIZ AYARI
                self.clear_solenoids()
                time.sleep(0.1)  # Harf arası boşluk
            
            self.current_position += 1
        
        self.is_playing = False
        self.save_progress()
        self.speak("Yazma modu tamamlandı.", slow=False)
    
    def mode_read_only(self):
        """Sadece okuma modu - HIZLI"""
        self.speak("Okuma modu başlıyor.", slow=False)
        time.sleep(0.5)
        
        # Metni parçalara böl (kesintisiz okuma için)
        chunk_size = 600
        text_to_read = self.current_text[self.current_position:]
        
        chunks = TurkishVoice.chunk_text(text_to_read, chunk_size)
        
        for chunk in chunks:
            if self.stop_event.is_set() or not self.is_playing:
                break
            
            if chunk.strip():
                self.speak(chunk, slow=False)
            
            self.current_position += len(chunk)
            
            if self.current_position % 2000 < chunk_size:  # Her 2000 karakterde bir kaydet
                self.save_progress()
        
        self.is_playing = False
        self.save_progress()
        self.speak("Kitap okuması tamamlandı.", slow=False)
    
    def mode_read_and_write(self):
        """Hem okuma hem yazma modu - HIZLI ve SENKRON"""
        self.speak("Okuma ve yazma modu başlıyor.", slow=False)
        time.sleep(0.5)
        
        # Metni kelimelere ayır
        text_to_process = self.current_text[self.current_position:self.current_position + 1000]
        words = text_to_process.split()
        
        word_index = 0
        while word_index < len(words) and not self.stop_event.is_set() and self.is_playing:
            word = words[word_index]
            
            # KELİMEYİ YAZ (harf harf hızlı)
            for char in word:
                char_lower = char.lower()
                if char_lower in self.braille_map:
                    self.set_solenoids(self.braille_map[char_lower])
                    time.sleep(self.base_write_speed * 0.7)  # DAHA HIZLI
                    self.clear_solenoids()
                    time.sleep(0.05)  # Çok kısa boşluk
            
            # KELİMEYİ OKU (bütün kelimeyi oku)
            if word.strip():
                # Kelimeyi asenkron oku (yazma devam ederken)
                self.speak_async(word + " ", slow=False)
            
            # Kelime arası boşluk yaz
            self.clear_solenoids()
            time.sleep(self.base_write_speed * 0.3)
            
            self.current_position += len(word) + 1  # +1 for space
            word_index += 1
            
            # Her 10 kelimede bir kaydet
            if word_index % 10 == 0:
                self.save_progress()
        
        self.is_playing = False
        self.save_progress()
        self.speak("Okuma ve yazma modu tamamlandı.", slow=False)
    
    def mode_education(self):
        """Braille eğitim modu"""
        self.speak("Braille eğitim modu başlıyor.", slow=False)
        time.sleep(1)
        
        letters = [("a", "a"), ("b", "b"), ("c", "c"), ("d", "d"), ("e", "e")]
        
        for char, sound in letters:
            if self.stop_event.is_set() or not self.is_playing:
                break
            
            self.speak(sound, slow=False)
            time.sleep(0.5)
            
            if char in self.braille_map:
                self.set_solenoids(self.braille_map[char])
                time.sleep(2)
                self.clear_solenoids()
                time.sleep(0.5)
        
        self.is_playing = False
        self.speak("Eğitim tamamlandı.", slow=False)
    
    # ==================== İLERLEME YÖNETİMİ ====================
    def load_progress(self):
        """İlerlemeyi yükle"""
        progress_file = f"{LOCAL_BOOKS_DIR}/progress.json"
        if os.path.exists(progress_file):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    self.progress_data = json.load(f)
            except:
                self.progress_data = {}
    
    def save_progress(self):
        """İlerlemeyi kaydet"""
        if not self.selected_book:
            return
        
        try:
            book_key = self.selected_book['filename']
            self.progress_data[book_key] = {
                'position': self.current_position,
                'mode': self.current_mode,
                'timestamp': time.time()
            }
            
            progress_file = f"{LOCAL_BOOKS_DIR}/progress.json"
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(self.progress_data, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    # ==================== ANA DÖNGÜ ====================
    def main_loop(self):
        """Ana program döngüsü"""
        try:
            while self.is_running:
                self.check_buttons()
                time.sleep(0.03)  # DAHA HIZLI KONTROL (30ms)
                
        except KeyboardInterrupt:
            print("\n⏹️ Durduruldu")
            self.cleanup()
        except Exception as e:
            print(f"Hata: {e}")
            self.cleanup()
    
    def cleanup(self):
        """Temizlik"""
        self.is_running = False
        self.stop_event.set()
        self.is_playing = False
        
        time.sleep(0.5)
        self.clear_solenoids()
        self.save_progress()
        GPIO.cleanup()
        print("✅ Sistem kapatıldı")

# ==================== ANA PROGRAM ====================
def main():
    """Ana fonksiyon"""
    print("=" * 60)
    print("⚡ HIZLI BRAİLLE KİTAP OKUYUCU - TÜRKÇE KADIN SESİ")
    print("=" * 60)
    
    # Bağımlılıkları kontrol et
    try:
        import requests
        import RPi.GPIO
    except ImportError:
        print("Paketler kuruluyor...")
        subprocess.run(["sudo", "apt", "install", "-y", "python3-pip"])
        subprocess.run(["pip3", "install", "requests", "RPi.GPIO"])
    
    # Programı başlat
    reader = BrailleBookReader()
    
    try:
        reader.main_loop()
    except Exception as e:
        print(f"Hata: {e}")
        reader.cleanup()

if __name__ == "__main__":
    main()

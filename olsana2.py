import time
import threading
import os
import random
from gtts import gTTS
import vlc
from gpiozero import OutputDevice, Button
from gpiozero.pins.pigpio import PiGPIOFactory

factory = PiGPIOFactory()

text_input = """
Üçüncü kattan sonra kırmızı halı bitiyor, gri bir muşamba başlıyordu.
Böyle saygın bir evde oturacağı için keyiflenen Octave bunu biraz
buruk karşıladı. Odasına giden koridora doğru mimarın peşinden
yürürken, yandaki yarı açık kapıdan bir beşiğin başında duran genç
bir kadın gördü. Kadın gürültüye başını kaldırdı. Sarışın kadının açık
renk gözleri boş boş bakıyordu. Octave'ın zihninde bu bakış kaldı,
çünkü kadın yakalanmış gibi yüzü kızararak kapıyı kapadı.
Campardon sonunda servis merdivenine bitişik bir kapının önünde
durdu. Daha yukarda hizmetçilerin odaları bulunuyordu.
"""

motor_pins = [5, 6, 13, 19, 26, 21]
motors = [OutputDevice(pin, pin_factory=factory) for pin in motor_pins]

buttons = {
    "speed_up": Button(22, pull_up=True, pin_factory=factory),
    "speed_down": Button(23, pull_up=True, pin_factory=factory)
}

braille_bin = {
    "a":"100000","b":"110000","c":"100100","ç":"100111","d":"100110","e":"100010",
    "f":"110100","g":"110110","ğ":"110111","h":"110010","ı":"010100","i":"010110",
    "j":"010111","k":"101000","l":"111000","m":"101100","n":"101110","o":"101010",
    "ö":"101111","p":"111100","r":"111010","s":"011100","ş":"011111","t":"011110",
    "u":"101001","ü":"101011","v":"111001","y":"111101","z":"101101"," ":"000000",
    ".":"010011",",":"010000","?":"001100","!":"011010","\n":"\n"
}

def speak(t):
    filename = f"./tts_{random.randint(1000,9999)}.mp3"
    p = filename
    
    try:
        gTTS(text=t, lang="tr").save(p)
        player = vlc.MediaPlayer(p)
        player.play()
        
        while player.get_state() != vlc.State.Ended:
            time.sleep(0.1)
            
        # Oynatma bittikten sonra dosyayı temizle
        if os.path.exists(p):
            os.remove(p)
    except Exception as e:
        print(f"TTS hatası: {e}")

def text_to_braille(t):
    out = []
    for ch in t.lower():
        if ch in braille_bin:
            out.append(braille_bin[ch])
    return out

def activate(pattern):
    # Pattern uzunluğunu kontrol et
    if len(pattern) < 6:
        print(f"Uyarı: Geçersiz pattern uzunluğu: {pattern}")
        return
    
    for i in range(6):
        if pattern[i] == "1": 
            motors[i].on()
        else: 
            motors[i].off()
    time.sleep(0.25)
    for m in motors: 
        m.off()

def main():
    speed = 0.35
    bra = text_to_braille(text_input)

    threading.Thread(target=speak, args=(text_input,), daemon=True).start()

    for p in bra:
        if p == "\n":  # Yeni satır karakterini atla
            continue
            
        activate(p)

        if buttons["speed_up"].is_pressed:
            speed = max(0.1, speed - 0.05)
            print(f"Hız arttı: {speed}")

        if buttons["speed_down"].is_pressed:
            speed += 0.05
            print(f"Hız azaldı: {speed}")

        time.sleep(speed)

if __name__ == "__main__":
    main()

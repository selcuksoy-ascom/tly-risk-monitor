[app]

# APK kimlik bilgileri
title = TLY Risk
package.name = tlyrisk
package.domain = com.tera
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt
version = 1.0
requirements = python3,kivy,yfinance,pandas,numpy,tabulate
orientation = portrait
fullscreen = 1
window_state = maximized

# Android izinleri
android.permissions = INTERNET
android.api = 31
android.minapi = 26
android.ndk = 25b
android.sdk = 34

# APK çıkış konumu
android.arch = arm64-v8a

# Derleme ayarları
p4a.branch = master
p4a.hostpython = python3

# Kivy gereksinimleri
kivy.kivy_android = 2.3.0

# Optimizasyon (APK boyutunu küçültür)
android.release_artifact = aab
android.presplash_color = #050A14
android.splash_color = #050A14

# Uygulama simgesi (isteğe bağlı — bir png dosyası yolu)
# icon.filename = icon.png

# Crash log
android.logcat_filters = *:S python:D
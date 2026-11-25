[app]

title = W-Sort
package.name = pilahpintar
package.domain = id.pilahpintar
source.dir = .
source.include_exts = py,kv,png,jpg,atlas,tflite
version = 0.1.0
orientation = portrait
fullscreen = 0

requirements = python3,kivy,numpy,pillow,pyjnius
android.permissions = CAMERA
android.api = 35
android.minapi = 23
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a
android.gradle_dependencies = org.tensorflow:tensorflow-lite:2.15.0
android.allow_backup = False
android.private_storage = True
android.accept_sdk_license = True
p4a.bootstrap = sdl2

[buildozer]
log_level = 2
warn_on_root = 1

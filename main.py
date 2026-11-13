import os, sys, subprocess, shutil
from pathlib import Path
from worlds_config import select_world
from experiment_config import load_config, save_config

def find_webots():
    configured = os.environ.get('WEBOTS_EXECUTABLE')
    if configured:
        return configured
    for command in ('webots', 'webots.exe', 'webotsw.exe'):
        found = shutil.which(command)
        if found:
            return found
    candidates = [
        Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Programs/Webots/msys64/mingw64/bin/webotsw.exe',
        Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Webots/msys64/mingw64/bin/webotsw.exe',
        Path('/Applications/Webots.app/Contents/MacOS/webots'),
        Path('/usr/local/webots/webots'),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError('Set WEBOTS_EXECUTABLE to your Webots executable.')


def menu():
    while True:
        print("\n================================================")
        print("  INF330 - Webots Yol Planlama Projesi")
        print("================================================")
        print("  1. Simülasyonu Başlat")
        print("  2. Algoritma Degistir")
        print("  3. Sonuclari Analiz Et")
        print("  0. Cikis")
        print("================================================")
        secim = input("  Secim: ").strip()

        if secim == "1":
            base = os.path.dirname(os.path.abspath(__file__))
            density = input("  Yogunluk (low/medium/high) [low]: ").strip() or "low"
            speed = input("  Engel hizi (static/slow/medium/fast) [static]: ").strip() or "static"
            try:
                world = select_world(density, speed)
                subprocess.Popen([find_webots(), str(world)])
            except (OSError, ValueError) as exc:
                print(f"  Simulasyon baslatilamadi: {exc}")
                continue
            print("  Webots baslatildi.")

        elif secim == "2":
            print("\n  Algoritmalar: A*  |  Dijkstra  |  RRT")
            alg = input("  Secin: ").strip()
            if alg not in ("A*", "Dijkstra", "RRT"):
                print("  Gecersiz.")
                continue
            try:
                config = load_config()
                config['algorithm'] = alg
                save_config(config)
            except (OSError, ValueError) as exc:
                print(f'  Ayarlar kaydedilemedi: {exc}')
                continue
            print(f"  Algoritma '{alg}' olarak ayarlandi.")

        elif secim == "3":
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from analysis.analyze import main as analyze
            analyze([])

        elif secim == "0":
            break

if __name__ == "__main__":
    menu()

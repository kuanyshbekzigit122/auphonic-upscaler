import subprocess
import sys

print("========================================================")
print("  Auphonic AI Upscaler - Pushing to GitHub...")
print("========================================================")

try:
    subprocess.run(["git", "branch", "-M", "main"], check=True)
    result = subprocess.run(["git", "push", "-u", "origin", "main", "--force"])
    if result.returncode == 0:
        print("\n========================================================")
        print("  [SUCCESS] Kod GitHub-ka sattі zhukteldi!")
        print("========================================================")
    else:
        print("\n[!] Push toqtatyldy nemese qate boldy.")
except Exception as e:
    print(f"\n[ERROR] {e}")

input("\nShygu ushin Enter basynyz...")

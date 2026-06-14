"""Quick syntax check for all wallet-monitor-bot modules."""
import py_compile
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))

files = [
    "seed_wallets.py",
    "models.py",
    "config.py",
    "scorer.py",
    "alpha.py",
    "monitor.py",
    "bot.py",
]

ok = True
for f in files:
    path = os.path.join(BASE, f)
    try:
        py_compile.compile(path, doraise=True)
        print(f"  ✅ {f}")
    except py_compile.PyCompileError as e:
        print(f"  ❌ {f}: {e}")
        ok = False

print("\n" + ("ALL FILES OK ✅" if ok else "SOME FILES FAILED ❌"))
sys.exit(0 if ok else 1)
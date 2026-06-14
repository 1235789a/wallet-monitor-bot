"""Integration test: verify all modules import correctly with DB init."""
import sys
import os

# CD to the bot directory so imports work
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("1. Testing config import...")
from config import *
print("   ✅ Config imported")

print("2. Testing models import (DB init)...")
from models import init_db
init_db()
print("   ✅ Models imported + DB initialized")

# Check new tables exist
from models import get_conn
conn = get_conn()
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for t in ["smart_wallets", "token_heat", "daily_digest"]:
    assert t in tables, f"Table {t} not found!"
    print(f"   ✅ Table '{t}' exists")
conn.close()

print("3. Testing scorer import...")
from scorer import calculate_score, compute_win_rate, compute_avg_roi, estimate_score_from_onchain
# Quick smoke test
result = calculate_score(win_rate=0.8, avg_roi=0.5, avg_hold_hours=10, large_tx_ratio=0.3, tx_count_7d=15, unique_tokens=5)
assert 0 <= result <= 100
print(f"   ✅ Scorer imported (test score={result})")

print("4. Testing alpha.py import...")
from alpha import AlphaAggregator
agg = AlphaAggregator()
print("   ✅ AlphaAggregator created")

print("5. Testing monitor.py import...")
from monitor import scan_all_chains, scan_smart_money, format_alert, format_smart_alert
print("   ✅ Monitor imported")

print("6. Testing seed_wallets.py import...")
from seed_wallets import SEED_WALLETS, seed_database
print(f"   ✅ Seed wallets imported ({len(SEED_WALLETS)} wallets)")

print("\n🎉 ALL INTEGRATION TESTS PASSED")
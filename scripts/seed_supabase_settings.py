"""One-click seed script to populate Supabase system_settings from current local env."""

import sys
from bot_app.storage.supabase import is_supabase_configured, supabase_get
from bot_app.services.settings import _get_default_settings, save_system_settings


def main():
    if not is_supabase_configured():
        print("❌ Supabase is not configured in .env (SUPABASE_URL or SUPABASE_KEY missing).")
        sys.exit(1)

    print("🔍 Testing Supabase connection...")
    rows = supabase_get("system_settings", {"select": "key"})
    if rows is None:
        print("❌ Could not connect to Supabase system_settings table.")
        print("💡 Please make sure the table exists and run in Supabase SQL Editor:")
        print("   ALTER TABLE system_settings DISABLE ROW LEVEL SECURITY;")
        sys.exit(1)

    print(f"📦 Current keys in DB: {[r.get('key') for r in rows]}")
    defaults = _get_default_settings()

    print("🚀 Seeding local configurations to Supabase...")
    saved = save_system_settings(defaults, updated_by="SeedScript")
    print("✅ Successfully seeded settings to Supabase:")
    print(f"   - Servers: {len(saved.get('servers', []))} configured")
    print(f"   - Payment Phones: {saved.get('payment_phones')}")
    print(f"   - Plans: {list(saved.get('plans', {}).keys())}")
    print(f"   - OCR API Key: {saved.get('ocr_api_key')[:4]}***")
    print(f"   - Required Channel: {saved.get('required_channel') or '(None)'}")
    print("\n🎉 Supabase is now fully populated! You can now safely remove these from .env.")


if __name__ == "__main__":
    main()

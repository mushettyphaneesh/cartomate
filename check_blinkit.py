import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

def main():
    profile_dir = Path("./browser_profile").resolve()
    lat = float(os.environ.get("BLINKIT_LAT", "12.9116"))
    lng = float(os.environ.get("BLINKIT_LNG", "77.6370"))
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 800},
            geolocation={"latitude": lat, "longitude": lng},
            permissions=["geolocation"],
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        page = context.pages[0] if context.pages else context.new_page()
        print("Navigating to blinkit.com...")
        page.goto("https://blinkit.com", wait_until="domcontentloaded", timeout=30000)
        
        print("Current URL:", page.url)
        print("Page Title:", page.title())
        
        # Take a screenshot to see the exact state
        page.screenshot(path="blinkit_state.png")
        print("Screenshot saved to blinkit_state.png")
        
        # Check if login input or search input exists
        search_inputs = page.query_selector_all("input")
        print(f"Found {len(search_inputs)} input elements:")
        for idx, inp in enumerate(search_inputs):
            print(f"[{idx}] name={inp.get_attribute('name')}, placeholder={inp.get_attribute('placeholder')}, type={inp.get_attribute('type')}, id={inp.get_attribute('id')}, class={inp.get_attribute('class')}")
            
        context.close()

if __name__ == "__main__":
    main()

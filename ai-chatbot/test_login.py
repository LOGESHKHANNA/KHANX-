import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        # Listen for console logs
        page.on("console", lambda msg: print(f"Browser Console: {msg.type}: {msg.text}"))
        page.on("pageerror", lambda err: print(f"Browser Error: {err}"))
        
        # Go to the login page with a mockup hash containing an access token
        # This will trigger the DOMContentLoaded event from supabase
        mock_hash = "#access_token=fake_token&expires_in=3600&provider_token=fake_provider_token&refresh_token=fake_refresh_token&token_type=bearer"
        print("Navigating to login page with mock OAuth hash...")
        
        # intercepting requests to mock supabase if needed, but let's just see errors first
        await page.goto("http://127.0.0.1:8000/login" + mock_hash)
        
        await asyncio.sleep(2)  # Wait for JS to execute
        
        # Dump localStorage to see if session was saved
        session = await page.evaluate("localStorage.getItem('khanx_session')")
        print(f"Session in localStorage: {session}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

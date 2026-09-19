import os
import time
from playwright.sync_api import sync_playwright

# ============================================================
# LOAD CREDENTIALS SECURELY FROM GITHUB SECRETS
# ============================================================
raw_emails = os.environ.get("ALL_EMAILS", "")
email_password = os.environ.get("ACCOUNT_PASSWORD", "")

ALL_EMAILS = [e.strip() for e in raw_emails.replace(",", " ").split() if e.strip()]

if not ALL_EMAILS:
    raise ValueError("ERROR: No emails found in 'ALL_EMAILS' secret! Please configure GitHub Secrets.")

# ============================================================
# TEST MODE LIMIT: Runs only the first 2 accounts
# Remove '[:2]' below when ready for production!
# ============================================================
ALL_EMAILS = ALL_EMAILS[:2]

ACCOUNTS = [{"email": email, "password": email_password} for email in ALL_EMAILS]
TARGET_BATCH_SIZE = 5


def check_login_failed(page):
    try:
        error_texts = [
            "Email does not exist!",
            "Email does not exist",
            "Invalid email or password",
            "User not found",
            "Password is incorrect",
            "Please enter a valid email address"
        ]
        for frame in page.frames:
            for txt in error_texts:
                element = frame.get_by_text(txt, exact=False)
                if element.count() > 0 and element.first.is_visible():
                    return True
    except Exception:
        pass
    return False


def dismiss_initial_popups(page):
    """Dismisses promotional modals ('GPT Image 2.5', 'SEEDANCE', 'WAN 3.0') on /earn-credits."""
    page.wait_for_timeout(2000)

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    except Exception:
        pass

    try:
        page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll('button, div, span, svg, i, a'));
            for (let b of buttons) {
                const txt = b.textContent ? b.textContent.trim() : '';
                const aria = b.getAttribute('aria-label') || '';
                if ((txt === '×' || txt === 'x' || txt === 'X' || aria.toLowerCase().includes('close')) && b.offsetWidth > 0 && b.offsetHeight > 0) {
                    b.click();
                }
            }
        }""")
        page.wait_for_timeout(1000)
    except Exception:
        pass

    try:
        page.evaluate("""() => {
            const badPhrases = ['gpt image 2.5', 'seedance', 'wan 3.0', "what's new", 'celebrity twin finder'];
            const allDivs = Array.from(document.querySelectorAll('div, section, dialog, [role="dialog"]'));
            
            allDivs.forEach(el => {
                const txt = el.textContent ? el.textContent.toLowerCase() : '';
                if (badPhrases.some(p => txt.includes(p)) && !txt.includes('watch ad to earn credits')) {
                    let container = el;
                    for (let i = 0; i < 8; i++) {
                        if (!container || container === document.body) break;
                        const style = window.getComputedStyle(container);
                        if (style.position === 'fixed' || style.position === 'absolute' || container.getAttribute('role') === 'dialog') {
                            container.remove();
                            break;
                        }
                        container = container.parentElement;
                    }
                }
            });

            const overlays = document.querySelectorAll('[class*="backdrop"], [class*="overlay"], [class*="mask"]');
            overlays.forEach(o => o.remove());
        }""")
        page.wait_for_timeout(500)
    except Exception:
        pass


def is_ad_player_open(page):
    """Checks if an actual ad overlay or video frame is currently open on the page."""
    try:
        for frame in page.frames:
            if frame.get_by_text("Close", exact=True).is_visible() or \
               frame.get_by_text("Advertisement", exact=False).is_visible() or \
               frame.locator("text=/^close$/i").is_visible():
                return True
        return page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('*'));
            return els.some(el => 
                el.children.length === 0 && 
                (el.textContent.trim().toLowerCase() === 'close' || el.textContent.includes('Advertisement')) && 
                el.offsetWidth > 0 && el.offsetHeight > 0
            );
        }""")
    except Exception:
        return False


def click_watch_ad(page):
    """Clears popups, scrolls to 'Watch ad to earn credits', clicks 'Go Now', and verifies ad opens."""
    for attempt in range(3):
        dismiss_initial_popups(page)
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(1000)

        try:
            card = page.locator("div").filter(has_text="Watch ad to earn credits")
            btn = card.get_by_text("Go Now").last
            if btn.is_visible():
                btn.scroll_into_view_if_needed()
                btn.click(force=True)
                page.wait_for_timeout(3000)
                if is_ad_player_open(page):
                    return True
        except Exception:
            pass

        try:
            clicked = page.evaluate("""() => {
                const allElements = Array.from(document.querySelectorAll('*'));
                const watchAdTitle = allElements.find(el =>
                    el.children.length === 0 && el.textContent.includes('Watch ad to earn credits')
                );
                if (!watchAdTitle) return false;

                let card = watchAdTitle;
                while (card && card.parentElement && !card.textContent.includes('10 ads/day')) {
                    card = card.parentElement;
                }
                if (!card) card = watchAdTitle.closest('div');
                if (!card) return false;

                const goNowBtn = Array.from(card.querySelectorAll('*')).find(el =>
                    el.textContent.trim().toLowerCase().includes('go now')
                );

                if (!goNowBtn) return false;
                goNowBtn.scrollIntoView({ behavior: 'instant', block: 'center' });
                goNowBtn.click();
                return true;
            }""")
            page.wait_for_timeout(3000)
            if clicked and is_ad_player_open(page):
                return True
        except Exception:
            pass

    return False


def check_daily_limit_reached(page):
    try:
        limit_text = "You have used all your ad watch opportunities for today"
        for frame in page.frames:
            element = frame.get_by_text(limit_text, exact=False)
            if element.count() > 0 and element.first.is_visible():
                return True
    except Exception:
        pass
    return False


def try_click_close(page):
    try:
        clicked = page.evaluate("""() => {
            const allElements = Array.from(document.querySelectorAll('*'));
            const closeEl = allElements.find(el => 
                el.children.length === 0 && 
                el.textContent.trim().toLowerCase() === 'close' &&
                el.offsetWidth > 0 && el.offsetHeight > 0
            );
            if (closeEl) {
                closeEl.click();
                return true;
            }
            return false;
        }""")
        if clicked:
            return True
    except Exception:
        pass

    for frame in page.frames:
        locators = [
            frame.get_by_text("Close", exact=True),
            frame.locator("text=/^close$/i"),
            frame.locator("span:has-text('Close')"),
            frame.locator("div:has-text('Close')"),
            frame.locator("button:has-text('Close')")
        ]
        for loc in locators:
            try:
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(force=True)
                    return True
            except Exception:
                pass
    return False


def try_click_ok(page):
    try:
        clicked = page.evaluate("""() => {
            const allElements = Array.from(document.querySelectorAll('*'));
            const okBtn = allElements.find(el => 
                (el.tagName === 'BUTTON' || el.tagName === 'DIV' || el.tagName === 'SPAN') &&
                el.textContent.trim().toLowerCase() === 'ok' &&
                el.offsetWidth > 0 && el.offsetHeight > 0
            );
            if (okBtn) {
                okBtn.click();
                return true;
            }
            return false;
        }""")
        if clicked:
            return True
    except Exception:
        pass

    for frame in page.frames:
        locators = [
            frame.get_by_role("button", name="OK"),
            frame.get_by_text("OK", exact=True),
            frame.locator("button:has-text('OK')"),
            frame.locator("div[role='dialog'] button")
        ]
        for loc in locators:
            try:
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(force=True)
                    return True
            except Exception:
                pass
    return False


def process_single_account(page, account):
    email = account["email"]
    password = account["password"]

    print(f"--- Logging into: {email} ---")
    page.goto("https://easemate.ai/Dashboard", wait_until="load")
    page.wait_for_timeout(3000)

    page.get_by_text("Log In", exact=True).first.click()
    page.wait_for_timeout(1000)

    try:
        email_option = page.get_by_text("Continue with Email", exact=True)
        if email_option.is_visible():
            email_option.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass

    page.wait_for_selector("input[placeholder='Enter your email address']")
    page.fill("input[placeholder='Enter your email address']", email)
    page.fill("input[placeholder='Enter your Password']", password)
    page.get_by_role("button", name="Log in").last.click()
    page.wait_for_timeout(3500)

    if check_login_failed(page):
        print(f"[{email}] LOGIN FAILED: 'Email does not exist' or invalid credentials detected!")
        return "INVALID_ACCOUNT"

    print(f"[{email}] Navigating to Earn Credits page...")
    page.goto("https://easemate.ai/earn-credits", wait_until="load")
    page.wait_for_timeout(3000)

    dismiss_initial_popups(page)

    if check_daily_limit_reached(page):
        print(f"[{email}] LIMIT DETECTED: Account has used all ad opportunities for today!")
        return "LIMIT_REACHED"

    print(f"[{email}] Starting ad task...")
    if not click_watch_ad(page):
        print(f"[{email}] ERROR: Could not click 'Go Now'. Skipping...")
        return "ERROR"

    page.wait_for_timeout(2000)
    if check_daily_limit_reached(page):
        print(f"[{email}] LIMIT DETECTED: 'You have used all your ad watch opportunities for today.'")
        return "LIMIT_REACHED"

    # --- WATCH AD FOR 35 SECONDS BEFORE CLOSING ---
    print(f"[{email}] Ad opened! Watching video ad for 35 seconds...")
    time.sleep(35)

    print(f"[{email}] Closing ad player...")
    ad_closed = False
    for _ in range(6):
        if try_click_close(page):
            print(f"[{email}] Ad closed successfully.")
            ad_closed = True
            break
        page.wait_for_timeout(1500)

    if not ad_closed:
        print(f"[{email}] Warning: Close button not found.")

    page.wait_for_timeout(2000)

    print(f"[{email}] Claiming reward...")
    reward_claimed = False
    for _ in range(6):
        if try_click_ok(page):
            print(f"[{email}] SUCCESS: Reward claimed!")
            reward_claimed = True
            break
        page.wait_for_timeout(1500)

    if not reward_claimed:
        print(f"[{email}] Warning: OK button not found.")

    return "SUCCESS"


def run_all_accounts():
    os.makedirs("videos", exist_ok=True)
    remaining_pool = list(ACCOUNTS)
    active_batch = []

    while remaining_pool and len(active_batch) < TARGET_BATCH_SIZE:
        active_batch.append(remaining_pool.pop(0))

    cycle_count = 1
    current_idx = 0

    with sync_playwright() as p:
        print(f"Total Accounts Loaded: {len(ACCOUNTS)}")
        
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        while active_batch:
            if current_idx >= len(active_batch):
                current_idx = 0
                cycle_count += 1
                print("\n" + "=" * 60)
                print(f"   STARTING CYCLE {cycle_count} ACROSS CURRENT {len(active_batch)} ACTIVE ACCOUNTS")
                print("=" * 60)

            account = active_batch[current_idx]
            print(f"\n[Cycle {cycle_count} | Slot {current_idx + 1}/{len(active_batch)}] Account: {account['email']}")

            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                record_video_dir="videos/",
                record_video_size={"width": 1920, "height": 1080}
            )
            page = context.new_page()

            try:
                status = process_single_account(page, account)
            except Exception as e:
                print(f"Error executing {account['email']}: {e}")
                status = "ERROR"

            context.close()

            if status in ["LIMIT_REACHED", "INVALID_ACCOUNT"]:
                reason = "invalid email" if status == "INVALID_ACCOUNT" else "limit reached"
                print(f"--> [REMOVING ACCOUNT] {account['email']} ({reason}). Dropping from active batch.")
                active_batch.pop(current_idx)

                if remaining_pool:
                    new_acc = remaining_pool.pop(0)
                    print(f"--> [ADDING NEW ACCOUNT] Pulled {new_acc['email']} into slot {current_idx + 1}.")
                    active_batch.insert(current_idx, new_acc)
                else:
                    print(f"--> Pool empty. Active batch size reduced to {len(active_batch)}.")
            else:
                current_idx += 1
                time.sleep(1)

        print("\n" + "=" * 60)
        print("ALL VALID ACCOUNTS HAVE COMPLETED THEIR PROCESS!")
        print("=" * 60)
        browser.close()


if __name__ == "__main__":
    run_all_accounts()

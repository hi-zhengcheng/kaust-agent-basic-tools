from playwright._impl._page import Page
from playwright._impl._browser_context import BrowserContext
from config import config
import re
import asyncio
from playwright.async_api import Locator

import base64
import json
from typing import Literal, Optional


async def highlight_element(locator: Locator, duration: int = 600, interval: int = 250):
    """
    Highlight an element by always showing a red border (via box-shadow),
    and blinking only the scale transform.
    - locator: playwright Locator
    - duration: total highlight time in ms (default 1000ms)
    - interval: scale toggle interval in ms (default 250ms)
    """
    await locator.wait_for(state="visible")

    await locator.evaluate(
        """(el, {duration, interval}) => {
            const originalTransform = el.style.transform;
            const originalTransition = el.style.transition;
            const originalBoxShadow = el.style.boxShadow;

            el.style.transition = "all 0.25s ease-in-out";
            // Always show red border effect (works for <li> too)
            el.style.boxShadow = "0 0 0 3px red";

            let scaledUp = false;
            const blink = setInterval(() => {
                if (scaledUp) {
                    el.style.transform = "scale(1)";
                } else {
                    el.style.transform = "scale(1.1)";
                }
                scaledUp = !scaledUp;
            }, interval);

            setTimeout(() => {
                clearInterval(blink);
                el.style.transform = originalTransform;
                el.style.transition = originalTransition;
                // el.style.boxShadow = originalBoxShadow;
            }, duration);
        }""",
        {"duration": duration, "interval": interval},
    )

    # Wait so highlight fully completes
    await asyncio.sleep(duration / 1000 + 0.1)


async def capture_and_push_screenshot(
    page: Page,
    answer_queue: asyncio.Queue,
    *,
    user: str = "user123",
    # "png" gives lossless; "jpeg" is smaller. Use "jpeg" + quality for bandwidth.
    fmt: Literal["png", "jpeg"] = "png",
    quality: Optional[int] = None,     # only used for jpeg (1-100)
    as_data_url: bool = True,          # True → send "data:image/...;base64,..." ; False → raw base64
) -> None:
    """
    Take a screenshot from the given Playwright page and push it to Redis as:
      {"type": "SCREENSHOT", "user": <user>, "message": <data-url-or-base64>}
    """
    # 1) Take screenshot (returns bytes if no 'path' given)
    shot_bytes = await page.screenshot(type=fmt, quality=quality if fmt == "jpeg" else None)

    # 2) Convert to base64 (string)
    b64 = base64.b64encode(shot_bytes).decode("ascii")

    # 3) Wrap as data URL if desired
    mime = f"image/{fmt}"
    message = f"data:{mime};base64,{b64}" if as_data_url else b64

    payload = {
        "type": "SCREENSHOT",
        "user": user,
        "message": message,
    }

    # 4) Push to Redis list (left-push so newest is at the head)
    await answer_queue.put(json.dumps(payload))


async def push_status_msg(
    msg: str,
    answer_queue: asyncio.Queue,
    *,
    user: str = "user123",
) -> None:

    payload = {
        "type": "STATUS",
        "user": user,
        "message": str,
    }
    await answer_queue.put(json.dumps(payload))


async def login(page: Page, r: asyncio.Queue) -> None:
    url = "https://portal.kaust.edu.sa"

    # Step 1: Navigate to URL
    await page.goto(url, wait_until='networkidle', timeout=12000)
    print(f"✅ Successfully navigated to {url}")
    await capture_and_push_screenshot(page, r)

    # Step 2: Wait for username and password fields
    username = page.locator('input[placeholder="KAUST Username"]')
    password = page.locator('input[placeholder="Password"]')
    await username.wait_for(timeout=60000)
    await password.wait_for(timeout=60000)

    # Step 3: Fill login credentials with highlight
    await highlight_element(username)
    await username.fill(config['name'])

    await highlight_element(password)
    await password.fill(config['passwd'])
    await capture_and_push_screenshot(page, r)

    sign_in_btn = page.locator('div >> span:has-text("Sign in")')
    await highlight_element(sign_in_btn)
    await sign_in_btn.click()
    print("🔐 Submitted login form.")

    # Step 4: Handle Duo 2FA
    iframe_element = await page.wait_for_selector('iframe#duo_iframe', timeout=60000)
    duo_frame = await iframe_element.content_frame()
    if not duo_frame:
        raise Exception("❌ Failed to get Duo iframe content.")

    try:
        duo_btn = duo_frame.locator('button:has-text("Send Me a Push")')
        await duo_btn.wait_for(timeout=60000)
        await highlight_element(duo_btn)
        await duo_btn.click()
        print("📲 Clicked 'Send Me a Push' inside Duo iframe.")
        await capture_and_push_screenshot(page, r)

        # Step 5: Wait for navigation after Duo approval
        print("⏳ Waiting for user to approve Duo push...")
        await page.wait_for_load_state("networkidle", timeout=120000)
        print("✅ Duo approval successful")
    except:
        print("ℹ️ No Duo 2FA required this time — continuing.")

    await page.wait_for_url("**/site#workzone-home&/home")
    await page.wait_for_load_state("networkidle")
    print("Login complete.")
    await capture_and_push_screenshot(page, r)


async def open_hr_connect(page: Page, context: BrowserContext, r: asyncio.Queue) -> Page:
    iframe_element = await page.wait_for_selector('iframe#__container1', timeout=60000)
    frame = await iframe_element.content_frame()
    if not frame:
        raise Exception("❌ Could not access HR iframe content.")

    hr_span = frame.locator("span", has_text=re.compile(r"^\s*HR\s*$", re.IGNORECASE))
    hr_li = hr_span.locator('..').locator('..')
    await highlight_element(hr_li)
    await capture_and_push_screenshot(page, r)
    await hr_li.hover()

    hrcon_span = frame.locator("span", has_text=re.compile(r"^\s*HR Connect\s*$", re.IGNORECASE))
    hrcon_li = hrcon_span.locator('..').locator('..')
    await hrcon_li.wait_for(state="visible", timeout=10000)
    print("HR Connect visible now")
    await capture_and_push_screenshot(page, r)

    async with context.expect_page() as new_page_info:
        await highlight_element(hrcon_li)
        await capture_and_push_screenshot(page, r)
        await hrcon_li.click()
    new_tab = await new_page_info.value
    await new_tab.wait_for_load_state("networkidle")
    await capture_and_push_screenshot(new_tab, r)
    return new_tab

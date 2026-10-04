import asyncio
import json
import re
from playwright.async_api import async_playwright, expect, TimeoutError as PlaywrightTimeoutError

from common_ops import open_hr_connect, highlight_element, capture_and_push_screenshot, push_status_msg
from config import config


# async def capture_and_push_screenshot(*argc, **argv):
#     pass


async def scroll_into_view(element):
    await element.evaluate("el => el.scrollIntoView({ behavior: 'instant', block: 'center' })")


async def dcpw_login(page, r):
    url = "https://dcwp.kaust.edu.sa/"

    await page.goto(url, wait_until='networkidle', timeout=12000)
    print(f"✅ Successfully navigated to {url}")

    username = page.locator('input[placeholder="KAUST User Name"]')
    password = page.locator('input[placeholder="Password"]')
    await username.wait_for(timeout=60000)
    await password.wait_for(timeout=60000)

    await highlight_element(username)
    await username.fill(config['name'])

    await highlight_element(password)
    await password.fill(config['passwd'])
    await capture_and_push_screenshot(page, r)

    button = page.locator("#submitLogin")
    await button.wait_for(timeout=60000)
    await highlight_element(button)
    await button.click()


    # Handle Duo 2FA
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
    except Exception as e:
        print("ℹ️ No Duo 2FA required this time — continuing." + str(e))
    await page.wait_for_url("**/Home/Index")
    await page.wait_for_load_state("networkidle")
    print("Login complete.")
    # await capture_and_push_screenshot(page, r)


async def add_one_room(page, r, building_name, level, room):
    button = page.locator('a.k-button.k-grid-add', has_text='New Location/Room')
    await button.wait_for(state='visible')
    await scroll_into_view(button)
    await capture_and_push_screenshot(page, r)
    await button.click()
    await asyncio.sleep(1)

    input_box = page.locator('input[name="BuildingName_input"]')
    await input_box.fill(building_name)
    await input_box.blur()
    async with page.expect_response(lambda r: 'Requests/GetBuildingLevels' in r.url and r.status == 200):
        print("Get Building Level")
    print("OK1")


    input_box = page.locator('input[name="BuildingLevel_input"]')
    await input_box.fill(str(level))
    await input_box.blur()
    # await page.mouse.click(0, 0)
    async with page.expect_response(lambda r: 'Requests/GetBuildingRooms' in r.url and r.status == 200):
        print("Get Building Room")
    print("OK1")

    input_box = page.locator('input[name="Room_input"]')
    await input_box.fill(room)
    await input_box.blur()

    save_button = page.locator('a.k-button.k-grid-update', has_text='Save')
    count = await save_button.count()
    assert count == 1, f"Expected 1 Save button, found {count}"
    await capture_and_push_screenshot(page, r)
    await save_button.click()
    await asyncio.sleep(1)
    await capture_and_push_screenshot(page, r)



async def add_man_power(page, r, kaustID):
    button = page.locator('a.k-button.k-grid-add', has_text='Add Manpower Detail')
    await scroll_into_view(button)
    await button.click()
    await asyncio.sleep(1)


    input_box = page.locator('input#KaustId')
    await input_box.fill(kaustID)
    await input_box.blur()
    # await page.mouse.click(0, 0)
    async with page.expect_response(lambda r: 'home/AllEmployeeKidsDetail' in r.url and r.status == 200):
        print("Get employee detail")
    print("OK1")
    await capture_and_push_screenshot(page, r)


    save_button = page.locator('a.k-button.k-grid-update', has_text='Save')
    count = await save_button.count()
    assert count == 1, f"Expected 1 Save button, found {count}"
    await save_button.click()
    await asyncio.sleep(1)
    await capture_and_push_screenshot(page, r)


def build_tool_dcwp(r: asyncio.Queue):
    async def request_data_center_work_permit() -> None:
        r"""Submit one request for data center work permit (dcwp)."""
        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                context = await browser.new_context()
                page = await context.new_page()

                await dcpw_login(page, r)


                button = page.locator('a.btn.btn-primary.btn-block.btn-lg', has_text='Add New DCWP Request')
                await button.wait_for(timeout=60000)
                await capture_and_push_screenshot(page, r)
                await button.click()
                await page.wait_for_url("**/DCWP/Requests/Create")
                await page.wait_for_load_state("networkidle")



                input_box = page.locator('input#RequesterKaustId')
                await input_box.wait_for(state='visible')
                await input_box.fill('103708')
                await input_box.blur()
                name_input = page.locator('#RequesterFirstName')
                await expect(name_input).to_have_value(re.compile(".+"))


                await page.locator('input#RequesterCompany').fill('KAUST')


                dropdown = page.locator('#Duration')
                await dropdown.wait_for(state='visible')
                await dropdown.select_option('7')
                await asyncio.sleep(1)

                await capture_and_push_screenshot(page, r)

                await add_one_room(page, r, 'Building-14 (BDC)', 3, 'R-315 HDR')
                await add_one_room(page, r, 'Building-14 (BDC)', 3, 'R-316 MDR')


                checkbox = page.locator("#IsColdWork")
                await checkbox.wait_for()
                await scroll_into_view(checkbox)
                await checkbox.check()
                await asyncio.sleep(0.5)
                await capture_and_push_screenshot(page, r)


                input_box = page.locator('input#ProponentKaustId')
                await scroll_into_view(input_box)
                await input_box.fill('121919')
                await input_box.blur()
                # await page.mouse.click(0, 0)
                async with page.expect_response(lambda r: 'home/EmployeeHRDetail' in r.url and r.status == 200):
                    print("Get employee detail")
                print("OK1")
                await capture_and_push_screenshot(page, r)


                textarea = page.locator('textarea#JobDescription')
                await scroll_into_view(textarea)
                await textarea.fill('GPU Nodes Config')
                await textarea.blur()
                await capture_and_push_screenshot(page, r)


                await add_man_power(page, r, '103708')
                await add_man_power(page, r, '104167')

                # button = page.locator('button.btn.btn-success', has_text='Create Request')
                # count = await button.count()
                # assert count == 1, f"Expected 1 'Create Request' button, found {count}"
                # await scroll_into_view(button)
                # await button.click()

                # await asyncio.sleep(60000)

                # Create a future that resolves when the page closes
                close_future = asyncio.get_event_loop().create_future()

                def on_close():
                    print("Page closed by user!")
                    if not close_future.done():
                        close_future.set_result(True)

                page.on("close", on_close)
                await close_future

                return "Success"

        except PlaywrightTimeoutError as e:
            print(f"❌ Timeout occurred: {e}")
            return f"❌ Timeout occurred: {e}"
        except Exception as e:
            print(f"❌ Error: {e}")
            return f"❌ Error: {e}"
        finally:
            try:
                if browser:
                    await browser.close()
            except:
                pass

    return request_data_center_work_permit

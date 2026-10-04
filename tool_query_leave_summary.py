import asyncio
import json
import re
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from common_ops import login, open_hr_connect, highlight_element, capture_and_push_screenshot


def build_tool_query_leave_summary(r: asyncio.Queue):
    async def query_leave_summary() -> str:
        r"""query the holiday information.

        This function queries the HR system for the current user
        and returns a summary of the available leave and flexible working
        balances. The result includes various categories such as annual leave, remote
        working (in and out of KSA), flexible working hours, and other entitlements.


        Returns:
            str:  a json string containing a dictionary containing the user's leave and time balances with
                the following keys:
                - "Annual Leave" (str): e.g., "12.15 days"
                - "Additional Remote Working" (str): e.g., "0 days"
                - "Remote Working (in Kingdom)" (str): e.g., "22 days"
                - "Remote Working (out of KSA)" (str): e.g., "22 days"
                - "Flexible Working" (str): e.g., "160:00 hours"
                - "Time Off in Lieu" (str): e.g., "00:00 hours"
                - "Recognition Award" (str): e.g., "0 days"
        """

        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                await login(page, r)
                new_tab = await open_hr_connect(page, context, r)

                # Step 7: Click "Leave, Remote, and Flex"
                hosts = new_tab.locator("ui5-busy-indicator")
                host_count = await hosts.count()
                print("Found", host_count, "ui5-busy-indicator hosts")
                if host_count == 0:
                    raise Exception("❌ No shadow host found")

                target_link = None
                for i in range(host_count):
                    if await hosts.nth(i).inner_text() == "Leave, Remote, and Flex":
                        target_link = hosts.nth(i)
                        break
                if not target_link:
                    raise Exception("❌ Didn't find 'Leave, Remote, and Flex' link")

                await highlight_element(target_link)
                await capture_and_push_screenshot(new_tab, r)
                await target_link.click()
                await new_tab.wait_for_load_state("networkidle", timeout=120000)

                # Step 8: Click "Show All Balances"
                show_balances_btn = new_tab.locator("#idEssContainer---main--showAllBalancesButton")
                await new_tab.wait_for_selector("#idEssContainer---main--showAllBalancesButton", timeout=60000)

                await highlight_element(show_balances_btn)
                await capture_and_push_screenshot(new_tab, r)
                await show_balances_btn.click()
                print("🟢 Clicked 'Show All Balances' button")
                await new_tab.wait_for_load_state("networkidle", timeout=120000)

                # Step 9: Read leave balance information
                vocation_info = {}
                await new_tab.wait_for_selector("#idEssContainer---main--timeTypeBalanceTable-listUl tbody tr", timeout=20000)
                await asyncio.sleep(1)
                rows = new_tab.locator("#idEssContainer---main--timeTypeBalanceTable-listUl tbody tr")
                row_count = await rows.count()

                print("Found", row_count, "rows")
                for i in range(row_count):
                    time_type = await rows.nth(i).locator("td:nth-of-type(2) span").inner_text()
                    available = await rows.nth(i).locator("td:nth-of-type(3) span").inner_text()
                    vocation_info[time_type.strip()] = available.strip()

                print("💼 Time-type balances:", vocation_info)
                await highlight_element(new_tab.locator("#idEssContainer---main--timeTypeBalanceTable-listUl tbody"))
                await asyncio.sleep(1)
                await capture_and_push_screenshot(new_tab, r)
                return json.dumps(vocation_info, indent=2)

        except PlaywrightTimeoutError as e:
            print(f"❌ Timeout occurred: {e}")
            return f"❌ Timeout occurred: {e}"
        except Exception as e:
            print(f"❌ Error: {e}")
            return f"❌ Error: {e}"
        finally:
            if browser:
                await browser.close()

    return query_leave_summary



if __name__ == '__main__':


    async def consumer(queue: asyncio.Queue, producer_task):
        while True:
            if not queue.empty():
                item = await queue.get()
                print(f"{item}")
                continue

            if producer_task.done():
                break

            await asyncio.sleep(0.05)


    async def main():
        answer_queue = asyncio.Queue()
        producer_task = asyncio.create_task(build_tool_query_leave_summary(answer_queue)())
        consumer_task = asyncio.create_task(consumer(answer_queue, producer_task))

        p_result, c_result = await asyncio.gather(producer_task, consumer_task)
        print(f'Final result: {p_result}')
        print(c_result)

    asyncio.run(main())
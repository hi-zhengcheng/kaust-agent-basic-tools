import asyncio
import json
import re
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from datetime import date, timedelta
from calendar import month_abbr
from datetime import datetime

from llama_index.llms.ollama import Ollama

from common_ops import login, open_hr_connect, highlight_element
from config import config


js_analyze_str = """
() => {
    const toast = document.createElement("div");
    toast.innerText = "🔍 Analyzing the page...";
    toast.style.position = "fixed";
    toast.style.bottom = "30px";
    toast.style.right = "30px";
    toast.style.padding = "12px 20px";
    toast.style.backgroundColor = "#333";
    toast.style.color = "#fff";
    toast.style.fontSize = "15px";
    toast.style.borderRadius = "8px";
    toast.style.boxShadow = "0 2px 8px rgba(0,0,0,0.2)";
    toast.style.opacity = "1";
    toast.style.transition = "opacity 1s ease-out";
    toast.style.zIndex = 99999;

    document.body.appendChild(toast);

    // Auto-fade and remove after 5 seconds
    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 1000);  // wait for transition to finish
    }, 5000);
}
"""


js_review_str = """
() => {
    const div = document.createElement("div");
    div.style.position = "fixed";
    div.style.top = "10px";
    div.style.left = "10px";
    div.style.padding = "15px 40px 15px 15px";
    div.style.backgroundColor = "yellow";
    div.style.fontSize = "16px";
    div.style.zIndex = 10000;
    div.style.border = "1px solid #aaa";
    div.style.borderRadius = "8px";
    div.style.boxShadow = "0 2px 5px rgba(0,0,0,0.2)";
    div.style.maxWidth = "400px";

    // Message text
    const message = document.createElement("span");
    message.innerText = "✅ Please review and submit manually, then close the browser.";
    div.appendChild(message);

    // Close button
    const closeBtn = document.createElement("span");
    closeBtn.innerText = "✖";  // Or use "❌"
    closeBtn.style.position = "absolute";
    closeBtn.style.top = "5px";
    closeBtn.style.right = "10px";
    closeBtn.style.cursor = "pointer";
    closeBtn.style.fontWeight = "bold";
    closeBtn.style.fontSize = "18px";
    closeBtn.onclick = () => div.remove();

    div.appendChild(closeBtn);
    document.body.appendChild(div);
}
"""



def estimate_input_fields(leave_description:str, time_types: list[str]) -> str:
    

    tomorrow_date = date.today() + timedelta(days=0)
    tomorrow_day_name = tomorrow_date.strftime("%A")
    tomorrow_str = f"{month_abbr[tomorrow_date.month]} {tomorrow_date.day:02d}, {tomorrow_date.year}"

    # my_reason = "I want to travel and italy is the target place. During the travel, I maybe not available to working meetings. After back from travel, I will catch up. I want to leave from October first. if the "
    hr_options = '\n'.join(time_types)

    prompt = f"""
A user needs to ask for leave for this reason:
{leave_description}.

In the HR system, there are following options:

{hr_options}

Help the user find which option should be chosen to ask for a leave in hr System. 
Please only answer the option name.

Also help writting a short Comment explaining the leave request based on above reason.

Based on the above reason, try to get the leave "start date", "end date", and "the number of days" if possible. 
If not possible, just anwser me with empth string "" or 0.
The format of "start date", "end date" should be "MMM dd, yyyy". e.g., "Sep 16, 2025". 

Today is: {tomorrow_str}. And tomorrow is {tomorrow_day_name}. The start date cannot be earlier than the date of today.

Finally, return one json string. the keys should include:
1. "option_name"
2. "start_date"
3. "end_date" 
5. "short_comment"

Make sure the result is json format and only return the json result without anything else.
"""

    print(f"the constructed prompt:\n{prompt}")

    # agent.clear_memory()
    # response = agent.step(prompt)
    # with_think = response.msgs[0].content

    llm = Ollama(model="llama3", base_url=config['ollama_base_url'], request_timeout=120.0, context_window=8000)
    with_think = llm.complete(prompt).text

    print(f"LLM raw response:\n{with_think}\n\n")

    without_think = re.sub(r"<think>.*?</think>\s*", "", with_think, flags=re.DOTALL | re.IGNORECASE)
    start, end = without_think.find("{"), without_think.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found after <think> block.")

    json_str = without_think[start:end+1]


    print(f"LLM response:\n{json_str}")
    json_result = json.loads(json_str)
    return json_result

def build_tool_create_leave_request(r: asyncio.Queue):
    async def create_leave_request(leave_description: str) -> str:
        r"""create a leave request in Portal system.

        This function help user to create a leave request in HR system or Portal system.


        Args:
            leave_description (str): the raw user description or request string which may contain the context information to create the leave request, e.g., reason of leave, start date, end date.

        Returns:
            str:  describe the result of creating the leave request.
        """

        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
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
                await target_link.click()
                await new_tab.wait_for_load_state("networkidle", timeout=120000)

                # Step 8: click "create request" button
                request_btn = new_tab.get_by_role("button", name="Create Request")
                await request_btn.wait_for(state="visible", timeout=60000)
                btn_count = await request_btn.count()
                if btn_count != 1:
                    raise Exception("❌ No 'Create Request' button found")

                await highlight_element(request_btn)
                await request_btn.click()

                await new_tab.evaluate(js_analyze_str)

                # Step 8: collect time type
                arrow = new_tab.locator("#__box1-arrow")
                await highlight_element(arrow)
                await arrow.click()

                items = new_tab.locator("ul[id$='-popup-list-listUl'][role='listbox']:visible li")
                count = await items.count()
                print(f"{count} Time Types")
                texts = []
                for i in range(count):
                    text = await items.nth(i).text_content()
                    if text:
                        texts.append(text.strip())
                print(texts)

                # Step 9: estimate input information using LLM
                json_result = estimate_input_fields(leave_description, texts)
                print(f"debug-json:\n{json_result}")

                # Step 10: select time type
                if "option_name" in json_result and json_result["option_name"]:
                    print(f'---debug--- option-name: {json_result["option_name"]}')
                    time_type = new_tab.get_by_role("option", name=json_result["option_name"])
                    btn_count = await time_type.count()
                    if btn_count == 0:
                        await highlight_element(arrow)
                        await arrow.click()
                        time_type = new_tab.get_by_role("option", name=json_result["option_name"])
                        await time_type.wait_for()
                        btn_count = await time_type.count()

                    print(f'---debug--- option-name: {json_result["option_name"]} : {btn_count}')
                    if btn_count != 1:
                        raise Exception("❌ No time type item found")

                    await highlight_element(time_type)
                    await time_type.click()

                # Step 11: start date
                if "start_date" in json_result and json_result["start_date"]:
                    start_input = new_tab.locator('[data-help-id="startDate"] input.sapMInputBaseInner')
                    await start_input.wait_for(state="visible")
                    await highlight_element(start_input)
                    await start_input.fill(json_result["start_date"])
                    await start_input.press("Enter")

                # Step 11: end date
                if ("start_date" in json_result and json_result["start_date"]) and ("end_date" not in json_result or not json_result["end_date"]):
                    dt = datetime.strptime(json_result["start_date"], "%b %d, %Y")
                    new_dt = dt + timedelta(days=4)
                    json_result["end_date"] = new_dt.strftime("%b %d, %Y")

                if "end_date" in json_result and json_result["end_date"]:
                    end_input = new_tab.locator('[data-help-id="endDate"] input.sapMInputBaseInner')
                    await end_input.wait_for(state="visible")
                    await highlight_element(end_input)
                    await end_input.fill(json_result["end_date"])
                    await end_input.press("Enter")

                # Step 13: Comment
                print(json_result)
                if "short_comment" in json_result and json_result["short_comment"]:
                    await asyncio.sleep(1)
                    comment_box = new_tab.locator('#__area0-inner')
                    await highlight_element(comment_box)
                    await comment_box.fill(json_result["short_comment"])
                    print("debug.......")

                print("✅ Form filled. Please review in the open browser and click 'Submit' manually.")
                await new_tab.evaluate(js_review_str)

                tab_closed_event = asyncio.Event()
                loop = asyncio.get_running_loop()

                def on_tab_close():
                    print("🧨 Tab closed by user.")
                    loop.call_soon_threadsafe(tab_closed_event.set)

                new_tab.on("close", on_tab_close)
                print("🕒 Waiting for user to close the browser...")
                await tab_closed_event.wait()

                return "Operation Finished."

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

    return create_leave_request


if __name__ == '__main__':
    leave_desc = "I want to travel and italy is the target place. During the travel, I maybe not available to working meetings. After back from travel, I will catch up. I want to leave from tomorrow."
    result = asyncio.run(build_tool_create_leave_request(asyncio.Queue())(leave_desc))
    print(result)

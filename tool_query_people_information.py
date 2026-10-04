import asyncio
import json
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import zlib
import base64

from common_ops import login, open_hr_connect, highlight_element, capture_and_push_screenshot, push_status_msg


org_chart_data = None


def convert_org_chart_to_mermaid(data):
    lines = ["graph TD"]
    visited = set()

    def format_node(person):
        """Generate Mermaid node ID and label"""
        name = person.get("displayName", "Unknown").replace('"', '')
        title = person.get("displayTitle", "No Title").replace('"', '')
        node_id = person.get("id", f"{name[:6]}_node").replace("-", "_")
        # label = f'{name}\n{title}'
        label = f'{name}<br/>{title}'
        return node_id, f'{node_id}["{label}"]'

    def traverse_up(person):
        """Recursively add supervisor chain"""
        if not person or "id" not in person:
            return None
        node_id, label = format_node(person)
        if node_id not in visited:
            lines.append(label)
            visited.add(node_id)
        supervisor = person.get("supervisorWorkProfile")
        if supervisor and "id" in supervisor:
            supervisor_id, sup_label = format_node(supervisor)
            if supervisor_id not in visited:
                lines.append(sup_label)
                visited.add(supervisor_id)
            lines.append(f"{supervisor_id} --> {node_id}")
            traverse_up(supervisor)

    def traverse_down(person):
        """Recursively add direct reports"""
        if not person or "id" not in person:
            return
        parent_id, parent_label = format_node(person)
        if parent_id not in visited:
            lines.append(parent_label)
            visited.add(parent_id)
        for child in person.get("directReports", []):
            child_id, child_label = format_node(child)
            if child_id not in visited:
                lines.append(child_label)
                visited.add(child_id)
            lines.append(f"{parent_id} --> {child_id}")
            traverse_down(child)

    traverse_up(data)
    traverse_down(data)
    return "\n".join(lines)


def generate_mermaid_link(mermaid_code) -> str:
    # The live editor expects a JSON object with a 'code' field.
    data = {"code": mermaid_code}
    json_data = json.dumps(data, separators=(',', ':'))

    # Compress the JSON string
    compressed_data = zlib.compress(json_data.encode("utf-8"), level=9)

    # Base64-encode the compressed data
    encoded_data = base64.urlsafe_b64encode(compressed_data).decode("ascii")

    url = f"https://mermaid.live/edit#pako:{encoded_data}"
    return url


# def open_mermaid_in_live_editor(mermaid_code: str):
#     # The live editor expects a JSON object with a 'code' field.
#     data = {"code": mermaid_code}
#     json_data = json.dumps(data, separators=(',', ':'))

#     # Compress the JSON string
#     compressed_data = zlib.compress(json_data.encode("utf-8"), level=9)

#     # Base64-encode the compressed data
#     encoded_data = base64.urlsafe_b64encode(compressed_data).decode("ascii")

#     url = f"https://mermaid.live/edit#pako:{encoded_data}"
    
#     print(f"Generated URL: {url}")


#     # using selenium
#     options = Options()
#     options.add_experimental_option("detach", True) # This is the key setting
#     # options.add_experimental_option("keep_alive", True)

#     driver = webdriver.Chrome(options=options)
#     driver.get(url)

#     # using webbrowser
#     # try:
#     #     webbrowser.open(url, new=1)
#     #     print("Mermaid Live Editor opened in your default web browser.")
#     # except webbrowser.Error as e:
#     #     print(f"Error opening browser: {e}")
#     #     print("Please copy and paste the URL manually to view the diagram.")


def remove_keys_recursive(data, keys_to_remove):
    """
    Recursively remove keys from a dictionary or list of dictionaries.

    Args:
        data: The input data (dict or list).
        keys_to_remove: A set or list of keys to remove from all dicts.

    Returns:
        A new dict or list with specified keys removed.
    """
    if isinstance(data, dict):
        return {
            key: remove_keys_recursive(value, keys_to_remove)
            for key, value in data.items()
            if key not in keys_to_remove
        }
    elif isinstance(data, list):
        return [remove_keys_recursive(item, keys_to_remove) for item in data]
    else:
        return data


def build_tool_query_person_info(r: asyncio.Queue):
    async def query_person_info(query_name: str) -> str:
        r"""query the information of a person inside KAUST based on person's name.

        This function queries the KAUST HR system for the detailed information of a person by name.
        It returns a json string.

        Args:
            query_name (str): the name of the person to query

        Returns:
            str:  a json string containing the following detailed information of a person:
                - Full Name
                - Department
                - Local Time
                - Phone Number
                - Email
                - Organizational Chart
        """
        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                await login(page, r)
                new_tab = await open_hr_connect(page, context, r)

                # Step 7: query basic information
                await new_tab.wait_for_selector("xweb-shellbar-search-input")

                # Access the shadow DOM's input element
                input_element = await new_tab.locator("xweb-shellbar-search-input").evaluate_handle(
                    "el => el.shadowRoot.querySelector('input')"
                )
                input_el = input_element.as_element()

                # Highlight + fill
                await highlight_element(new_tab.locator("xweb-shellbar-search-input"))
                await capture_and_push_screenshot(new_tab, r)
                await input_el.fill(query_name)

                await new_tab.wait_for_selector("ui5-suggestion-item-custom-sf-header", timeout=5000)
                suggestions = new_tab.locator("ui5-suggestion-item-custom-sf-header")
                count = await suggestions.count()
                print(f"Number of suggestion items: {count}")

                if count == 0:
                    raise Exception("No result found")

                await capture_and_push_screenshot(new_tab, r)

                first_suggestion = suggestions.nth(0)
                await highlight_element(first_suggestion)
                await first_suggestion.click()

                # Wait for page update
                await new_tab.wait_for_load_state("networkidle")
                await new_tab.wait_for_timeout(3000)

                # ----------
                await capture_and_push_screenshot(new_tab, r)

                first_btn = new_tab.locator('[data-testid="userDisplayNameOpenPublicProfile"]').nth(1)
                await first_btn.wait_for(state="visible")
                await first_btn.click()

                await new_tab.wait_for_load_state("networkidle")
                await capture_and_push_screenshot(new_tab, r)

                locator = new_tab.locator('ui5-link-xweb-people-profile[href^="mailto:"]').nth(1)
                email = await locator.inner_text()
                print(email)


                locator = new_tab.locator(
                    'ui5-link-xweb-people-profile.IconDetails_itemContent__CrTIt[href^="tel:"]'
                )
                phone_text = None
                if await locator.count() > 0:
                    # Optionally ensure the first one is visible
                    first = locator.first
                    await first.wait_for(state="visible")
                    phone_text = await first.inner_text()
                print(f'phone: {phone_text}')


                locator = new_tab.locator(
                    "ui5-text-xweb-people-profile.ContextSwitcher_label__KvjJK"
                ).first
                await locator.wait_for(state="visible")
                title = await locator.inner_text()
                print("Title:", title)


                locator = new_tab.locator(
                    "ui5-text-xweb-people-profile.ContextSwitcher_label__KvjJK"
                ).nth(1)
                await locator.wait_for(state="visible")
                department = await locator.inner_text()
                print("department:", department)


                # Locate using unique testid
                locator = new_tab.locator(
                    'ui5-text-xweb-people-profile[data-testid="userDisplayName"]'
                ).nth(1)
                await locator.wait_for(state="visible")
                display_name = await locator.inner_text()
                print("User Display Name:", display_name)                


                button = new_tab.locator('ui5-button-xweb-people-profile[data-testid="openOrgChart"]')
                await button.wait_for(state="visible")
                async with new_tab.expect_response(lambda resp: "workforce/v1/workProfiles" in resp.url) as resp_info:
                    await button.click()
                response = await resp_info.value
                json_data = await response.json()
                keys_to_remove = [
                    "assignmentTag",
                    "isPrimary",
                    "workerType",
                    "workProfileSizeInfo",
                    "inverseJobRelationships",
                    "$metadata",
                    "photos"
                ]
                clean_org_data = remove_keys_recursive(json_data, keys_to_remove)
                print(json.dumps(clean_org_data, indent=2))

                await new_tab.wait_for_load_state("networkidle")
                await capture_and_push_screenshot(new_tab, r)

                final_result = {
                    "full_name": display_name,
                    "department": department,
                    "phone_number": phone_text,
                    "email": email,
                    "org_chart": clean_org_data 
                }

                return json.dumps(final_result, indent=2)

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

    return query_person_info


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
        query_name = input('input your query name: ')
        producer_task = asyncio.create_task(build_tool_query_person_info(answer_queue)(query_name))
        consumer_task = asyncio.create_task(consumer(answer_queue, producer_task))

        p_result, c_result = await asyncio.gather(producer_task, consumer_task)
        print(f'Final result: {p_result}')
        print(c_result)

    asyncio.run(main())
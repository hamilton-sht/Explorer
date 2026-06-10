import traceback
import logging

from PIL import Image
from .utils import pil_to_b64
from .actions import create_id_based_action, create_none_action
from traj_gen.llm_utils import call_gpt4v
import re
from traj_gen.utils import calc_num_tokens
import tiktoken


class TaskProposalAgent:
    def __init__(self, args, browser_env, image_processor):
        self.args = args
        self.browser_env = browser_env
        self.image_processor = image_processor

        self.sm = f"""What does this webpage show? Imagine you are real user on this webpage. Given the webpage screenshot, please provide a single task that a user might perform on this page and the corresponding first action towards completing that task.
    Do the following step by step:
    1. Generate a single task that a user might perform on this webpage. Be creative and come up with diverse tasks
    2. Given the webpage screenshot, generate the first action towards completing that task (in natural language form).
    3. Given the webpage screenshot and the natural language action, generate the grounded version of that action.

    *ACTION SPACE*: Your action space is: [`move(x,y)`, `hover(x,y)`, `click(x,y)`, `doubleclick(x,y)`, `rightclick(x,y)`, `type("text")`, `press("Enter")`, `keyup("shift")`, `scroll("down", 600)`, `wait()`, `go_back()`, `go_forward()`, `navigate("https://allowed.example")`, `zoom_region(x,y,w,h)`, `zoom_out()`, `answer("final answer")`, `stop()`].
    Action output should follow the syntax as given below:
    `move(x,y)`: Move the mouse to image-pixel coordinate (x,y).
    `hover(x,y)`: Hover at image-pixel coordinate (x,y).
    `click(x,y)`: Click at image-pixel coordinate (x,y).
    `doubleclick(x,y)`: Double-click at image-pixel coordinate (x,y).
    `rightclick(x,y)`: Right-click at image-pixel coordinate (x,y).
    `type("text")`: Type text into the currently focused field.
    `press("Enter")`: Press a key.
    `keyup("shift")`: Release a key.
    `scroll("down", 600)` / `scroll("up", 600)`: Scroll the page.
    `wait()`: Wait.
    `go_back()` / `go_forward()`: Browser history navigation.
    `navigate("https://allowed.example")`: Navigate to a URL.
    `zoom_region(x,y,w,h)`: Mark a visual region for closer inspection.
    `zoom_out()`: Return to the full screenshot.
    `answer("final answer")`: Finish with a final answer when the task IS completed (information found / form submitted / item added to cart).
    `stop()`: Terminate when the task is UNSOLVABLE on this site (login wall, CAPTCHA, content does not exist, asks for credit card). Do NOT use `stop()` when you simply haven't found the answer yet — keep exploring.

    *IMPORTANT* To be successful, it is important to STRICTLY follow the below rules:

    *  Action generation rules *
    1. You should generate a single atomic action at each step.
    2. The action should be an atomic action from the given visual function vocabulary.
    3. **COORDINATES ARE ABSOLUTE PIXELS (NOT NORMALIZED)**. The screenshot is 1920 x 1080 pixels. x ∈ [0, 1920], y ∈ [0, 1080]. Use the center of the visible target.
       ✓ CORRECT: `click(960, 540)` — clicks the screen center
       ✓ CORRECT: `click(345.7, 88.0)` — fractional pixels are fine
       ✗ WRONG: `click(0.5, 0.5)` — these are normalized [0,1], they will click pixel (0, 0)
       ✗ WRONG: `click(0.277, 0.965)` — also normalized, will hit top-left corner
       ✗ WRONG: `click(500, 1000)` for normalized [0,1000] — that's the Qwen-VL format, NOT used here
       If you see numbers like 0.277 in your action, you are wrong — multiply by 1920 / 1080 to get pixels.
    4. The grounded action must be exactly one function call from the action space, with no element IDs, no square-bracket syntax, and no extra text.
    5. If the type action is selected, the natural language form of action ("action_in_natural_language") should always specify the actual text to be typed.
    6. You should issue `stop()` if the current webpage asks to login or for credit card information.
    7. To input text, first output `click(x,y)` on the target textbox/search field. In the next step output `type("content")`. If submission is needed, output `press("Enter")` as the third separate step. Do not combine click, type, and keypress in one action.
    8. STRICTLY Avoid repeating the same action (click/type) if the webpage remains unchanged. You may have selected the wrong web element.
    9. Use quotation marks only for string arguments inside function calls.

    *  Task proposal rules *
    0. **DEAD-PAGE DETECTION (FIRST CHECK)**: If the screenshot shows a SERVER ERROR PAGE, a BROWSER ERROR PAGE, or an ACCESS BLOCK page — DO NOT propose a task. Issue `stop()` as the first action and set "task" to "site unreachable". The page is dead, there is nothing meaningful for a user to do here. Signals (any one is enough):
       - HTTP error codes shown as page content: "403", "404", "500", "502", "503", "504", "Forbidden", "Not Found", "Bad Gateway", "Service Unavailable", "Gateway Timeout"
       - Access blocks: "Access Denied", "You don't have permission", "This site can't be reached", "DNS_PROBE_FINISHED", "ERR_CONNECTION_REFUSED", Cloudflare "Sorry, you have been blocked" / "Checking your browser"
       - CAPTCHA gates: "I'm not a robot", reCAPTCHA, hCaptcha, Cloudflare Turnstile as the main page content
       - Login walls: a login form is the ONLY meaningful thing visible on the homepage
       Reading off the error code as `answer("403 ERROR")` is NOT a real task — that is the system failing, not a user succeeding. Refuse it.
    1. You should propose tasks that are relevant to the website and can be completed using the website.
    2. You should only propose tasks that do not require login to execute the task.
    3. You should propose tasks that are clear and specific.
    4. For each task, provide concrete information or constraints, and use mock-up information (identifier, number, personal information, name, attributes, etc.) to make the task more specific and realistic.
    5. The task description should provide all the necessary information to complete the task.
    6. The task should be feasible to complete by a real user and should not require any additional information that is not available on the website.
    7. **The task MUST have a concrete verifiable target** — at least one of: a specific number/date/price visible on a page, a specific page reached (e.g. "Privacy Policy page"), a form filled with given values, or a specific product added to cart. Avoid pure "Read / Browse / Explore / Learn about" tasks that have no checkable endpoint.
    8. **The task MUST be solvable within ~20 atomic actions** using only the visual action space on this website. Do NOT propose tasks requiring: external search engines, bookmarks, file downloads to a specific folder, CAPTCHA, login/registration, payment processing, multi-day booking flows, or features that don't exist on this site.
    9. **The task MUST be reachable from the current page** using only the visible UI (nav, search, content links, footer). Describe WHAT to find, not HOW to navigate — do NOT bake a specific menu path or step sequence into the task instruction (e.g. write "Find the contact phone number for the Sefton parking permits office" rather than "Navigate to Council Services > Parking > Permits and find the phone number"). Let the agent choose the path.

    The output should be in below format:
    *OUTPUT FORMAT*: Please give a short analysis of the screenshot, then put your answer within ``` ```, for example, "In summary, the proposed task and the corresponding action is: ```{{"task": <TASK>:str, "action_in_natural_language":<ACTION_IN_NATURAL_LANGUAGE>:str, "grounded_action": "click(320,180)"}}```"

    """

    def act(self, image_obs):
        is_action_valid = True

        try:
            messages = self.create_request(image_obs)

            ans_1st_pass, _ = call_gpt4v(
                self.args, messages, temperature=self.args.temp_refiner
            )

            if self.args.print_num_toks:
                n_inp_tokens = calc_num_tokens(messages)
                encoding = tiktoken.encoding_for_model("gpt-4o")
                n_op_tokens = len(encoding.encode(ans_1st_pass))
                n_tokens = n_inp_tokens + n_op_tokens

                logging.info(f"Number of tokens: {n_tokens}")

        except Exception as e:
            result = None
            ans_1st_pass = ""
            finish_reason = ""
            usage = {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}
            logging.info(traceback.format_exc())
            is_action_valid = False

        response = ans_1st_pass
        logging.info(f"response = {response}")

        try:
            import ast

            try:
                pred = re.findall(r"```(.*?)```", response, re.DOTALL)[-1]
            except:
                try:
                    pred = response.split("```")[-2]  # handle case with three ```
                except:
                    logging.error("Error in parsing the prediction ``````")
                    pred = ""
                    logging.error(traceback.format_exc())
                    is_action_valid = False

            try:
                if pred.startswith("json"):
                    pred = pred[4:]
                pred = ast.literal_eval(pred)
            except:
                logging.error("Error in parsing the prediction dict {}".format(pred))
                pred = {
                    "task": "regex fail",
                    "action_in_natural_language": "regex fail",
                    "grounded_action": "regex fail",
                }
                logging.error(traceback.format_exc())
                is_action_valid = False

            action_grounded = pred["grounded_action"]

            try:
                cur_action = create_id_based_action(action_grounded)
            except:
                logging.error("Action parsing error")
                logging.error(traceback.format_exc())

                cur_action = create_none_action()
                is_action_valid = False

            logging.info(f"Action to be executed: {cur_action}")

            is_success = self.browser_env.step(cur_action)
            if not is_success:
                is_action_valid = False

            logging.info("URL 0: {}".format(self.browser_env.page.url))

        except:
            pred = {
                "task": "regex fail",
                "action_in_natural_language": "regex fail",
                "grounded_action": "regex fail",
            }
            browser_env_state = {}
            logging.error(traceback.format_exc())
            is_action_valid = False

        return response, pred, is_action_valid

    def create_request(self, image_obs):
        prompt = [
            {
                "type": "text",
                "text": f"WEBSITE URL: {self.args.init_url}\nUse only the screenshot to choose a visual action.",
            },
            {
                "type": "image_url",
                "image_url": {"url": pil_to_b64(Image.fromarray(image_obs))},
            },
        ]

        messages = [{"role": "system", "content": [{"type": "text", "text": self.sm}]}]

        messages.append({"role": "user", "content": prompt})
        return messages

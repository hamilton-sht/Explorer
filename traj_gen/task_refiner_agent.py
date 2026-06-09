import traceback
import logging

from PIL import Image
from .utils import pil_to_b64
from .actions import create_id_based_action, create_none_action
from traj_gen.llm_utils import call_gpt4v
import re
from traj_gen.utils import calc_num_tokens
import tiktoken


class TaskRefinerAgent:
    def __init__(self, args, browser_env, image_processor):
        self.args = args
        self.browser_env = browser_env
        self.image_processor = image_processor

        self.sm = """Imagine you are real user on this webpage, and your overall task is {overall_task}. This is the list of actions you have performed which lead to the current page {prev_action_list}. You are also given the webpage screenshot.
    Do the following step by step:
    1. Please predict what action the user might perform next that is consistent with the overall task and previous action list in natural language.
    2. Then based on the screenshot and the natural language action, generate the grounded action.
    3. Output the task you are currently pursuing in the "task" field. Default: keep the original overall task verbatim. Only modify it under the controlled-pivot rule below.


    *  Task fidelity rules with controlled pivot *

    1. **Default = keep**: in almost all steps, the "task" field MUST equal the overall task above verbatim. Copy it byte-for-byte.
    2. Do NOT change the task type lightly (information-seeking ↔ transactional). Do NOT silently drop a date / location / identifier / person name unless the pivot rule (#4) triggers.
    3. If the overall task is information-seeking ("find / check / what is / explain"), keep pursuing the information. Do NOT secretly convert it into "find a dealer contact form" or any other unrelated action.
    4. **Controlled pivot — only when truly stuck**: if you have evidence the original task cannot be completed on this site (e.g. you've explored ≥3 distinct paths without progress, OR the specific item / page / value clearly does not exist), you MAY pivot to a closely-related task that satisfies ALL of these:
       (a) the pivoted task is on the SAME website and the SAME general topic as the original (e.g. original "find revenue 2023" → pivot "find any recent financial figure" is OK; pivot "find dealer contact form" is NOT OK);
       (b) the pivoted task can be completed in ≤3 more actions from your current state;
       (c) the pivoted task has a concrete verifiable target (a visible number / date / name / page reached);
       (d) you have actually attempted the original task with multiple paths before pivoting.
       When you pivot, the "task" field becomes the pivoted task (NOT the original), and the next action should make progress on the pivot.
    5. **Anti-frivolous-pivot**: do NOT pivot just because the first path failed. Do NOT pivot to make the task easier without exploring. Pivots are an escape valve, not a shortcut.

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
    `answer("final answer")`: Finish with a final answer when the task IS completed.
    `stop()`: Terminate when the task is UNSOLVABLE on this site (login wall, CAPTCHA, content does not exist). Do NOT use `stop()` just because you haven't found the answer yet — keep exploring instead.

    *IMPORTANT* To be successful, it is important to STRICTLY follow the below rules:

    *  Action generation rules *
    1. You should generate a single atomic action at each step.
    2. The action should be an atomic action from the given visual function action space.
    3. The screenshot is 1920 x 1080 pixels. x ∈ [0, 1920], y ∈ [0, 1080]. Use the center of the visible target.
       ✓ CORRECT: `click(960, 540)` — clicks the screen center
    4. The grounded action must be exactly one function call from the action space, with no element IDs, no square-bracket syntax, and no extra text.
    5. If the type action is selected, the natural language form of action ("action_in_natural_language") should always specify the actual text to be typed.
    6. You should issue `stop()` if the current webpage asks to login or for credit card information.
    7. To input text, first output `click(x,y)` on the target textbox/search field. In the next step output `type("content")`. If submission is needed, output `press("Enter")` as the third separate step. Do not combine click, type, and keypress in one action.
    8. STRICTLY Avoid repeating the same action (click/type) if the webpage remains unchanged. You may have selected the wrong web element.
    8b. **Anti-scroll-loop**: if you have scrolled in the same direction 3+ times without finding the target content, STOP scrolling. Switch strategy: click a relevant menu link / use the search box / check the footer / try a different section. Endless scrolling wastes the action budget.
    9. If you cannot identify a valid visible text input or search box in the current screenshot, do not output a type action. Use click or scroll instead.
    10. Use quotation marks only for string arguments inside function calls.

    The output should be in below format:
    *OUTPUT FORMAT*: Please give a short analysis of the screenshot and history, then put your answer within ``` ```, for example, "In summary, the proposed task and the corresponding action is: ```{{"task": <TASK>:str, "action_in_natural_language":<ACTION_IN_NATURAL_LANGUAGE>:str, "grounded_action": "click(320,180)"}}```"
    """


    def act(self, image_obs, action_history, refined_goal, image_history=None):
        is_action_valid = True
        self.refined_goal = refined_goal

        try:
            messages = self.create_request(
                image_obs, action_history, image_history=image_history
            )
            logging.info(
                "refiner image history count = {}".format(
                    len(image_history or [])
                )
            )

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
            logging.error(traceback.format_exc())
            is_action_valid = False

        return response, pred, is_action_valid

    def create_request(self, image_obs, action_history, image_history=None):
        prompt = [
            {
                "type": "text",
                "text": f"WEBSITE URL: {self.args.init_url}\nUse only the screenshot to choose a visual action.",
            }
        ]

        history_list = image_history or []
        total_prev = max(len(history_list) - 1, 0)
        for idx, history_image in enumerate(history_list):
            if idx == 0:
                label = "Initial screenshot (episode start)"
            else:
                label = (
                    f"Previous screenshot {idx} of {total_prev} "
                    "(ordered oldest → newest; the Current screenshot below is the latest)"
                )
            prompt.extend(
                [
                    {"type": "text", "text": f"{label}:"},
                    {
                        "type": "image_url",
                        "image_url": {"url": pil_to_b64(Image.open(history_image))},
                    },
                ]
            )

        prompt.extend(
            [
                {"type": "text", "text": "Current screenshot:"},
                {
                    "type": "image_url",
                    "image_url": {"url": pil_to_b64(Image.fromarray(image_obs))},
                },
            ]
        )

        messages = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": self.sm.format(
                            prev_action_list=action_history,
                            overall_task=self.refined_goal,
                        ),
                    }
                ],
            }
        ]

        messages.append({"role": "user", "content": prompt})
        return messages

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
    3. Output the SAME overall task verbatim in the "task" field — DO NOT rewrite, paraphrase, or change the task in any way.


    *  Task fidelity rules — CRITICAL *

    1. The "task" field in your JSON output MUST exactly match the overall task above, word-for-word. Copy it verbatim.
    2. Do NOT change the task type (information-seeking ↔ transactional). Do NOT add, drop, or substitute any constraint (price, date, location, identifier, person name).
    3. If the overall task is information-seeking ("find / check / what is / explain / read about"), keep pursuing the information — do NOT silently convert it into "find a dealer contact form" or "request a quote" or any other action.
    4. If the task seems impossible on this site, keep pursuing what is visibly available; when a hard blocker or mismatch is clear, issue `stop()`. Do NOT swap in an easier task.
    5. **Anti-drift check before emitting JSON**: confirm your "task" string is byte-identical to the overall_task above. If they differ at all, fix it before output.

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
    3. All x/y coordinates are image-pixel coordinates from the screenshot. Use the center of the visible target.
    4. The grounded action must be exactly one function call from the action space, with no element IDs, no square-bracket syntax, and no extra text.
    5. If the type action is selected, the natural language form of action ("action_in_natural_language") should always specify the actual text to be typed.
    6. You should issue `stop()` if the current webpage asks to login or for credit card information.
    7. To input text, first output `click(x,y)` on the target textbox/search field. In the next step output `type("content")`. If submission is needed, output `press("Enter")` as the third separate step. Do not combine click, type, and keypress in one action.
    8. STRICTLY Avoid repeating the same action (click/type) if the webpage remains unchanged. You may have selected the wrong web element.
    9. If you cannot identify a valid visible text input or search box in the current screenshot, do not output a type action. Use click or scroll instead.
    10. Use quotation marks only for string arguments inside function calls.

    The output should be in below format:
    *OUTPUT FORMAT*: Please give a short analysis of the screenshot and history, then put your answer within ``` ```, for example, "In summary, the proposed task and the corresponding action is: ```{{"task": <TASK>:str, "action_in_natural_language":<ACTION_IN_NATURAL_LANGUAGE>:str, "grounded_action": "click(320,180)"}}```"
    """

    # Task-following variant: used when args.task is set. The overall task is
    # FIXED — agent must NOT rewrite it. Information seeking is allowed. When
    # the task asks for a piece of information, the agent should issue answer()
    # and put the answer in the `answer` field of the JSON output.
    sm_task_following = """You are an expert web navigation agent. Your overall task is FIXED and given below:

OVERALL TASK: {overall_task}

You are given the webpage screenshot and the list of actions you have already performed: {prev_action_list}.

Your job: pick the NEXT single atomic action that makes progress on the overall task.

*ACTION SPACE*: [`move(x,y)`, `hover(x,y)`, `click(x,y)`, `doubleclick(x,y)`, `rightclick(x,y)`, `type("text")`, `press("Enter")`, `keyup("shift")`, `scroll("down", 600)`, `wait()`, `go_back()`, `go_forward()`, `navigate("https://allowed.example")`, `zoom_region(x,y,w,h)`, `zoom_out()`, `answer("final answer")`, `stop()`].

*RULES*:
1. Do NOT modify or rewrite the overall task. Output the SAME task verbatim in the "task" field every step.
2. The action must be a single atomic action from the action space.
3. **ANSWER CRITERION**: Only issue `answer("...")` when the SPECIFIC information requested is currently VISIBLE in the screenshot. Do NOT stop on the homepage just because the topic seems related. Do NOT invent or paraphrase content that isn't displayed. If the answer is plainly visible on the homepage (banner/headline/main content), stop immediately on step 0 or 1 — do not over-explore.
4. **Anti-hallucination — VERY IMPORTANT**: When you write a FINAL ANSWER, every fact in it must come DIRECTLY from text you can read in the latest screenshot. Do not use background knowledge. Do not say "based on visible content" if the content isn't actually there. If unsure, KEEP NAVIGATING — click into menus, sections, or sub-pages.
5. **For information-seeking tasks**: when the page text/visible content already shows the answer, issue `answer("...")` with the FULL answer string in the "answer" field — quote the exact text from the page.
6. **For multi-step navigation tasks**: complete all listed steps, then issue `answer("")` if everything went through.
6b. **Unsolvable tasks**: if the site does not contain the requested info, or asks for login/CAPTCHA, issue `stop()` (NOT `answer("not found")` — `stop()` is the dedicated signal).
7. Don't get stuck — if a path doesn't work after 3-4 actions, try a different path (search box, top nav, footer, sitemap).
8. **Step budget awareness**: If you have already taken 20+ actions, this is your last chance — issue `answer("...")` on the next action with your best partial answer based on what you have seen so far. Do NOT continue exploring past 25 actions.
9. STRICTLY avoid repeating the same action if the page didn't change — try a different element or strategy.
10. To input text, first output `click(x,y)` on the target textbox/search field. In the next step output `type("content")`. If submission is needed, output `press("Enter")` as the third separate step. Do not combine click, type, and keypress in one action.
11. If a login or credit card page appears, issue `stop()`.
12. **CRITICAL**: Whenever you issue `answer("...")` on an information-seeking task, the answer string must be NON-EMPTY and the content must be DIRECTLY READABLE in the current screenshot. An answer not grounded in the visible page = failure.

*OUTPUT FORMAT*: Brief analysis, then JSON within ``` ```, e.g.:
```{{"task": <TASK>, "action_in_natural_language": <ACTION_NL>, "grounded_action": <ACTION>, "answer": <OPTIONAL_ANSWER>}}```
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

        is_task_following = bool(getattr(self.args, "task", None))
        system_prompt = self.sm_task_following if is_task_following else self.sm

        messages = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": system_prompt.format(
                            prev_action_list=action_history,
                            overall_task=self.refined_goal,
                        ),
                    }
                ],
            }
        ]

        messages.append({"role": "user", "content": prompt})
        return messages

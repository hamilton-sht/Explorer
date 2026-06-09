import traceback
import logging

from PIL import Image
from .utils import pil_to_b64
from traj_gen.llm_utils import call_gpt4v
from traj_gen.utils import calc_num_tokens
import tiktoken
import os


class TrajectoryVerifierAgent:
    def __init__(self, args):
        self.args = args

        self.sm = """You are an expert in evaluating the performance of a web navigation agent. The agent is designed to help a human user navigate a website to complete a task. Given the user's intent, the agent's action history, the final state of the webpage, and the agent's response to the user, your goal is to decide whether the agent's execution is successful or not.

There are three types of tasks:
1. Transaction: The user wants to perform a transaction on the webpage, such as booking a ticket, ordering a product, etc. The bot should at least initiate the add-to-cart or checkout process. It is still a success if the bot has done actions of 'add to cart' or checkout and encounters the login page.  If the bot fails to do so, the task is considered a failure.
2. Information seeking: The user wants to obtain certain information from the webpage. Count as **success** if EITHER:
   (a) the agent's final action contains "FINAL ANSWER: <text>" and the answer is factually consistent with the visible page content, OR
   (b) the final webpage screenshot/text clearly displays the requested information on screen (even if the agent did not articulate an answer), OR
   (c) the agent has navigated to the section of the website that authoritatively contains the answer (e.g. a "Pricing" page when asked about price, a "Hazards" page when asked about hazards), AND the screenshot shows the relevant content.
   Count as **failure** if: the bot's final answer (FINAL ANSWER) is factually wrong, OR the agent ended on an irrelevant/error page, OR the agent gave up without reaching content related to the task.
   Be careful about hard constraints in the task (e.g. "at least 5 items", "for the year 2023") — partial answers covering most but not all required facts still count as success unless the missing piece is the core of the task.
3. Site navigation: The user wants to navigate to a specific page. Carefully examine the bot's action history and the final state of the webpage to determine whether the bot successfully completes the task. No need to consider the bot's response.
4. Content modification: The user wants to modify the content of a webpage or configuration. Carefully examine the bot's action history and the final state of the webpage to determine whether the bot successfully completes the task. No need to consider the bot's response.

*IMPORTANT*
- **Termination signals**: the agent ends a trajectory with either `answer("text")` (task completed) or `stop()` (task is unsolvable on this site).
- **`stop()` semantics — TREAT CAREFULLY**:
  - If the final webpage shows a hard blocker that the task asks the agent to interact with (login wall, paywall, CAPTCHA challenge, requires credit card, content removed/404, site explicitly forbids what the task wants), `stop()` is the CORRECT signal → **count as success** because the agent correctly identified infeasibility.
  - If the URL is structurally unrelated to the task (e.g. task asks about Barcelona Aquarium but URL is valgrind.org), `stop()` is correct → **success**.
  - If the requested information IS visible on the final page (or clearly reachable from it) and the agent issued `stop()` instead of `answer(...)`, that is a premature give-up → **failure**.
  - If the agent issued `stop()` after just 1-2 actions without exploring, default to **failure** unless the blocker is unambiguous in the final screenshot.
- If the task name and the initial URL are mismatched (e.g. the task asks about Barcelona Aquarium but the URL is valgrind.org), the task is **unsolvable** — count as failure ONLY if the agent kept blindly trying; count as success if the agent correctly stopped early and stated the URL is unrelated.
- If a product has been added to the bag/cart in the action list but just the purchase is pending, it should be counted as success.
- If you see the checkout page for the product you want to purchase, it should be counted as success.
- Format your response into two lines as shown below:

Thoughts: <your thoughts and reasoning process>
Status: "success" or "failure"
"""

    def act(self, intent, last_actions, image_obs, last_page_md):
        call_api_success = False
        try:
            messages = self.create_request(
                intent, last_actions, image_obs, last_page_md
            )

            ans_1st_pass, call_api_success = call_gpt4v(
                self.args, messages, temperature=self.args.temp_summ_verf
            )

            if self.args.print_num_toks:
                n_inp_tokens = calc_num_tokens(messages)
                encoding = tiktoken.encoding_for_model("gpt-4o")
                n_op_tokens = len(encoding.encode(ans_1st_pass))
                n_tokens = n_inp_tokens + n_op_tokens

                logging.info(f"Number of tokens: {n_tokens}")
                print(f"Number of tokens: {n_tokens}")

        except Exception as e:
            ans_1st_pass = ""
            logging.info("error in trajectory verifier agent")
            logging.info(traceback.format_exc())

        response = ans_1st_pass

        if not call_api_success:
            response = "API call failed after 3 tries"
            logging.info("verifier API call failed after 3 tries")

        return response

    def create_request(self, intent, last_actions, image_obs, last_page_md=None):
        if self.args.use_all_screenshots_verifier:
            prompt = f"""User Intent: {intent}\n Action History: {last_actions}\n The content of the last webpage in markdown format is given below \n{last_page_md}\n The snapshots of all webpages corresponding to the actions are shown in the images."""
        else:
            prompt = f"""User Intent: {intent}\n Action History: {last_actions}\n The content of the last webpage in markdown format is given below \n{last_page_md}\n The last snapshot of the web page is shown in the image."""

        messages = [{"role": "system", "content": [{"type": "text", "text": self.sm}]}]

        user_msg = [{"type": "text", "text": prompt}]

        if isinstance(image_obs, list):
            for screenshot_path in image_obs:
                if os.path.exists(screenshot_path):
                    print(screenshot_path)
                    user_msg += [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": pil_to_b64(Image.open(screenshot_path))
                            },
                        }
                    ]
        else:
            user_msg.append(
                {
                    "type": "image_url",
                    "image_url": {"url": pil_to_b64(Image.open(image_obs))},
                }
            )

        messages.append({"role": "user", "content": user_msg})

        return messages

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
2. Information seeking: The user wants to obtain certain information from the webpage. **You are given the ENTIRE screenshot history of the trajectory, NOT just the final screenshot. The answer may have been visible in an intermediate screenshot — examine ALL screenshots before judging.** Count as **success** if ANY of:
   (a) the agent's final action contains `answer("...")` with text that is factually consistent with content visible in ANY screenshot of the trajectory (intermediate OR final). It is COMMON for the agent to find the answer mid-trajectory then navigate back to home — this is still success, NOT failure. OR
   (b) any screenshot in the trajectory clearly displays the requested information on screen (even if the agent did not articulate an answer), OR
   (c) the agent navigated through the section of the website that authoritatively contains the answer (e.g. a "Pricing" page, a "Contact" page) during the trajectory, AND a screenshot in the trajectory shows the relevant content.
   Count as **failure** only if: the bot's final answer is factually inconsistent with ALL screenshots (hallucinated), OR the agent never reached any page containing the requested info, OR the agent gave up before reaching content related to the task.
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
            prompt = f"""User Intent: {intent}\n Action History: {last_actions}\n The HTML content of the FINAL webpage (after the last action) is given below for textual reference — but remember the answer might have been visible on an EARLIER page, so check the images too.\n\n--- FINAL PAGE HTML ---\n{last_page_md}\n\n--- TRAJECTORY SCREENSHOTS ---\nThe screenshots that follow are labelled with their step number. Step 0 is the starting page, then each step shows the page AFTER the agent's action at that step. The last image is `screenshot_final.png` (the page after the trajectory terminated). Examine ALL of them when judging — the requested information may be visible on any one of them, not just the final one."""
        else:
            prompt = f"""User Intent: {intent}\n Action History: {last_actions}\n The content of the last webpage in markdown format is given below \n{last_page_md}\n The last snapshot of the web page is shown in the image."""

        messages = [{"role": "system", "content": [{"type": "text", "text": self.sm}]}]

        user_msg = [{"type": "text", "text": prompt}]

        if isinstance(image_obs, list):
            n_total = len(image_obs)
            for i, screenshot_path in enumerate(image_obs):
                if os.path.exists(screenshot_path):
                    # Label this image so the verifier knows which step it is.
                    fname = os.path.basename(screenshot_path)
                    if "final" in fname:
                        label = f"Screenshot #{i} — FINAL page (after trajectory ended)"
                    elif i == 0:
                        label = f"Screenshot #{i} — Step 0 (initial page, BEFORE any action)"
                    else:
                        label = f"Screenshot #{i} — page AFTER step {i - 1}'s action"
                    user_msg.append({"type": "text", "text": label})
                    user_msg.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": pil_to_b64(Image.open(screenshot_path))
                            },
                        }
                    )
        else:
            user_msg.append(
                {
                    "type": "image_url",
                    "image_url": {"url": pil_to_b64(Image.open(image_obs))},
                }
            )

        messages.append({"role": "user", "content": user_msg})

        return messages

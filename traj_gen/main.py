import os
import random
import traceback
from .task_proposal_agent import TaskProposalAgent
from .task_refiner_agent import TaskRefinerAgent
from .task_summarization_flow import TaskSummarizationAgent
import json
from .trajectory_verifier import TrajectoryVerifierAgent
from .captcha_detection_agent import CaptchaDetectionAgent
from PIL import Image, ImageDraw, ImageFont
import argparse
import logging
from tqdm import tqdm
import requests
from bs4 import BeautifulSoup
from .browser_env import ScriptBrowserEnv
from .processors import ImageObservationProcessor
import re
from .actions import create_id_based_action

logger = logging.getLogger("__main__")


def save_action_som(raw_screenshot_path, output_path, bounding_box_coord, label=None):
    img = Image.open(raw_screenshot_path).convert("RGB")

    if bounding_box_coord is None:
        img.save(output_path)
        return

    center_x = bounding_box_coord["x"]
    center_y = bounding_box_coord["y"]
    width = bounding_box_coord["width"]
    height = bounding_box_coord["height"]

    left = max(0, center_x - width / 2)
    top = max(0, center_y - height / 2)
    right = min(img.width - 1, center_x + width / 2)
    bottom = min(img.height - 1, center_y + height / 2)
    if right < left:
        left, right = right, left
    if bottom < top:
        top, bottom = bottom, top

    draw = ImageDraw.Draw(img)
    color = (255, 0, 0)
    draw.rectangle([left, top, right, bottom], outline=color, width=4)

    if label:
        font = ImageFont.load_default()
        text = str(label)
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        label_left = int(left)
        label_top = max(0, int(top) - text_height - 8)
        draw.rectangle(
            [
                label_left,
                label_top,
                label_left + text_width + 8,
                label_top + text_height + 6,
            ],
            fill=color,
        )
        draw.text(
            (label_left + 4, label_top + 3),
            text,
            fill=(255, 255, 255),
            font=font,
        )

    img.save(output_path)


def select_refiner_image_history(image_history, max_images):
    if max_images <= 0 or not image_history:
        return []

    selected = [image_history[0]]
    for image_path in image_history[-(max_images - 1) :]:
        if image_path not in selected:
            selected.append(image_path)
    return selected


def select_summarization_screenshots(screenshot_history, max_images):
    if max_images <= 0 or not screenshot_history:
        return []
    if len(screenshot_history) <= max_images:
        return list(screenshot_history)

    last_count = min(3, max_images - 1)
    middle_count = max_images - 1 - last_count
    last_images = screenshot_history[-last_count:]
    middle_pool = screenshot_history[1:-last_count] if last_count else screenshot_history[1:]

    selected = [screenshot_history[0]]
    if middle_count > 0 and middle_pool:
        if len(middle_pool) <= middle_count:
            selected.extend(middle_pool)
        else:
            for i in range(middle_count):
                idx = round(i * (len(middle_pool) - 1) / (middle_count - 1)) if middle_count > 1 else len(middle_pool) // 2
                selected.append(middle_pool[idx])

    selected.extend(last_images)

    deduped = []
    for image_path in selected:
        if image_path not in deduped:
            deduped.append(image_path)
    return deduped[:max_images]


class Explorer:
    def __init__(self, args):
        self.args = args

        self.viewport_size = {
            "width": args.viewport_width,
            "height": args.viewport_height,
        }
        self.image_observation_type = "image_som"

        self.browser_env = ScriptBrowserEnv(
            args, browser_type="chrome", viewport_size=self.viewport_size
        )

        self.init_setup_error = False
        try:
            self.browser_env.setup(args.init_url)
        except:
            self.init_setup_error = True
            logging.info("Error in setting up the environment. Exiting...")
            logging.info(traceback.format_exc())
            return
        self.image_processor = ImageObservationProcessor(
            args, self.image_observation_type, self.viewport_size
        )

        self.task_proposal_agent = TaskProposalAgent(
            args, self.browser_env, self.image_processor
        )
        self.task_refiner_agent = TaskRefinerAgent(
            args, self.browser_env, self.image_processor
        )
        self.summarization_agent = TaskSummarizationAgent(
            args, self.browser_env, self.image_processor
        )
        self.verifier_agent = TrajectoryVerifierAgent(args)

        self.captcha_detection_agent = CaptchaDetectionAgent(args)

    def get_state(self):
        som_image_obs, parsed_html_str = self.image_processor.process_new(
            self.browser_env.page,
            self.browser_env.page.client,
            use_id_selector=True,
            intent=None,
        )

        html = self.browser_env.page.content()

        return {
            "page": self.browser_env.page,
            "client": self.browser_env.page.client,
            "content_str": parsed_html_str,
            "image_obs": som_image_obs,
            "html": html,
        }

    def run(self, ex_log_dir="."):
        if self.init_setup_error:
            return [], "Error in setting up the environment", False

        task_trajectory_data = {}
        task_trajectory_data["init_url"] = self.args.init_url
        task_trajectory_data["viewport-width"] = self.args.viewport_width
        task_trajectory_data["viewport-height"] = self.args.viewport_height

        task_trajectory_data["actions"] = []
        completed = False

        task_refinement_history = []
        action_history = []
        action_screenshot_history = []
        refiner_image_history = []
        original_task = None
        step = 0
        execution_id = 0

        try:
            while step < self.args.max_steps and execution_id <= 2:
                action = {}
                logging.info(f"Step {step}:\n")
                if completed:
                    break
                if self.browser_env.page is not None and any(
                    self.browser_env.page.url.startswith(prefix)
                    for prefix in self.args.abort_on_url_prefix
                ):
                    logging.info(
                        "aborting trajectory because current URL starts with blocked prefix: %s",
                        self.browser_env.page.url,
                    )
                    break

                # get state of the environment
                if self.browser_env.page is not None:
                    try:
                        browser_env_state = self.get_state()
                    except:
                        logging.info(
                            "Error in getting state, resetting the environment..."
                        )
                        traceback.print_exc()
                        logging.info(traceback.format_exc())
                        # reset the environment
                        self.browser_env.setup(self.args.init_url)

                        task_trajectory_data["actions"] = []
                        task_refinement_history = []
                        action_history = []
                        action_screenshot_history = []
                        refiner_image_history = []
                        original_task = None
                        step = 0
                        execution_id += 1
                        continue

                    if self.args.print_parsed_tree:
                        logging.info(
                            "acc_tree = {}".format(browser_env_state["content_str"])
                        )

                    action["acc_tree_before"] = browser_env_state["content_str"]
                    # action['html_before'] = browser_env_state['html']
                    with open(
                        os.path.join(ex_log_dir, f"html_{step}.html"),
                        "w",
                        encoding="utf-8",
                    ) as f1:
                        f1.write(browser_env_state["html"])

                    if not self.args.no_dump_screenshots:
                        self.browser_env.page.screenshot(
                            path=os.path.join(ex_log_dir, f"screenshot_{step}.png")
                        )

                        img = Image.fromarray(browser_env_state["image_obs"])
                        img.save(os.path.join(ex_log_dir, f"screenshot_som_{step}.png"))
                else:
                    browser_env_state = None

                # check if current page contains a captcha
                if step == 0:
                    captcha_response = self.captcha_detection_agent.act(
                        os.path.join(ex_log_dir, f"screenshot_{step}.png")
                    )
                    logging.info("captcha_response = {}".format(captcha_response))

                    is_captcha = captcha_response.split("Answer:")[-1].strip().lower()

                    if is_captcha == "yes":
                        logging.info("Captcha detected. Terminating the traj.")
                        return [], "Captcha detected", False

                if step == 0:
                    response, pred, is_action_valid = self.task_proposal_agent.act(
                        browser_env_state["content_str"], browser_env_state["image_obs"]
                    )
                else:
                    response, pred, is_action_valid = self.task_refiner_agent.act(
                        browser_env_state["content_str"],
                        browser_env_state["image_obs"],
                        action_history,
                        refined_goal,
                        image_history=select_refiner_image_history(
                            refiner_image_history,
                            self.args.refiner_image_history_steps,
                        ),
                    )

                logging.info(f"pred = {pred}")

                new_action_nl, new_action_grounded, refined_goal = (
                    pred["action_in_natural_language"],
                    pred["grounded_action"],
                    pred["task"],
                )
                if original_task is None and refined_goal != "regex fail":
                    original_task = refined_goal

                # get element id from new_action_grounded
                try:
                    match = re.search(r"\[(\d+)\]", new_action_grounded)
                    element_id = match.group(1)

                    # get bbox coordinates from som_id_info
                    som_id_info = self.image_processor.som_id_info
                    bounding_box_coord = {
                        "x": som_id_info[element_id][0],
                        "y": som_id_info[element_id][1],
                        "width": som_id_info[element_id][2],
                        "height": som_id_info[element_id][3],
                    }
                except:  # scroll action
                    bounding_box_coord = None

                logging.info("Agent response: {}".format(response))

                logging.info("Action (NL): {}\n".format(new_action_nl))
                logging.info("Action (grounded): {}\n".format(new_action_grounded))

                logging.info(f"refined_goal: {refined_goal}\n")

                if (
                    new_action_grounded == "stop"
                    and len(task_trajectory_data["actions"]) < self.args.min_actions_before_stop
                ):
                    logging.info(
                        "overriding early stop before min_actions_before_stop=%s",
                        self.args.min_actions_before_stop,
                    )
                    new_action_nl = "Scroll down to continue exploring relevant public content"
                    new_action_grounded = "scroll [down]"
                    bounding_box_coord = None
                    is_action_valid = self.browser_env.step(
                        create_id_based_action(new_action_grounded)
                    )

                action["step_action_nl"] = new_action_nl
                action["new_action_grounded"] = new_action_grounded
                action["bounding_box_coord"] = bounding_box_coord
                action["step_refined_goal"] = refined_goal
                action["step_reasoning_response"] = response

                task_refinement_history.append(refined_goal)
                action_history.append(new_action_nl)

                raw_screenshot_path = os.path.join(ex_log_dir, f"screenshot_{step}.png")
                action_som_path = os.path.join(
                    ex_log_dir, f"screenshot_action_som_{step}.png"
                )
                save_action_som(
                    raw_screenshot_path,
                    action_som_path,
                    bounding_box_coord,
                    label=element_id if bounding_box_coord is not None else None,
                )
                action["screenshot_action_som"] = os.path.basename(action_som_path)

                # ground / execute the action
                if new_action_grounded == "stop":
                    completed = True
                    break

                logging.info("URL: {}".format(self.browser_env.page.url))

                if is_action_valid:
                    action["URL_after"] = self.browser_env.page.url
                    task_trajectory_data["actions"].append(action)
                    action_screenshot_history.append(action_som_path)
                    refiner_image_history.append(
                        os.path.join(ex_log_dir, f"screenshot_som_{step}.png")
                    )

                logging.info("##############################\n\n")
                step += 1
        except:
            logging.info("Error in step {}".format(step))

            # put traceback in logging log
            logging.error("{}".format(traceback.format_exc()))
            step += 1

        # summarize the task description using history
        screenshot_history = select_summarization_screenshots(
            action_screenshot_history,
            self.args.summarization_max_screenshots,
        )
        summarization_response, summarization_pred = self.summarization_agent.act(
            action_history, screenshot_history
        )
        if summarization_pred == "regex fail":
            fallback_task = original_task or (task_refinement_history[-1] if task_refinement_history else None)
            if fallback_task and fallback_task != "regex fail":
                logging.info(
                    "summarization failed; falling back to task = {}".format(
                        fallback_task
                    )
                )
                summarization_pred = fallback_task

        # Verify against the summarized intent so long trajectories are judged
        # by the task actually implied by the full action sequence.
        user_intent = summarization_pred

        history = [
            action["step_action_nl"] for action in task_trajectory_data["actions"]
        ]
        img_path = os.path.join(ex_log_dir, "screenshot_final.png")

        logging.info("user_intent = {}".format(user_intent))
        logging.info("history = {}".format(history))

        self.browser_env.page.screenshot(path=img_path)

        try:
            last_page_html = self.browser_env.page.content()
            soup = BeautifulSoup(last_page_html, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            last_page_md = "\n".join(
                line.strip()
                for line in soup.get_text("\n").splitlines()
                if line.strip()
            )[:20000]
        except:
            logging.info("failed to extract final page text for verifier")
            logging.info(traceback.format_exc())
            last_page_md = None

        self.browser_env.close()

        if self.args.use_all_screenshots_verifier:
            screenshot_history = [
                os.path.join(ex_log_dir, f"screenshot_{i}.png") for i in range(step + 1)
            ] + [img_path]
            verifier_agent_response = self.verifier_agent.act(
                user_intent, history, screenshot_history, last_page_md
            )
        else:
            verifier_agent_response = self.verifier_agent.act(
                user_intent, history, img_path, last_page_md
            )

        logging.info("verifier_agent_response = {}".format(verifier_agent_response))

        task_trajectory_data["task_summary"] = user_intent
        task_trajectory_data["original_task"] = original_task
        task_trajectory_data["summarization_agent_response"] = summarization_response
        task_trajectory_data["verifier_agent_response"] = verifier_agent_response

        return task_trajectory_data, verifier_agent_response, True


def to_raw_string(s):
    return s.replace("\\", "\\\\")


def setup_logging(ex_log_dir):
    # Clear existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Create a new file handler
    log_file = os.path.join(ex_log_dir, "step_simulator_flow.log")
    logging.basicConfig(
        level=logging.INFO,
        filename=log_file,
        filemode="w",
        format="%(asctime)s - %(message)s",
    )


def main(args):
    # set seed
    random.seed(args.seed)

    # create a default unique model dir if not specified
    if args.model_dir is None:
        args.model_dir = "model_" + str(random.randint(0, 1000000))

    if not os.path.exists(args.model_dir):
        os.makedirs(args.model_dir, exist_ok=True)

    flow = Explorer(args)

    setup_logging(args.model_dir)

    task_trajectory_data, verifier_agent_response, is_traj_success = flow.run(
        args.model_dir
    )

    if not is_traj_success:
        return

    # dump the task trajectory data
    with open(os.path.join(args.model_dir, "task_trajectory_data.json"), "w") as f:
        json.dump(task_trajectory_data, f, indent=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-steps", type=int, default=5, help="Maximum number of steps to simulate"
    )
    parser.add_argument(
        "--print-parsed-tree",
        action="store_true",
        help="Print the parsed tree in stdout",
    )
    parser.add_argument(
        "--no-dump-screenshots",
        action="store_true",
        help="Do NOT dump screenshots of each step in screenshots/",
    )
    parser.add_argument(
        "--model-dir", type=str, default=None, help="Directory to save the models"
    )
    parser.add_argument("--seed", type=int, default=736537, help="Random seed")
    parser.add_argument(
        "--init-url",
        type=str,
        default="https://www.amazon.com/",
        help="initial url for the browser env",
    )
    parser.add_argument(
        "--temp-refiner",
        type=float,
        default=0.01,
        help="temperature for the refiner agent",
    )
    parser.add_argument(
        "--omit-acc-tree", action="store_true", help="omit the accessibility tree"
    )
    parser.add_argument(
        "--viewport-width", type=int, default=1920, help="viewport width"
    )
    parser.add_argument(
        "--viewport-height", type=int, default=1080, help="viewport height"
    )
    parser.add_argument(
        "--print-num-toks",
        action="store_true",
        help="print the token count for each module",
        default=False,
    )
    parser.add_argument(
        "--deployment",
        type=str,
        default="gpt-4o",
        help="API model deployment",
    )
    parser.add_argument(
        "--use-all-screenshots-verifier",
        action=argparse.BooleanOptionalAction,
        help="use all screenshots for verifier",
        default=True,
    )
    parser.add_argument(
        "--temp-summ-verf",
        type=float,
        default=0.01,
        help="temperature for the summarizer and verifier agents",
    )
    parser.add_argument(
        "--refiner-image-history-steps",
        type=int,
        default=5,
        help="number of previous SOM screenshots to include in each refiner request",
    )
    parser.add_argument(
        "--summarization-max-screenshots",
        type=int,
        default=8,
        help="maximum number of action-focused screenshots to send to summarization",
    )
    parser.add_argument(
        "--min-actions-before-stop",
        type=int,
        default=0,
        help="replace stop with scroll down until this many valid actions are collected",
    )
    parser.add_argument(
        "--abort-on-url-prefix",
        nargs="*",
        default=["chrome-error://"],
        help="stop rollout when the current URL starts with any of these prefixes",
    )
    parser.add_argument(
        "--verifier-intent-source",
        choices=["summary", "original"],
        default="original",
        help="which task text to use as verifier intent",
    )

    args = parser.parse_args()
    print(args)

    main(args)

# Standard library imports
import os
import json
import asyncio
import itertools
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Union, Tuple
from logging.handlers import RotatingFileHandler
from google.genai import types
from google import genai

# Third-party library imports
import aiolimiter
import anthropic
from openai import AsyncOpenAI
from tqdm.asyncio import tqdm_asyncio
import yaml
import requests
import base64
from pprint import pprint
import argparse

# Type alias definitions
ModelInput = Dict[
    str, Union[str, List[str]]
]  # Dictionary type containing system_input, user_input and images_url_list
ModelResponse = Dict[str, Any]  # Model response dictionary type
ModelConfig = Dict[str, Dict[str, Any]]  # Model configuration dictionary type
ModelClients = Dict[
    str, List[Union[anthropic.AsyncAnthropic, AsyncOpenAI, genai.Client]]
]  # Model client dictionary type
ModelIterators = Dict[str, itertools.cycle]  # Model iterator dictionary type


def setup_logger(output_dir: str) -> logging.Logger:
    """Configure logger

    Creates a logger that outputs to both file and console.
    File logging uses RotatingFileHandler, supporting log file rotation.

    Log format:
        timestamp - log level - message content
        Example: 2024-02-16 17:57:13,456 - INFO - Starting task execution

    Args:
        output_dir: Log file output directory

    Returns:
        Configured logger

    Configuration details:
        - Log file: execution.log
        - Single log file size limit: 10MB
        - Number of files to keep: 5
        - Log level: INFO
        - Character encoding: UTF-8
    """
    logger = logging.getLogger("model_call")
    logger.setLevel(logging.INFO)

    # Clear existing handlers
    if logger.handlers:
        logger.handlers.clear()

    # Log format
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # File handler (supports log rotation)
    log_file = os.path.join(output_dir, "execution.log")
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


@dataclass
class Config:
    """Configuration class, managing all runtime parameters for model invocation

    This class is responsible for managing all runtime configuration, including:
    - Basic configuration: file path, output directory, etc.
    - Runtime parameters: RPM limit, batch size, etc.
    - Model configuration: model parameters loaded from configuration file

    Attributes:
        model_config_path (str): Path to model configuration file
        output_root (str): Root directory for output files
        model_name (str): Model name to use
        qa_file_path (str): QA dataset file path
        eval_data_root_dir (str): Root directory for evaluation data
        rpm (int): Maximum requests per minute limit
        max_no_improve_round_count (int): Maximum allowed consecutive rounds without improvement
        batch_size (Optional[int]): Batch size, None or negative means no limit, positive means process task count
        model_config (Dict): Model configuration data, loaded in __post_init__
    """

    # Basic configuration
    model_config_path: str
    output_root: str
    model_name: str
    qa_file_path: str
    eval_data_root_dir: str = (
        "/home/l/MyCode/MultiModal/05-evaluation/results/MultiFinance"
    )

    # Runtime parameters
    rpm: int = 60
    max_no_improve_round_count: int = 3
    batch_size: Optional[int] = None  # None or negative means no limit, positive means process task count

    def __post_init__(self) -> None:
        """Initialize configuration

        - Create necessary output directories
        - Load model configuration file

        Raises:
            FileNotFoundError: When model configuration file does not exist
        """
        os.makedirs(self.output_root, exist_ok=True)
        self._load_model_config()

    def _load_model_config(self) -> None:
        """Load model configuration file

        Raises:
            FileNotFoundError: When configuration file does not exist
        """
        try:
            with open(self.model_config_path, "r", encoding="utf-8") as f:
                self.model_config = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file {self.model_config_path} not found")

    def create_output_dirs(
        self, model_name: str, dataset_name: str = ""
    ) -> Dict[str, str]:
        """Create output directory structure for model run

        Create separate directory for each run with timestamp, containing rounds subdirectory for storing results for each round.
        Directory format: model_name/timestamp_dataset_name/

        Args:
            model_name: Model name
            dataset_name: Dataset name, default empty string

        Returns:
            Dictionary containing base and rounds directory paths
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # If dataset name is provided, add as suffix
        if dataset_name:
            # Remove file extension and get base name
            dataset_basename = os.path.splitext(os.path.basename(dataset_name))[0]
            dir_name = f"{timestamp}_{dataset_basename}"
        else:
            dir_name = timestamp

        output_dir = os.path.join(self.output_root, model_name, dir_name)
        rounds_dir = os.path.join(output_dir, "rounds")

        os.makedirs(rounds_dir, exist_ok=True)
        return {"base": output_dir, "rounds": rounds_dir}

    def get_model_config(self, model_name: str) -> Dict[str, Any]:
        """Get specified model configuration information

        Args:
            model_name: Model name

        Returns:
            Model configuration information

        Raises:
            ValueError: When specified model name does not exist
        """
        if model_name not in self.model_config:
            raise ValueError(f"Unknown model name: {model_name}")
        return self.model_config[model_name]


def initialize_model_clients(
    config_path: str, model_name_list: List[str] = []
) -> Tuple[ModelConfig, ModelClients, ModelIterators]:
    """Load model configuration and initialize model clients and iterators

    Args:
        config_path: Configuration file path
        model_name_list: List of model names to load, empty means load all models

    Returns:
        Tuple[ModelConfig, ModelClients, ModelIterators]: Tuple containing:
            - model_config: Model configuration dictionary
            - model_clients: Model client dictionary
            - model_iterators: Model iterator dictionary

    Raises:
        FileNotFoundError: When configuration file does not exist
        ValueError: When API style is not supported
    """
    # Load model configuration
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            model_config = json.load(f)
    except FileNotFoundError:
        print(f"Configuration file {config_path} not found, program exits")
        exit(1)

    # Create model client dictionary and iterator dictionary
    model_clients = {}
    model_iterators = {}

    # If model_name_list is not empty, only process models in the list
    models_to_process = model_name_list if model_name_list else model_config.keys()

    # Create corresponding client list for each model
    for model_name in models_to_process:
        if model_name not in model_config:
            print(f"Warning: Model {model_name} does not exist in configuration file, will be skipped")
            continue

        model_info = model_config[model_name]
        clients_config = model_info.get("clients", [])
        if not clients_config:
            print(f"Warning: Model {model_name} does not have clients configuration, will be skipped")
            continue

        model_clients[model_name] = []

        for client_config in clients_config:
            api_key = client_config.get("api_key")
            if not api_key:
                print(f"Warning: Some client of model {model_name} does not have api_key configuration, will be skipped")
                continue

            if model_info["api_style"] == "claude":
                client = anthropic.AsyncAnthropic(api_key=api_key)
            elif model_info["api_style"] == "google":
                client = genai.Client(api_key=api_key)
            elif model_info["api_style"] == "openai" or model_info["api_style"] == "grok":
                base_url = client_config.get("base_url") or model_info.get(
                    "base_url_default", "https://api.openai.com/v1"
                )
                client = AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url,
                )
            else:
                raise ValueError(f"Unsupported API style: {model_info['api_style']}")
            model_clients[model_name].append(client)

        if model_clients[model_name]:
            # Print model client situation
            print(f"Model {model_name} initialization completed:")
            print(f"  - API style: {model_info['api_style']}")
            print(f"  - Client count: {len(model_clients[model_name])}")

            # Create loop iterators
            model_iterators[model_name] = itertools.cycle(model_clients[model_name])

    return model_config, model_clients, model_iterators


async def create_model_messages_parts(
    model_input: ModelInput, api_style: str
) -> List[Dict[str, Any]]:
    """Create model messages

    Args:
        model_input: Dictionary containing system_input, user_input, and images_url_list input
        api_style: Model API style, "claude" or "openai" or "google"

    Returns:
        List of model messages
    """
    if api_style == "openai":
        user_content = [
            {
                "type": "image_url",
                "image_url": {"url": image_url},
            }
            for image_url in model_input["images_url_list"]
        ]
        user_content.append(
            {
                "type": "text",
                "text": model_input["user_input"],
            }
        )
        messages = [
            {
                "role": "system",
                "content": model_input["system_input"],
            },
            {"role": "user", "content": user_content},
        ]
        return messages
    elif api_style == "google":
        def encode_image_from_url(image_url):
            image = requests.get(image_url)
            image_part = types.Part.from_bytes(data=image.content, mime_type="image/jpeg")
            return image_part
        
        system_content = types.GenerateContentConfig(
            system_instruction=model_input["system_input"]
        )
        user_content = [ encode_image_from_url(image_url) for image_url in model_input["images_url_list"]]
        user_content.append(model_input["user_input"])
        messages = [
            {
                "system_content": system_content,
                "user_content": user_content,
            }
        ]
        return messages
    elif api_style == "grok":
        def encode_image_from_url(image_url):
            response = requests.get(image_url)
            response.raise_for_status()
            encoded_string = base64.b64encode(response.content).decode("utf-8")
            return encoded_string
        
        user_content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{encode_image_from_url(image_url)}",
                    "detail": "high",
                },
            }
            for image_url in model_input["images_url_list"]
        ]
        user_content.append(
            {
                "type": "text",
                "text": model_input["user_input"],
            }
        )
        messages = [
            {
                "role": "system",
                "content": model_input["system_input"],
            },
            {"role": "user", "content": user_content},
        ]
        return messages
    else:
        raise ValueError(f"Unsupported API style: {api_style}")


async def create_final_result_item(
    model_raw_response: Any, original_data: Dict[str, Any], api_style: str
) -> ModelResponse:
    question_id = original_data["question_id"] if "question_id" in original_data else ""
    ground_truth = (
        original_data["ground_truth"] if "ground_truth" in original_data else None
    )
    question = original_data["question"] if "question" in original_data else ""
    context = original_data["context"] if "context" in original_data else ""

    if api_style == "openai" or api_style == "grok":
        return {
            "question_id": question_id,
            "question": question,
            "context": context,
            "output": model_raw_response.choices[0].message.content,
            "completion_tokens": (
                model_raw_response.usage.completion_tokens
                if model_raw_response.usage
                else 0
            ),
            "ground_truth": ground_truth,
            "execution_outcome": {"is_success": True},
            "original_data": original_data,
            "model_raw_response": model_raw_response.model_dump_json(),
        }
    elif api_style == "google":
        return {
            "question_id": question_id,
            "question": question,
            "context": context,
            "output": model_raw_response.candidates[0].content.parts[0].text,
            "completion_tokens": (
                model_raw_response.usage_metadata.candidates_token_count
                if model_raw_response.usage_metadata
                else 0
            ),
            "ground_truth": ground_truth,
            "execution_outcome": {"is_success": True},
            "original_data": original_data,
            "model_raw_response": model_raw_response.model_dump_json(),
        }
    elif api_style == "claude":
        return {
            "question_id": question_id,
            "question": question,
            "context": context,
            "output": model_raw_response.content[0].text,
            "completion_tokens": (
                model_raw_response.usage.completion_tokens
                if model_raw_response.usage
                else 0
            ),
            "ground_truth": ground_truth,
            "execution_outcome": {"is_success": True},
            "original_data": original_data,
            "model_raw_response": model_raw_response.model_dump_json(),
        }
    else:
        raise ValueError(f"Unsupported API style: {api_style}")


async def process_one_task(
    combined_input: Dict[str, Any],
    model_name: str,
    model_iterators: ModelIterators,
    model_config: ModelConfig,
    limiter: Optional[aiolimiter.AsyncLimiter] = None,
    info_to_print: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> ModelResponse:
    """Process single model invocation task

    Execute corresponding API call based on model type (Claude/OpenAI/Google), supporting rate limit and log recording.

    Args:
        combined_input: Dictionary containing model_input and original_data
            - model_input: Dictionary containing system_input, user_input, and images_url_list
            - original_data: All fields from original dataset
        model_name: Model name
        model_iterators: Model iterator dictionary
        model_config: Model configuration dictionary
        limiter: Rate limiter
        info_to_print: Task information for log output
        logger: Logger

    Returns:
        Dictionary containing model response, execution result, and original data

    Note:
        - Successful response format: {
            "model_raw_response": response,
            "execution_outcome": {"is_success": True},
            "original_data": original_data
          }
        - Failed response format: {
            "model_raw_response": None,
            "execution_outcome": {"is_success": False, "error_message": str},
            "original_data": original_data
          }
    """
    if limiter:
        await limiter.acquire()

    try:
        client = next(model_iterators[model_name])
        api_style = model_config[model_name]["api_style"]

        # Create model messages
        messages = await create_model_messages_parts(
            combined_input["model_input"], api_style
        )

        # Call model based on API type, actual model call function
        model_raw_response = await _call_model_api(
            client, model_name, messages, api_style
        )

        return await create_final_result_item(
            model_raw_response, combined_input["original_data"], api_style
        )

    except Exception as e:
        error_msg = f"★★★Task Info: {info_to_print or 'Nothing'}.\tError Call {model_name}.\tDetails:{str(e)}"
        if logger:
            logger.error(error_msg)
        else:
            print(error_msg)
        return {
            "model_raw_response": None,
            "execution_outcome": {"is_success": False, "error_message": str(e)},
            "original_data": combined_input["original_data"],  # Add original data
        }


async def _call_model_api(
    client: Union[anthropic.AsyncAnthropic, AsyncOpenAI, genai.Client],
    model_name: str,
    messages: List[Dict[str, Any]],
    api_style: str,
) -> Any:
    """Execute model API call

    Args:
        client: Model client (supports Claude/OpenAI/Google type)
        model_name: Model name
        messages: Message list
        api_style: API type ("claude"/"openai"/"google")

    Returns:
        Any: Model response object, specific type depends on API type

    Raises:
        ValueError: When API type is not supported
    """

    if api_style == "openai" or api_style == "grok":
        return await client.chat.completions.create(
            model=model_name,
            messages=messages,
        )
    elif api_style == "google":
        # pprint(messages[0]["system_content"])
        # pprint(messages[0]["user_content"])
        return client.models.generate_content(
            model=model_name,
            config=messages[0]["system_content"],
            contents=messages[0]["user_content"],
        )
    elif api_style == "claude":
        return await client.messages.create(
            model=model_name,
            messages=messages,
        )
    else:
        raise ValueError(f"Unsupported API style: {api_style}")


async def _process_round(
    pending_indices: List[int],
    model_input_list: List[ModelInput],
    model_name: str,
    limiter: aiolimiter.AsyncLimiter,
    round_count: int,
    logger: logging.Logger,
    model_iterators: ModelIterators,
    model_config: ModelConfig,
) -> Tuple[List[ModelResponse], List[int], bool]:
    """Process single request round

    Args:
        pending_indices: List of pending task indices to process
        model_input_list: Model input list
        model_name: Model name
        limiter: Rate limiter
        round_count: Current round count
        logger: Logger
        model_iterators: Model iterator dictionary
        model_config: Model configuration dictionary

    Returns:
        Tuple[List[ModelResponse], List[int], bool]: Tuple containing:
            - current_round_results: Current round results list
            - new_pending_indices: New pending task indices list
            - has_improvement: Whether there is improvement
    """
    # Create task list for this round, based on pending_indices, create tasks one by one
    async_task_list = []
    for index in pending_indices:
        task_info = f"Round {round_count}, Task {index + 1} of {len(model_input_list)}"
        async_task_list.append(
            process_one_task(
                model_input_list[index],
                model_name,
                model_iterators,
                model_config,
                limiter,
                info_to_print=task_info,
                logger=logger,
            )
        )

    # Execute all tasks for this round
    current_round_results = await tqdm_asyncio.gather(*async_task_list)

    # Process results
    new_pending_indices = []
    has_improvement = False
    for task_index in pending_indices:
        result = current_round_results[pending_indices.index(task_index)]
        if not result["execution_outcome"]["is_success"]:
            new_pending_indices.append(task_index)
        else:
            has_improvement = True

    return current_round_results, new_pending_indices, has_improvement


def _save_round_results(
    output_dir: str,
    round_count: int,
    round_info: Dict[str, Any],
    current_results: List[ModelResponse],
    pending_indices: List[int],
    final_results: List[Optional[ModelResponse]],
    is_final: bool = False,
) -> None:
    """Save round results

    Args:
        output_dir: Output directory
        round_count: Round count
        round_info: Round information
        current_results: Current round results
        pending_indices: Pending task indices list
        final_results: Cumulative results list
        is_final: Whether it is final round
    """
    round_result = {
        "round_info": round_info,
        "current_round_results": {
            str(idx): result for idx, result in zip(pending_indices, current_results)
        },
        "cumulative_results": {
            str(i): result
            for i, result in enumerate(final_results)
            if result is not None
        },
    }

    # Build filename
    filename = f"round_{round_count:03d}"
    if is_final:
        filename += "_final"
    filename += ".json"

    # Save file
    round_file = os.path.join(output_dir, filename)
    with open(round_file, "w", encoding="utf-8") as f:
        json.dump(round_result, f, ensure_ascii=False, indent=4)


def _generate_statistics(
    final_results: List[ModelResponse], round_count: int, logger: logging.Logger
) -> Dict[str, Any]:
    """Generate execution statistics information

    Args:
        final_results: Final results list
        round_count: Total round count
        logger: Logger

    Returns:
        Statistics dictionary
    """
    total_requests = len(final_results)
    success_count = sum(
        1 for result in final_results if result["execution_outcome"]["is_success"]
    )
    failed_count = total_requests - success_count

    # Collect error statistics
    error_statistics = {}
    if failed_count > 0:
        for result in final_results:
            if not result["execution_outcome"]["is_success"]:
                error_message = result["execution_outcome"]["error_message"]
                key_error = error_message.split("\n")[0]
                error_statistics[key_error] = error_statistics.get(key_error, 0) + 1

    # Print statistics information
    logger.info("Execution result statistics:")
    logger.info(f"Total requests: {total_requests}")
    logger.info(
        f"Successful requests: {success_count} ({(success_count/total_requests*100):.2f}%)"
    )

    if error_statistics:
        logger.info(
            f"Failed requests: {failed_count} ({(failed_count/total_requests*100):.2f}%)"
        )
        logger.info("Error type statistics:")
        sorted_errors = sorted(
            error_statistics.items(), key=lambda x: x[1], reverse=True
        )
        for error_type, count in sorted_errors:
            logger.info(
                f"  - {error_type}: {count} times ({(count/failed_count*100):.2f}%)"
            )

    # Build statistics information dictionary
    return {
        "execution_summary": {
            "total_requests": total_requests,
            "success_count": success_count,
            "success_rate": f"{(success_count/total_requests*100):.2f}%",
            "failed_count": failed_count,
            "failure_rate": f"{(failed_count/total_requests*100):.2f}%",
            "total_rounds": round_count,
        },
        "error_statistics": (
            {
                error_type: {
                    "count": count,
                    "percentage": f"{(count/failed_count*100):.2f}%",
                }
                for error_type, count in sorted_errors
            }
            if error_statistics
            else {}
        ),
    }


async def _save_inference_file(
    qa_file_path: str,
    model_name: str,
    results: List[ModelResponse],
    logger: logging.Logger,
    eval_data_root_dir: str,
) -> None:
    """Create evaluation directory structure and save inference results

    Args:
        qa_file_path: Dataset file path
        model_name: Model name
        results: Model output results list
        logger: Logger
        eval_data_root_dir: Root directory for evaluation data
    """
    try:
        # Extract directory name from dataset path
        dataset_name = os.path.splitext(os.path.basename(qa_file_path))[0]

        # Parse directory structure
        parts = dataset_name.split("_")
        if len(parts) >= 2:  # Ensure at least dataset and prompt two parts
            dataset_dir = parts[0] + "_" + parts[1]
            prompt_type = parts[2]

            # Build evaluation directory path
            eval_dir = os.path.join(
                eval_data_root_dir, dataset_dir, prompt_type, model_name
            )
            os.makedirs(eval_dir, exist_ok=True)

            # Save inference.json
            inference_file = os.path.join(eval_dir, "inference.json")
            with open(inference_file, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=4)

            logger.info(f"Evaluation directory structure created and inference.json saved: {inference_file}")
    except Exception as e:
        logger.error(f"Error occurred when creating evaluation directory structure: {str(e)}")


async def async_generate_model_output_list(
    model_input_list: List[ModelInput],
    config: Config,
) -> List[ModelResponse]:
    """Asynchronously generate model output list

    This function ensures all requests are processed through multiple rounds of retries until the termination condition is met. Each round's results are saved,
    and processing stops when the maximum retry count is reached or all requests are successful.

    Main functions:
    1. Create output directory and logger
    2. Set rate limit
    3. Loop through requests until termination condition is met
    4. Save each round results and statistics

    Args:
        model_input_list: Model input list
        config: Running configuration instance

    Returns:
        List of all request results

    Raises:
        ValueError: When model has no available clients
    """
    # Initialize model clients
    MODEL_CONFIG, MODEL_CLIENTS, MODEL_ITERATORS = initialize_model_clients(
        config.model_config_path
    )

    # Create output directory
    output_dirs = config.create_output_dirs(config.model_name, config.qa_file_path)
    logger = setup_logger(output_dirs["base"])

    # Check and set rate limit
    client_count = len(MODEL_CLIENTS[config.model_name])
    if client_count == 0:
        raise ValueError(f"Model {config.model_name} has no available clients")

    # Calculate available RPM for each client
    per_client_rpm = max(1, int(config.rpm / client_count))
    # Calculate actual total RPM
    actual_total_rpm = per_client_rpm * client_count
    # Create rate limiter
    limiter = aiolimiter.AsyncLimiter(1, 60.0 / actual_total_rpm)

    # Record RPM configuration
    logger.info(f"=====================================")
    logger.info(f"Model {config.model_name} RPM allocation:")
    logger.info(f"  - User set total RPM: {config.rpm}")
    logger.info(f"  - Client count: {client_count}")
    logger.info(f"  - RPM for each client: {per_client_rpm}")
    logger.info(f"  - Actual total RPM: {actual_total_rpm}")
    logger.info(f"  - Output directory: {output_dirs['base']}")
    logger.info(f"=====================================")

    # Process batch_size, if batch_size is set, only process the first batch_size tasks, if batch_size is illegal, no limit
    if config.batch_size is not None and 0 < config.batch_size <= len(model_input_list):
        model_input_list = model_input_list[: config.batch_size]

    # Initialize state
    final_results = [None] * len(model_input_list)
    pending_indices = list(range(len(model_input_list)))  # List of pending task indices
    round_count = 0
    no_improve_count = 0

    # Main processing loop
    while pending_indices:
        round_count += 1
        logger.info(
            f"Starting {round_count}th round request, pending task count: {len(pending_indices)}"
        )

        # Process current round
        current_results, new_pending_indices, has_improvement = await _process_round(
            pending_indices,
            model_input_list,
            config.model_name,
            limiter,
            round_count,
            logger,
            MODEL_ITERATORS,
            MODEL_CONFIG,
        )

        # Update results
        for task_index, result in zip(pending_indices, current_results):
            if result["execution_outcome"]["is_success"]:
                final_results[task_index] = result

        # Prepare round information
        round_info = {
            "round_number": round_count,
            "total_tasks": len(model_input_list),
            "pending_tasks": len(pending_indices),
            "successful_tasks": len(pending_indices) - len(new_pending_indices),
            "remaining_tasks": len(new_pending_indices),
            "has_improvement": has_improvement,
            "no_improve_count": no_improve_count,
        }

        # Save round results
        _save_round_results(
            output_dirs["rounds"],
            round_count,
            round_info,
            current_results,
            pending_indices,
            final_results,
        )

        # Update no improvement count
        if not has_improvement:
            no_improve_count += 1
            logger.warning(f"★★★Continuous {no_improve_count} rounds without successful new requests")
        else:
            no_improve_count = 0

        # Check termination condition
        if no_improve_count >= config.max_no_improve_round_count:
            logger.warning(f"★★★Continuous {no_improve_count} rounds without successful new requests, stop retrying")
            # Record remaining failed results
            for idx in new_pending_indices:
                final_results[idx] = current_results[pending_indices.index(idx)]

            # Save final round results
            round_info.update(
                {
                    "is_final_round": True,
                    "termination_reason": "max_no_improve_round_count_reached",
                }
            )
            _save_round_results(
                output_dirs["rounds"],
                round_count,
                round_info,
                current_results,
                pending_indices,
                final_results,
                is_final=True,
            )
            break

        pending_indices = new_pending_indices

    logger.info(f"All requests completed, {round_count} rounds requested")

    # Generate and save statistics information
    statistics = _generate_statistics(final_results, round_count, logger)
    statistics_file = os.path.join(output_dirs["base"], "execution_statistics.json")
    with open(statistics_file, "w", encoding="utf-8") as f:
        json.dump(statistics, f, ensure_ascii=False, indent=4)

    # Save final results
    final_results_file = os.path.join(output_dirs["base"], "final_results.json")
    with open(final_results_file, "w", encoding="utf-8") as f:
        json.dump(final_results, f, ensure_ascii=False, indent=4)

    # Create evaluation directory structure and save inference.json
    await _save_inference_file(
        config.qa_file_path,
        config.model_name,
        final_results,
        logger,
        config.eval_data_root_dir,
    )

    return final_results


def make_args():
    """Parse command line parameters"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True, help="Path to configuration file")
    return parser.parse_args()


async def main(yaml_path: str):
    """Main function, responsible for reading configuration file and executing model invocation process"""
    # Load YAML configuration file
    with open(yaml_path, "r", encoding="utf-8") as f:
        config_dict = yaml.safe_load(f)

    # Create configuration instance
    custom_config = Config(**config_dict)

    # Load data
    with open(custom_config.qa_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Extract required fields from dataset while retaining original data
    model_input_list = []
    for item in data:
        # Extract input fields required for model
        model_input = {
            "system_input": item["system_input"],
            "user_input": item["user_input"],
            "images_url_list": item["images"],
        }
        # Combine original data and model input
        combined_input = {
            "model_input": model_input,
            "original_data": item,  # Retain all fields of original data
        }
        model_input_list.append(combined_input)

    # Call model generation function
    await async_generate_model_output_list(
        model_input_list=model_input_list,
        config=custom_config,
    )


if __name__ == "__main__":
    # Replace original yaml_path hardcoding
    args = make_args()
    asyncio.run(main(args.config))

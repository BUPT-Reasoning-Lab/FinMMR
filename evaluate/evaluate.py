import json
import os
import argparse
import multiprocessing
from tqdm import tqdm
from loguru import logger
from utils.config import EvaluationConfig
from utils.llm import LLM 
from utils.evaluation_utils import (
    extract_cot_answers, 
    extract_pot_answers,
    get_acc,
)
from multiprocessing import Process, Queue

def get_statistics(data):
    total_acc = 0
    total_execution = 0
    total_tokens = 0
    for record in data:
        total_acc += record["result"]["acc"]
        total_execution += record["result"]["execution_rate"]
        total_tokens += record["completion_tokens"]
    return {
        "avg_accuracy": round(total_acc / len(data) * 100, 2),
        "avg_execution_rate": round(total_execution / len(data) * 100, 2),
        "total_tokens": total_tokens
    }

def eval_cot(
    data, 
    ans_extract_model: LLM, 
    eval_data = None,
    force_extract_answer: bool = False
):

    def vailid(output: str):
        return output and "none" not in output.lower()
    extract_answer = force_extract_answer or eval_data is None
    if extract_answer:
        responses = extract_cot_answers(data, ans_extract_model)
        to_retry = [
            idx for idx, response in enumerate(responses) 
            if not vailid(response['output'])
        ]
        if len(to_retry) > 0:
            retry_responses = extract_cot_answers([data[i] for i in to_retry], ans_extract_model)
            for idx, response in enumerate(retry_responses):
                responses[to_retry[idx]] = response
    for idx, record in tqdm(enumerate(data), desc="Evaluating COT"):
        if extract_answer:
            extracted_answer = responses[idx]['output']
        else:
            assert eval_data[idx]["question_id"] == record["question_id"]
            extracted_answer = eval_data[idx]['result']['extracted_answer']
        eval_result = { "execution_rate": 0, "acc": 0, "extracted_answer": None }
        if vailid(extracted_answer):
            eval_result = { 
                "execution_rate": 1, 
                "acc": get_acc(extracted_answer, record["ground_truth"]),
                "extracted_answer": extracted_answer
            }
        record["result"] = eval_result

    statistics = get_statistics(data)

    return data, statistics

def empty_print(*args, **kwargs):
    pass
    
def run_code_in_process(code, result_queue):
    try:
        namespace = {"print": empty_print}
        exec(code, namespace)
        result = namespace["solution"]()
        result_queue.put(("success", result))
    except Exception as e:
        result_queue.put(("error", str(e)))

def exec_code_with_timeout(code, timeout_duration):
    result_queue = Queue()
    process = Process(target=run_code_in_process, args=(code, result_queue))
    process.start()
    try:
        status, result = result_queue.get(timeout=timeout_duration)
        if status == "error":
            raise Exception(result)
        return result
    except multiprocessing.queues.Empty:
        raise Exception("Code execution took too long!")
    except Exception : raise
    finally: process.kill()

def eval_pot( data, timeout_duration: int):

    for record in tqdm(data, desc="Evaluating POT"):
        code = extract_pot_answers(record['output'])
        record["result"] = { "acc": 0, "execution_rate": 0, "executed_result": None }
        try:
            executed_result = exec_code_with_timeout(code, timeout_duration)
        except Exception as e:
            logger.warning(f"Error while executing code: {e}")
            continue
        record["result"] = {
            "acc": get_acc(executed_result, record["ground_truth"]),
            "execution_rate": 1,
            "executed_result": str(executed_result)
        }

    statistics = get_statistics(data)
    return data, statistics


def make_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True)
    return parser.parse_args()

def main():
    args = make_args()
    config = EvaluationConfig.from_yaml(args.config)
    data = json.load(open(config.inference_file, "r", encoding="utf-8"))
    
    print(os.path.abspath(config.evaluation_file))

    if 'cot' in config.prompt_type:
        eval_data = None
        if os.path.exists(config.evaluation_file):
            print(f"Loading evaluation data from {config.evaluation_file}")
            with open(config.evaluation_file, "r", encoding="utf-8") as f:
                eval_data = json.load(f)
                
        ans_extract_model = LLM(config.llms[config.ans_extract_model_name])
        force_extract_answer = config.force_extract_answer
        data, statistics = eval_cot(data, ans_extract_model, eval_data, force_extract_answer)
    elif 'pot' in config.prompt_type:
        data, statistics = eval_pot(data, config.timeout_duration)

    logger.info(f"Statistics: {statistics}")

    with open(config.evaluation_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    

if __name__ == "__main__":
    main()

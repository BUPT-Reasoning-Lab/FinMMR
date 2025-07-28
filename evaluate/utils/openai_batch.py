from openai import OpenAI
import json
from loguru import logger
import argparse
import os

def format_openai_response(response):
    if response:
        content = response["choices"][0]["message"]["content"]
        completion_tokens = response["usage"]["completion_tokens"]
        reasoning_content = response["choices"][0]["message"].get("reasoning_content", None)
        return { "output": content, "reasoning_content": reasoning_content, "completion_tokens": completion_tokens}
    else: return { "output": None, "reasoning_content": None, "completion_tokens": None }

def process_batch_results(
    dataset: str,
    model: str,
    prompt: str,
    subset: str
):
    prefix = f'{dataset}_{subset}_{prompt}_{model}'
    with open(os.path.join("batch", "output", f'{prefix}_batch_results.jsonl'), 'r') as file:
        data = [json.loads(line) for line in file]
    with open(os.path.join("data", dataset, f"{subset}.json"), "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    result_prefix = os.path.join("results", dataset, subset, prompt, model)
    os.makedirs(result_prefix, exist_ok=True)
    output_data = []
    for item in data:
        idx = int(item["custom_id"])
        output = format_openai_response(item['response']['body'])
        result = {
            **raw_data[idx],
            **output
        }
        output_data.append(result)
    with open(os.path.join(result_prefix, "inference.json"), "w", encoding="utf-8") as file:
        json.dump(output_data, file, indent=4, ensure_ascii=False)

def prepare_data(
    dataset: str, 
    subset: str, 
    prompt: str, 
    model: str
):
    prefix = f'{dataset}_{subset}_{prompt}_{model}'
    with open(f'{prefix}_prompts.json', 'r') as file:
        prompts = json.load(file)
    bath_input_dir = os.path.join("./batch", "input")
    os.makedirs(bath_input_dir, exist_ok=True)
    with open(os.path.join(bath_input_dir, f'{prefix}_batch.jsonl'), 'w') as file:
        for i in range(len(prompts)):
            item = {
                "custom_id": str(i),
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": model,
                    "messages": prompts[i]
                }
            }
            file.write(json.dumps(item) + '\n')

def upload_file(
    client: OpenAI, 
    dataset: str, 
    subset: str, 
    prompt: str, 
    model: str
):
    prefix = f'{dataset}_{subset}_{prompt}_{model}'
    bath_input_dir = os.path.join("./batch", "input")
    file = client.files.create(
        file=open(os.path.join(bath_input_dir, f'{prefix}_batch.jsonl'), 'rb'),
        purpose='batch'
    )
    batch = client.batches.create(
        input_file_id=file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={ "description": f"{prefix}_batch" }
    )
    return batch

def download_file(
    client: OpenAI, 
    batch_id: str, 
    dataset: str, 
    subset: str, 
    prompt: str, 
    model: str
):
    prefix = f'{dataset}_{subset}_{prompt}_{model}'
    batch = client.batches.retrieve(batch_id)
    if batch.status != "completed":
        raise ValueError(f"Batch {batch_id} is not completed")
    file = client.files.retrieve(batch.output_file_id)
    bath_output_dir = os.path.join("./batch", "output")
    with open(os.path.join(bath_output_dir, f'{prefix}_batch_results.jsonl'), 'w') as file:
        file.write(file.content)

def make_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, required=True)
    parser.add_argument("--subset", type=str, required=True)
    parser.add_argument("--prompt", type=str, required=True)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--api_key", type=str, required=True)
    parser.add_argument("--base_url", type=str, required=True)
    return parser.parse_args()


def main():
    args = make_args()
    client = OpenAI(api_key=args.api_key, base_url=args.base_url)
    prepare_data(args.dataset, args.subset, args.prompt, args.model)
    """
    You can check the batch status on openai dashboard.
    https://platform.openai.com/batches
    """
    batch = upload_file(client, args.dataset, args.subset, args.prompt, args.model)
    logger.info(f"Batch {batch.id} is created")
    """
    Or you can download the results from openai dashboard.
    https://platform.openai.com/batches
    """
    # download_file(client, batch.id, args.model, args.prompt, args.subset)
    # process_batch_results(args.dataset, args.model, args.prompt, args.subset)
if __name__ == '__main__':
    main()






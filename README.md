## FinMMR

The data and code for the paper `FinMMR: Make Financial Numerical Reasoning More Multimodal, Comprehensive, and Challenging`.

**FinMMR** is a novel bilingual multimodal benchmark tailored to evaluate the reasoning capabilities of multimodal large language models (MLLMs) in financial numerical reasoning tasks.  

## FinMMR Dataset
Based on the difficulty of reasoning, we divided the problems into three subsets: *Easy* (1,500 examples), *Medium* (1,500 examples), and *Hard* (1,300 examples). 

The dataset is provided in json format and contains the following attributes at the `data` directory:

```json
{
    "question_id": "[string] Unique identifier for the question",
    "question": "[string] The question text, typically a financial data analysis problem",
    "python_solution": "[string] Python solution code written by financial experts, with clear variable names and execution logic",
    "ground_truth": "[number] The standard answer, typically the result of executing the Python solution",
    "source": "[string] Source identifier of the question",
    "source_id": "[string] Question identifier in the original dataset",
    "subfield": "[string] Financial subfield of the question (e.g., industry, market, macro)",
    "statistics": {
        "number_statistics": "[object] Statistics about numbers, including count of numbers in the question",
        "operator_statistics": "[object] Statistics about operator usage, tracking frequency of different operators",
        "code_statistics": "[object] Code-related statistics, such as number of code lines and parentheses count"
    },
    "difficulty": "[float] Difficulty coefficient of the question, higher values indicate greater difficulty",
    "images": "[array] List of all image URLs related to the question",
    "ground_images": "[array] List of essential image URLs needed to solve the question",
    "context": "[string] Background information for the question",
    "grade": "[string] Difficulty level classification of the question (e.g., Hard)",
    "language": "[string] Language of the question (Chinese or English)",
    "system_input": "[string] System prompt provided to the model",
    "user_input": "[string] User prompt provided to the model"
}
```

The images used in FinMMR are provided at the `images` directory.

## Financial Functions Library

The financial functions library is a collection of financial functions that are used to solve the financial numerical reasoning problems. It is provided in json format and contains the following attributes at the `data/functions` directory:

```json
{
    "function_id": "[string] Unique identifier for the function",
    "function": "[string] The function code",
    "function_docstring": "[string] The docstring of the function"
}
```

## Financial Documents Library

The financial documents library is a collection of financial documents that are used to solve the financial numerical reasoning problems. It is provided in json format and contains the following attributes at the `data/documents` directory:

```json
{
    "document_id": "[string] Unique identifier for the document",
    "document": "[string] The document text",
    "document_docstring": "[string] The docstring of the document"
}
```

## Experiments

### Directory Structure

```
.
├── data/                           # Data directory
│   ├── easy_validation_*.json     # CoT&PoT Prompts for easy difficulty validation subset
│   ├── easy_test_*.json           # CoT&PoT Prompts for easy difficulty test subset
│   ├── medium_validation_*.json   # CoT&PoT Prompts for medium difficulty validation subset
│   ├── medium_test_*.json         # CoT&PoT Prompts for medium difficulty test subset
│   ├── hard_validation_*.json     # CoT&PoT Prompts for hard difficulty validation subset
│   ├── hard_test_*.json           # CoT&PoT Prompts for hard difficulty test subset
│   ├── validation/       # Validation subset
|      ├── easy_validation.json     # Easy difficulty validation subset         
|      ├── medium_validation.json   # Medium difficulty validation subset
|      └── hard_validation.json     # Hard difficulty validation subset
│   └── test/             # Test subset
|      ├── easy_test.json           # Easy difficulty test subset         
|      ├── medium_test.json         # Medium difficulty test subset
|      └── hard_test.json           # Hard difficulty test subset
│   ├── functions/        # Financial functions library
│       └──functions-article-all.json 
│   └── documents/        # Financial documents library
│       └──financial_documents.json               
│
├── inference/                      # Inference related code and configuration
│   ├── inference.py              # Main inference code
│   ├── inference.sh              # Inference execution script
│   ├── model-config.json         # Model configuration file
│   └── inference-config.yaml     # Inference configuration file
│
├── evaluate/                      # Evaluation related code
│   ├── evaluate.py              # Main evaluation script
│   ├── evaluate.sh             # Evaluation execution script
│   ├── evaluate-config.yaml    # Evaluation configuration file
│   └── utils/                  # Evaluation utility functions
│
├── results/                      # Results output directory
│   ├── inference-results/      # Model inference output results
│   └── evaluate-results/       # Evaluation metrics results
│
└── requirements.txt              # Project dependencies file
```

### Model Configuration Guide in `model-config.json`

#### Example

```json
{
    "gemini-2.0-flash": {
        "base_url_default": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "clients": [
            {
                "api_key": "AIzaxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"
            }
        ],
        "api_style": "google"
    }
}
```

#### Required Fields
- `key`: Model name, used when calling the model
- `value`: Model configuration, including:
  - `api_key`: Model API key for authentication
  - `base_url`: Base URL for API endpoint
  - `api_style`: API style/type for model interaction
  - `base_url_default`: Default base URL for API endpoint


#### API Styles
The following API styles are supported:

- `claude`: Uses the Anthropic library with image url as input
- `openai`: Uses the OpenAI library with image url as input
- `google`: Uses the Google GenAI library with image url as input
- `grok`: Uses the OpenAI library with `base64` encoded image as input


### Inference Configuration Guide in `inference-config.yaml`

The inference configuration file contains the following key settings:

```yaml
model_config_path: Path to the model configuration JSON file
output_root: Root directory for storing inference results
eval_data_root_dir: Root directory for evaluation results
max_no_improve_round_count: Maximum rounds without improvement before stopping
rpm: Rate limit for API calls (requests per minute)
batch_size: Number of examples to process in each batch, process all examples if set to -1
model_name: Name of the model to use for inference, should be the same as the model name in `model-config.json`
qa_file_path: Path to the input dataset file
```

### Evaluation Configuration Guide in `evaluate-config.yaml`

The evaluation configuration file contains two main sections:

#### Evaluation Settings
```yaml
evaluation:
  force_extract_answer: Whether to force answer extraction, set to true if you want to extract the answer from the model's response, this will cover previous answer extraction results
  timeout_duration: Timeout duration in seconds
  result_dir: Directory for storing evaluation results
  dataset: Dataset name
  ans_extract_model_name: Model name for answer extraction
  model_name: Name of the model being evaluated
  subset: Dataset subset (easy_validation/easy_test/medium_validation/medium_test/hard_validation/hard_test)
  prompt_type: Type of prompt used (cot/pot)
```

#### LLM Settings
```yaml
llms:
  ans_extract_model:
    model_id: Model identifier
    api_key: API key for authentication
    base_url: Base URL for API endpoint
    support_system_role: Whether model supports system role
    reasoner: Whether model is used for reasoning
    rpm: Rate limit (requests per minute)
    sampling_args:
      temperature: Sampling temperature
      max_tokens: Maximum tokens in response
      top_p: Top-p sampling parameter
```

### Environment Setup
You can install the dependencies by the following command:
```bash
pip install -r requirements.txt
```

### Running Inference
We support inference with various LLM models through two approaches:

1. **Configuration-based Inference**
   ```bash
   bash inference.sh
   ```
   This method uses the configuration file to specify model settings, dataset parameters, and inference options.

2. **Batch API Inference**
   ```bash
   python utils/openai_batch.py \
     --dataset "FinMMR" \
     --subset "hard" \
     --prompt "cot" \
     --model "your_model_id" \
     --api_key "your_api_key" \
     --base_url "your_base_url"
   ```
   This method allows you to get 50% discount on the openai inference cost.


### Running Evaluate
Evaluate model performance using:
```bash
bash evaluate.sh
```

### Model Output
The inference and evaluation results will be saved in the `results` directory with the following structure:

```
results/
├── inference-results/                                  # Model inference output results
│   └── {model_name}/                                   # Organized by model name
│       └── {timestamp}_{subset name}_{prompt type}/    # Specific execution results
│           ├── execution_statistics.json               # Execution statistics
│           ├── final_results.json                      # Execution results
│           └── execution.log                           # Execution logs
│
└── evaluate-results/                                   # Evaluation results
    └── FinMMR/                                         # Dataset evaluation results
        └── {subset name}/                              # Organized by difficulty subset
            └── {prompt type}/                          # Organized by prompt type
                └── {model name}/                       # Organized by model name
                    ├── inference.json                  # Inference results file, auto-generated by inference code
                    └── evaluation.json                 # Evaluation results file, generated by evaluation code
```

- `execution_statistics.json` contains execution success rates and other statistics
- `execution.log` records detailed execution process and timestamps
- `inference.json` stores the final model inference results

### Note
This project was developed with the assistance of modern AI-powered development tools, including Cursor IDE and Tongyi Qianwen. All code has been carefully reviewed to ensure originality and compliance with best practices. The implementation represents original work by the authors.

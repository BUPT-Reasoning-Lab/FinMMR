"""
This code is adapted from:
https://github.com/yale-nlp/FinanceMath/blob/main/utils/evaluation_utils.py

Original repository: https://github.com/yale-nlp/FinanceMath
"""

import re
from utils.llm import LLM
from loguru import logger

def within_eps(pred: float, gt: float):
    eps = abs(gt) * 0.002
    if pred >= gt - eps and pred <= gt + eps:
        return True
    else:
        return False

def is_number(string):
    pattern = r'^[-+]?(\d{1,3}(,\d{3})*|(\d+))(\.\d+)?$'
    match = re.match(pattern, string)
    return bool(match)

def is_scientific_number(string):
    pattern = r'^[-+]?\d+(\.\d+)?e[-]?\d+$'
    match = re.match(pattern, string)
    return bool(match)

def contain_num_and_str(string):
    pattern_str = r'[a-zA-Z]'
    pattern_num = r'[0-9]'
    return bool(re.search(pattern_str, string) and re.search(pattern_num, string))

def normalize(prediction: str):
    try:
        prediction = eval(prediction)
    except Exception:
    # Preprocessing the string [Stage 1]
        prediction = prediction.strip().lower()
        prediction = prediction.rstrip('.')

        for money in ["£", "€", "¥", "million", "billion", "thousand", "us", "usd", "rmb"]:
            prediction = prediction.replace(money, '')
            
        # Replace special tokens
        if '=' in prediction:
            prediction = prediction.split('=')[-1].strip()
        if '≈' in prediction:
            prediction = prediction.split('≈')[-1].strip()
        if '`' in prediction:
            prediction = prediction.replace('`', '')
        if '%' in prediction:
            prediction = prediction.replace('%', '')
        if '$' in prediction:
            prediction = prediction.replace('$', '')
        if '°' in prediction:
            prediction = prediction.replace('°', '')

        # Detect the boolean keyword in the generation
        if prediction in ['true', 'yes', 'false', 'no']:
            if prediction == 'true' or prediction == 'yes':
                prediction = 'True'
            else:
                prediction = 'False'
        if 'true' in prediction or 'false' in prediction:
            prediction = 'True' if 'true' in prediction else 'False'

        # Detect the approximation keyword
        if 'approximately' in prediction:
            prediction = prediction.replace('approximately', '').strip()
        if ' or ' in prediction:
            prediction = prediction.split(' or ')[0]

        # Drop the units before and after the number
        if re.match(r'[-+]?(?:[\d,]*\.*\d+) [^0-9 ]+$', prediction):
            prediction = re.search(r'([-+]?(?:[\d,]*\.*\d+)) [^0-9 ]+$', prediction).group(1)
        if re.match(r'[^0-9 ]+ [-+]?(?:[\d,]*\.*\d+)$', prediction):
            prediction = re.search(r'[^0-9 ]+ ([-+]?(?:[\d,]*\.*\d+))$', prediction).group(1)
        if re.match(r'[-+]?(?:[\d,]*\.*\d+)[^\d]{1,2}$', prediction):
            prediction = re.search(r'([-+]?(?:[\d,]*\.*\d+))[^\d]{1,2}$', prediction).group(1)
        if re.match(r'[^-+\d]{1,2}(?:[\d,]*\.*\d+)$', prediction):
            prediction = re.search(r'[^-+\d]{1,2}((?:[\d,]*\.*\d+))$', prediction).group(1)

        # Preprocessing the number [Stage 1]
        if '10^' in prediction:
            prediction = re.sub(r'10\^(-?\d+)', r'math.pow(10, \1)', prediction)
        if ' x ' in prediction:
            prediction = prediction.replace(' x ', '*')
        if ' × ' in prediction:
            prediction = prediction.replace(' × ', '*')
        if is_number(prediction):
            prediction = prediction.replace(',', '')

        # If the prediction is empty, use dummy '0'
        if not prediction:
            prediction = "None" 

        try:
            prediction = eval(prediction)
        except Exception:
            prediction = None

        # Check the type of the prediction

    return prediction

def get_acc(prediction, gt):
    try:
        assert isinstance(gt, (int, float, bool)), type(gt)
        if isinstance(prediction, str):
            prediction = normalize(prediction)
        if isinstance(prediction, (tuple, list)):
            prediction = prediction[0]
        if prediction is None:
            return 0
        elif isinstance(gt, bool) or isinstance(prediction, bool):
            return int(prediction == gt)
        else:
            return int(within_eps(prediction, gt))
    except Exception as e:
        logger.warning(f"Error while comparing prediction: {prediction} and ground truth: {gt}, {e}")
        return 0
    
def extract_cot_answers(data, ans_extract_model: LLM):
    system_prompt = """Extract the final answer of the question as a numeric value from the given solution. If you cannot extract an answer, return "None".

You should either return "None" or a numeric value without any additional words."""
    user_inputs = []
    for record in data:
        user_inputs.append(f"Question: {record['question']}\nSolution: {record['output']}")
    prompts = ans_extract_model.apply_chat_template(
        [system_prompt] * len(data),
        user_inputs
    )
    results = ans_extract_model.batch_generate(prompts, desc="Extracting COT answers")
    return results

def extract_pot_answers(output):
    # this heuristic is not perfect, if you have a better heuristic, please submit a PR, thanks!
    if not output or 'argparse' in output:
        return ''
    tmp = re.findall(r"```python(.*?)```", output, re.DOTALL)
    if len(tmp) > 0:
        processed_output = tmp[0].strip("\n")
    else:
        tmp = re.findall(r"```(.*?)```", output, re.DOTALL)
        if len(tmp) > 0:
            processed_output = tmp[0].strip("\n")
        else:
            tmp = re.findall(r"```", output, re.DOTALL)
            if len(tmp) == 1 and 'def solution():' not in output:
                if len(output) > 4 and output[:4] == '    ':
                    processed_output = "def solution():\n" + output.split("```")[0]
                else:
                    processed_output = "def solution():\n    " + output.split("```")[0]
            else:
                if 'def solution():' not in output and len(output) > 4 and output[:4] == '    ':
                    processed_output = "def solution():\n" + output
                elif 'def solution():' not in output:
                    processed_output = "def solution():\n    " + output
                else:
                    processed_output = output.strip()
    processed_output = processed_output.strip("```")
    processed_output = processed_output.strip()
    return processed_output
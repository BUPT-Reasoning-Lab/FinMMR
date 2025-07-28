import json
import re

def extract_code(output):
    """
    参考 extract_pot_answers 方法，从 output 中提取 Python 代码。
    """
    # 如果 output 是列表，取第一个元素
    if isinstance(output, list):
        output = output[0] if output else ''
    if not isinstance(output, str):
        return ''
    # 尝试提取代码块，首先匹配 ```python ... ```
    tmp = re.findall(r"```python(.*?)```", output, re.DOTALL)
    if len(tmp) > 0:
        processed_output = tmp[0].strip("\n")
    else:
        # 没有找到带 python 标签的代码块，则匹配 ``` ... ```
        tmp = re.findall(r"```(.*?)```", output, re.DOTALL)
        if len(tmp) > 0:
            processed_output = tmp[0].strip("\n")
        else:
            # 如果只找到一个 ``` 且 output 中没有 "def solution():"
            tmp = re.findall(r"```", output, re.DOTALL)
            if len(tmp) == 1 and 'def solution():' not in output:
                if len(output) > 4 and output[:4] == '    ':
                    processed_output = "def solution():\n" + output.split("```")[0]
                else:
                    processed_output = "def solution():\n    " + output.split("```")[0]
            else:
                # 若没有找到代码块，但 output 中不含 "def solution():"，则补全
                if 'def solution():' not in output and len(output) > 4 and output[:4] == '    ':
                    processed_output = "def solution():\n" + output
                elif 'def solution():' not in output:
                    processed_output = "def solution():\n    " + output
                else:
                    processed_output = output.strip()
    processed_output = processed_output.strip("```")
    processed_output = processed_output.strip()
    return processed_output

def extract_and_execute_code(output_obj):
    """
    提取 output 字段中的 Python 代码并执行，
    返回 solution() 函数的返回值，或者在出错时返回错误信息。
    """
    code = extract_code(output_obj)
    if not code:
        return "Error: 未找到 python 代码块"
    namespace = {}
    try:
        exec(code, namespace)
        if "solution" in namespace and callable(namespace["solution"]):
            result = namespace["solution"]()
            return result
        else:
            return "Error: 没有定义 solution 函数"
    except Exception as e:
        return f"Error: {e}"

def filter_json(input_file, output_file):
    # 读取原始 JSON 数据
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 筛选出 result 中 acc 为 0 的大字典，并提取 output 中代码的执行结果
    filtered_data = []
    for entry in data:
        if 'result' in entry and entry['result'].get('acc') == 0:
            if 'output' in entry:
                exec_result = extract_and_execute_code(entry['output'])
                entry["exec_result"] = exec_result
            filtered_data.append(entry)
    
    # 将筛选结果写入到新的 JSON 文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    filter_json('/home/lirongjin/FinanceBench/finance-reasoning-master/results/MultiFinance/easy/pot/test/qwen-omni-turbo/evaluation.json', 'output.json')

import json
import re

def is_chinese(text):
    """
    判断文本中是否包含中文字符，
    这里简单判断是否存在 Unicode 范围内的中文字符。
    """
    return re.search(r'[\u4e00-\u9fff]', text) is not None

# 读取 evaluation.json 文件
with open('/home/lirongjin/FinanceBench/finance-reasoning-master/results/MultiFinance/easy/pot/test/qwen-omni-turbo/evaluation.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 初始化统计变量
chinese_total = 0
chinese_correct = 0
english_total = 0
english_correct = 0

# 遍历每条记录进行统计
for record in data:
    question = record.get("question", "")
    # 获取评测结果中的 acc，1表示正确，0表示错误
    acc = record.get("result", {}).get("acc", 0)
    if is_chinese(question):
        chinese_total += 1
        if acc == 1:
            chinese_correct += 1
    else:
        english_total += 1
        if acc == 1:
            english_correct += 1

# 计算准确率（百分比）
chinese_accuracy = (chinese_correct / chinese_total * 100) if chinese_total > 0 else 0
english_accuracy = (english_correct / english_total * 100) if english_total > 0 else 0

print("中文题目正确率: {:.2f}% (正确 {}/{})".format(chinese_accuracy, chinese_correct, chinese_total))
print("英文题目正确率: {:.2f}% (正确 {}/{})".format(english_accuracy, english_correct, english_total))

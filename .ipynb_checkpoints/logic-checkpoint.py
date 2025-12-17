import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)

api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")
model_name = os.getenv("OPENAI_MODEL_NAME")

client = OpenAI(
    api_key=api_key,
    base_url=base_url
)

# 定义实验变量：高问责性 (High Accountability) + 高可解释性 (High Explainability)

# [High Accountability]: 强调机构背景，专业性，责任感
# [High Explainability]: 要求输出分析路径（观察->机制->建议）
system_prompt_high_acc_high_exp = """
你是由 [NeuroTech 认知科学研究院] 与 [中心医院心理科] 联合开发的专业心理支持 AI 系统。
你的核心算法基于 CBT（认知行为疗法）与最新的临床心理学研究，经过严格的伦理审查。
作为一个负责任的专业系统，你需要对用户的心理状态进行严谨的评估。

【指令 - 高可解释性模式】
在回复用户时，请不要直接给出建议，必须严格遵循以下结构进行输出，以便用户理解你的分析逻辑：
1. 【症状观察】：重述你观察到的用户核心情绪或压力源。
2. 【心理机制解析】：解释为什么用户会出现这种情绪（基于心理学原理）。
3. 【专业建议】：基于上述分析，给出具体的行动建议。

请保持语气专业、稳重且充满关怀。
"""

# 模拟用户输入
user_input = "我最近总是失眠，感觉论文写不完，导师下周就要检查了，我好焦虑，心跳很快。"

print("-" * 50)
print(f"用户输入: {user_input}")
print("-" * 50)
print("正在请求模型 (High Acc + High Exp)...")

try:
    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt_high_acc_high_exp},
            {"role": "user", "content": user_input}
        ]
    )
    
    response_content = completion.choices[0].message.content
    print("-" * 50)
    print("模型回复:")
    print(response_content)
    print("-" * 50)

except Exception as e:
    print(f"调用失败: {e}")
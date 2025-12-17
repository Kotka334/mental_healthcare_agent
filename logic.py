import os
import json
import time
import re  # [新增] 用于正则清洗 JSON
from openai import OpenAI
from dotenv import load_dotenv

# 引入我们写好的 V7 剧本
import prompts

# 加载环境变量
load_dotenv(override=True)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)
MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4.1")

def get_group_settings(session_state):
    """根据组别获取开场白"""
    if session_state['group_acc'] == 'High':
        greeting = prompts.GREETING_HIGH_ACC
    else:
        greeting = prompts.GREETING_LOW_ACC
    return greeting

def calculate_stage(start_time):
    """
    计算当前 SST 阶段
    返回: (stage_name, progress_percentage)
    """
    if start_time is None:
        return "Phase 1", 0
    
    elapsed_minutes = (time.time() - start_time) / 60
    
    # 实验时间设定 (标准 10 分钟)
    # Phase 1: 0-3 分钟 (倾听)
    # Phase 2: 3-9 分钟 (建议)
    # Phase 3: 9-10 分钟 (结束)
    
    if elapsed_minutes < 3.0:
        return "Phase 1", elapsed_minutes / 10.0
    elif elapsed_minutes < 9.0:
        return "Phase 2", elapsed_minutes / 10.0
    else:
        return "Phase 3", elapsed_minutes / 10.0

def clean_json_string(json_str):
    """
    [新增] 健壮性清洗函数
    防止 GPT 输出 ```json ... ``` 格式导致解析失败
    """
    # 1. 移除 Markdown 代码块标记
    cleaned = re.sub(r"```json", "", json_str, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned)
    # 2. 移除首尾空白
    return cleaned.strip()

def run_hidden_analysis(messages):
    """
    【幕后逻辑】运行核心建议生成器
    """
    print(">>> 正在执行幕后分析 (Core Advice Generation)...")
    
    # 构造请求，只把历史记录发给“督导”
    analysis_messages = [
        {"role": "system", "content": prompts.HIDDEN_ANCHOR_PROMPT}
    ]
    # 过滤掉之前的 system prompt，只保留对话
    for msg in messages:
        if msg["role"] != "system":
            analysis_messages.append(msg)
            
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=analysis_messages,
            temperature=0.3, # 分析任务需要严谨，温度低
            response_format={"type": "json_object"} # 强制 JSON 模式
        )
        
        raw_content = response.choices[0].message.content
        # [关键] 清洗 JSON 字符串
        cleaned_content = clean_json_string(raw_content)
        
        result = json.loads(cleaned_content)
        print(f">>> 分析成功: {result}")
        
        # 提取建议，如果没有则使用备用方案
        return result.get("core_advice", "简单的深呼吸练习")
        
    except Exception as e:
        print(f"!!! 分析解析失败: {e}")
        print(f"原始返回: {raw_content if 'raw_content' in locals() else 'None'}")
        return "记录三件好事" # 降级方案 (Fallback)

def generate_ai_response(session_state, user_input):
    """
    主生成函数：接收用户输入，返回 AI 回复
    """
    # 1. 确定当前阶段
    current_stage, _ = calculate_stage(session_state['start_time'])
    messages = session_state['messages']
    
    # 初始化 flag
    if 'advice_given' not in session_state:
        session_state['advice_given'] = False
    
    # 2. 组装 System Prompt
    system_instruction = prompts.COMMON_SYSTEM_PROMPT
    
    # === Phase 1: 倾听 ===
    if current_stage == "Phase 1":
        system_instruction += f"\n\n{prompts.PHASE_1_LISTENING}"
        
    # === Phase 2: 建议与跟进 ===
    elif current_stage == "Phase 2":
        
        # A. 如果还没生成过核心建议，先去生成
        if 'core_advice' not in session_state:
            session_state['core_advice'] = run_hidden_analysis(messages)
        
        advice = session_state['core_advice']
        
        # B. 判断是“第一次给建议”还是“讨论建议”
        if not session_state['advice_given']:
            # --- 场景 1: 首次给出建议 ---
            print(">>> 首次输出建议 (First Delivery)")
            if session_state['group_exp'] == 'High':
                template = prompts.INSTRUCTION_HIGH_EXP
            else:
                template = prompts.INSTRUCTION_LOW_EXP
            
            final_instruction = template.format(core_advice=advice)
            session_state['advice_given'] = True # 标记已送达
            
        else:
            # --- 场景 2: 建议已给出，进行跟进讨论 ---
            print(">>> 进入跟进模式 (Follow-up)")
            final_instruction = prompts.INSTRUCTION_FOLLOWUP.format(core_advice=advice)

        system_instruction += f"\n\n{final_instruction}"
        
    # === Phase 3: 结束 ===
    elif current_stage == "Phase 3":
        system_instruction += f"\n\n{prompts.PHASE_3_CLOSING}"
    
    # 3. 构造 API 消息列表
    api_messages = [{"role": "system", "content": system_instruction}] + messages
    
    # 4. 调用 API
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=api_messages,
            temperature=0.7 
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"系统繁忙，请稍后再试。({e})"
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
    """根据用户选择的话题获取开场白"""
    topic = session_state.get("sub_topic") if session_state.get("topic") == "其他" else session_state.get("topic")
    topic_question = f"请问您最近在{topic}上有什么困扰？"
    if session_state['group_acc'] == 'High':
        greeting = prompts.GREETING_HIGH_ACC
    else:
        greeting = prompts.GREETING_LOW_ACC
    return greeting.format(topic_question=topic_question)

def calculate_stage(start_time):
    """
    计算当前 SST 阶段
    返回: (stage_name, progress_percentage)
    """
    if start_time is None:
        return "Phase 1", 0
    
    elapsed_minutes = (time.time() - start_time) / 60
    
    # 实验时间设定 (标准 5 分钟)
    # Phase 1: 0-1.5 分钟 (倾听)
    # Phase 2: 1.5-4.5 分钟 (诊断与建议)
    # Phase 3: 4.5-5 分钟 (结束)
    
    if elapsed_minutes < 1.5:
        return "Phase 1", elapsed_minutes / 5.0
    elif elapsed_minutes < 4.5:
        return "Phase 2", elapsed_minutes / 5.0
    else:
        return "Phase 3", elapsed_minutes / 5.0

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

def get_selected_topic(session_state):
    return session_state.get("sub_topic") if session_state.get("topic") == "其他" else session_state.get("topic")

def get_topic_general_advice(session_state):
    topic = get_selected_topic(session_state) or "压力"
    base_topic = session_state.get("topic")

    advice_map = {
        "工作": "将工作压力拆分成一个最小可执行任务，并为它设定清晰的开始和结束时间",
        "学习": "把学习任务拆成短时间专注单元，并在每个单元结束后记录一个具体进展",
        "人际关系": "先区分事实、感受和期待，再用一句清楚但不攻击的表达进行沟通",
        "其他": f"围绕“{topic}”做一次压力记录，写下最困扰你的情境、感受和下一步小行动"
    }
    return advice_map.get(base_topic, f"围绕“{topic}”做一次压力记录，写下最困扰你的情境、感受和下一步小行动")

def get_or_create_core_advice(session_state):
    if 'core_advice' in session_state:
        return session_state['core_advice']

    session_state['core_advice'] = run_hidden_analysis(session_state['messages'])
    session_state['advice_source'] = "llm_history_judgement"
    return session_state['core_advice']

def build_topic_instruction(session_state):
    topic = get_selected_topic(session_state)
    if not topic:
        return ""

    return (
        f"\n\n本轮咨询主题是：{topic}。"
        "请围绕该主题理解用户困扰、进行回应和提供建议；"
        "如用户明显偏离主题，请温和地将对话带回该主题。"
    )

def build_first_advice_instruction(session_state, advice):
    if session_state['group_exp'] == 'High':
        template = prompts.INSTRUCTION_HIGH_EXP
    else:
        template = prompts.INSTRUCTION_LOW_EXP

    topic = get_selected_topic(session_state) or "当前主题"
    general_advice = get_topic_general_advice(session_state)

    return (
        template.format(core_advice=advice)
        + "\n\n【历史有效性判断】请你根据完整对话 history 自行判断用户此前是否提供了可用于判断困扰的有效信息。"
        + "如果 history 中有具体、可理解的困扰描述，请基于 history 给出诊断与建议。"
        + f"如果 history 为空、明显无意义、测试输入、乱码、重复字符或无法判断真实困扰，请不要假设具体经历，只围绕“{topic}”给出通识性建议。"
        + "\n\n【结尾限制】给出诊断与建议后必须用陈述句收尾，不要再提出问题、不要询问用户是否愿意尝试、不要询问建议是否可行、不要邀请用户继续评价建议。"
        + f"\n\n【候选个性化建议】如果 history 有效，可围绕这个建议展开：{advice}"
        + f"\n\n【通识兜底建议】如果 history 无效，请围绕这个通识建议展开：{general_advice}"
    )

def generate_timeout_advice(session_state):
    """
    时间到但尚未给出建议时，强制生成一条诊断与建议，保证数据中包含建议内容。
    """
    messages = session_state['messages']
    advice = get_or_create_core_advice(session_state)
    system_instruction = prompts.COMMON_SYSTEM_PROMPT
    system_instruction += build_topic_instruction(session_state)
    system_instruction += "\n\n【当前阶段：Phase 2 - 诊断与建议】对话时间已到，且此前尚未给出诊断与建议。请立即给出一段完整、自然的诊断与建议，不要继续追问，也不要在结尾询问用户是否愿意尝试或是否觉得可行。"
    system_instruction += f"\n\n{build_first_advice_instruction(session_state, advice)}"

    api_messages = [{"role": "system", "content": system_instruction}] + messages

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=api_messages,
            temperature=0.7
        )
        session_state['advice_given'] = True
        session_state['advice_completion_prompt_pending'] = True
        return completion.choices[0].message.content
    except Exception as e:
        session_state['advice_given'] = True
        session_state['advice_completion_prompt_pending'] = True
        return f"根据目前的信息，建议你先尝试{advice}。这可以作为一个安全、简单的起点，帮助你把注意力从持续的压力或担忧中稍微拉出来。({e})"

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
    system_instruction += build_topic_instruction(session_state)
    
    # === Phase 1: 倾听 ===
    if current_stage == "Phase 1":
        system_instruction += f"\n\n{prompts.PHASE_1_LISTENING}"
        
    # === Phase 2: 建议与跟进 ===
    elif current_stage == "Phase 2":

        # A. 如果还没生成过核心建议，先根据有效历史或主题通识建议生成
        advice = get_or_create_core_advice(session_state)

        # B. 判断是“第一次给建议”还是“讨论建议”
        if not session_state['advice_given']:
            # --- 场景 1: 首次给出建议 ---
            print(">>> 首次输出建议 (First Delivery)")
            final_instruction = build_first_advice_instruction(session_state, advice)
            session_state['advice_given'] = True # 标记已送达
            session_state['advice_completion_prompt_pending'] = True

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

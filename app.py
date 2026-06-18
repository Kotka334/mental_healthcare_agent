import streamlit as st
import uuid
import time
import random
import firebase_admin
from firebase_admin import credentials, firestore

import logic

CHAT_DURATION_MINUTES = 5.0
TOPIC_OPTIONS = ["工作", "学习", "人际关系", "其他"]


# 基础配置与状态初始化 (Setup & State Management)
st.set_page_config(
    page_title="AI Psychological Support Study",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="expanded"
)

def get_first_query_param(query_params, names):
    """Return the first non-empty query parameter value from a list of possible names."""
    for name in names:
        if name not in query_params:
            continue

        value = query_params[name]
        if isinstance(value, list):
            value = value[0] if value else ""

        value = str(value).strip()
        if value:
            return value, name

    return None, None

def init_session_state():
    """初始化用户 Session，处理随机分组或强制分组逻辑"""
    if "user_id" not in st.session_state:
        # 获取 URL 参数
        # 格式示例: /?uid=TEST001&acc=High&exp=Low
        qp = st.query_params

        # 优先使用问卷平台通过 URL 传来的 ID；没有传入时再生成本地测试 ID
        incoming_user_id, incoming_id_key = get_first_query_param(
            qp,
            [
                "uid", "userid", "user_id",
                "用户ID", "userID", "UserID",
                "answer_id", "response_id", "respondent_id", "rid", "id",
                "作答ID", "答卷ID", "答题ID"
            ]
        )
        if incoming_user_id:
            st.session_state.user_id = incoming_user_id
            st.session_state.user_id_source = f"URL 参数: {incoming_id_key}"
        else:
            st.session_state.user_id = str(uuid.uuid4())[:8] # 取前8位
            st.session_state.user_id_source = "本地随机生成"
        st.session_state.initial_query_params = dict(qp)
        
        if "acc" in qp and qp["acc"] in ["High", "Low"]:
            st.session_state.group_acc = qp["acc"]
        else:
            st.session_state.group_acc = random.choice(["High", "Low"])
            
        if "exp" in qp and qp["exp"] in ["High", "Low"]:
            st.session_state.group_exp = qp["exp"]
        else:
            st.session_state.group_exp = random.choice(["High", "Low"])

        # 将最终组别写回 URL，避免刷新或重新加载页面时重新随机分组。
        st.query_params["acc"] = st.session_state.group_acc
        st.query_params["exp"] = st.session_state.group_exp
        
        # 初始化对话状态
        st.session_state.messages = []      
        st.session_state.start_time = None  
        st.session_state.is_finished = False 
        st.session_state.topic = None
        st.session_state.sub_topic = None
        st.session_state.pending_other_topic = False
        st.session_state.greeting_added = False
        st.session_state.advice_completion_prompt_pending = False
        st.session_state.continue_after_advice = False
        
        # 后台日志
        print(f"User Init: {st.session_state.user_id} | Group: {st.session_state.group_acc} / {st.session_state.group_exp}")

# 运行初始化
init_session_state()

# 动态 UI 渲染
def render_header():
    group_acc = st.session_state.group_acc
    sidebar_text = (
        "由知名精神科医院以及认知科学研究院基于大模型研发的聊天机器人"
    )
    if group_acc != "High":
        sidebar_text = (
            "基于大模型创建的聊天机器人"
        )
    
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/caduceus.png", width=60)
        st.markdown("### 心理健康聊天机器人")
        st.info(sidebar_text)

# 执行 UI 渲染
render_header()

st.session_state.setdefault("topic", None)
st.session_state.setdefault("sub_topic", None)
st.session_state.setdefault("pending_other_topic", False)
st.session_state.setdefault("greeting_added", False)
st.session_state.setdefault("advice_completion_prompt_pending", False)
st.session_state.setdefault("continue_after_advice", False)

def render_topic_selection():
    st.markdown("### 请选择您想咨询的话题")

    if st.session_state.pending_other_topic:
        sub_topic = st.text_input("请填写您想咨询的主题", key="sub_topic_input")
        if st.button("进入对话", type="primary", use_container_width=True):
            cleaned_sub_topic = sub_topic.strip()
            if cleaned_sub_topic:
                st.session_state.topic = "其他"
                st.session_state.sub_topic = cleaned_sub_topic
                st.rerun()
            else:
                st.warning("请先填写想咨询的主题。")
        if st.button("返回重新选择", use_container_width=True):
            st.session_state.pending_other_topic = False
            st.rerun()
        return

    col1, col2 = st.columns(2)
    for index, topic in enumerate(TOPIC_OPTIONS):
        column = col1 if index % 2 == 0 else col2
        with column:
            if st.button(topic, key=f"topic_{topic}", use_container_width=True):
                if topic == "其他":
                    st.session_state.pending_other_topic = True
                else:
                    st.session_state.topic = topic
                    st.session_state.sub_topic = None
                st.rerun()

if not st.session_state.topic:
    render_topic_selection()
    st.stop()

if not st.session_state.greeting_added:
    greeting_text = logic.get_group_settings(st.session_state)
    st.session_state.messages.append({"role": "assistant", "content": greeting_text})
    st.session_state.greeting_added = True

def finish_with_timeout_advice():
    if not st.session_state.get("advice_given"):
        advice_text = logic.generate_timeout_advice(st.session_state)
        st.session_state.messages.append({"role": "assistant", "content": advice_text})
    st.session_state.is_finished = True

def end_after_advice():
    st.session_state.advice_completion_prompt_pending = False
    st.session_state.is_finished = True

def continue_after_advice():
    st.session_state.advice_completion_prompt_pending = False
    st.session_state.continue_after_advice = True

def render_advice_completion_prompt():
    if not st.session_state.get("advice_completion_prompt_pending") or st.session_state.is_finished:
        return

    if hasattr(st, "dialog"):
        @st.dialog("当前对话已满足要求")
        def completion_dialog():
            st.write("系统已经完成诊断与建议。您可以现在结束对话，也可以继续交流直到 5 分钟结束。")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("立即结束", type="primary", use_container_width=True):
                    end_after_advice()
                    st.rerun()
            with col2:
                if st.button("继续聊到 5 分钟", use_container_width=True):
                    continue_after_advice()
                    st.rerun()
        completion_dialog()
    else:
        st.info("系统已经完成诊断与建议。您可以现在结束对话，也可以继续交流直到 5 分钟结束。")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("立即结束", type="primary", use_container_width=True):
                end_after_advice()
                st.rerun()
        with col2:
            if st.button("继续聊到 5 分钟", use_container_width=True):
                continue_after_advice()
                st.rerun()

# 聊天主界面

# 渲染历史消息
for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

# 处理用户输入
# 如果实验结束 (is_finished=True)，输入框会自动禁用
if prompt := st.chat_input("请输入您的想法...", disabled=st.session_state.is_finished):
    
    # 1. 启动隐形计时器
    if st.session_state.start_time is None:
        st.session_state.start_time = time.time()

    elapsed_min = (time.time() - st.session_state.start_time) / 60
    if elapsed_min >= CHAT_DURATION_MINUTES:
        finish_with_timeout_advice()
        st.rerun()
    
    # 2. 显示用户消息
    with st.chat_message("user"):
        st.write(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("..."): 
            response_text = logic.generate_ai_response(st.session_state, prompt)
            st.write(response_text)
    
    st.session_state.messages.append({"role": "assistant", "content": response_text})

    elapsed_min = (time.time() - st.session_state.start_time) / 60
    if elapsed_min >= CHAT_DURATION_MINUTES:
        finish_with_timeout_advice()
        st.rerun()

render_advice_completion_prompt()

# 实验结束与数据闭环
if st.session_state.is_finished:
    st.divider()
    st.success("本次对话已结束，感谢您的使用。")
    st.info(f"您的对话 ID 为：{st.session_state.user_id}。请将该 ID 填写回问卷中。")

    if "data_saved" not in st.session_state:
        st.session_state.data_saved = False

    if not st.session_state.data_saved:
        try:
            with st.spinner("正在安全同步您的实验数据..."):
                # 1. 初始化 Firebase (确保只初始化一次)
                if not firebase_admin._apps:
                    # 将 Streamlit Secrets 转换为字典传入
                    firebase_creds = dict(st.secrets["firebase"])
                    cred = credentials.Certificate(firebase_creds)
                    firebase_admin.initialize_app(cred)
                
                db = firestore.client()
                
                # 2. 准备数据包
                final_group_id = f"{st.session_state.group_acc}_{st.session_state.group_exp}"
                doc_data = {
                    "user_id": st.session_state.user_id,
                    "conversation_id": st.session_state.user_id,
                    "group_acc": st.session_state.group_acc,
                    "group_exp": st.session_state.group_exp,
                    "group_id": final_group_id,
                    "topic": st.session_state.topic,
                    "sub_topic": st.session_state.sub_topic,
                    "advice_source": st.session_state.get("advice_source"),
                    "chat_history": st.session_state.messages,
                    "timestamp": firestore.SERVER_TIMESTAMP # 云端自动生成精确时间
                }
                
                # 3. 写入云端 (存入名为 'sessions' 的集合中)
                db.collection('sessions').document(st.session_state.user_id).set(doc_data)
                
                # 4. 锁定状态，防止重复上传
                st.session_state.data_saved = True
                print(f">>> 数据库同步成功: {st.session_state.user_id}")
        except Exception as e:
            print(f"!!! 数据库同步失败: {e}")

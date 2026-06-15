import streamlit as st
import uuid
import time
import random
import urllib.parse
import qrcode
from PIL import Image
import io
import firebase_admin
from firebase_admin import credentials, firestore

import logic


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
        
        # 初始化对话状态
        st.session_state.messages = []      
        st.session_state.start_time = None  
        st.session_state.is_finished = False 
        
        # 预加载开场白
        greeting_text = logic.get_group_settings(st.session_state)
        st.session_state.messages.append({"role": "assistant", "content": greeting_text})
        
        # 后台日志
        print(f"User Init: {st.session_state.user_id} | Group: {st.session_state.group_acc} / {st.session_state.group_exp}")

# 运行初始化
init_session_state()

# 动态 UI 渲染
def render_header():
    group_acc = st.session_state.group_acc
    group_exp = st.session_state.group_exp
    
    # 场景 A: High Accountability
    if group_acc == "High":
        # 侧边栏
        with st.sidebar:
            st.image("https://img.icons8.com/color/96/caduceus.png", width=60) # 蛇杖图标
            st.markdown("### NeuroHelp™ 认知系统")
            st.info("✅ **资质认证**\n\n由 [认知科学研究院] 与 [中心医院] 联合监制。\n\n伦理审查编号: IRB-2025-CN")
            st.markdown("---")
            st.caption("© 2025 NeuroCognitive Institute.")
            
            # [调试水印] 仅方便教授确认当前组别
            st.markdown("---")
            st.caption(f"🔧 Debug: [{group_acc} Acc / {group_exp} Exp]")
            st.caption(f"🆔 UID: {st.session_state.user_id}")
            st.caption(f"ID Source: {st.session_state.user_id_source}")

        # 主界面 Banner (医疗蓝)
        st.markdown(
            """
            <div style='background-color: #ebf8ff; padding: 15px; border-radius: 8px; border-left: 5px solid #2b6cb0; margin-bottom: 20px;'>
                <h3 style='color: #2c5282; margin:0; font-size: 20px;'>🏥 NeuroHelp Professional</h3>
                <p style='color: #4a5568; margin:0; font-size: 14px;'>基于临床循证心理学(EBP)的专业辅助系统</p>
            </div>
            """, unsafe_allow_html=True
        )

    # 场景 B: Low Accountability
    else:
        # 侧边栏
        with st.sidebar:
            st.header("🚧 Dev Mode")
            st.warning("⚠️ **免责声明**\n\n这是一个开源社区的 Beta 测试项目。\nAI 回复仅供娱乐，可能包含错误。")
            st.markdown("[GitHub Repo (v0.9)](https://github.com)")
            
            # [调试水印]
            st.markdown("---")
            st.caption(f"🔧 Debug: [{group_acc} Acc / {group_exp} Exp]")
            st.caption(f"🆔 UID: {st.session_state.user_id}")
            st.caption(f"ID Source: {st.session_state.user_id_source}")
        
        # 主界面 Banner (警告黄)
        st.markdown(
            """
            <div style='background-color: #fffaf0; padding: 15px; border-radius: 8px; border: 1px dashed #ed8936; margin-bottom: 20px;'>
                <h3 style='color: #c05621; margin:0; font-size: 20px;'>⚠️ ChatBot Beta v0.9</h3>
                <p style='color: #744210; margin:0; font-size: 14px;'>实验性项目 | 不保证准确性 | 仅供测试</p>
            </div>
            """, unsafe_allow_html=True
        )

# 执行 UI 渲染
render_header()

# 聊天主界面

with st.sidebar:
    st.markdown("---")
    # 允许用户提前结束实验 (符合伦理要求)
    if st.button("🚪 结束本次咨询", type="secondary", help="点击此处可提前结束对话并进入反馈环节"):
        st.session_state.is_finished = True
        st.rerun()

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
    
    # 2. 显示用户消息
    with st.chat_message("user"):
        st.write(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    elapsed_min = (time.time() - st.session_state.start_time) / 60
    
    phase_3_threshold = 9.0
    is_time_up = elapsed_min >= 10.0
    
    if is_time_up:
        st.session_state.is_finished = True
        st.rerun()
    
    with st.chat_message("assistant"):
        with st.spinner("..."): 
            response_text = logic.generate_ai_response(st.session_state, prompt)
            st.write(response_text)
    
    st.session_state.messages.append({"role": "assistant", "content": response_text})

# 实验结束与数据闭环 (Data Loop & QR Code)
if st.session_state.is_finished:
    st.divider()
    st.success("🕒 本次咨询体验时间已到。")

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
                    "group_acc": st.session_state.group_acc,
                    "group_exp": st.session_state.group_exp,
                    "group_id": final_group_id,
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
    
    st.markdown("### 🎉 感谢您的参与")
    st.write("为了帮助我们改进系统，请填写一份简短的反馈问卷（约 1 分钟）。")
    st.caption("您的实验分组 ID 已自动包含在链接中，请直接扫码或点击填写。")
    
    # 请将此处替换为真实的 Qualtrics/问卷星 链接
    BASE_SURVEY_URL = "https://www.qualtrics.com/jfe/form/SV_example123"
    
    # 组合分组 ID (例如: High_Low)
    final_group_id = f"{st.session_state.group_acc}_{st.session_state.group_exp}"
    
    params = {
        "group": final_group_id,    # 对应问卷平台的 Embedded Data 'group'
        "uid": st.session_state.user_id # 对应 Embedded Data 'uid'
    }
    final_url = f"{BASE_SURVEY_URL}?{urllib.parse.urlencode(params)}"
    
    # --- 生成二维码 ---
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(final_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # 将 PIL 图片转换为字节流
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    
    # 布局：左边二维码，右边按钮
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image(img_byte_arr.getvalue(), width=150)
    with col2:
        st.markdown(f"<br>", unsafe_allow_html=True) 
        st.link_button("👉 点击直接跳转问卷", final_url, type="primary")
        st.caption(f"Session ID: {st.session_state.user_id}")

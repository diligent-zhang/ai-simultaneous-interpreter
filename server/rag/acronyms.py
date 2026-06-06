"""常见缩写解析字典 (~100 条)。

每条: acronym → (full_form, chinese_translation)
"""
import re
import logging

logger = logging.getLogger(__name__)

ACRONYM_DICT: dict[str, tuple[str, str]] = {
    # AI / ML
    "RLHF": ("Reinforcement Learning from Human Feedback", "基于人类反馈的强化学习"),
    "LLM": ("Large Language Model", "大语言模型"),
    "RAG": ("Retrieval-Augmented Generation", "检索增强生成"),
    "ASR": ("Automatic Speech Recognition", "自动语音识别"),
    "TTS": ("Text-to-Speech", "语音合成"),
    "NLP": ("Natural Language Processing", "自然语言处理"),
    "CV": ("Computer Vision", "计算机视觉"),
    "DL": ("Deep Learning", "深度学习"),
    "ML": ("Machine Learning", "机器学习"),
    "RL": ("Reinforcement Learning", "强化学习"),
    "GAN": ("Generative Adversarial Network", "生成对抗网络"),
    "CNN": ("Convolutional Neural Network", "卷积神经网络"),
    "RNN": ("Recurrent Neural Network", "循环神经网络"),
    "LSTM": ("Long Short-Term Memory", "长短期记忆网络"),
    "GPT": ("Generative Pre-trained Transformer", "生成式预训练 Transformer"),
    "BERT": ("Bidirectional Encoder Representations from Transformers", "双向编码器表征 Transformer"),
    "ViT": ("Vision Transformer", "视觉 Transformer"),
    "CLIP": ("Contrastive Language-Image Pre-training", "对比语言-图像预训练"),
    "SFT": ("Supervised Fine-Tuning", "监督微调"),
    "DPO": ("Direct Preference Optimization", "直接偏好优化"),
    "PPO": ("Proximal Policy Optimization", "近端策略优化"),
    "MCTS": ("Monte Carlo Tree Search", "蒙特卡洛树搜索"),
    "CoT": ("Chain of Thought", "思维链"),
    "LoRA": ("Low-Rank Adaptation", "低秩适配"),
    "MoE": ("Mixture of Experts", "混合专家"),
    "MHA": ("Multi-Head Attention", "多头注意力"),
    "FFN": ("Feed-Forward Network", "前馈网络"),
    "SGD": ("Stochastic Gradient Descent", "随机梯度下降"),
    "GPU": ("Graphics Processing Unit", "图形处理器"),
    "TPU": ("Tensor Processing Unit", "张量处理器"),
    "NPU": ("Neural Processing Unit", "神经网络处理器"),
    # Infrastructure
    "API": ("Application Programming Interface", "应用程序接口"),
    "SDK": ("Software Development Kit", "软件开发工具包"),
    "CLI": ("Command Line Interface", "命令行接口"),
    "SaaS": ("Software as a Service", "软件即服务"),
    "PaaS": ("Platform as a Service", "平台即服务"),
    "IaaS": ("Infrastructure as a Service", "基础设施即服务"),
    "SQL": ("Structured Query Language", "结构化查询语言"),
    "NoSQL": ("Not Only SQL", "非关系型数据库"),
    "HTTP": ("Hypertext Transfer Protocol", "超文本传输协议"),
    "HTTPS": ("Hypertext Transfer Protocol Secure", "超文本传输安全协议"),
    "TCP": ("Transmission Control Protocol", "传输控制协议"),
    "UDP": ("User Datagram Protocol", "用户数据报协议"),
    "DNS": ("Domain Name System", "域名系统"),
    "CDN": ("Content Delivery Network", "内容分发网络"),
    "VPC": ("Virtual Private Cloud", "虚拟私有云"),
    "K8s": ("Kubernetes", "Kubernetes 容器编排"),
    "VM": ("Virtual Machine", "虚拟机"),
    "AWS": ("Amazon Web Services", "亚马逊云服务"),
    "GCP": ("Google Cloud Platform", "谷歌云平台"),
    "Azure": ("Microsoft Azure", "微软 Azure 云"),
    # CS concepts
    "OOP": ("Object-Oriented Programming", "面向对象编程"),
    "FP": ("Functional Programming", "函数式编程"),
    "GC": ("Garbage Collection", "垃圾回收"),
    "JIT": ("Just-In-Time Compilation", "即时编译"),
    "AOT": ("Ahead-Of-Time Compilation", "预编译"),
    "ORM": ("Object-Relational Mapping", "对象关系映射"),
    "CRUD": ("Create, Read, Update, Delete", "增删改查操作"),
    "MVC": ("Model-View-Controller", "模型-视图-控制器模式"),
    "MVVM": ("Model-View-ViewModel", "模型-视图-视图模型模式"),
    "SSR": ("Server-Side Rendering", "服务端渲染"),
    "CSR": ("Client-Side Rendering", "客户端渲染"),
    "SSG": ("Static Site Generation", "静态站点生成"),
    "SPA": ("Single Page Application", "单页应用"),
    "PWA": ("Progressive Web Application", "渐进式 Web 应用"),
    "SEO": ("Search Engine Optimization", "搜索引擎优化"),
    "TLS": ("Transport Layer Security", "传输层安全协议"),
    "SSL": ("Secure Sockets Layer", "安全套接层"),
    "JWT": ("JSON Web Token", "JSON Web 令牌"),
    "OAuth": ("Open Authorization", "开放授权协议"),
    "RBAC": ("Role-Based Access Control", "基于角色的访问控制"),
    "DDOS": ("Distributed Denial of Service", "分布式拒绝服务攻击"),
    "XSS": ("Cross-Site Scripting", "跨站脚本攻击"),
    "CSRF": ("Cross-Site Request Forgery", "跨站请求伪造"),
    "ETL": ("Extract, Transform, Load", "提取-转换-加载数据管道"),
    "EDA": ("Event-Driven Architecture", "事件驱动架构"),
    "CQRS": ("Command Query Responsibility Segregation", "命令查询职责分离"),
    "DDD": ("Domain-Driven Design", "领域驱动设计"),
    "TDD": ("Test-Driven Development", "测试驱动开发"),
    "CI/CD": ("Continuous Integration / Continuous Deployment", "持续集成/持续部署"),
    "CAP": ("Consistency, Availability, Partition tolerance", "CAP 定理"),
}

_ACRONYM_PATTERN = re.compile(r'\b([A-Z]{2,}(?:/[A-Z]{2,})?)\b')


def resolve_acronyms(text: str) -> list[dict]:
    """扫描文本中的缩写，返回已解析的术语列表。

    Args:
        text: 需要扫描的英文文本

    Returns:
        [{"en": "LLM", "zh": "大语言模型", "full": "Large Language Model"}, ...]
    """
    found = set()
    results = []

    for match in _ACRONYM_PATTERN.finditer(text):
        acronym = match.group(1)
        if acronym in found:
            continue
        found.add(acronym)

        entry = ACRONYM_DICT.get(acronym)
        if entry:
            results.append({
                "en": acronym,
                "full": entry[0],
                "zh": entry[1],
                "source": "acronym_dict",
            })

    return results


def lookup_acronym(acronym: str) -> dict | None:
    """单个缩写查询。"""
    entry = ACRONYM_DICT.get(acronym.upper())
    if entry:
        return {"en": acronym.upper(), "full": entry[0], "zh": entry[1]}
    return None

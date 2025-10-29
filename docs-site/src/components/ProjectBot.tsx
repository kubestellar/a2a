import React, { useState, useRef, useEffect } from "react";
import styles from "./ProjectBot.module.css";
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';

interface FAQItem {
  q: string;
  keywords: string[];
  a: string;
  category?: string;
}

const faq: FAQItem[] = [
  {
    q: "How do I install KubeStellar A2A?",
    keywords: ["install", "installation", "setup", "getting started"],
    a: "You can install KubeStellar A2A using **uv** (recommended) or pip:\n\n```bash\n# Install uv\ncurl -LsSf https://astral.sh/uv/install.sh | sh\n\n# Clone and install\ngit clone https://github.com/kubestellar/a2a.git\ncd a2a\nuv pip install -e \".[dev]\"\n```\n\nFor detailed instructions, check our [Installation Guide](/a2a/docs/getting-started/installation).",
    category: "Getting Started"
  },
  {
    q: "What is KubeStellar A2A?",
    keywords: ["what is", "about", "overview", "definition"],
    a: "**KubeStellar A2A** is an intelligent orchestrator for multi-cluster Kubernetes operations. It provides:\n\n- 🤖 **AI-powered automation** with natural language interfaces\n- 🌐 **Multi-cluster management** with advanced targeting\n- ⚙️ **KubeStellar integration** with WDS, ITS, and binding policies\n- 💬 **Interactive agent mode** for conversational management",
    category: "Overview"
  },
  {
    q: "How do I use the AI agent?",
    keywords: ["agent", "ai", "natural language", "chat", "conversation"],
    a: "Start the AI agent with:\n\n```bash\n# Set your API key first\nuv run kubestellar config set-key gemini YOUR_GEMINI_API_KEY\n\n# Start agent\nuv run kubestellar agent\n```\n\nThen you can use natural language commands like:\n- \"Deploy nginx to all production clusters\"\n- \"Show me cluster health status\"\n- \"List all pods across namespaces\"",
    category: "AI Features"
  },
  {
    q: "Where can I find the quick start guide?",
    keywords: ["quick start", "tutorial", "getting started", "guide"],
    a: "Check out our [Quick Start Guide](/a2a/docs/getting-started/quick-start) to get up and running in 5 minutes!",
    category: "Getting Started"
  },
  {
    q: "What AI providers are supported?",
    keywords: ["ai providers", "llm", "openai", "gemini", "providers"],
    a: "Currently supported AI providers:\n\n- **OpenAI** (GPT-4, GPT-4o, etc.)\n- **Google Gemini** (gemini-2.0-flash, gemini-1.5-pro, etc.)\n\nSet up with:\n```bash\nuv run kubestellar config set-key <provider> YOUR_API_KEY\n```",
    category: "AI Features"
  },
  {
    q: "How do I contribute to the project?",
    keywords: ["contribute", "development", "pull request", "github"],
    a: "We welcome contributions! Here's how to get started:\n\n1. Fork the repository\n2. Create a feature branch\n3. Make your changes\n4. Run tests: `pytest`\n5. Submit a pull request\n\nSee our [Contributing Guide](/a2a/docs/CONTRIBUTING) for detailed guidelines.",
    category: "Development"
  },
  {
    q: "What are the system requirements?",
    keywords: ["requirements", "prerequisites", "python", "system"],
    a: "**Minimum Requirements:**\n- Python 3.11+\n- 512MB RAM\n- 100MB disk space\n- Internet connection\n\n**Recommended:**\n- Python 3.12+\n- 2GB RAM\n- kubectl configured\n- Helm 3.x",
    category: "Installation"
  }
];

function findAnswer(question: string): string {
  const q = question.toLowerCase();
  let bestMatch: FAQItem | null = null;
  let bestScore = 0;

  for (const item of faq) {
    let score = 0;
    
    // Check exact question match
    if (q.includes(item.q.toLowerCase())) {
      score += 10;
    }
    
    // Check keywords
    for (const keyword of item.keywords) {
      if (q.includes(keyword.toLowerCase())) {
        score += keyword.length > 3 ? 3 : 2;
      }
    }
    
    if (score > bestScore) {
      bestScore = score;
      bestMatch = item;
    }
  }

  if (bestMatch && bestScore > 1) {
    return bestMatch.a;
  }

  return "🤔 I couldn't find information about that. I can help you with:\n\n- Installation and setup\n- Using the AI agent\n- Contributing to the project\n- System requirements\n- AI providers\n\nTry asking about one of these topics, or check our [documentation](/a2a/docs/intro/).";
}

const quickActions = [
  { label: "🚀 How to install?", question: "How do I install KubeStellar A2A?" },
  { label: "🤖 Using AI agent", question: "How do I use the AI agent?" },
  { label: "📚 Quick start", question: "Where can I find the quick start guide?" },
  { label: "🔧 Contributing", question: "How do I contribute to the project?" }
];

export default function ProjectBot() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<{q: string, a: string, timestamp: Date}[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const historyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
 const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    if (historyRef.current) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight;
    }
  }, [history]);

  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
    }
  }, [open]);

  useEffect(() => {
  if (open && fullscreen) {
    document.body.classList.add('bot-fullscreen');
  } else {
    document.body.classList.remove('bot-fullscreen');
  }
  return () => {
    document.body.classList.remove('bot-fullscreen');
  };
}, [open, fullscreen]);

  function handleSend(question?: string) {
    const questionText = question || input;
    if (!questionText.trim()) return;
    
    setIsTyping(true);
    
    setTimeout(() => {
      const answer = findAnswer(questionText);
      setHistory(prev => [...prev, {
        q: questionText,
        a: answer,
        timestamp: new Date()
      }]);
      setInput("");
      setIsTyping(false);
    }, 500);
  }

  function handleClear() {
    setHistory([]);
  }

  function formatAnswer(answer: string) {
    return answer
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .split('\n')
      .map((line, i) => <div key={i} dangerouslySetInnerHTML={{__html: line || '<br>'}} />);
  }

  return (
    <div className={`${styles.botContainer} ${fullscreen ? styles.fullscreen : ""}`}>
    <button 
      className={`${styles.botButton} ${open ? styles.botButtonActive : ''}`}
      onClick={() => setOpen(true)}
      aria-label="Open project assistant"
      style={{ display: open ? 'none' : 'flex' }}
    >
      Ask Assistant
    </button>
    
    {open && (
      <div className={styles.botWindow}>
        <div className={styles.botHeader}>
          <div className={styles.botTitle}>
            <span className={styles.botIcon}>🤖</span>
            <strong>KubeStellar Assistant</strong>
          </div>
          <div>
            {history.length > 0 && (
              <button onClick={handleClear} className={styles.clearButton}>
                Clear
              </button>
            )}
            <button
                className={styles.fullscreenButton}
                onClick={() => setFullscreen(f => !f)}
                aria-label={fullscreen ? "Exit fullscreen" : "Enter fullscreen"}
                title={fullscreen ? "Exit fullscreen" : "Enter fullscreen"}
              >
                {fullscreen ? "🗗" : "🗖"}
              </button>
            <button
                onClick={() => {
                setOpen(false);
                 setFullscreen(false);
                   }}
                  className={styles.closeButton}
                  aria-label="Close assistant"
                  title="Close"
                  style={{ marginLeft: '8px' }}
                     >
                       ✕
                  </button>
          </div>
        </div>
          
          <div className={styles.botHistory} ref={historyRef}>
            {history.length === 0 ? (
              <div className={styles.welcomeMessage}>
                <div className={styles.welcomeText}>
                  👋 Hi! I'm here to help you with KubeStellar A2A.
                </div>
                <div className={styles.quickActions}>
                  {quickActions.map((action, idx) => (
                    <button
                      key={idx}
                      className={styles.quickAction}
                      onClick={() => handleSend(action.question)}
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              history.map((item, idx) => (
                <div key={idx} className={styles.conversation}>
                  <div className={styles.userMessage}>
                    <div className={styles.messageHeader}>
                      <span className={styles.userIcon}>👤</span>
                      <span className={styles.userName}>You</span>
                    </div>
                    <div className={styles.messageText}>{item.q}</div>
                  </div>
                  <div className={styles.botMessage}>
                    <div className={styles.messageHeader}>
                      <span className={styles.botIcon}>🤖</span>
                      <span className={styles.botName}>Assistant</span>
                    </div>
                    <div className={styles.messageText}>
                      {formatAnswer(item.a)}
                    </div>
                  </div>
                </div>
              ))
            )}
            
            {isTyping && (
              <div className={styles.botMessage}>
                <div className={styles.messageHeader}>
                  <span className={styles.botIcon}>🤖</span>
                  <span className={styles.botName}>Assistant</span>
                </div>
                <div className={styles.typingIndicator}>
                  <span></span><span></span><span></span>
                </div>
              </div>
            )}
          </div>
          
          <div className={styles.botInputRow}>
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="Ask me anything about KubeStellar A2A..."
              className={styles.botInput}
              onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleSend()}
              disabled={isTyping}
            />
            <button 
              onClick={() => handleSend()} 
              className={styles.sendButton}
              disabled={!input.trim() || isTyping}
            >
              {isTyping ? '⏳' : '📤'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
import { useEffect, useRef, useState } from "react";

interface Message {
  id: string;
  sender: "user" | "sentinel";
  text: string;
  agent?: { role: string; name: string; icon: string };
  follow_up_questions?: string[];
  steps?: string[];
  helplines?: string[];
}

interface Props {
  selectedDistrict?: string;
  selectedState?: string;
  selectedHazard?: string;
}

const PRESET_QUESTIONS = [
  { label: "🚑 First Aid", query: "What first aid should I do for flood injuries?" },
  { label: "⛺ Shelter & Food", query: "Where can I find safe shelter and clean water?" },
  { label: "⚡ Electrical Safety", query: "What electrical safety precautions during floods?" },
  { label: "📡 Weather Update", query: "Is more heavy rain forecast for my area?" },
  { label: "👴 Elderly Care", query: "My grandfather cannot walk. How do I evacuate?" },
  { label: "🏥 Hospital Info", query: "Where is the nearest hospital with beds?" },
];

export function CitizenAssistantChat({ selectedDistrict, selectedState, selectedHazard }: Props) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "init",
      sender: "sentinel",
      text: `Hello! I'm your SentinelAI emergency assistant. I can help you with disaster safety, first aid, shelter locations, and more. How can I help?`,
      agent: { role: "knowledge", name: "Sentinel AI", icon: "🤖" },
    },
  ]);

  const [inputQuery, setInputQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new message
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = async (queryText: string) => {
    const text = queryText.trim();
    if (!text || loading) return;

    const userMsg: Message = { id: Date.now().toString(), sender: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setInputQuery("");
    setLoading(true);

    try {
      const res = await fetch("/api/assistant/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: text,
          district: selectedDistrict || "",
          state: selectedState || "",
          hazard: selectedHazard || "flood",
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const botMsg: Message = {
          id: (Date.now() + 1).toString(),
          sender: "sentinel",
          text: data.answer_summary,
          agent: data.agent,
          follow_up_questions: data.follow_up_questions,
          steps: data.steps,
          helplines: data.helplines,
        };
        setMessages((prev) => [...prev, botMsg]);
      } else {
        throw new Error("Failed");
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: "sentinel",
          text: "I'm having trouble connecting. Please dial emergency helpline 112 or 1070 for immediate assistance.",
          agent: { role: "knowledge", name: "Emergency", icon: "🚨" },
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        maxWidth: 640,
        margin: "0 auto",
        background: "var(--color-bg)",
      }}
    >
      {/* Chat Header */}
      <div
        style={{
          padding: "14px 16px",
          borderBottom: "1px solid var(--color-border)",
          background: "var(--color-bg-card)",
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 12,
            background: "linear-gradient(135deg, #2563EB, #0EA5E9)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 18,
          }}
        >
          🤖
        </div>
        <div>
          <h3
            style={{
              margin: 0,
              fontSize: 15,
              fontWeight: 700,
              color: "var(--color-text)",
              fontFamily: "var(--font-heading)",
            }}
          >
            AI Emergency Assistant
          </h3>
          <p style={{ margin: 0, fontSize: 11, color: "var(--color-text-muted)", fontWeight: 500 }}>
            {selectedDistrict ? `Helping in ${selectedDistrict}` : "Ask any emergency question"}
          </p>
        </div>
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "16px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: msg.sender === "user" ? "flex-end" : "flex-start",
            }}
          >
            {/* AI avatar */}
            {msg.sender === "sentinel" && msg.agent && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  marginBottom: 4,
                  fontSize: 11,
                  color: "var(--color-text-muted)",
                  fontWeight: 600,
                }}
              >
                <span>{msg.agent.icon}</span>
                <span>{msg.agent.name}</span>
              </div>
            )}

            {/* Bubble */}
            <div className={msg.sender === "user" ? "chat-bubble-user" : "chat-bubble-ai"}>
              <p style={{ margin: 0 }}>{msg.text}</p>

              {/* Follow-up Questions from AI Assistant */}
              {msg.follow_up_questions && msg.follow_up_questions.length > 0 && (
                <div
                  style={{
                    marginTop: 10,
                    padding: "10px 12px",
                    background: "rgba(37, 99, 235, 0.08)",
                    borderRadius: 10,
                    borderLeft: "3px solid var(--color-primary)",
                  }}
                >
                  <p style={{ margin: "0 0 6px", fontSize: 11, fontWeight: 700, color: "var(--color-primary)" }}>
                    ❓ Clarifying Questions (click to reply):
                  </p>
                  <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                    {msg.follow_up_questions.map((q, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSend(q)}
                        style={{
                          textAlign: "left",
                          background: "var(--color-bg-card)",
                          border: "1px solid var(--color-border)",
                          borderRadius: 8,
                          padding: "6px 10px",
                          fontSize: 12,
                          fontWeight: 600,
                          color: "var(--color-text)",
                          cursor: "pointer",
                          transition: "all 0.15s ease",
                        }}
                      >
                        👉 {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Steps */}
              {msg.steps && msg.steps.length > 0 && (
                <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                  {msg.steps.map((step, i) => (
                    <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                      <span
                        style={{
                          minWidth: 22,
                          height: 22,
                          borderRadius: "50%",
                          background: "var(--color-primary)",
                          color: "white",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 11,
                          fontWeight: 800,
                          flexShrink: 0,
                        }}
                      >
                        {i + 1}
                      </span>
                      <p
                        style={{
                          margin: 0,
                          fontSize: 13,
                          lineHeight: 1.4,
                          color: "var(--color-text)",
                        }}
                      >
                        {step}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {/* Helplines */}
              {msg.helplines && msg.helplines.length > 0 && (
                <div
                  style={{
                    marginTop: 10,
                    paddingTop: 8,
                    borderTop: "1px solid var(--color-border)",
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 6,
                  }}
                >
                  {msg.helplines.map((h, i) => (
                    <span
                      key={i}
                      style={{
                        padding: "3px 8px",
                        borderRadius: 6,
                        background: "var(--color-primary-light)",
                        color: "var(--color-primary)",
                        fontSize: 11,
                        fontWeight: 700,
                      }}
                    >
                      {h}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Typing indicator */}
        {loading && (
          <div style={{ display: "flex", alignItems: "flex-start" }}>
            <div className="chat-bubble-ai">
              <div className="typing-indicator">
                <div className="typing-dot" />
                <div className="typing-dot" />
                <div className="typing-dot" />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Quick Questions */}
      <div
        style={{
          padding: "8px 16px",
          borderTop: "1px solid var(--color-border-light)",
          display: "flex",
          gap: 6,
          overflowX: "auto",
          flexShrink: 0,
        }}
      >
        {PRESET_QUESTIONS.map((q) => (
          <button
            key={q.label}
            onClick={() => handleSend(q.query)}
            disabled={loading}
            style={{
              padding: "6px 12px",
              borderRadius: 999,
              border: "1px solid var(--color-border)",
              background: "var(--color-bg-card)",
              fontSize: 12,
              fontWeight: 600,
              color: "var(--color-text-secondary)",
              cursor: "pointer",
              whiteSpace: "nowrap",
              flexShrink: 0,
              transition: "all 0.15s ease",
            }}
          >
            {q.label}
          </button>
        ))}
      </div>

      {/* Input */}
      <div
        style={{
          padding: "12px 16px",
          borderTop: "1px solid var(--color-border)",
          background: "var(--color-bg-card)",
          display: "flex",
          gap: 8,
          alignItems: "center",
          flexShrink: 0,
        }}
      >
        <input
          type="text"
          value={inputQuery}
          onChange={(e) => setInputQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend(inputQuery)}
          placeholder="Type your emergency question..."
          disabled={loading}
          style={{
            flex: 1,
            padding: "10px 14px",
            borderRadius: 12,
            border: "1px solid var(--color-border)",
            background: "var(--color-bg-elevated)",
            fontSize: 14,
            color: "var(--color-text)",
            outline: "none",
            fontFamily: "var(--font-sans)",
          }}
        />
        <button
          onClick={() => handleSend(inputQuery)}
          disabled={loading || !inputQuery.trim()}
          style={{
            width: 40,
            height: 40,
            borderRadius: 12,
            border: "none",
            background:
              inputQuery.trim() ? "var(--color-primary)" : "var(--color-bg-elevated)",
            color: inputQuery.trim() ? "white" : "var(--color-text-muted)",
            fontSize: 18,
            cursor: inputQuery.trim() ? "pointer" : "default",
            transition: "all 0.15s ease",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          ↑
        </button>
      </div>
    </div>
  );
}
